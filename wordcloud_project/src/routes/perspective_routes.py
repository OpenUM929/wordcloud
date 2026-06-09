"""Perspective analysis routes - X/Y matrix group analysis API."""
import os
import json as json_lib
import zipfile
import tempfile
from flask import Blueprint, request, jsonify, session, Response, send_file
from src.services.perspective_service import (
    load_all_batches, get_matrix_meta,
    generate_perspective_matrix, save_to_deploy,
    generate_all_employee_matrix, parse_csv_employee_ids,
    build_profanity_summary, _get_pseudo_mgr,
    TEST_SENTENCES_100, split_sentences, has_contrastive,
    sentence_sentiment_override, _get_sentence_level_scores,
    OUTPUTS_DIR_PATH,
)
from src.services.deploy_session_service import (
    create_session, allocate_chunk, report_chunk,
    get_active_sessions, resume_session, cancel_session,
    cleanup_old_sessions, get_session_progress,
    get_session_tasks, get_recently_completed_sessions,
    retry_failed_tasks,
)
from src.services.audit_service import log_action

perspective_bp = Blueprint('perspective', __name__, url_prefix='/api/perspective')


def _is_admin():
    return session.get('admin_logged_in', False)


def _resolve_output_mode(data):
    mode = data.get('output_mode', 'pseudonym')
    if mode == 'real':
        if not _is_admin():
            return None, '관리자 로그인이 필요합니다.'
        return True, None
    return False, None


@perspective_bp.route('/meta', methods=['POST'])
def api_get_meta():
    data = request.get_json(silent=True) or {}
    employee_id = data.get('employee_id')
    unified = load_all_batches()
    if not unified:
        return jsonify({'success': False, 'error': '처리된 배치 데이터가 없습니다.'}), 404
    meta = get_matrix_meta(unified, employee_id=employee_id, enrich=_is_admin())
    return jsonify({'success': True, 'admin': _is_admin(), **meta})


@perspective_bp.route('/csv-parse', methods=['POST'])
def api_csv_parse():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '파일이 필요합니다.'}), 400

    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({'success': False, 'error': 'CSV 파일만 업로드 가능합니다.'}), 400

    try:
        content = file.read().decode('utf-8-sig')
        ids = parse_csv_employee_ids(content)
    except Exception as e:
        return jsonify({'success': False, 'error': f'파일 읽기 실패: {str(e)}'}), 400

    if not ids:
        return jsonify({'success': False, 'error': 'CSV에서 직원 ID를 찾을 수 없습니다.'}), 400

    unified = load_all_batches()
    if not unified:
        return jsonify({'success': False, 'error': '배치 데이터가 없습니다.'}), 404

    pseudo_mgr = _get_pseudo_mgr()
    pseudo_to_real = {}
    all_known = set()
    for er in unified.get('employee_results', []):
        meta = er.get('metadata', {})
        eid = meta.get('target_employee_id')
        if eid:
            all_known.add(eid)
            real_id = pseudo_mgr.get_real_id(eid)
            if real_id and real_id != eid:
                all_known.add(real_id)
                pseudo_to_real[eid] = real_id
                pseudo_to_real[real_id] = real_id

    matched_real, not_found, seen = [], [], set()
    for eid in ids:
        if eid in all_known:
            real = pseudo_to_real.get(eid, eid)
            if real not in seen:
                seen.add(real)
                matched_real.append(real)
        else:
            not_found.append(eid)

    return jsonify({
        'success': True,
        'total': len(ids),
        'matched': len(matched_real),
        'matched_ids': matched_real,
        'not_found': not_found,
    })


@perspective_bp.route('/parse-ids', methods=['POST'])
def api_parse_ids():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'error': 'ids가 필요합니다.'}), 400

    unified = load_all_batches()
    if not unified:
        return jsonify({'success': False, 'error': '배치 데이터가 없습니다.'}), 404

    ids = list(dict.fromkeys([str(i).strip() for i in ids if str(i).strip()]))

    # PseudonymManager를 사용하여 가명/원본 매핑 추가
    pseudo_mgr = _get_pseudo_mgr()

    emp_map = {}
    for er in unified.get('employee_results', []):
        meta = er.get('metadata', {})
        eid = meta.get('target_employee_id')
        if eid:
            info = {
                'employee_id': eid,
                'name': meta.get('target_employee_name', ''),
                'department': meta.get('target_employee_department', ''),
                'position': meta.get('target_employee_position', ''),
                'evaluation_count': len(meta.get('evaluations', [])),
            }
            emp_map[eid] = info
            real_id = pseudo_mgr.get_real_id(eid)
            if real_id and real_id != eid:
                emp_map[real_id] = info

    matched = []
    not_found = []
    details = []
    seen_ids = set()
    for eid in ids:
        if eid in emp_map:
            info = emp_map[eid]
            if info['employee_id'] not in seen_ids:
                seen_ids.add(info['employee_id'])
                real_id = pseudo_mgr.get_real_id(info['employee_id'])
                matched.append(real_id)
                details.append({**info, 'employee_id': real_id})
        else:
            not_found.append(eid)

    return jsonify({
        'success': True,
        'total': len(ids),
        'matched': len(matched),
        'matched_ids': matched,
        'not_found': not_found,
        'details': details,
    })


@perspective_bp.route('/deploy-session/start', methods=['POST'])
def api_deploy_session_start():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    options = data.get('options', {})
    employee_ids = data.get('employee_ids', [])
    if not employee_ids:
        return jsonify({'success': False, 'error': 'employee_ids가 필요합니다.'}), 400

    cleanup_old_sessions(days=7)
    session_id = create_session(options, employee_ids)
    return jsonify({'success': True, 'session_id': session_id, 'total': len(employee_ids)})


@perspective_bp.route('/deploy-session/chunk', methods=['GET'])
def api_deploy_session_chunk():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    session_id = request.args.get('session_id', '')
    count = request.args.get('count', 50, type=int)
    if not session_id:
        return jsonify({'success': False, 'error': 'session_id가 필요합니다.'}), 400

    ids = allocate_chunk(session_id, count)
    return jsonify({'success': True, 'employee_ids': ids})


@perspective_bp.route('/deploy-session/complete', methods=['POST'])
def api_deploy_session_complete():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id', '')
    # completed_items: [{employee_id, result_data}] — result_data에 워드클라우드 경로 포함
    # 하위 호환: completed_ids (str list) 도 수용
    completed_items = data.get('completed_items') or [
        {'employee_id': eid} for eid in data.get('completed_ids', [])
    ]
    failed_items = data.get('failed_items', [])

    report_chunk(session_id, completed_items, failed_items)
    progress = get_session_progress(session_id)
    return jsonify({'success': True, 'progress': progress})


@perspective_bp.route('/deploy-session/active', methods=['GET'])
def api_deploy_session_active():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    sessions = get_active_sessions()
    return jsonify({'success': True, 'sessions': sessions})


@perspective_bp.route('/deploy-session/resume', methods=['POST'])
def api_deploy_session_resume():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id', '')
    if not session_id:
        return jsonify({'success': False, 'error': 'session_id가 필요합니다.'}), 400

    resume_session(session_id)
    return jsonify({'success': True})


@perspective_bp.route('/deploy-session/retry', methods=['POST'])
def api_deploy_session_retry():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id', '')
    if not session_id:
        return jsonify({'success': False, 'error': 'session_id가 필요합니다.'}), 400

    progress = get_session_progress(session_id)
    if not progress:
        return jsonify({'success': False, 'error': '세션을 찾을 수 없습니다.'}), 404

    retry_failed_tasks(session_id)
    return jsonify({'success': True, 'session_id': session_id})


@perspective_bp.route('/deploy-session/cancel', methods=['POST'])
def api_deploy_session_cancel():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id', '')
    if not session_id:
        return jsonify({'success': False, 'error': 'session_id가 필요합니다.'}), 400

    cancel_session(session_id)
    return jsonify({'success': True})


@perspective_bp.route('/deploy-session/progress', methods=['GET'])
def api_deploy_session_progress():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    session_id = request.args.get('session_id', '')
    if not session_id:
        return jsonify({'success': False, 'error': 'session_id가 필요합니다.'}), 400
    progress = get_session_progress(session_id)
    if not progress:
        return jsonify({'success': False, 'error': '세션을 찾을 수 없습니다.'}), 404
    return jsonify({'success': True, 'progress': progress})


@perspective_bp.route('/deploy-session/tasks', methods=['GET'])
def api_deploy_session_tasks():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    session_id = request.args.get('session_id', '')
    if not session_id:
        return jsonify({'success': False, 'error': 'session_id가 필요합니다.'}), 400
    tasks = get_session_tasks(session_id)
    return jsonify({'success': True, 'tasks': tasks})


@perspective_bp.route('/deploy-session/recent-completed', methods=['GET'])
def api_deploy_session_recent_completed():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    hours = request.args.get('hours', 24, type=int)
    sessions = get_recently_completed_sessions(hours)
    return jsonify({'success': True, 'sessions': sessions})


@perspective_bp.route('/deploy-session/download', methods=['GET'])
def api_deploy_session_download():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    session_id = request.args.get('session_id', '')
    if not session_id:
        return jsonify({'success': False, 'error': 'session_id가 필요합니다.'}), 400

    tasks = get_session_tasks(session_id)
    if not tasks:
        return jsonify({'success': False, 'error': '세션을 찾을 수 없습니다.'}), 404

    file_paths = []
    for task in tasks:
        if task.get('status') != 'completed':
            continue
        result_path = task.get('result_path', '')
        if not result_path:
            continue
        try:
            result = json_lib.loads(result_path)
        except (json_lib.JSONDecodeError, TypeError):
            continue

        urls = []
        if 'combined' in result:
            urls.append(result['combined'])
        if 'positive' in result:
            urls.append(result['positive'])
        if 'negative' in result:
            urls.append(result['negative'])
        for row_data in result.get('row_results', {}).values():
            if isinstance(row_data, dict):
                urls.extend([row_data.get('combined'), row_data.get('positive'), row_data.get('negative')])

        for url in urls:
            if not url:
                continue
            clean_url = url.split('?')[0]
            rel = clean_url.lstrip('/')
            if rel.startswith('outputs/'):
                rel = rel[8:]
            abs_path = os.path.join(OUTPUTS_DIR_PATH, rel)
            if os.path.exists(abs_path):
                file_paths.append(abs_path)

    if not file_paths:
        return jsonify({'success': False, 'error': '다운로드할 파일이 없습니다.'}), 404

    from datetime import datetime as _dt
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    with zipfile.ZipFile(tmp.name, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fp in file_paths:
            arcname = os.path.relpath(fp, OUTPUTS_DIR_PATH).replace('\\', '/')
            zf.write(fp, arcname)

    return send_file(tmp.name, mimetype='application/zip',
                     as_attachment=True,
                     download_name=f'deploy_{session_id[:8]}_{_dt.now().strftime("%Y%m%d")}.zip')


@perspective_bp.route('/matrix', methods=['POST'])
def api_generate_matrix():
    data = request.get_json(silent=True) or {}
    employee_id = data.get('employee_id')
    row_field = data.get('row_field', 'evaluation_date__year')
    col_mode = data.get('col_mode', 'all')
    analysis_type = data.get('analysis_type', 'nlp')
    all_employees = data.get('all_employees', False)
    employee_ids = data.get('employee_ids')

    if not employee_id and not all_employees and not employee_ids:
        return jsonify({'success': False, 'error': 'employee_id 또는 employee_ids가 필요합니다.'}), 400

    options = {
        'wordcloud_pos': data.get('wordcloud_pos', ['Noun']),
        'background_color': data.get('background_color', 'white'),
        'apply_emotion_colors': data.get('apply_emotion_colors', True),
        'remove_profanity': data.get('remove_profanity', False),
        'generate_png': data.get('generate_png', True),
        'width': data.get('width', 400),
        'height': data.get('height', 300),
        'max_words': data.get('max_words', 80),
        'output_mode': data.get('output_mode', 'pseudonym'),
        'row_values': data.get('row_values'),
        'row_combine_all': data.get('row_combine_all', False),
        'deploy_mode': data.get('deploy_mode', 'combined+individual'),
        'analysis_types': data.get('analysis_types'),
        'batch_title': (data.get('batch_title') or '').strip() or None,
    }

    enrich, err = _resolve_output_mode(data)
    if err:
        return jsonify({'success': False, 'error': err}), 401

    unified = load_all_batches()
    if not unified:
        return jsonify({'success': False, 'error': '처리된 배치 데이터가 없습니다.'}), 404

    if all_employees or employee_ids:
        results = generate_all_employee_matrix(unified, row_field, col_mode, analysis_type, options, employee_ids=employee_ids)
        if results is None:
            return jsonify({'success': False, 'error': '매트릭스 생성 실패'}), 400
        return jsonify({
            'success': True,
            'row_field': row_field,
            'col_mode': col_mode,
            'analysis_type': analysis_type,
            'all_employees': True,
            'employee_results': results,
            'output_mode': 'real' if enrich else 'pseudonym',
        })

    result = generate_perspective_matrix(unified, employee_id, row_field, col_mode, analysis_type, options)
    if result is None:
        return jsonify({
            'success': False,
            'error': f"'{employee_id}' 직원의 조건에 맞는 평가가 없습니다."
        }), 400

    return jsonify({
        'success': True,
        'output_mode': 'real' if enrich else 'pseudonym',
        **result,
    })


@perspective_bp.route('/matrix/save-deploy', methods=['POST'])
def api_save_deploy():
    data = request.get_json(silent=True) or {}
    employee_id = data.get('employee_id')
    employee_ids = data.get('employee_ids')
    all_employees = data.get('all_employees', False)
    row_field = data.get('row_field', 'evaluation_date__year')
    col_mode = data.get('col_mode', 'all')
    analysis_type = data.get('analysis_type', 'nlp')

    if not employee_id and not employee_ids and not all_employees:
        return jsonify({'success': False, 'error': 'employee_id 또는 employee_ids가 필요합니다.'}), 400
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    output_mode = data.get('output_mode', 'pseudonym')
    options = {
        'wordcloud_pos': data.get('wordcloud_pos', ['Noun']),
        'background_color': data.get('background_color', 'white'),
        'width': data.get('width', 800),
        'height': data.get('height', 600),
        'max_words': data.get('max_words', 100),
        'remove_profanity': data.get('remove_profanity', False),
        'row_values': data.get('row_values'),
        'row_combine_all': data.get('row_combine_all', False),
        'deploy_mode': data.get('deploy_mode', 'combined+individual'),
        'analysis_types': data.get('analysis_types'),
        'output_mode': output_mode,
        'include_name': data.get('include_name', True),
        'include_id': data.get('include_id', True),
        'apply_emotion_colors': data.get('apply_emotion_colors', True),
        'batch_title': (data.get('batch_title') or '').strip() or None,
    }

    unified = load_all_batches()
    if not unified:
        return jsonify({'success': False, 'error': '처리된 배치 데이터가 없습니다.'}), 404

    if all_employees and not employee_ids:
        seen = set()
        all_ids = []
        for er in unified.get('employee_results', []):
            eid = er.get('metadata', {}).get('target_employee_id')
            if eid and eid not in seen:
                seen.add(eid)
                all_ids.append(eid)
        employee_ids = all_ids

    if employee_ids:
        results_list = []
        for eid in employee_ids:
            result = save_to_deploy(unified, eid, row_field, col_mode, analysis_type, options, request)
            if result:
                results_list.append(result)

        if not results_list:
            return jsonify({'success': False, 'error': '매칭되는 직원의 평가 데이터가 없습니다.'}), 400

        log_action('csv_batch_save_deploy', {
            'count': len(results_list),
            'employee_ids': employee_ids,
            'row_field': row_field,
            'col_mode': col_mode,
            'analysis_type': analysis_type,
        }, request)

        return jsonify({
            'success': True,
            'results': results_list,
            'total': len(results_list),
            'batch': True,
        })

    results = save_to_deploy(unified, employee_id, row_field, col_mode, analysis_type, options, request)
    if not results:
        return jsonify({
            'success': False,
            'error': f"'{employee_id}' 직원의 조건에 맞는 평가가 없습니다."
        }), 400

    log_action('matrix_save_deploy', {
        'employee_id': employee_id,
        'row_field': row_field,
        'col_mode': col_mode,
        'analysis_type': analysis_type,
        'paths': {k: v for k, v in results.items() if k not in ('name', 'timestamp')},
        'name': results.get('name'),
    }, request)

    return jsonify({'success': True, **results})


@perspective_bp.route('/matrix/save-deploy-stream', methods=['POST'])
def api_save_deploy_stream():
    data = request.get_json(silent=True) or {}
    employee_ids = data.get('employee_ids')
    employee_id = data.get('employee_id')
    all_employees = data.get('all_employees', False)
    row_field = data.get('row_field', 'evaluation_date__year')
    col_mode = data.get('col_mode', 'all')
    analysis_type = data.get('analysis_type', 'nlp')

    if not employee_id and not employee_ids and not all_employees:
        return jsonify({'success': False, 'error': 'employee_id가 필요합니다.'}), 400
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    output_mode = data.get('output_mode', 'pseudonym')
    options = {
        'wordcloud_pos': data.get('wordcloud_pos', ['Noun']),
        'background_color': data.get('background_color', 'white'),
        'width': data.get('width', 800),
        'height': data.get('height', 600),
        'max_words': data.get('max_words', 100),
        'remove_profanity': data.get('remove_profanity', False),
        'row_values': data.get('row_values'),
        'row_combine_all': data.get('row_combine_all', False),
        'deploy_mode': data.get('deploy_mode', 'combined+individual'),
        'analysis_types': data.get('analysis_types'),
        'output_mode': output_mode,
        'include_name': data.get('include_name', True),
        'include_id': data.get('include_id', True),
        'apply_emotion_colors': data.get('apply_emotion_colors', True),
        'batch_title': (data.get('batch_title') or '').strip() or None,
    }

    unified = load_all_batches()
    if not unified:
        return jsonify({'success': False, 'error': '배치 데이터가 없습니다.'}), 404

    if all_employees and not employee_ids:
        seen = set()
        all_ids = []
        for er in unified.get('employee_results', []):
            eid = er.get('metadata', {}).get('target_employee_id')
            if eid and eid not in seen:
                seen.add(eid)
                all_ids.append(eid)
        employee_ids = all_ids

    ids = employee_ids if employee_ids else [employee_id]

    def generate():
        success_list = []
        fail_list = []
        total = len(ids)

        for idx, eid in enumerate(ids):
            try:
                yield json_lib.dumps({'employee': eid, 'status': 'processing', 'current': idx + 1, 'total': total}) + '\n'
                result = save_to_deploy(unified, eid, row_field, col_mode, analysis_type, options, request)
                if result:
                    real_name = result.get('name', eid)
                    result['employee_id'] = eid
                    result['profanity_summary'] = build_profanity_summary(unified, eid)
                    success_list.append(result)
                    yield json_lib.dumps({'employee': eid, 'name': real_name, 'status': 'done', 'result': result, 'current': idx + 1, 'total': total}) + '\n'
                else:
                    fail_list.append({'employee_id': eid, 'error': '평가 데이터 없음'})
                    yield json_lib.dumps({'employee': eid, 'status': 'fail', 'error': '평가 데이터 없음', 'current': idx + 1, 'total': total}) + '\n'
            except Exception as ex:
                fail_list.append({'employee_id': eid, 'error': str(ex)})
                yield json_lib.dumps({'employee': eid, 'status': 'fail', 'error': str(ex), 'current': idx + 1, 'total': total}) + '\n'

        log_action('csv_batch_save_deploy_stream', {
            'total': total,
            'success': len(success_list),
            'fail': len(fail_list),
            'failed_employees': [f['employee_id'] for f in fail_list],
        }, request)

        yield json_lib.dumps({
            'status': 'complete',
            'success': success_list,
            'fail': fail_list,
            'total': total,
        }) + '\n'

    return Response(generate(), mimetype='application/x-ndjson')


@perspective_bp.route('/users', methods=['GET'])
def api_get_users():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    unified = load_all_batches()
    if not unified:
        return jsonify({'success': False, 'error': '처리된 배치 데이터가 없습니다.'}), 404

    users = {}
    for er in unified.get('employee_results', []):
        meta = er.get('metadata', {})
        emp_id = meta.get('target_employee_id')
        if not emp_id:
            continue
        if emp_id not in users:
            users[emp_id] = {
                'employee_id': emp_id,
                'department': meta.get('target_employee_department', ''),
                'position': meta.get('target_employee_position', ''),
                'name': meta.get('target_employee_name', ''),
                'total_evaluations': 0,
                'batches': {},
            }
        info = users[emp_id]
        evals = meta.get('evaluations', [])
        info['total_evaluations'] += len(evals)
        # Count evaluations per batch (each evaluation has embedded batch_id)
        for ev in evals:
            bid = ev.get('batch_id', '')
            if bid:
                if bid not in info['batches']:
                    info['batches'][bid] = 0
                info['batches'][bid] += 1

    result = []
    for emp_id in sorted(users):
        info = users[emp_id]
        info['batches'] = [
            {'batch_id': bid, 'evaluation_count': cnt}
            for bid, cnt in sorted(info['batches'].items())
        ]
        result.append(info)

    return jsonify({'success': True, 'users': result, 'total_users': len(result)})


@perspective_bp.route('/batches', methods=['GET'])
def api_batch_history():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    unified = load_all_batches()
    if not unified:
        return jsonify({'success': False, 'batches': []})
    return jsonify({
        'success': True,
        'batches': unified.get('batches', []),
        'batch_info': unified.get('batch_info', {}),
    })


@perspective_bp.route('/batch/<batch_id>', methods=['DELETE'])
def api_batch_delete(batch_id):
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    from src.config.settings import PROCESSED_DATA_DIR_PATH
    from src.services.user_data_manager import remove_batch_from_all
    batch_dir = os.path.join(PROCESSED_DATA_DIR_PATH, 'batch', batch_id)
    if not os.path.isdir(batch_dir):
        return jsonify({'success': False, 'error': f'배치({batch_id})를 찾을 수 없습니다.'}), 404

    # 1. Get employee_ids from lightweight batch_summary
    from src.services.perspective_service import load_batch_summary
    summary = load_batch_summary(batch_dir)
    employee_ids = summary.get('employee_ids', []) if summary else []

    # 2. Remove batch data from user files
    removed_count = remove_batch_from_all(batch_id, employee_ids)

    # 3. Remove batch directory
    import shutil
    shutil.rmtree(batch_dir)

    log_action('batch_delete', {
        'batch_id': batch_id, 'path': batch_dir,
        'affected_employees': len(employee_ids),
        'removed_evaluations': removed_count,
    }, request)
    return jsonify({'success': True, 'message': f'배치 {batch_id} 삭제 완료 ({removed_count}건 평가 제거)'})


@perspective_bp.route('/test/sentence-sentiment', methods=['POST'])
def api_test_sentence_sentiment():
    """문장별 감정 분석 테스트 엔드포인트 (개별/일괄)."""
    data = request.get_json(silent=True) or {}
    text = data.get('text', '')
    run_batch = data.get('batch', False)
    threshold = data.get('threshold', 0.20)
    weight = data.get('weight', 2.0)
    include_strong = data.get('include_strong', True)
    include_medium = data.get('include_medium', True)
    include_suffix = data.get('include_suffix', True)
    include_idiomatic = data.get('include_idiomatic', True)

    from src.modules.emotion_analysis import analyze_emotion
    from src.services.translation_service import back_translate

    def analyze_one(sent_text, is_last=False, total=1, item_expected=None, include_bt=False):
        """한 문장 분석 + 교정."""
        try:
            result = analyze_emotion(sent_text)
            scores = result.get('analysis', {}).get('base_result', {}).get('mapped', {}).get('sentiment_scores', {})
            pos = scores.get('positive', 0.0) or 0.0
            neg = scores.get('negative', 0.0) or 0.0
            neutral = scores.get('neutral', 0.0) or 0.0
            confidence = abs(pos - neg)
            strength = pos + neg
            has_contrast = has_contrastive(sent_text)
            original_score = round(pos - neg, 4)
            corrected_score = round(sentence_sentiment_override(
                pos, neg, sent_text, is_last, total,
                threshold=threshold, weight=weight, neutral=neutral
            ), 4)

            # 판정
            if corrected_score > 0:
                result_label = 'positive'
            elif corrected_score < 0:
                result_label = 'negative'
            else:
                result_label = 'neutral'

            match = None
            if item_expected:
                match = (result_label == item_expected)

            res = {
                'text': sent_text,
                'pos': round(pos, 4),
                'neg': round(neg, 4),
                'neutral': round(neutral, 4),
                'confidence': round(confidence, 4),
                'strength': round(strength, 4),
                'has_contrast': has_contrast,
                'is_last': is_last,
                'original_score': original_score,
                'corrected_score': corrected_score,
                'result': result_label,
                'expected': item_expected,
                'match': match,
            }

            # Back-translation comparison (optional)
            if include_bt and sent_text.strip():
                try:
                    # opus-mt back-translation
                    opus = back_translate(sent_text, 'opus')
                    opus_result = analyze_emotion(opus['back_translated'])
                    opus_scores = opus_result.get('analysis', {}).get('base_result', {}).get('mapped', {}).get('sentiment_scores', {})

                    # nllb back-translation
                    nllb = back_translate(sent_text, 'nllb')
                    nllb_result = analyze_emotion(nllb['back_translated'])
                    nllb_scores = nllb_result.get('analysis', {}).get('base_result', {}).get('mapped', {}).get('sentiment_scores', {})

                    res['back_translation'] = {
                        'opus': {
                            'english': opus['english'],
                            'back_translated': opus['back_translated'],
                            'pos': round(opus_scores.get('positive', 0.0), 4),
                            'neg': round(opus_scores.get('negative', 0.0), 4),
                        },
                        'nllb': {
                            'english': nllb['english'],
                            'back_translated': nllb['back_translated'],
                            'pos': round(nllb_scores.get('positive', 0.0), 4),
                            'neg': round(nllb_scores.get('negative', 0.0), 4),
                        }
                    }
                except Exception as bt_err:
                    res['back_translation_error'] = str(bt_err)

            return res
        except Exception as e:
            return {
                'text': sent_text,
                'error': str(e),
                'expected': item_expected,
                'match': False,
            }

    if run_batch:
        # 100개 일괄 테스트 (back-translation 포함)
        all_results = []
        correct_count = 0
        total_count = 0
        for item in TEST_SENTENCES_100:
            sentences = split_sentences(item['text'])
            total = len(sentences)
            sent_results = []
            for i, sent in enumerate(sentences):
                is_last = (i == total - 1)
                # 마지막 문장의 판정만 평가 기준으로 삼음
                expected = item['expected'] if is_last else None
                res = analyze_one(sent, is_last, total, expected, include_bt=True)
                sent_results.append(res)
                if is_last:
                    if res.get('match') is True:
                        correct_count += 1
                    total_count += 1
            all_results.append({
                'id': item['id'],
                'category': item['category'],
                'text': item['text'],
                'sentences': sent_results,
            })
        accuracy = round(correct_count / total_count * 100, 2) if total_count > 0 else 0
        return jsonify({
            'success': True,
            'batch': True,
            'total': total_count,
            'correct': correct_count,
            'accuracy': accuracy,
            'threshold': threshold,
            'weight': weight,
            'results': all_results,
        })

    # 단일 문장 테스트
    sentences = split_sentences(text)
    total = len(sentences)
    sent_results = []
    for i, sent in enumerate(sentences):
        is_last = (i == total - 1)
        res = analyze_one(sent, is_last, total, include_bt=True)
        sent_results.append(res)

    return jsonify({
        'success': True,
        'text': text,
        'sentence_count': total,
        'threshold': threshold,
        'weight': weight,
        'sentences': sent_results,
    })


@perspective_bp.route('/deploy-gallery/list', methods=['GET'])
def api_deploy_gallery_list():
    """List deployment gallery entries with filtering and pagination."""
    from src.services.perspective_service import DEPLOY_MANIFEST_PATH
    
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)
    employee_id = request.args.get('employee_id', '').strip()
    output_mode = request.args.get('output_mode', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    batch_title_filter = request.args.get('batch_title', '').strip()

    is_admin = _is_admin()

    # Load manifest
    manifest = {"version": "1.0", "entries": []}
    if os.path.exists(DEPLOY_MANIFEST_PATH):
        try:
            with open(DEPLOY_MANIFEST_PATH, 'r', encoding='utf-8') as f:
                manifest = json_lib.load(f)
        except Exception as e:
            print(f"[DeployGallery] Manifest read error: {e}")

    entries = manifest.get('entries', [])
    source_filter = request.args.get('source', '').strip()
    dates_filter = request.args.get('dates', '').strip()
    date_list = [d.strip() for d in dates_filter.split(',') if d.strip()] if dates_filter else []

    # Filter
    filtered = []
    for entry in entries:
        # Non-admin: exclude real mode entirely
        if not is_admin and entry.get('output_mode') == 'real':
            continue

        # source 역호환: 필드 없으면 'deploy'로 간주
        entry_source = entry.get('source', 'deploy')
        if source_filter and entry_source != source_filter:
            continue

        if employee_id and entry.get('employee_id') != employee_id:
            continue

        if output_mode and entry.get('output_mode') != output_mode:
            continue

        ts = entry.get('timestamp', '')
        date_part = ts[:8] if len(ts) >= 8 else ts

        if date_list and date_part not in date_list:
            continue

        if date_from and date_part < date_from:
            continue
        if date_to and date_part > date_to:
            continue

        if batch_title_filter:
            entry_bt = (entry.get('batch_title') or '').lower()
            if batch_title_filter.lower() not in entry_bt:
                continue

        # Build list item
        images = entry.get('images', {})
        row_results = entry.get('row_results', {})
        top_count = sum(1 for v in images.values() if v)
        row_count = sum(
            1 for rv in row_results.values()
            for v in (rv.values() if isinstance(rv, dict) else [])
            if v
        )
        bt = entry.get('batch_title') or None
        list_item = {
            "id": entry.get('id'),
            "employee_id": entry.get('employee_id'),
            "deploy_name": entry.get('deploy_name'),
            "batch_title": bt,
            "display_title": bt or entry.get('deploy_name') or entry.get('employee_id'),
            "timestamp": entry.get('timestamp'),
            "output_mode": entry.get('output_mode'),
            "source": entry_source,
            "image_count": top_count + row_count,
            "thumbnail_url": images.get('combined'),
        }
        filtered.append(list_item)

    # batch_title 있는 항목 먼저, 그 다음 batch_title asc, timestamp asc
    filtered.sort(key=lambda x: (
        not bool(x.get('batch_title')),
        x.get('batch_title') or '',
        x.get('timestamp', ''),
    ))
    
    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = filtered[start:end]
    
    return jsonify({
        'success': True,
        'total': total,
        'page': page,
        'per_page': per_page,
        'entries': paginated,
    })


@perspective_bp.route('/deploy-gallery/detail/<entry_id>', methods=['GET'])
def api_deploy_gallery_detail(entry_id):
    """Get detailed information for a single gallery entry."""
    from src.services.perspective_service import DEPLOY_MANIFEST_PATH
    
    is_admin = _is_admin()
    
    manifest = {"entries": []}
    if os.path.exists(DEPLOY_MANIFEST_PATH):
        try:
            with open(DEPLOY_MANIFEST_PATH, 'r', encoding='utf-8') as f:
                manifest = json_lib.load(f)
        except Exception as e:
            print(f"[DeployGallery] Manifest read error: {e}")
    
    for entry in manifest.get('entries', []):
        if entry.get('id') == entry_id:
            # Permission check
            if not is_admin and entry.get('output_mode') == 'real':
                return jsonify({'success': False, 'error': '접근 권한이 없습니다.'}), 403
            
            return jsonify({
                'success': True,
                'entry': entry,
            })
    
    return jsonify({'success': False, 'error': 'Entry not found'}), 404


@perspective_bp.route('/deploy-gallery/employee-entries/<employee_id>', methods=['GET'])
def api_employee_entries(employee_id):
    """같은 직원의 deploy/matrix 양쪽 최신 entry를 반환."""
    from src.services.perspective_service import DEPLOY_MANIFEST_PATH
    
    is_admin = _is_admin()
    manifest = {"entries": []}
    if os.path.exists(DEPLOY_MANIFEST_PATH):
        try:
            with open(DEPLOY_MANIFEST_PATH, 'r', encoding='utf-8') as f:
                manifest = json_lib.load(f)
        except Exception:
            pass

    latest = {'deploy': None, 'matrix': None}
    for entry in manifest.get('entries', []):
        if entry.get('employee_id') != employee_id:
            continue
        if not is_admin and entry.get('output_mode') == 'real':
            continue
        src = entry.get('source', 'deploy')
        if src not in latest:
            continue
        current = latest[src]
        if current is None or entry.get('timestamp', '') > current.get('timestamp', ''):
            latest[src] = entry

    return jsonify({
        'success': True,
        'employee_id': employee_id,
        'deploy': latest['deploy'],
        'matrix': latest['matrix'],
    })


def _load_manifest_entries():
    from src.services.perspective_service import DEPLOY_MANIFEST_PATH
    if not os.path.exists(DEPLOY_MANIFEST_PATH):
        return []
    try:
        with open(DEPLOY_MANIFEST_PATH, 'r', encoding='utf-8') as f:
            return json_lib.load(f).get('entries', [])
    except Exception:
        return []


@perspective_bp.route('/deploy-gallery/dates', methods=['GET'])
def api_deploy_gallery_dates():
    """갤러리 항목에 존재하는 날짜(YYYYMMDD) 목록 반환."""
    entries = _load_manifest_entries()
    is_admin = _is_admin()
    dates = set()
    for e in entries:
        if not is_admin and e.get('output_mode') == 'real':
            continue
        ts = e.get('timestamp', '')
        if len(ts) >= 8:
            dates.add(ts[:8])
    return jsonify({'success': True, 'dates': sorted(dates, reverse=True)})


@perspective_bp.route('/deploy-gallery/batch-titles', methods=['GET'])
def api_deploy_gallery_batch_titles():
    """갤러리 항목에 존재하는 배치 명칭 목록 반환."""
    entries = _load_manifest_entries()
    is_admin = _is_admin()
    titles = set()
    for e in entries:
        if not is_admin and e.get('output_mode') == 'real':
            continue
        bt = (e.get('batch_title') or '').strip()
        if bt:
            titles.add(bt)
    return jsonify({'success': True, 'batch_titles': sorted(titles)})


@perspective_bp.route('/deploy-gallery/entries', methods=['DELETE'])
def api_deploy_gallery_delete():
    """갤러리 항목 삭제 (관리자 전용)."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    from src.services.perspective_service import DEPLOY_MANIFEST_PATH
    data = request.get_json(silent=True) or {}
    entry_ids = set(data.get('entry_ids', []))
    if not entry_ids:
        return jsonify({'success': False, 'error': 'entry_ids가 필요합니다.'}), 400

    manifest = {"version": "1.0", "entries": []}
    if os.path.exists(DEPLOY_MANIFEST_PATH):
        try:
            with open(DEPLOY_MANIFEST_PATH, 'r', encoding='utf-8') as f:
                manifest = json_lib.load(f)
        except Exception as e:
            return jsonify({'success': False, 'error': f'Manifest 읽기 실패: {e}'}), 500

    to_delete = [e for e in manifest.get('entries', []) if e.get('id') in entry_ids]
    remaining = [e for e in manifest.get('entries', []) if e.get('id') not in entry_ids]

    # 이미지 파일 best-effort 삭제
    from src.config.settings import OUTPUTS_DIR_PATH
    for entry in to_delete:
        images = entry.get('images', {})
        row_results = entry.get('row_results', {})
        all_paths = list(images.values())
        for rv in row_results.values():
            if isinstance(rv, dict):
                all_paths.extend(rv.values())
        for url_or_path in all_paths:
            if not url_or_path:
                continue
            # URL → 파일 경로 변환 (/outputs/배포/xxx.png → 실제 경로)
            rel = url_or_path.lstrip('/')
            if rel.startswith('outputs/'):
                rel = rel[len('outputs/'):]
            fpath = os.path.join(OUTPUTS_DIR_PATH, rel)
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception:
                pass

    manifest['entries'] = remaining
    try:
        with open(DEPLOY_MANIFEST_PATH, 'w', encoding='utf-8') as f:
            json_lib.dump(manifest, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Manifest 저장 실패: {e}'}), 500

    log_action('gallery_delete', {'entry_ids': list(entry_ids), 'deleted_count': len(to_delete)}, request)
    return jsonify({'success': True, 'deleted_count': len(to_delete)})


@perspective_bp.route('/deploy-title/check', methods=['POST'])
def api_deploy_title_check():
    """배치 명칭 중복 확인."""
    data = request.get_json(silent=True) or {}
    batch_title = (data.get('batch_title') or '').strip()
    if not batch_title:
        return jsonify({'success': True, 'exists': False, 'count': 0, 'sources': []})

    entries = _load_manifest_entries()
    matches = [e for e in entries if (e.get('batch_title') or '').strip() == batch_title]
    sources = list({e.get('source', 'deploy') for e in matches})
    return jsonify({
        'success': True,
        'exists': len(matches) > 0,
        'count': len(matches),
        'sources': sources,
    })
