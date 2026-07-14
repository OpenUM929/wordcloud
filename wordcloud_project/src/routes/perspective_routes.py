"""Perspective analysis routes - X/Y matrix group analysis API."""
import os
import re
import uuid as uuid_lib
import json as json_lib
import zipfile
import tempfile
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Blueprint, request, jsonify, session, Response, send_file
from src.services.perspective_service import (
    load_all_batches, load_employee_batch, list_all_employee_ids,
    load_employees_batch, list_employee_roster, list_users_with_batch_counts,
    load_batch_history,
    get_matrix_meta, get_matrix_meta_light,
    generate_perspective_matrix, save_to_deploy,
    generate_all_employee_matrix, parse_csv_employee_ids,
    build_profanity_summary, _get_pseudo_mgr,
    TEST_SENTENCES_100, split_sentences, has_contrastive,
    sentence_sentiment_override, _get_sentence_level_scores,
    _load_corrections_map, _setup_korean_font,
    save_acquired_sentence, list_acquired_sentences,
    delete_acquired_sentence, delete_acquired_sentences_bulk,
    delete_acquired_sentences_filtered, analyze_acquired_sentences,
    export_acquired_sentences_csv, export_acquired_sentences_refined_csv,
    import_acquired_sentences_csv, save_acquired_sentences_bulk,
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
from utils.logger import get_pipeline_logger, _mask_real_id

pipeline_logger = get_pipeline_logger()

perspective_bp = Blueprint('perspective', __name__, url_prefix='/api/perspective')


def _gen_request_id():
    return uuid_lib.uuid4().hex[:12]


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
    # 0619_03 후속: X축(시간/회차) 메타도 load_all_batches()의 19,000건 json.loads
    # 병목을 그대로 타고 있었다. row_options는 batch_id·evaluation_date 인덱스 컬럼
    # GROUP BY만으로 산출 가능하므로 data blob 미적재 경량 빌더로 교체.
    meta = get_matrix_meta_light(employee_id=employee_id, enrich=_is_admin())
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

    # ID 소속 확인만 필요 — 가명 ID 목록만 적재(평가 본문 미적재) 후 원본 매핑(0714).
    known_pseudo_ids = list_all_employee_ids()
    if not known_pseudo_ids:
        return jsonify({'success': False, 'error': '배치 데이터가 없습니다.'}), 404

    pseudo_mgr = _get_pseudo_mgr()
    pseudo_to_real = {}
    all_known = set()
    for eid in known_pseudo_ids:
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

    # ID 매칭은 명부(id/이름/부서/직급/건수)만 필요 — 평가 본문 미적재 경량 로더(0714).
    roster = list_employee_roster()
    if not roster:
        return jsonify({'success': False, 'error': '배치 데이터가 없습니다.'}), 404

    ids = list(dict.fromkeys([str(i).strip() for i in ids if str(i).strip()]))

    # PseudonymManager를 사용하여 가명/원본 매핑 추가
    pseudo_mgr = _get_pseudo_mgr()

    emp_map = {}
    for row in roster:
        eid = row['employee_id']
        if eid:
            info = {
                'employee_id': eid,
                'name': row['name'],
                'department': row['department'],
                'position': row['position'],
                'evaluation_count': row['evaluation_count'],
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
    tmp_name = tmp.name
    tmp.close()
    with zipfile.ZipFile(tmp_name, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fp in file_paths:
            arcname = os.path.relpath(fp, OUTPUTS_DIR_PATH).replace('\\', '/')
            zf.write(fp, arcname)

    return send_file(tmp_name, mimetype='application/zip',
                     as_attachment=True,
                     download_name=f'deploy_{session_id[:8]}_{_dt.now().strftime("%Y%m%d")}.zip')


@perspective_bp.route('/matrix', methods=['POST'])
def api_generate_matrix():
    request_id = _gen_request_id()
    data = request.get_json(silent=True) or {}
    employee_id = data.get('employee_id')
    row_field = data.get('row_field', 'evaluation_date__year')
    col_mode = data.get('col_mode', 'all')
    analysis_type = data.get('analysis_type', 'nlp')
    all_employees = data.get('all_employees', False)
    employee_ids = data.get('employee_ids')

    if not employee_id and not all_employees and not employee_ids:
        return jsonify({'success': False, 'error': 'employee_id 또는 employee_ids가 필요합니다.'}), 400

    pipeline_logger.info("employee_id=%s", _mask_real_id(str(employee_id)) if employee_id else '', extra={'request_id': request_id, 'stage': 'MATRIX_API'})

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

        'analysis_types': data.get('analysis_types'),
        'word_color': data.get('word_color'),
        'batch_title': (data.get('batch_title') or '').strip() or None,
    }

    enrich, err = _resolve_output_mode(data)
    if err:
        return jsonify({'success': False, 'error': err}), 401

    # 선택 범위만 적재한다 — 1명·소수 선택 시 전 직원(1.9만) json.loads 낭비 제거(0714).
    # all_employees(전원)만 전량 적재, employee_ids(소수)/단일은 선택분만.
    if all_employees:
        unified = load_all_batches()
    elif employee_ids:
        unified = load_employees_batch(employee_ids)
    else:
        unified = load_employee_batch(employee_id)
    if not unified:
        return jsonify({'success': False, 'error': '처리된 배치 데이터가 없습니다.'}), 404

    if all_employees or employee_ids:
        results = generate_all_employee_matrix(unified, row_field, col_mode, analysis_type, options, employee_ids=employee_ids)
        if results is None:
            return jsonify({'success': False, 'error': '매트릭스 생성 실패'}), 400
        pipeline_logger.info("done duration_ms=%.0f", 0.0, extra={'request_id': request_id, 'stage': 'MATRIX_API'})
        return jsonify({
            'success': True,
            'row_field': row_field,
            'col_mode': col_mode,
            'analysis_type': analysis_type,
            'all_employees': True,
            'employee_results': results,
            'output_mode': 'real' if enrich else 'pseudonym',
        })

    result = generate_perspective_matrix(unified, employee_id, row_field, col_mode, analysis_type, options, request_id=request_id)
    if result is None:
        pipeline_logger.info("done duration_ms=%.0f", 0.0, extra={'request_id': request_id, 'stage': 'MATRIX_API'})
        return jsonify({
            'success': False,
            'error': f"'{employee_id}' 직원의 조건에 맞는 평가가 없습니다."
        }), 400

    pipeline_logger.info("done duration_ms=%.0f", 0.0, extra={'request_id': request_id, 'stage': 'MATRIX_API'})
    return jsonify({
        'success': True,
        'output_mode': 'real' if enrich else 'pseudonym',
        **result,
    })


@perspective_bp.route('/matrix/save-deploy', methods=['POST'])
def api_save_deploy():
    request_id = _gen_request_id()
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
    pipeline_logger.info("employee_id=%s output_mode=%s", _mask_real_id(str(employee_id)) if employee_id else '', output_mode, extra={'request_id': request_id, 'stage': 'API_ENTRY'})

    options = {
        'wordcloud_pos': data.get('wordcloud_pos', ['Noun']),
        'background_color': data.get('background_color', 'white'),
        'width': data.get('width', 800),
        'height': data.get('height', 600),
        'max_words': data.get('max_words', 100),
        'remove_profanity': data.get('remove_profanity', False),
        'row_values': data.get('row_values'),
        'row_combine_all': data.get('row_combine_all', False),

        'analysis_types': data.get('analysis_types'),
        'output_mode': output_mode,
        'include_name': data.get('include_name', True),
        'include_id': data.get('include_id', True),
        'apply_emotion_colors': data.get('apply_emotion_colors', True),
        'word_color': data.get('word_color'),
        'batch_title': (data.get('batch_title') or '').strip() or None,
    }

    _setup_korean_font()  # 배치/단일 분기 진입 전 1회 호출(save_to_deploy 내부 호출 대체)

    # 0619_02: 전체 코퍼스 일괄 적재(load_all_batches) 제거 → 직원 1명분만 로딩하여 메모리 폭증 방지.
    if all_employees and not employee_ids:
        employee_ids = list_all_employee_ids()

    if employee_ids:
        results_list = []
        for eid in employee_ids:
            emp_unified = load_employee_batch(eid)
            result = save_to_deploy(emp_unified, eid, row_field, col_mode, analysis_type, options, request, request_id=request_id)
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

    emp_unified = load_employee_batch(employee_id)
    results = save_to_deploy(emp_unified, employee_id, row_field, col_mode, analysis_type, options, request, request_id=request_id)
    if not results:
        pipeline_logger.warning("deploy_failed employee_id=%s duration_ms=%.0f", _mask_real_id(str(employee_id)) if employee_id else '', 0.0, extra={'request_id': request_id, 'stage': 'API_ENTRY'})
        return jsonify({
            'success': False,
            'error': f"'{employee_id}' 직원의 조건에 맞는 평가가 없습니다."
        }), 400

    pipeline_logger.info("deploy_done success=True duration_ms=%.0f", 0.0, extra={'request_id': request_id, 'stage': 'API_ENTRY'})

    log_action('matrix_save_deploy', {
        'employee_id': employee_id,
        'row_field': row_field,
        'col_mode': col_mode,
        'analysis_type': analysis_type,
        'paths': {k: v for k, v in results.items() if k not in ('name', 'timestamp')},
        'name': results.get('name'),
    }, request)

    pipeline_logger.info("response success=True status=200", extra={'request_id': request_id, 'stage': 'API_ENTRY'})
    return jsonify({'success': True, **results})


@perspective_bp.route('/sentence-corrections/by-employee/<employee_id>', methods=['GET'])
def api_get_sentence_corrections(employee_id):
    """해당 직원의 문장 수정 내역을 조회."""
    try:
        corrections_map = _load_corrections_map(employee_id)
        return jsonify({'success': True, 'corrections': corrections_map})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@perspective_bp.route('/sentence-corrections/save', methods=['POST'])
def api_save_sentence_corrections():
    """문장 수정 내역을 DB에 저장."""
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    corrections = data.get('corrections', {})

    if not corrections:
        return jsonify({'success': True, 'saved': 0})

    from src.services.deploy_session_service import _get_conn
    conn = _get_conn()
    saved_count = 0
    try:
        # corrections는 {db_id(str): {sentence_index(str): sentiment}} 형태.
        # evaluation_id는 중복될 수 있어 고유한 DB row id로 매칭한다.
        for db_id, sent_corrections in corrections.items():
            try:
                db_id_int = int(db_id)
            except (ValueError, TypeError):
                _logger.warning(f"[corrections/save] 잘못된 db_id={db_id!r} 건너뜀")
                continue
            # 기존 corrections 로드 후 병합 (새 값 우선, 없던 인덱스 보존)
            existing_row = conn.execute(
                "SELECT sentiment_corrections FROM evaluations WHERE id = ?",
                (db_id_int,)
            ).fetchone()
            existing_corr = {}
            if existing_row and existing_row[0]:
                try:
                    existing_corr = json_lib.loads(existing_row[0])
                    if not isinstance(existing_corr, dict):
                        existing_corr = {}
                except (json_lib.JSONDecodeError, TypeError):
                    existing_corr = {}
            merged = {**existing_corr, **sent_corrections}
            corrections_json = json_lib.dumps(merged, ensure_ascii=False)
            cursor = conn.execute(
                "UPDATE evaluations SET sentiment_corrections = ? WHERE id = ?",
                (corrections_json, db_id_int)
            )
            rows_affected = cursor.rowcount
            saved_count += rows_affected
            _logger.info(f"[corrections/save] db_id={db_id_int} rows={rows_affected} merged={merged}")
        conn.commit()
        _logger.info(f"[corrections/save] 완료: {saved_count}행 저장")
        return jsonify({'success': True, 'saved': saved_count})
    except Exception as e:
        _logger.error(f"[corrections/save] 오류: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@perspective_bp.route('/judgment/extract', methods=['POST'])
def api_judgment_extract():
    """판정 작업 패킷 추출 — 가명 평가에서 하드케이스를 뽑아 자기설명 패킷(JSON) 다운로드.

    body: {batch_id?, margin?}. 패킷은 가명(실 ID 없음)이라 그대로 LLM 전달 가능.
    """
    import logging as _logging
    from flask import Response
    _logger = _logging.getLogger(__name__)
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    batch_id = data.get('batch_id') or None
    # margin 미지정 시 None → 가장 넓은 밴드로 추출 + 마진 밴드 요약(검색형). 지정 시 그 값만.
    margin = None
    if data.get('margin') is not None:
        try:
            margin = float(data.get('margin'))
        except (TypeError, ValueError):
            margin = None
    try:
        from src.services.judgment_packet_service import build_judgment_packet
        packet, quarantined = build_judgment_packet(batch_id=batch_id, margin=margin)
        packet['_status']['counts']['quarantined'] = len(quarantined)
        _logger.info(f"[judgment/extract] batch={batch_id} items={len(packet['items'])} "
                     f"quarantined={len(quarantined)}")
        body = json_lib.dumps(packet, ensure_ascii=False, indent=1)
        return Response(
            body, mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename="{packet["packet_id"]}.json"'})
    except Exception as e:
        _logger.error(f"[judgment/extract] 오류: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@perspective_bp.route('/judgment/apply', methods=['POST'])
def api_judgment_apply():
    """판정 패킷 반영 — status==3(확정) item 만 corrections 에 in-place 반영(status 기반).

    입력: 파일 업로드(request.files['packet']) | JSON body 패킷 | body {file:<서버 패킷 상대경로>}.
    업로드/본문 패킷은 서버(eval/judgment/**)에 저장해, status==2 남은 항목을 그룹검토 게시판이
    이어서 판정할 수 있게 한다(재적용은 {file} 로 서버 패킷 지정).
    """
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    from src.services.judgment_packet_service import (
        apply_judgment_packet, save_packet_file, load_packet)
    body = request.get_json(silent=True) if not request.files else None
    packet, packet_file = None, None
    # 1) 서버 저장 패킷 재적용
    if body and body.get('file'):
        path = _safe_packet_path(body.get('file'))
        if not path:
            return jsonify({'success': False, 'error': '허용되지 않은 파일'}), 400
        try:
            packet = load_packet(path)
        except Exception as e:
            return jsonify({'success': False, 'error': f'패킷 로드 실패: {e}'}), 400
        packet_file = os.path.relpath(path, _EVAL_DIR).replace('\\', '/')
    else:
        # 2) 업로드 파일 또는 JSON 본문 패킷
        if 'packet' in request.files:
            try:
                packet = json_lib.loads(request.files['packet'].read().decode('utf-8'))
            except Exception as e:
                return jsonify({'success': False, 'error': f'패킷 파싱 실패: {e}'}), 400
        else:
            packet = body
        if not isinstance(packet, dict) or 'items' not in packet:
            return jsonify({'success': False, 'error': '유효한 패킷이 아닙니다(items 필요).'}), 400
        # 서버 저장(게시판 접근용) — 실패해도 반영은 진행
        try:
            src = packet.get('source') or {}
            label = src.get('judgment_label') or 'uploaded'
            batch_id = src.get('batch_id') or packet.get('packet_id') or 'packet'
            path = save_packet_file(packet, label, batch_id)
            packet_file = os.path.relpath(path, _EVAL_DIR).replace('\\', '/')
        except Exception as e:
            _logger.warning(f"[judgment/apply] 패킷 서버 저장 실패: {e}")
    try:
        summary = apply_judgment_packet(packet)
        _logger.info(f"[judgment/apply] inserted={summary['inserted_sentences']} "
                     f"pending_human={summary['pending_human']} pending_ai={summary['pending_ai']} "
                     f"skipped={summary['skipped']} file={packet_file}")
        return jsonify({'success': True, 'summary': summary, 'packet_file': packet_file})
    except Exception as e:
        _logger.error(f"[judgment/apply] 오류: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@perspective_bp.route('/judgment/packets', methods=['GET'])
def api_judgment_packets():
    """서버 저장 판정 패킷 목록(+status 분포) — 판정반영 페이지 재적용 드롭다운용."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    from src.services.judgment_packet_service import load_packet, resolve_item
    out = []
    if os.path.isdir(_JUDGMENT_DIR):
        for dirpath, _dirs, files in os.walk(_JUDGMENT_DIR):
            for nm in sorted(files):
                if not nm.endswith('.json'):
                    continue
                p = os.path.join(dirpath, nm)
                counts = {}
                try:
                    for it in load_packet(p).get('items', []):
                        st, _lbl = resolve_item(it)
                        counts[st] = counts.get(st, 0) + 1
                except (OSError, ValueError):
                    continue
                out.append({
                    'name': os.path.relpath(p, _EVAL_DIR).replace('\\', '/'),
                    'pending_ai': counts.get(1, 0),        # AI 판정 대기
                    'pending_human': counts.get(2, 0),     # 사람 판정 대기
                    'ai_ready': counts.get(3, 0),          # AI 작업완료(DB 반영 대기)
                    'human_ready': counts.get(4, 0),       # Human 작업완료(DB 반영 대기)
                    'ai_applied': counts.get(10, 0),       # AI DB 반영 완료
                    'human_applied': counts.get(11, 0),    # Human DB 반영 완료
                    'confirmed': counts.get(3, 0) + counts.get(4, 0),  # 하위호환(작업완료 합)
                })
    return jsonify({'success': True, 'packets': out})


@perspective_bp.route('/judgment/apply-db', methods=['POST'])
def api_judgment_apply_db():
    """"DB에 반영" 버튼 — 작업 완료분을 DB 반영하고 status 전이(3→10, 4→11).

    body: {file:<서버 패킷 상대경로>, target?: 'ai'|'human'|'all'}.
      judgment_apply 버튼 → target='ai'(3만), group_review 버튼 → target='human'(4만).
    반영 후 패킷을 같은 경로에 in-place 저장. AI 반영(10) 직후 사람 이관분(2)이 남아
    Human 반영(11)이 아직 없으면 그룹검토로 유도하도록 redirect_to_group_review=True.
    """
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    from src.services.judgment_packet_service import (
        load_packet, apply_db_to_packet, resolve_item)
    data = request.get_json(silent=True) or {}
    path = _safe_packet_path(data.get('file'))
    if not path:
        return jsonify({'success': False, 'error': '허용되지 않은 파일'}), 400
    target = data.get('target') or 'all'
    if target not in ('ai', 'human', 'all'):
        target = 'all'
    try:
        packet = load_packet(path)
    except Exception as e:
        return jsonify({'success': False, 'error': f'패킷 로드 실패: {e}'}), 400
    try:
        result = apply_db_to_packet(packet, target=target)
        with open(path, 'w', encoding='utf-8') as f:
            json_lib.dump(result['packet'], f, ensure_ascii=False, indent=1)
        items = result['packet'].get('items', [])
        has_ai_applied = any(resolve_item(it)[0] == 10 for it in items)     # AI DB 반영 완료
        has_human_applied = any(resolve_item(it)[0] == 11 for it in items)  # Human DB 반영 완료
        has_human_pending = any(resolve_item(it)[0] == 2 for it in items)   # 사람 이관분 잔존
        need_human = has_ai_applied and (not has_human_applied) and has_human_pending
        summary = {'applied_ai': result['applied_ai'], 'applied_human': result['applied_human'],
                   'skipped': result['skipped']}
        _logger.info(f"[judgment/apply-db] target={target} applied_ai={summary['applied_ai']} "
                     f"applied_human={summary['applied_human']} skipped={summary['skipped']} "
                     f"need_human={need_human} file={data.get('file')}")
        return jsonify({'success': True, 'summary': summary,
                        'redirect_to_group_review': need_human})
    except Exception as e:
        _logger.error(f"[judgment/apply-db] 오류: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@perspective_bp.route('/matrix/regenerate', methods=['POST'])
def api_regenerate_matrix():
    """수정된 감정으로 해당 직원의 매트릭스 + 워드클라우드 재생성."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    employee_id = data.get('employee_id')
    if not employee_id:
        return jsonify({'success': False, 'error': 'employee_id가 필요합니다.'}), 400

    row_field = data.get('row_field', 'evaluation_date__year')
    col_mode = data.get('col_mode', 'all')
    analysis_type = data.get('analysis_type', 'nlp')

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

        'analysis_types': data.get('analysis_types'),
        'word_color': data.get('word_color'),
        'batch_title': (data.get('batch_title') or '').strip() or None,
    }

    # 재생성은 항상 단일 직원 대상 — 선택 1명분만 적재(0714).
    unified = load_employee_batch(employee_id)
    if not unified:
        return jsonify({'success': False, 'error': '처리된 배치 데이터가 없습니다.'}), 404

    try:
        corrections_map = _load_corrections_map(employee_id)
        result = generate_perspective_matrix(
            unified, employee_id, row_field, col_mode, analysis_type, options,
            corrections_map=corrections_map
        )
        if result is None:
            return jsonify({
                'success': False,
                'error': f"'{employee_id}' 직원의 조건에 맞는 평가가 없습니다."
            }), 400
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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

        'analysis_types': data.get('analysis_types'),
        'output_mode': output_mode,
        'include_name': data.get('include_name', True),
        'include_id': data.get('include_id', True),
        'apply_emotion_colors': data.get('apply_emotion_colors', True),
        'word_color': data.get('word_color'),
        'batch_title': (data.get('batch_title') or '').strip() or None,
    }

    # 0619_02: 전체 코퍼스 일괄 적재 제거 → all_employees는 ID만 경량 조회, 워커가 직원 1명분만 로딩.
    if all_employees and not employee_ids:
        employee_ids = list_all_employee_ids()

    ids = employee_ids if employee_ids else [employee_id]

    def generate():
        success_list = []
        fail_list = []
        total = len(ids)

        _setup_korean_font()  # 워커 진입 전 1회 호출(작업4 — save_to_deploy 내부 호출 대체)
        num_workers = min(multiprocessing.cpu_count(), 8)  # 매트릭스 경로와 동일 관례, GPU 미사용 CPU/IO 워크로드
        completed = 0

        def _work(eid):
            # request는 save_to_deploy 본문에서 미사용(죽은 파라미터) + 워커 스레드엔 Flask 요청 컨텍스트 없음 → None 전달
            # 0619_02: 직원 1명분만 로딩(전체 적재 제거). emp_unified는 _work 종료 시 회수.
            emp_unified = load_employee_batch(eid)
            result = save_to_deploy(emp_unified, eid, row_field, col_mode, analysis_type, options, None)
            if result is not None:
                result['profanity_summary'] = build_profanity_summary(emp_unified, eid)
            return result

        with ThreadPoolExecutor(max_workers=num_workers) as ex:
            futures = {ex.submit(_work, eid): eid for eid in ids}
            for fut in as_completed(futures):
                eid = futures[fut]
                completed += 1
                try:
                    result = fut.result()
                    if result:
                        real_name = result.get('name', eid)
                        result['employee_id'] = eid
                        success_list.append(result)
                        yield json_lib.dumps({'employee': eid, 'name': real_name, 'status': 'done', 'result': result, 'current': completed, 'total': total}) + '\n'
                    else:
                        fail_list.append({'employee_id': eid, 'error': '평가 데이터 없음'})
                        yield json_lib.dumps({'employee': eid, 'status': 'fail', 'error': '평가 데이터 없음', 'current': completed, 'total': total}) + '\n'
                except Exception as exc:
                    fail_list.append({'employee_id': eid, 'error': str(exc)})
                    yield json_lib.dumps({'employee': eid, 'status': 'fail', 'error': str(exc), 'current': completed, 'total': total}) + '\n'

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
    # 직원 명부 + 배치별 카운트만 필요 — 평가 본문 미적재 SQL 집계(0714).
    result = list_users_with_batch_counts()
    return jsonify({'success': True, 'users': result, 'total_users': len(result)})


@perspective_bp.route('/batches', methods=['GET'])
def api_batch_history():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    # 0619_03: 이력은 목록·카운트만 필요하므로 전체 적재(load_all_batches) 대신
    # 경량 로더 사용 — 1.7만명 평가 본문 미적재로 조회 지연/메모리 폭증 해소.
    unified = load_batch_history()
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
    from src.services.batch_work_order_service import (
        get_work_order_by_batch_id, delete_work_order,
    )

    # 0. 작업서 레지스트리 존재 여부 (평가 중복 제거로 evaluations 행이 0건일 수 있음)
    work_order = get_work_order_by_batch_id(batch_id)

    # 1. Remove batch data from DB
    removed_count = remove_batch_from_all(batch_id, [])
    if removed_count == 0 and work_order is None:
        return jsonify({'success': False, 'error': f'배치({batch_id})를 찾을 수 없습니다.'}), 404

    # 2. 작업서 레지스트리 정리 (이력은 작업서 기준으로 출력되므로 함께 삭제)
    delete_work_order(batch_id)

    # 3. Remove physical batch directory (if exists)
    import shutil
    batch_dir = os.path.join(PROCESSED_DATA_DIR_PATH, 'batch', batch_id)
    if os.path.isdir(batch_dir):
        try:
            shutil.rmtree(batch_dir)
        except Exception:
            pass

    log_action('batch_delete', {
        'batch_id': batch_id, 'path': batch_dir,
        'removed_evaluations': removed_count,
    }, request)
    return jsonify({'success': True, 'message': f'배치 {batch_id} 삭제 완료 ({removed_count}건 평가 제거)'})


@perspective_bp.route('/batch/<batch_id>/display-name', methods=['PATCH'])
def api_batch_update_display_name(batch_id):
    """배치 명칭(display_name) 수정"""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    data = request.get_json(silent=True) or {}
    display_name = (data.get('display_name') or '').strip()

    from src.config.settings import PROCESSED_DATA_DIR_PATH
    summary_path = os.path.join(PROCESSED_DATA_DIR_PATH, 'batch', batch_id, 'tdata', 'batch_summary.json')

    try:
        if os.path.exists(summary_path):
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary = json_lib.load(f)
        else:
            os.makedirs(os.path.dirname(summary_path), exist_ok=True)
            summary = {'batch_info': {'batch_id': batch_id}}

        if 'batch_info' not in summary:
            summary['batch_info'] = {}
        summary['batch_info']['display_name'] = display_name

        with open(summary_path, 'w', encoding='utf-8') as f:
            json_lib.dump(summary, f, ensure_ascii=False, indent=2)

        log_action('batch_display_name_update', {
            'batch_id': batch_id,
            'display_name': display_name,
        }, request)

        return jsonify({'success': True, 'display_name': display_name})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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

    def analyze_one(sent_text, is_last=False, total=1, item_expected=None):
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
                res = analyze_one(sent, is_last, total, expected)
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
        res = analyze_one(sent, is_last, total)
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
    from src.services import gallery_db_service

    fetch_all = request.args.get('all', '0') == '1'
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 200)
    employee_id = request.args.get('employee_id', '').strip() or None
    output_mode = request.args.get('output_mode', '').strip() or None
    source = request.args.get('source', '').strip() or None
    date_from = request.args.get('date_from', '').strip() or None
    date_to = request.args.get('date_to', '').strip() or None
    dates_str = request.args.get('dates', '').strip()
    dates = set(d.strip() for d in dates_str.split(',') if d.strip()) if dates_str else None
    batch_title_filter = request.args.get('batch_title', '').strip() or None
    batch_titles = {batch_title_filter} if batch_title_filter else None

    result = gallery_db_service.list_entries(
        page=page, per_page=per_page, fetch_all=fetch_all,
        employee_id=employee_id, source=source,
        output_mode=output_mode, date_from=date_from, date_to=date_to,
        dates=dates, batch_titles=batch_titles,
        is_admin=_is_admin(),
    )

    return jsonify({
        'success': True,
        'total': result['total'],
        'page': page,
        'per_page': per_page,
        'entries': result['entries'],
    })


@perspective_bp.route('/deploy-gallery/detail/<entry_id>', methods=['GET'])
def api_deploy_gallery_detail(entry_id):
    """Get detailed information for a single gallery entry."""
    from src.services import gallery_db_service

    entry = gallery_db_service.get_entry(entry_id)
    if not entry:
        return jsonify({'success': False, 'error': 'Entry not found'}), 404

    if not _is_admin() and entry.get('output_mode') == 'real':
        return jsonify({'success': False, 'error': '접근 권한이 없습니다.'}), 403

    return jsonify({'success': True, 'entry': entry})


@perspective_bp.route('/deploy-gallery/employee-entries/<employee_id>', methods=['GET'])
def api_employee_entries(employee_id):
    """같은 직원의 deploy/matrix 양쪽 최신 entry를 반환."""
    from src.services import gallery_db_service

    is_admin = _is_admin()
    result = gallery_db_service.list_entries(
        per_page=1000, employee_id=employee_id, is_admin=is_admin
    )

    latest_id = {'deploy': None, 'matrix': None}
    latest_ts = {'deploy': '', 'matrix': ''}
    for e in result['entries']:
        src = e.get('source', 'deploy')
        if src not in latest_id:
            continue
        ts = e.get('timestamp', '')
        if ts > latest_ts[src]:
            latest_ts[src] = ts
            latest_id[src] = e['id']

    deploy = gallery_db_service.get_entry(latest_id['deploy']) if latest_id['deploy'] else None
    matrix = gallery_db_service.get_entry(latest_id['matrix']) if latest_id['matrix'] else None

    return jsonify({
        'success': True,
        'employee_id': employee_id,
        'deploy': deploy,
        'matrix': matrix,
    })


@perspective_bp.route('/deploy-gallery/dates', methods=['GET'])
def api_deploy_gallery_dates():
    """갤러리 항목에 존재하는 날짜(YYYYMMDD) 목록 반환."""
    from src.services import gallery_db_service
    dates = gallery_db_service.get_distinct_dates(is_admin=_is_admin())
    return jsonify({'success': True, 'dates': sorted(dates, reverse=True)})


@perspective_bp.route('/deploy-gallery/batch-titles', methods=['GET'])
def api_deploy_gallery_batch_titles():
    """갤러리 항목에 존재하는 배치 명칭 목록 반환."""
    from src.services import gallery_db_service
    titles = gallery_db_service.get_distinct_batch_titles(is_admin=_is_admin())
    return jsonify({'success': True, 'batch_titles': titles})


@perspective_bp.route('/deploy-gallery/entries', methods=['DELETE'])
def api_deploy_gallery_delete():
    """갤러리 항목 삭제 (관리자 전용)."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    from src.services import gallery_db_service
    data = request.get_json(silent=True) or {}
    entry_ids = list(set(data.get('entry_ids', [])))
    if not entry_ids:
        return jsonify({'success': False, 'error': 'entry_ids가 필요합니다.'}), 400

    result = gallery_db_service.delete_entries(entry_ids)
    log_action('gallery_delete', {'entry_ids': entry_ids, 'deleted_count': result['deleted_count']}, request)
    return jsonify({'success': True, 'deleted_count': result['deleted_count']})


@perspective_bp.route('/deploy-gallery/download', methods=['POST'])
def api_deploy_gallery_download():
    """갤러리 선택 항목 이미지 ZIP 다운로드."""
    from datetime import datetime as _dt
    data = request.get_json(silent=True) or {}
    entry_ids = data.get('entry_ids', [])
    folder_mode = data.get('folder_mode', 'flat')  # 'flat' | 'by_type'
    if not entry_ids:
        return jsonify({'success': False, 'error': 'entry_ids가 필요합니다.'}), 400

    try:
        from src.services import gallery_db_service
        is_admin = _is_admin()
        selected = gallery_db_service.get_entries_by_ids(entry_ids, is_admin=is_admin)

        if not selected:
            return jsonify({'success': False, 'error': '다운로드할 항목이 없습니다.'}), 404

        # 이미지 수집
        file_items = []  # [(abs_path, arc_name)]
        for entry in selected:
            emp_id = entry.get('employee_id', 'unknown')
            images = entry.get('images', {})
            row_results = entry.get('row_results', {})

            # 최상위 images
            for img_type, url in images.items():
                if not url:
                    continue
                abs_path = _url_to_abs_path(url)
                if abs_path and os.path.exists(abs_path):
                    arc_name = _build_arc_name(folder_mode, emp_id, None, img_type, abs_path)
                    file_items.append((abs_path, arc_name))

            # row_results (연도별)
            for year, row_data in row_results.items():
                if not isinstance(row_data, dict):
                    continue
                for img_type, url in row_data.items():
                    if not url:
                        continue
                    abs_path = _url_to_abs_path(url)
                    if abs_path and os.path.exists(abs_path):
                        arc_name = _build_arc_name(folder_mode, emp_id, year, img_type, abs_path)
                        file_items.append((abs_path, arc_name))

        if not file_items:
            return jsonify({'success': False, 'error': '다운로드할 이미지 파일이 없습니다.'}), 404

        # ZIP 생성 — Windows: NamedTemporaryFile 핸들을 먼저 닫아야 같은 이름으로 재오픈 가능
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        tmp_name = tmp.name
        tmp.close()
        with zipfile.ZipFile(tmp_name, 'w', zipfile.ZIP_DEFLATED) as zf:
            for abs_path, arc_name in file_items:
                zf.write(abs_path, arc_name)

        return send_file(tmp_name, mimetype='application/zip',
                         as_attachment=True,
                         download_name=f'gallery_{_dt.now().strftime("%Y%m%d_%H%M%S")}.zip')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _url_to_abs_path(url):
    """URL/경로 문자열을 실제 파일 절대 경로로 변환."""
    if not url:
        return None
    clean = url.split('?')[0].lstrip('/')
    if clean.startswith('outputs/'):
        clean = clean[8:]
    return os.path.join(OUTPUTS_DIR_PATH, clean) if OUTPUTS_DIR_PATH else None


def _build_arc_name(folder_mode, emp_id, year, img_type, abs_path):
    """ZIP 내부 파일 경로 생성."""
    base_name = os.path.basename(abs_path)
    ext = base_name.rsplit('.', 1)[1] if '.' in base_name else 'png'
    if folder_mode == 'by_type':
        type_folder = {'combined': 'combined', 'positive': 'positive', 'negative': 'negative'}.get(img_type, 'other')
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', f"{emp_id}{'_' + year if year else ''}")
        return f"{type_folder}/{safe_name}.{ext}"
    # flat: 직원ID_연도_통합.png
    type_ko = {'combined': '통합', 'positive': '긍정', 'negative': '부정'}.get(img_type, img_type)
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', f"{emp_id}{'_' + year if year else ''}_{type_ko}")
    return f"{safe_name}.{ext}"


@perspective_bp.route('/deploy-title/check', methods=['POST'])
def api_deploy_title_check():
    """배치 명칭 중복 확인."""
    data = request.get_json(silent=True) or {}
    batch_title = (data.get('batch_title') or '').strip()
    if not batch_title:
        return jsonify({'success': True, 'exists': False, 'count': 0, 'sources': []})

    from src.services import gallery_db_service
    info = gallery_db_service.check_batch_title(batch_title)
    return jsonify({'success': True, **info})


@perspective_bp.route('/acquired-sentences/save', methods=['POST'])
def api_acquired_sentences_save():
    """문장을 코퍼스(corpus)에 저장."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    required = ['sentence_text', 'user_label', 'model_label']
    for field in required:
        if not data.get(field):
            return jsonify({'success': False, 'error': f'{field}가 필요합니다.'}), 400
    ok = save_acquired_sentence(data)
    return jsonify({'success': ok})


@perspective_bp.route('/acquired-sentences/list', methods=['GET'])
def api_acquired_sentences_list():
    """저장된 문장 목록 조회 (페이지네이션 + 필터)."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    mismatch_only = request.args.get('mismatch_only', '0') == '1'
    label = request.args.get('label', '').strip() or None
    date_from = request.args.get('date_from', '').strip() or None
    date_to = request.args.get('date_to', '').strip() or None
    result = list_acquired_sentences(
        page=page, per_page=per_page,
        mismatch_only=mismatch_only, label=label,
        date_from=date_from, date_to=date_to,
    )
    return jsonify({'success': True, **result})


@perspective_bp.route('/acquired-sentences/<int:sentence_id>', methods=['DELETE'])
def api_acquired_sentences_delete(sentence_id):
    """단건 삭제."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    ok = delete_acquired_sentence(sentence_id)
    return jsonify({'success': ok})


@perspective_bp.route('/acquired-sentences/delete-bulk', methods=['POST'])
def api_acquired_sentences_delete_bulk():
    """선택한 id 목록 일괄 삭제."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'error': '삭제할 항목을 선택하세요.'}), 400
    deleted = delete_acquired_sentences_bulk(ids)
    return jsonify({'success': True, 'deleted': deleted})


@perspective_bp.route('/acquired-sentences/delete-all', methods=['POST'])
def api_acquired_sentences_delete_all():
    """현재 필터(불일치/라벨/기간)에 해당하는 전체 삭제. 필터 없으면 전체."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    mismatch_only = bool(data.get('mismatch_only', False))
    label = (data.get('label') or '').strip() or None
    date_from = (data.get('date_from') or '').strip() or None
    date_to = (data.get('date_to') or '').strip() or None
    deleted = delete_acquired_sentences_filtered(
        mismatch_only=mismatch_only, label=label,
        date_from=date_from, date_to=date_to,
    )
    return jsonify({'success': True, 'deleted': deleted})


@perspective_bp.route('/acquired-sentences/analyze', methods=['POST'])
def api_acquired_sentences_analyze():
    """선택 문장 분석 실행."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    analysis_types = data.get('analysis_types', ['emotion', 'profanity', 'sarcasm'])
    if not ids:
        return jsonify({'success': False, 'error': 'ids가 필요합니다.'}), 400
    results = analyze_acquired_sentences(ids, analysis_types)
    return jsonify({'success': True, 'results': results})


@perspective_bp.route('/acquired-sentences/export', methods=['GET'])
def api_acquired_sentences_export():
    """CSV보내기."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    mismatch_only = request.args.get('mismatch_only', '0') == '1'
    csv_content = export_acquired_sentences_csv(mismatch_only=mismatch_only)
    from datetime import datetime as _dt
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=acquired_sentences_{_dt.now().strftime("%Y%m%d")}.csv'},
    )


@perspective_bp.route('/acquired-sentences/export-refined', methods=['GET'])
def api_acquired_sentences_export_refined():
    """정제(KoTE 재계산 + 규칙 재현) CSV 내보내기 — 규칙 마이닝용 데이터셋."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    mismatch_only = request.args.get('mismatch_only', '0') == '1'
    csv_content = export_acquired_sentences_refined_csv(mismatch_only=mismatch_only)
    from datetime import datetime as _dt
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=acquired_sentences_refined_{_dt.now().strftime("%Y%m%d")}.csv'},
    )


@perspective_bp.route('/acquired-sentences/import', methods=['POST'])
def api_acquired_sentences_import():
    """기본/정제 CSV 업로드 → acquired_sentences 적재 (dev 검증용 데이터 반입)."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'success': False, 'error': '업로드할 CSV 파일을 선택하세요.'}), 400
    overwrite = request.form.get('overwrite', '0') == '1'
    try:
        raw = file.read()
        try:
            csv_text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            csv_text = raw.decode('cp949', errors='replace')
        result = import_acquired_sentences_csv(csv_text, overwrite=overwrite)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@perspective_bp.route('/acquired-sentences/save-bulk', methods=['POST'])
def api_acquired_sentences_save_bulk():
    """집단 분석/제출용 배포 결과 문장(긍/부/중/욕)을 acquired_sentences에 일괄 적재."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    items = data.get('items')
    if not items or not isinstance(items, list):
        return jsonify({'success': False, 'error': '이동할 문장이 없습니다.'}), 400
    overwrite = bool(data.get('overwrite', False))
    try:
        result = save_acquired_sentences_bulk(items, overwrite=overwrite)
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@perspective_bp.route('/profanity-list', methods=['GET'])
def api_profanity_list():
    """전사 욕설 리스트 조회."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    search = request.args.get('search', '')
    department = request.args.get('department', '')
    min_count = request.args.get('min_count', 1, type=int)
    sort = request.args.get('sort', 'count')
    order = request.args.get('order', 'desc')
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)

    from src.services.perspective_service import build_all_profanity_summary
    result = build_all_profanity_summary(
        search=search or None,
        department=department or None,
        min_count=min_count,
        sort=sort,
        order=order,
        page=page,
        limit=limit,
    )
    return jsonify({'success': True, **result})


@perspective_bp.route('/profanity-list/csv', methods=['GET'])
def api_profanity_list_csv():
    """전사 욕설 리스트 CSV 다운로드."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    search = request.args.get('search', '')
    department = request.args.get('department', '')
    min_count = request.args.get('min_count', 1, type=int)
    sort = request.args.get('sort', 'count')
    order = request.args.get('order', 'desc')

    from src.services.perspective_service import build_all_profanity_summary
    result = build_all_profanity_summary(
        search=search or None,
        department=department or None,
        min_count=min_count,
        sort=sort,
        order=order,
        page=1,
        limit=10000,  # CSV는 전체
        include_sentences=True,
    )

    import csv
    import io
    from datetime import datetime as _dt

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['사번', '이름', '부서', '총평가수', '욕설건수', '비율', '감지단어', '문장목록'])

    for item in result.get('items', []):
        sentences = []
        for s in item.get('profanity_sentences', []):
            sentences.append(s.get('original_text', ''))
        writer.writerow([
            item['employee_id'],
            item['name'],
            item['department'],
            item['total_evaluations'],
            item['profanity_count'],
            f"{item['profanity_ratio']:.2%}",
            ', '.join(item.get('profanity_words', [])),
            ' | '.join(sentences),
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=profanity_list_{_dt.now().strftime("%Y%m%d")}.csv'},
    )


@perspective_bp.route('/profanity-list/sentences/<employee_id>', methods=['GET'])
def api_profanity_list_sentences(employee_id):
    """특정 직원의 욕설 문장 조회."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    from src.services.profanity_db_service import get_profanity_sentences
    sentences = get_profanity_sentences(employee_id)
    return jsonify({'success': True, 'sentences': sentences})


@perspective_bp.route('/profanity-list/departments', methods=['GET'])
def api_profanity_list_departments():
    """욕설 데이터가 있는 부서 목록."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401

    from src.services.profanity_db_service import get_distinct_departments
    departments = get_distinct_departments()
    return jsonify({'success': True, 'departments': departments})


# ── 신규 그룹 gold 검토 도구(0624_05) — eval/*.jsonl 사람 판정. 데이터 추가 시 재사용. ──
_EVAL_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'plans', '_datasets', 'kote_finetune', 'eval'))
# 현재 검토 대상 파일만 모으는 전용 폴더 — 게시판은 이것만 나열한다(벤치마크·gold·학습·소스 등
#   파이프라인 데이터 파일은 eval/ 최상위에 그대로 두어 스크립트 경로 불변). 0703 그룹재편성.
_REVIEW_DIR = os.path.join(_EVAL_DIR, 'review')


def _safe_eval_path(name):
    """basename 화이트리스트 + .jsonl만 + review/ 우선·eval/ 최상위 고정(traversal 차단)."""
    base = os.path.basename(name or '')
    if not base.endswith('.jsonl'):
        return None
    for root in (_REVIEW_DIR, _EVAL_DIR):                 # review/ 우선, 없으면 eval/ 최상위
        path = os.path.abspath(os.path.join(root, base))
        if os.path.dirname(path) == os.path.abspath(root) and os.path.isfile(path):
            return path
    return None


# 판정 패킷 루트(eval/judgment/**/*.json) — 게시판이 패킷을 직접 로드/저장(0701_03 v2).
_JUDGMENT_DIR = os.path.join(_EVAL_DIR, 'judgment')


def _safe_packet_path(name):
    """eval/judgment/** 하위 .json 화이트리스트(traversal 차단). name 은 eval 기준 상대경로."""
    rel = (name or '').replace('\\', '/')
    if not rel.endswith('.json'):
        return None
    path = os.path.abspath(os.path.join(_EVAL_DIR, *[s for s in rel.split('/') if s]))
    jroot = os.path.abspath(_JUDGMENT_DIR)
    if path != jroot and not path.startswith(jroot + os.sep):
        return None
    if not os.path.isfile(path):
        return None
    return path


def _packet_item_to_row(it):
    """패킷 item → 게시판 행(그룹검토 로드 계약과 동일 필드)."""
    return {
        'rec_id': it.get('rec_id'),
        'text': it.get('text'),
        'field': it.get('field'),
        'group': None,
        'cur_rule_label': it.get('cur_rule_label'),
        'ai_reference': it.get('ai_reference'),
        'claude_judgment': it.get('claude_judgment'),
        'decision': it.get('human_decision'),
    }


@perspective_bp.route('/group-review/files', methods=['GET'])
def api_group_review_files():
    """검토 가능한 eval/*.jsonl 목록(+행수)."""
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    files = []
    # 검토 전용 폴더(review/)만 나열 — 없으면 하위호환으로 eval/ 최상위 사용.
    list_dir = _REVIEW_DIR if os.path.isdir(_REVIEW_DIR) else _EVAL_DIR
    if os.path.isdir(list_dir):
        for nm in sorted(os.listdir(list_dir)):
            if nm.endswith('.jsonl'):
                p = os.path.join(list_dir, nm)
                n, decided = 0, 0        # n=전체 행, decided=사람 판정(human_decision/gold) 완료 행
                try:
                    with open(p, encoding='utf-8') as f:
                        for line in f:
                            if not line.strip():
                                continue
                            n += 1
                            try:
                                r = json_lib.loads(line)
                            except ValueError:
                                continue
                            if r.get('human_decision') is not None or r.get('gold') is not None:
                                decided += 1
                except OSError:
                    n, decided = 0, 0
                try:
                    mtime = os.path.getmtime(p)
                except OSError:
                    mtime = 0
                files.append({'name': nm, 'rows': n, 'total': n, 'decided': decided,
                              'mtime': mtime})
    # 판정 패킷(eval/judgment/**/*.json)도 게시판 대상으로 노출 — rows=사람 판정 대기(status==2) 건수
    if os.path.isdir(_JUDGMENT_DIR):
        from src.services.judgment_packet_service import load_packet, resolve_item
        for dirpath, _dirs, names in os.walk(_JUDGMENT_DIR):
            for nm in sorted(names):
                if not nm.endswith('.json'):
                    continue
                p = os.path.join(dirpath, nm)
                try:
                    statuses = [resolve_item(it)[0] for it in load_packet(p).get('items', [])]
                except (OSError, ValueError):
                    continue
                n = sum(1 for s in statuses if s == 2)          # 사람 판정 대기
                human_ready = sum(1 for s in statuses if s == 4)  # Human 작업완료(DB 반영 대기)
                try:
                    mtime = os.path.getmtime(p)
                except OSError:
                    mtime = 0
                files.append({'name': os.path.relpath(p, _EVAL_DIR).replace('\\', '/'),
                              'rows': n, 'human_ready': human_ready,
                              'total': n + human_ready, 'decided': human_ready,
                              'mtime': mtime})
    return jsonify({'success': True, 'files': files})


@perspective_bp.route('/group-review/load', methods=['GET'])
def api_group_review_load():
    """파일 행 로드(text·field·ai_reference·현재 결정). offset/limit 페이징.

    파일이 판정 패킷(.json)이면 items 중 status==2(사람 판정 대기)만 게시판 행으로 매핑.
    """
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    fname = request.args.get('file')
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 200))
    ppath = _safe_packet_path(fname)
    if ppath:                                       # 판정 패킷: status==2 만 노출
        from src.services.judgment_packet_service import load_packet, resolve_item
        pending = [it for it in load_packet(ppath).get('items', [])
                   if resolve_item(it)[0] == 2]
        total = len(pending)
        items = [_packet_item_to_row(it) for it in pending[offset:offset + limit]]
        return jsonify({'success': True, 'total': total, 'offset': offset, 'items': items})
    path = _safe_eval_path(fname)
    if not path:
        return jsonify({'success': False, 'error': '허용되지 않은 파일'}), 400
    items, total = [], 0
    with open(path, encoding='utf-8') as f:
        for i, line in enumerate(f):
            total += 1
            if i < offset or len(items) >= limit:
                continue
            try:
                r = json_lib.loads(line)
            except ValueError:
                continue
            items.append({
                'rec_id': r.get('rec_id'), 'text': r.get('text'),
                'field': r.get('field'), 'group': r.get('group') or r.get('group_weak'),
                'cur_rule_label': r.get('cur_rule_label') or r.get('rule_label_before'),
                'ai_reference': r.get('ai_reference'),
                'claude_judgment': r.get('claude_judgment'),
                'decision': r.get('human_decision') if r.get('human_decision') is not None else r.get('gold'),
                'decision_source': r.get('decision_source'),      # 'human'=사람확정 gold
                'suggested_source': r.get('suggested_source'),    # 'claude_auto'=제 silver 프리필
            })
    return jsonify({'success': True, 'total': total, 'offset': offset, 'items': items})


@perspective_bp.route('/group-review/save', methods=['POST'])
def api_group_review_save():
    """행 결정 저장 — 배치 원자적 기록(검토파일 한정). 단일 또는 다건.

    바디: {file, decisions:[{rec_id, decision}, ...]}  또는 레거시 {file, rec_id, decision}.
    여러 행을 **한 번의 read-modify-write**로 적용(병렬 POST의 lost-update 방지).
    """
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    fname = data.get('file')
    decisions = data.get('decisions')
    if decisions is None:                       # 레거시 단건 호환
        decisions = [{'rec_id': data.get('rec_id'), 'decision': data.get('decision')}]
    valid = ('positive', 'negative', 'neutral', 'not_group', 'skip')
    dmap = {}
    for d in decisions:
        if d.get('decision') not in valid:
            return jsonify({'success': False, 'error': '잘못된 decision'}), 400
        dmap[str(d.get('rec_id'))] = d.get('decision')
    # 판정 패킷(.json): item 의 human_decision 기록·status 전이(위임)
    ppath = _safe_packet_path(fname)
    if ppath:
        from src.services.judgment_packet_service import update_packet_decisions
        saved = update_packet_decisions(
            ppath, [{'rec_id': k, 'decision': v} for k, v in dmap.items()])
        return jsonify({'success': True, 'saved': saved})
    path = _safe_eval_path(fname)
    if not path:
        return jsonify({'success': False, 'error': '허용되지 않은 파일'}), 400
    is_baseline = 'baseline' in os.path.basename(path)
    rows, found = [], 0
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line:
                continue
            try:
                r = json_lib.loads(line)
            except ValueError:
                rows.append(line)
                continue
            dec = dmap.get(str(r.get('rec_id')))
            if dec is not None:
                r['human_decision'] = dec
                r['decision_source'] = 'human'   # 사람 실제 판정 표식(claude_auto 프리필과 구분 → gold 순수성)
                if is_baseline:
                    r['gold'] = None if dec in ('not_group', 'skip') else dec
                found += 1
            rows.append(json_lib.dumps(r, ensure_ascii=False))
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rows) + '\n')
    return jsonify({'success': True, 'saved': found})
