"""Plans Kanban board routes — 폴더 선택형 다중 프로젝트 지원."""

import os
import re
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request
from functools import wraps

from src.config.settings import PLANS_DIR, PLANS_ROOTS_LIST

plans_bp = Blueprint('plans', __name__, url_prefix='/admin')

# === CR Monthly View Config ===
# PLANS_DIR = wordcloud_project/plans/2026 → CR_DIR = D:\dev\wordcloud\.clinerules\docs\cr
CR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(PLANS_DIR)))),
    '.clinerules', 'docs', 'cr'
)


def _parse_cr_date(date_str):
    date_str = date_str.strip()
    for fmt in ['%Y.%m.%d', '%Y-%m-%d', '%Y/%m/%d']:
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _parse_cr_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None

    fname = os.path.basename(filepath)
    req_id = fname.replace('.md', '')

    if req_id.endswith('-r'):
        return None

    type_m = re.search(r'요청\s*유형\s*\*{0,2}\s*:\s*(.+)', content)
    req_type = type_m.group(1).strip() if type_m else '-'

    date_m = re.search(r'요청\s*날짜\s*\*{0,2}\s*:\s*(.+)', content)
    date_raw = date_m.group(1).strip() if date_m else ''
    date = _parse_cr_date(date_raw)

    summary_m = re.search(r'###\s*변경\s*요약[\s\S]*?>\s*(.+?)(?:\n|$)', content)
    summary = summary_m.group(1).strip() if summary_m else ''

    fp = None
    for pat in [r'FP\s*합계\s*:\s*(\d+)', r'FP\s*:\s*(\d+)\s*\(', r'기능\s*점수\s*\(FP\)\s*[|]\s*(\d+)', r'FP\s*[|:]\s*(\d+)']:
        fp_m = re.search(pat, content)
        if fp_m:
            fp = int(fp_m.group(1))
            break

    hours = None
    for pat in [r'공수\s*:\s*([\d.]+)\s*[Hh]', r'(\d+)\s*FP\s*=\s*([\d.]+)\s*[Hh]', r'예상\s*공수\s*[|]\s*([\d.]+)\s*[일Hh]']:
        h_m = re.search(pat, content)
        if h_m:
            val = float(h_m.group(1) if len(h_m.groups()) == 1 else h_m.group(2))
            if '일' in h_m.group(0):
                val *= 8.0
            hours = round(val, 1)
            break

    work_m = re.search(r'작업\s*유형\s*\*{0,2}\s*:\s*(.+)', content)
    work_type = work_m.group(1).strip() if work_m else '-'

    ym = date[:7] if date else 'unknown'
    month_label = ''
    if date:
        dt = datetime.strptime(date, '%Y-%m-%d')
        month_label = f'{dt.year}년 {dt.month}월'

    return {
        'req_id': req_id,
        'type': req_type,
        'summary': summary,
        'date': date,
        'ym': ym,
        'month_label': month_label,
        'fp': fp,
        'hours': hours,
        'work_type': work_type,
        'raw': content,
    }


def _scan_all_crs():
    if not os.path.isdir(CR_DIR):
        return []
    crs = []
    for fname in sorted(os.listdir(CR_DIR)):
        if not fname.startswith('REQ-') or not fname.endswith('.md'):
            continue
        fpath = os.path.join(CR_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        cr = _parse_cr_file(fpath)
        if cr:
            crs.append(cr)
    return crs


def _group_crs_by_month(crs):
    groups = {}
    for cr in crs:
        ym = cr['ym']
        if ym not in groups:
            groups[ym] = {'ym': ym, 'label': cr['month_label'], 'crs': [], 'fp_total': 0, 'hours_total': 0}
        groups[ym]['crs'].append(cr)
        if cr['fp'] is not None:
            groups[ym]['fp_total'] += cr['fp']
        if cr['hours'] is not None:
            groups[ym]['hours_total'] += cr['hours']

    for ym in groups:
        groups[ym]['crs'].sort(key=lambda x: x['date'] or '')
        groups[ym]['count'] = len(groups[ym]['crs'])

    sorted_asc = sorted(groups.keys())
    cum_fp, cum_h = 0, 0.0
    for ym in sorted_asc:
        cum_fp += groups[ym]['fp_total']
        cum_h += groups[ym]['hours_total']
        groups[ym]['cum_fp'] = cum_fp
        groups[ym]['cum_hours'] = round(cum_h, 1)

    return [groups[ym] for ym in sorted(groups.keys(), reverse=True)]


STATUS_MAP = {
    'Done': 'done',
    'Todo': 'todo',
    'Pre-Done': 'predone',
    'Doing': 'doing',
    'Hold': 'hold',
    'Drop': 'drop',
}
STATUS_LABEL = {'done': '✅ Done', 'doing': '🔄 Doing', 'todo': '📋 Todo', 'predone': '🔶 Pre-Done', 'hold': '📌 Hold', 'drop': '🗑️ Drop'}

TABLE_RE = re.compile(
    r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(Todo|Doing|Pre-Done|Done|Hold|Drop)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|',
    re.MULTILINE
)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        from flask import session
        if not session.get('admin_logged_in'):
            if request.is_json:
                return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
            return render_template('admin_login.html', error='로그인이 필요합니다.')
        return f(*args, **kwargs)
    return decorated


def _resolve_plans_dir():
    dir_param = request.args.get('dir', '').strip()
    if dir_param:
        abs_path = os.path.abspath(dir_param)
        if os.path.isdir(abs_path):
            return abs_path
    return os.path.abspath(PLANS_DIR)


def _parse_index_md(plans_dir):
    index_path = os.path.join(plans_dir, '_index.md')
    if not os.path.isfile(index_path):
        return [], 0.0

    mtime = os.path.getmtime(index_path)
    with open(index_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # normalize line endings for ^ anchor compatibility
    content = content.replace('\r\n', '\n')

    plans = []
    for match in TABLE_RE.finditer(content):
        plan_id = match.group(1).strip()
        summary = match.group(2).strip()
        raw_status = match.group(3).strip()
        date_str = match.group(4).strip()

        status = STATUS_MAP.get(raw_status, 'todo')

        folder = os.path.join(plans_dir, plan_id)
        main_md = os.path.join(folder, f'{plan_id}.md')
        has_main = os.path.isfile(main_md)
        has_result = os.path.isdir(os.path.join(folder, 'result'))
        has_test = os.path.isdir(os.path.join(folder, 'test'))

        # Plan 폴더의 모든 .md 파일 (메인 제외 부가문서)
        extra_files = []
        if os.path.isdir(folder):
            for fname in sorted(os.listdir(folder)):
                fpath = os.path.join(folder, fname)
                if os.path.isfile(fpath) and fname.endswith('.md') and fname != f'{plan_id}.md':
                    extra_files.append(fname)

        plans.append({
            'id': plan_id,
            'summary': summary,
            'status': status,
            'date': date_str,
            'has_main': has_main,
            'has_result': has_result,
            'has_test': has_test,
            'folder': folder,
            'main_md': main_md if has_main else None,
            'extra_files': extra_files,
        })

    return plans, mtime


def _group_by_status(plans):
    grouped = {'todo': [], 'doing': [], 'predone': [], 'done': [], 'hold': [], 'drop': []}
    for p in plans:
        s = p['status']
        if s in grouped:
            grouped[s].append(p)
    # each column sorted by date ascending (oldest first)
    for s in grouped:
        grouped[s].sort(key=lambda x: x['date'])
    return grouped


def _load_folder_list(base_dir):
    folders = []
    for entry in sorted(os.listdir(base_dir)):
        entry_path = os.path.join(base_dir, entry)
        if os.path.isdir(entry_path) and os.path.isfile(os.path.join(entry_path, '_index.md')):
            folders.append(entry_path)
    return folders


@plans_bp.route('/plans')
@admin_required
def plans_page():
    plans_dir = _resolve_plans_dir()
    plans, mtime = _parse_index_md(plans_dir)
    grouped = _group_by_status(plans)

    stats = {
        'total': len(plans),
        'predone': len(grouped['predone']),
        'done': len(grouped['done']),
        'doing': len(grouped['doing']),
        'todo': len(grouped['todo']),
        'hold': len(grouped['hold']),
        'drop': len(grouped['drop']),
    }

    # collect available plan roots for the dropdown
    available_roots = [os.path.abspath(PLANS_DIR)]
    for r in PLANS_ROOTS_LIST:
        rp = os.path.abspath(r)
        if rp != available_roots[0] and rp not in available_roots:
            available_roots.append(rp)

    # also auto-discover sibling directories that have _index.md
    parent_dir = os.path.dirname(os.path.abspath(PLANS_DIR))
    for entry in sorted(os.listdir(parent_dir)):
        entry_path = os.path.join(parent_dir, entry)
        if os.path.isdir(entry_path) and os.path.isfile(os.path.join(entry_path, '_index.md')):
            if entry_path not in available_roots:
                available_roots.append(entry_path)

    return render_template(
        'plans_kanban.html',
        plans=plans,
        grouped=grouped,
        stats=stats,
        current_dir=plans_dir,
        available_roots=available_roots,
        mtime=mtime,
        STATUS_LABEL=STATUS_LABEL,
    )


@plans_bp.route('/api/plans/check')
@admin_required
def plans_check():
    plans_dir = _resolve_plans_dir()
    index_path = os.path.join(plans_dir, '_index.md')
    if not os.path.isfile(index_path):
        return jsonify({'success': False, 'error': '_index.md not found'}), 404
    mtime = os.path.getmtime(index_path)
    return jsonify({'success': True, 'modified_at': mtime, 'dir': plans_dir})


@plans_bp.route('/api/plans')
@admin_required
def plans_data():
    plans_dir = _resolve_plans_dir()
    plans, mtime = _parse_index_md(plans_dir)
    grouped = _group_by_status(plans)

    stats = {
        'total': len(plans),
        'predone': len(grouped['predone']),
        'done': len(grouped['done']),
        'doing': len(grouped['doing']),
        'todo': len(grouped['todo']),
        'hold': len(grouped['hold']),
        'drop': len(grouped['drop']),
    }

    return jsonify({
        'success': True,
        'plans': plans,
        'grouped': {
            'todo': grouped['todo'],
            'doing': grouped['doing'],
            'predone': grouped['predone'],
            'done': grouped['done'],
            'hold': grouped['hold'],
            'drop': grouped['drop'],
        },
        'stats': stats,
        'modified_at': mtime,
        'dir': plans_dir,
    })


@plans_bp.route('/api/plans/<plan_id>/content')
@admin_required
def plan_content(plan_id):
    plans_dir = _resolve_plans_dir()
    main_md = os.path.join(plans_dir, plan_id, f'{plan_id}.md')

    if not os.path.isfile(main_md):
        # fallback: find any .md inside the folder
        folder = os.path.join(plans_dir, plan_id)
        if os.path.isdir(folder):
            for fname in sorted(os.listdir(folder)):
                if fname.endswith('.md'):
                    main_md = os.path.join(folder, fname)
                    break
        if not os.path.isfile(main_md):
            return jsonify({'success': False, 'error': 'Plan file not found'}), 404

    try:
        with open(main_md, 'r', encoding='utf-8') as f:
            raw = f.read()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    # build side links
    folder = os.path.dirname(main_md)
    result_files = []
    result_dir = os.path.join(folder, 'result')
    if os.path.isdir(result_dir):
        result_files = sorted(os.listdir(result_dir))

    test_files = []
    test_dir = os.path.join(folder, 'test')
    if os.path.isdir(test_dir):
        test_files = sorted(os.listdir(test_dir))

    return jsonify({
        'success': True,
        'plan_id': plan_id,
        'raw': raw,
        'folder': folder,
        'result_files': result_files,
        'test_files': test_files,
        'extra_files': sorted([
            f for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f)) and f.endswith('.md')
            and f != os.path.basename(main_md)
        ]) if os.path.isdir(folder) else [],
    })


@plans_bp.route('/api/plans/cr-monthly')
@admin_required
def plans_cr_monthly():
    crs = _scan_all_crs()
    months = _group_crs_by_month(crs)
    total_fp = sum(g['fp_total'] for g in months)
    total_hours = round(sum(g['hours_total'] for g in months), 1)
    return jsonify({
        'success': True,
        'months': months,
        'total_crs': len(crs),
        'total_fp': total_fp,
        'total_hours': total_hours,
    })


@plans_bp.route('/api/plans/cr/<req_id>')
@admin_required
def plans_cr_detail(req_id):
    fname = f'{req_id}.md'
    if not req_id.startswith('REQ-'):
        fname = f'REQ-{req_id}.md'
    fpath = os.path.join(CR_DIR, fname)
    if not os.path.isfile(fpath):
        return jsonify({'success': False, 'error': 'CR file not found'}), 404
    cr = _parse_cr_file(fpath)
    if not cr:
        return jsonify({'success': False, 'error': 'Failed to parse CR file'}), 500
    return jsonify({
        'success': True,
        'cr': cr,
    })
