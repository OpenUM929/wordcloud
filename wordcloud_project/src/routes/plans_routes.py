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


def _cr_monthly_for_year(year):
    """연도(yyyy) 기준 CR 월별 집계.
    반환: {mm: {'count':int, 'fp':int, 'hours':float}} (mm='01'..'12')
    """
    crs = _scan_all_crs()
    ystr = str(year)
    agg = {f'{m:02d}': {'count': 0, 'fp': 0, 'hours': 0.0} for m in range(1, 13)}
    for cr in crs:
        if not cr['ym'].startswith(ystr + '-'):
            continue
        mm = cr['ym'].split('-')[1]
        agg[mm]['count'] += 1
        if cr['fp'] is not None:
            agg[mm]['fp'] += cr['fp']
        if cr['hours'] is not None:
            agg[mm]['hours'] += cr['hours']
    return agg


def _plans_monthly_for_year(year):
    """plans/<year>/MM/_index.md 기준 계획서 월별 건수.
    반환: {mm: count} (mm='01'..'12'). 해당 연도 폴더가 없으면 전부 0.
    """
    base = os.path.dirname(os.path.abspath(PLANS_DIR))
    year_dir = os.path.join(base, str(year))
    counts = {f'{m:02d}': 0 for m in range(1, 13)}
    if not os.path.isdir(year_dir):
        return counts
    for mm in counts:
        month_dir = os.path.join(year_dir, mm)
        ip = os.path.join(month_dir, '_index.md')
        if os.path.isfile(ip):
            plans, _ = _parse_index_md(month_dir)
            counts[mm] = len(plans)
    return counts


def _normalize_work_type(raw):
    """work_type 자유텍스트 → A~E 정규화. 미분류/공백은 'other'.

    A=버그수정 B=기능개선 C=설계/아키텍처 D=리팩토링 E=DB마이그레이션
    (계획서 헤더 표기 불일치 대응: '기능 개선'·'bug fi'·'type-B' 등 혼재)
    """
    if not raw:
        return 'other'
    s = raw.strip().lower()
    if s in ('a', 'b', 'c', 'd', 'e'):
        return s.upper()
    m = re.search(r'type-([a-e])', s)
    if m:
        return m.group(1).upper()
    if '버그' in s or 'bug' in s:
        return 'A'
    if 'db' in s or '마이그레이션' in s or 'migration' in s or '데이터베이스' in s:
        return 'E'
    if '리팩터' in s or 'refactor' in s:
        return 'D'
    if '설계' in s or '아키텍처' in s or 'design' in s or 'architect' in s:
        return 'C'
    if '기능' in s or 'feature' in s or 'feat' in s:
        return 'B'
    return 'other'


def _plans_by_type_for_year(year):
    """plans/<year>/MM/_index.md 기준 계획서 작업유형(A~E)별 건수.
    반환: (table: {ym: {'A':int,'B':int,'C':int,'D':int,'E':int,'other':int}}, total:int)
    """
    base = os.path.dirname(os.path.abspath(PLANS_DIR))
    year_dir = os.path.join(base, str(year))
    types = ['A', 'B', 'C', 'D', 'E', 'other']
    table = {}
    total = 0
    if os.path.isdir(year_dir):
        for mm in range(1, 13):
            ym = f'{year}-{mm:02d}'
            month_dir = os.path.join(year_dir, f'{mm:02d}')
            counts = {t: 0 for t in types}
            if os.path.isdir(month_dir):
                plans, _ = _parse_index_md(month_dir)
                for p in plans:
                    wt = _normalize_work_type(p.get('work_type') or '')
                    counts[wt] += 1
                    total += 1
            table[ym] = counts
    return table, total


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


def _resolve_plan_folder(plans_dir, plan_id):
    """plan_id에 대응하는 실제 폴더 경로를 해석한다.

    18_05 설계의 'plan_id == 폴더명' 강결합을 완화: 정확 일치 폴더가 없으면
    (리네임 누락 등) 유사 폴더를 탐색하여 경로 깨짐을 방지한다.
    """
    exact = os.path.join(plans_dir, plan_id)
    if os.path.isdir(exact):
        return exact
    if not os.path.isdir(plans_dir):
        return exact
    # 폴더명이 plan_id와 어긋난 경우를 대비한 안전 탐색 (결정적 순서)
    exact_hit = None
    candidates = []
    for entry in sorted(os.listdir(plans_dir)):
        ep = os.path.join(plans_dir, entry)
        if not os.path.isdir(ep):
            continue
        if entry == plan_id:
            exact_hit = ep
        elif entry.startswith(plan_id + '_') or entry.endswith('_' + plan_id):
            candidates.append(ep)
    if exact_hit:
        return exact_hit
    return candidates[0] if candidates else exact


def _find_main_md(folder, plan_id):
    """폴더 내 메인 .md 해석 — plan_id.md 우선, 없으면 plan_id 접두 .md, 그 외 첫 .md."""
    primary = os.path.join(folder, f'{plan_id}.md')
    if os.path.isfile(primary):
        return primary
    if not os.path.isdir(folder):
        return primary
    prefixed = None
    fallback = None
    for fn in sorted(os.listdir(folder)):
        if not fn.endswith('.md'):
            continue
        if fn.startswith(plan_id):
            prefixed = fn
        if fallback is None:
            fallback = fn
    chosen = prefixed or fallback
    return os.path.join(folder, chosen) if chosen else primary


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
    lines = content.splitlines()
    for match in TABLE_RE.finditer(content):
        plan_id = match.group(1).strip()
        summary = match.group(2).strip()
        raw_status = match.group(3).strip()
        date_str = match.group(4).strip()

        # 전체 라인 추출 → 5·6·7컬럼 (관련 CR · 선행 · 에픽)
        line_no = content[:match.start()].count('\n')
        full_line = lines[line_no] if line_no < len(lines) else ''
        cells = [c.strip() for c in full_line.split('|')]
        # cells[0] is empty (before first |), cells[1]=id, [2]=summary, [3]=status, [4]=date, [5]=related_cr, [6]=depends, [7]=epic
        related_cr_str = cells[5] if len(cells) > 5 else ''
        depends_str = cells[6] if len(cells) > 6 else ''
        epic_str = cells[7] if len(cells) > 7 else ''
        related_cr = [c.strip() for c in related_cr_str.split(',') if c.strip()] if related_cr_str else []
        depends = [c.strip() for c in depends_str.split(',') if c.strip()] if depends_str else []

        status = STATUS_MAP.get(raw_status, 'todo')

        folder = _resolve_plan_folder(plans_dir, plan_id)
        main_md = _find_main_md(folder, plan_id)
        has_main = os.path.isfile(main_md)

        # result/test count (boolean → count 승격)
        result_count = 0
        test_count = 0
        result_dir = os.path.join(folder, 'result')
        test_dir = os.path.join(folder, 'test')
        if os.path.isdir(result_dir):
            result_count = len([f for f in os.listdir(result_dir) if os.path.isfile(os.path.join(result_dir, f))])
        if os.path.isdir(test_dir):
            test_count = len([f for f in os.listdir(test_dir) if os.path.isfile(os.path.join(test_dir, f))])

        # work_type 추출 (plan .md 헤더, 처음 25줄)
        work_type = ''
        end_date = None
        if has_main:
            try:
                with open(main_md, 'r', encoding='utf-8-sig') as wf:
                    header_lines = []
                    for _ in range(25):
                        line = wf.readline()
                        if not line:
                            break
                        header_lines.append(line)
                    header_text = ''.join(header_lines)
                m = re.search(r'(?:-\s*)?(?:>|\*\*)?\s*작업\s*유형\s*(?:\*\*)?\s*[:：]\s*(.+)', header_text)
                if m:
                    val = m.group(1).strip()
                    cm = re.match(r'^([A-Ea-e])\b', val)
                    work_type = cm.group(1).upper() if cm else val[:6]
                # 완료일 추출 — 표준 `완료일:`, fallback `완료일시:`
                ed = re.search(r'완료일:\s*(\d{4}-\d{2}-\d{2})', header_text)
                if ed:
                    end_date = ed.group(1)
                else:
                    ed2 = re.search(r'완료일시:\s*(\d{4}-\d{2}-\d{2})', header_text)
                    if ed2:
                        end_date = ed2.group(1)
            except (OSError, UnicodeDecodeError):
                work_type = ''  # graceful: 칩 생략

        # Plan 폴더의 모든 .md 파일 (메인 제외 부가문서)
        extra_files = []
        if os.path.isdir(folder):
            for fname in sorted(os.listdir(folder)):
                fpath = os.path.join(folder, fname)
                if os.path.isfile(fpath) and fname.endswith('.md') and fname != os.path.basename(main_md):
                    extra_files.append(fname)

        plans.append({
            'id': plan_id,
            'summary': summary,
            'status': status,
            'date': date_str,
            'has_main': has_main,
            'work_type': work_type,
            'result_count': result_count,
            'test_count': test_count,
            'folder': folder,
            'main_md': main_md if has_main else None,
            'extra_files': extra_files,
            'related_cr': related_cr,
            'depends': depends,
            'epic': epic_str,
            'end_date': end_date,
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


def _discover_month_dirs(base_dir):
    """PLANS_DIR/MM/ 중 _index.md 를 보유한 월 폴더 (MM, 절대경로) 리스트, 최신월 우선."""
    month_dirs = []
    if not os.path.isdir(base_dir):
        return month_dirs
    for entry in sorted(os.listdir(base_dir), reverse=True):
        entry_path = os.path.join(base_dir, entry)
        if os.path.isdir(entry_path) and re.match(r'^\d{2}$', entry) \
                and os.path.isfile(os.path.join(entry_path, '_index.md')):
            month_dirs.append((entry, os.path.abspath(entry_path)))
    return month_dirs


def _plans_year():
    """PLANS_DIR 경로의 연도(마지막 세그먼트)를 반환 — 하드코딩 연도 제거."""
    return os.path.basename(os.path.abspath(PLANS_DIR).rstrip(os.sep))


def parse_all_months():
    """PLANS_DIR/MM/ 하위 _index.md 를 전부 스캔·병합, 각 plan에 month(MM) 태그 부여."""
    base = os.path.abspath(PLANS_DIR)
    all_plans = []
    for mm, mpath in _discover_month_dirs(base):
        plans, _ = _parse_index_md(mpath)
        for p in plans:
            p['month'] = mm
            all_plans.append(p)
    return all_plans


def _build_plans_response(plans, grouped, mtime, board_month, month_param):
    total_visible = (len(grouped['todo']) + len(grouped['doing']) + len(grouped['predone'])
                     + len(grouped['done']) + len(grouped['hold']) + len(grouped['drop']))
    stats = {
        'total': total_visible,
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
        'board_month': board_month,
        'month': month_param,
    })


@plans_bp.route('/plans')
@admin_required
def plans_page():
    plans = parse_all_months()
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

    base = os.path.abspath(PLANS_DIR)
    month_options = _discover_month_dirs(base)
    available_months = [mm for mm, _ in month_options]
    now = datetime.now()
    current_month = now.strftime('%m')
    if current_month not in available_months and available_months:
        current_month = available_months[0]

    return render_template(
        'plans_kanban.html',
        plans=plans,
        grouped=grouped,
        stats=stats,
        plans_base=base,
        plans_year=_plans_year(),
        month_options=month_options,
        current_month=current_month,
        mtime=0,
        STATUS_LABEL=STATUS_LABEL,
    )


@plans_bp.route('/api/plans/check')
@admin_required
def plans_check():
    month_param = request.args.get('month', '').strip()
    base = os.path.abspath(PLANS_DIR)
    if month_param:
        index_path = os.path.join(base, month_param, '_index.md')
        if not os.path.isfile(index_path):
            return jsonify({'success': False, 'error': '_index.md not found'}), 404
        mtime = os.path.getmtime(index_path)
    else:
        mtime = 0.0
        for mm, mpath in _discover_month_dirs(base):
            ip = os.path.join(mpath, '_index.md')
            if os.path.isfile(ip):
                mtime = max(mtime, os.path.getmtime(ip))
    return jsonify({'success': True, 'modified_at': mtime, 'month': month_param})


@plans_bp.route('/api/plans')
@admin_required
def plans_data():
    month_param = request.args.get('month', '').strip()
    base = os.path.abspath(PLANS_DIR)

    all_plans = parse_all_months()

    non_done = [p for p in all_plans if p['status'] != 'done']
    done = [p for p in all_plans if p['status'] == 'done']
    board_month = (_plans_year() + '-' + month_param) if month_param else None

    grouped = _group_by_status(non_done)
    grouped['done'] = done

    mtime = 0.0
    for mm, mpath in _discover_month_dirs(base):
        ip = os.path.join(mpath, '_index.md')
        if os.path.isfile(ip):
            mtime = max(mtime, os.path.getmtime(ip))

    return _build_plans_response(all_plans, grouped, mtime, board_month, month_param)


@plans_bp.route('/api/plans/<plan_id>/content')
@admin_required
def plan_content(plan_id):
    plans_dir = _resolve_plans_dir()
    folder = _resolve_plan_folder(plans_dir, plan_id)
    main_md = _find_main_md(folder, plan_id)

    if not os.path.isfile(main_md):
        return jsonify({'success': False, 'error': 'Plan file not found'}), 404

    try:
        with open(main_md, 'r', encoding='utf-8') as f:
            raw = f.read()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    # build side links
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


@plans_bp.route('/api/plans/trend')
@admin_required
def plans_trend():
    year_param = request.args.get('year', '').strip() or _plans_year()
    try:
        year = int(year_param)
    except ValueError:
        year = int(_plans_year())
    prev_year = year - 1

    cr_cur = _cr_monthly_for_year(year)
    cr_prev = _cr_monthly_for_year(prev_year)
    pl_cur = _plans_monthly_for_year(year)
    pl_prev = _plans_monthly_for_year(prev_year)

    months = [f'{m:02d}' for m in range(1, 13)]

    def _pack(cur, prev, key):
        return {
            'cur': [cur[m][key] if isinstance(cur[m], dict) else cur[m] for m in months],
            'prev': [prev[m][key] if isinstance(prev[m], dict) else prev[m] for m in months],
        }

    series = {
        'cr_count': _pack(cr_cur, cr_prev, 'count'),
        'fp': _pack(cr_cur, cr_prev, 'fp'),
        'hours': _pack(cr_cur, cr_prev, 'hours'),
        'plan_count': {
            'cur': [pl_cur[m] for m in months],
            'prev': [pl_prev[m] for m in months],
        },
    }

    def _tot(arr):
        return round(sum(arr), 1)

    totals = {
        'cr_count': {'cur': _tot(series['cr_count']['cur']), 'prev': _tot(series['cr_count']['prev'])},
        'fp': {'cur': _tot(series['fp']['cur']), 'prev': _tot(series['fp']['prev'])},
        'hours': {'cur': _tot(series['hours']['cur']), 'prev': _tot(series['hours']['prev'])},
        'plan_count': {'cur': _tot(series['plan_count']['cur']), 'prev': _tot(series['plan_count']['prev'])},
    }

    return jsonify({
        'success': True,
        'year': year,
        'prev_year': prev_year,
        'series': series,
        'totals': totals,
    })


WORK_TYPE_LABELS = {
    'A': '버그수정',
    'B': '기능개선',
    'C': '설계/아키텍처',
    'D': '리팩토링',
    'E': 'DB마이그레이션',
    'other': '미분류',
}


def _cr_by_type_for_year(year):
    """CR `요청 유형`(cr['type']) 기준 연도별 월별 집계.
    반환: (agg: {mm: {type:count}}, types: sorted list)
    """
    crs = _scan_all_crs()
    ystr = str(year)
    agg = {f'{m:02d}': {} for m in range(1, 13)}
    types = set()
    for cr in crs:
        if not cr['ym'].startswith(ystr + '-'):
            continue
        mm = cr['ym'].split('-')[1]
        t = cr['type'] or '-'
        agg[mm][t] = agg[mm].get(t, 0) + 1
        types.add(t)
    return agg, sorted(types)


def _available_years():
    """CR 연도 ∪ plans 연도 폴더 합집합 (정렬, 문자열 'YYYY' 리스트)."""
    base = os.path.dirname(os.path.abspath(PLANS_DIR))
    years = set()
    for cr in _scan_all_crs():
        if cr['ym'][:4].isdigit():
            years.add(cr['ym'][:4])
    if os.path.isdir(base):
        for name in os.listdir(base):
            if re.fullmatch(r'\d{4}', name) and os.path.isdir(os.path.join(base, name)):
                years.add(name)
    return sorted(years, key=lambda x: int(x))


@plans_bp.route('/api/plans/trend-type')
@admin_required
def plans_trend_type():
    """그래프 분석 신규 지표 전용 엔드포인트 (기존 plans_trend 는 수정하지 않음).
    - mode=monthly&year=YYYY → 월별 CR/계획서 유형별(cur/prev)
    - mode=yearly&mStart=&mEnd= → 연별 집계 + 유형별(cur/prev)
    """
    mode = (request.args.get('mode', 'monthly') or 'monthly').strip().lower()
    cur_year = int(_plans_year())
    cur_month = datetime.now().month

    if mode == 'yearly':
        try:
            mstart = int(request.args.get('mStart', '1') or 1)
        except ValueError:
            mstart = 1
        try:
            mend = int(request.args.get('mEnd', str(cur_month)) or cur_month)
        except ValueError:
            mend = cur_month
        mstart = max(1, min(12, mstart))
        mend = max(mstart, min(12, mend))

        years = [int(y) for y in _available_years()]
        plan_types = ['A', 'B', 'C', 'D', 'E', 'other']
        cr_types_union = set()
        series = {
            'cr_count': {}, 'fp': {}, 'hours': {}, 'plan_count': {},
            'cr_by_type': {'types': [], 'data': {}},
            'plan_by_type': {'types': plan_types, 'data': {}},
        }
        for y in years:
            eff_end = mend if y >= cur_year else min(mend, cur_month)
            cr_m = _cr_monthly_for_year(y)
            crbt, crtypes = _cr_by_type_for_year(y)
            cr_types_union |= set(crtypes)
            plbt, _ = _plans_by_type_for_year(y)

            cr_count_y = sum(cr_m[f'{m:02d}']['count'] for m in range(mstart, eff_end + 1))
            fp_y = sum(cr_m[f'{m:02d}']['fp'] for m in range(mstart, eff_end + 1))
            hours_y = round(sum(cr_m[f'{m:02d}']['hours'] for m in range(mstart, eff_end + 1)), 1)
            plan_count_y = sum(
                plbt.get(f'{y}-{m:02d}', {}).get(t, 0)
                for m in range(mstart, eff_end + 1) for t in plan_types
            )
            cr_by_type_y = {
                t: sum(crbt.get(f'{m:02d}', {}).get(t, 0) for m in range(mstart, eff_end + 1))
                for t in crtypes
            }
            plan_by_type_y = {
                t: sum(plbt.get(f'{y}-{m:02d}', {}).get(t, 0) for m in range(mstart, eff_end + 1))
                for t in plan_types
            }

            series['cr_count'][y] = cr_count_y
            series['fp'][y] = fp_y
            series['hours'][y] = hours_y
            series['plan_count'][y] = plan_count_y
            series['cr_by_type']['data'][y] = cr_by_type_y
            series['plan_by_type']['data'][y] = plan_by_type_y
        series['cr_by_type']['types'] = sorted(cr_types_union)

        return jsonify({
            'success': True,
            'mode': 'yearly',
            'years': years,
            'mStart': mstart,
            'mEnd': mend,
            'cur_month': cur_month,
            'work_type_labels': WORK_TYPE_LABELS,
            'series': series,
        })

    # ---- monthly by-type ----
    year_param = request.args.get('year', '').strip() or _plans_year()
    try:
        year = int(year_param)
    except ValueError:
        year = cur_year
    prev_year = year - 1

    crbt_cur, crtypes_cur = _cr_by_type_for_year(year)
    crbt_prev, crtypes_prev = _cr_by_type_for_year(prev_year)
    plbt_cur, _ = _plans_by_type_for_year(year)
    plbt_prev, _ = _plans_by_type_for_year(prev_year)

    plan_types = ['A', 'B', 'C', 'D', 'E', 'other']
    cr_types = sorted(set(crtypes_cur) | set(crtypes_prev))
    months = [f'{m:02d}' for m in range(1, 13)]

    return jsonify({
        'success': True,
        'mode': 'monthly',
        'year': year,
        'prev_year': prev_year,
        'work_type_labels': WORK_TYPE_LABELS,
        'cr_by_type': {
            'types': cr_types,
            'cur': [crbt_cur.get(m, {}) for m in months],
            'prev': [crbt_prev.get(m, {}) for m in months],
        },
        'plan_by_type': {
            'types': plan_types,
            'cur': [plbt_cur.get(f'{year}-{m}', {t: 0 for t in plan_types}) for m in months],
            'prev': [plbt_prev.get(f'{prev_year}-{m}', {t: 0 for t in plan_types}) for m in months],
        },
    })


def _link_linter(plans):
    """링크 린터 — 실존 검증 + 선행 DAG 순환 검증.
    반환: [{'type':'dangling_cr'|'unresolved_dep'|'cycle_dep', 'plan', 'ref', 'msg'}, ...]
    """
    violations = []
    # CR 실존
    if os.path.isdir(CR_DIR):
        cr_files = {fn.replace('.md', '') for fn in os.listdir(CR_DIR)
                    if fn.startswith('REQ-') and fn.endswith('.md') and not fn.endswith('-r.md')}
    else:
        cr_files = set()
    for p in plans:
        for cr_ref in p.get('related_cr', []):
            if cr_ref not in cr_files:
                violations.append({
                    'type': 'dangling_cr',
                    'plan': p['id'],
                    'ref': cr_ref,
                    'msg': f"CR {cr_ref} not found in {CR_DIR}",
                })
    # 선행 실존
    for p in plans:
        for ref in p.get('depends', []):
            resolved = _resolve_ref(plans, ref)
            if not resolved:
                violations.append({
                    'type': 'unresolved_dep',
                    'plan': p['id'],
                    'ref': ref,
                    'msg': f"선행 좌표 {ref} cannot be resolved to any plan",
                })
    # 선행 DAG 순환 검증
    dep_graph = {}
    for p in plans:
        dep_graph[p['id']] = []
        for ref in p.get('depends', []):
            resolved = _resolve_ref(plans, ref)
            if resolved and resolved != p['id']:
                dep_graph[p['id']].append(resolved)
    all_ids = list(dep_graph.keys())
    for start_id in all_ids:
        visited = set()
        stack = [start_id]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            for dep_id in dep_graph.get(node, []):
                if dep_id == start_id:
                    violations.append({
                        'type': 'cycle_dep',
                        'plan': start_id,
                        'ref': dep_id,
                        'msg': f"선행 순환 감지: {start_id} → ... → {dep_id}",
                    })
                    break
                stack.append(dep_id)
    return violations


def _resolve_ref(plans, ref):
    """plan_id + month 에 대해 DD_NN/YYYY/MM/DD_NN 참조 해소.
    
    ref 'DD_NN' → prefix/suffix matching
    ref 'YYYY/MM/DD_NN' → prefix matching + month filter
    """
    parts = ref.split('/')
    if len(parts) == 3:
        # 타월 참조 YYYY/MM/DD_NN
        target_month = parts[1]
        short_id = parts[2]
        for p in plans:
            if p['month'] == target_month:
                if p['id'] == short_id or p['id'].startswith(short_id + '_') or p['id'].endswith('_' + short_id):
                    return p['id']
    else:
        # 동월 참조 DD_NN (또는 전체 ID)
        short_id = ref
        for p in plans:
            if p['id'] == short_id or p['id'].startswith(short_id + '_') or p['id'].endswith('_' + short_id):
                return p['id']
    return None


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


@plans_bp.route('/api/plans/gantt')
@admin_required
def plans_gantt():
    year_param = request.args.get('year', '').strip() or _plans_year()
    plans = parse_all_months()
    crs = [c for c in _scan_all_crs() if c['date']]

    # 에픽별 그룹 (스윔레인)
    epic_order = []
    epic_plans = {}
    for p in plans:
        ep = p.get('epic') or ''
        if ep not in epic_plans:
            epic_plans[ep] = []
            epic_order.append(ep)
        epic_plans[ep].append(p)

    tasks = []
    for p in plans:
        end = p.get('end_date')
        t = {
            'id': p['id'],
            'summary': p['summary'],
            'status': p['status'],
            'date': p['date'],
            'month': p['month'],
            'epic': p.get('epic') or '',
            'end_date': end,
            'work_type': p.get('work_type', ''),
        }
        tasks.append(t)

    # ◆ 마일스톤
    milestones = []
    for c in crs:
        milestones.append({
            'req_id': c['req_id'],
            'summary': c['summary'],
            'date': c['date'],
            'ym': c['ym'],
            'fp': c['fp'],
            'hours': c['hours'],
        })

    # 선행 간선 해소
    deps = []
    dep_warnings = []
    for p in plans:
        for ref in p.get('depends', []):
            resolved = _resolve_ref(plans, ref)
            if resolved:
                deps.append({'from': p['id'], 'to': resolved})
            else:
                dep_warnings.append({'plan': p['id'], 'ref': ref, 'warning': 'unresolved'})

    # CR 링크
    cr_links = []
    cr_index = {}
    for c in crs:
        cr_index[c['req_id']] = c
    for p in plans:
        for cr_ref in p.get('related_cr', []):
            if cr_ref in cr_index:
                cr_links.append({'plan': p['id'], 'cr': cr_ref})

    # 계획서 작업유형별 집계 (간트차트 요약용)
    plan_table, plan_total = _plans_by_type_for_year(year_param)
    plan_by_type = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0, 'other': 0}
    for _ym, _c in plan_table.items():
        for _k in plan_by_type:
            plan_by_type[_k] += _c[_k]

    return jsonify({
        'success': True,
        'year': year_param,
        'epics': [{'name': ep, 'plans': epic_plans[ep]} for ep in epic_order],
        'tasks': tasks,
        'milestones': milestones,
        'deps': deps,
        'dep_warnings': dep_warnings,
        'cr_links': cr_links,
        'plan_total': plan_total,
        'plan_by_type': plan_by_type,
    })


@plans_bp.route('/api/plans/lint')
@admin_required
def plans_lint():
    plans = parse_all_months()
    violations = _link_linter(plans)
    return jsonify({
        'success': True,
        'violations': violations,
        'pass': len(violations) == 0,
    })
