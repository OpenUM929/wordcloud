"""Perspective analysis routes - X/Y matrix group analysis API."""
import os
import json as json_lib
from flask import Blueprint, request, jsonify, session, Response
from src.services.perspective_service import (
    load_all_batches, get_matrix_meta,
    generate_perspective_matrix, save_to_deploy,
    generate_all_employee_matrix, parse_csv_employee_ids,
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

    all_known = set()
    for er in unified.get('employee_results', []):
        meta = er.get('metadata', {})
        eid = meta.get('target_employee_id')
        if eid:
            all_known.add(eid)

    matched = [eid for eid in ids if eid in all_known]
    not_found = [eid for eid in ids if eid not in all_known]

    return jsonify({
        'success': True,
        'total': len(ids),
        'matched': len(matched),
        'matched_ids': matched,
        'not_found': not_found,
    })


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
        'row_values': data.get('row_values'),
        'row_combine_all': data.get('row_combine_all', False),
        'deploy_mode': data.get('deploy_mode', 'combined+individual'),
        'analysis_types': data.get('analysis_types'),
        'output_mode': output_mode,
        'include_name': data.get('include_name', True),
        'include_id': data.get('include_id', True),
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
        'row_values': data.get('row_values'),
        'row_combine_all': data.get('row_combine_all', False),
        'deploy_mode': data.get('deploy_mode', 'combined+individual'),
        'analysis_types': data.get('analysis_types'),
        'output_mode': output_mode,
        'include_name': data.get('include_name', True),
        'include_id': data.get('include_id', True),
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
