"""Batch processing routes for the WordCloud application."""

from flask import Blueprint, request, jsonify, session
from src.services.batch_service import (
    upload_batch_file,
    start_preprocessing,
    process_batch_integrated_data,
    get_batch_list,
    delete_batch,
    download_batch_results,
    get_sample_integrated_data,
    get_failed_list,
    retry_failed_employees,
    resume_batch_metadata,
    open_folder
)

batch_bp = Blueprint('batch', __name__, url_prefix='/api/batch')


@batch_bp.route('/upload', methods=['POST'])
def upload():
    """Upload batch file or select folder for processing."""
    try:
        result, status = upload_batch_file(request, session)
        return jsonify(result), status
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/preprocess', methods=['POST'])
def preprocess():
    """Start data preprocessing."""
    try:
        data = request.json
        result, status = start_preprocessing(data, session)
        return jsonify(result), status
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/process', methods=['POST'])
def process():
    """Process batch metadata."""
    try:
        data = request.json
        result, status = process_batch_integrated_data(data, session)
        return jsonify(result), status
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/list', methods=['GET'])
def list_batches():
    """Get list of available batches."""
    try:
        batches = get_batch_list()
        return jsonify({'success': True, 'data': batches})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/delete', methods=['POST'])
def delete():
    """Delete a batch.

    DEPRECATED: Use DELETE /api/perspective/batch/<batch_id> for full cleanup.
    This endpoint now cleans up evaluations DB before removing the batch directory.
    """
    try:
        data = request.json
        batch_path = data.get('batch_path')
        if not batch_path:
            return jsonify({'success': False, 'error': '배치 경로가 필요합니다.'}), 400

        result, status = delete_batch(batch_path)
        return jsonify(result), status
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/download', methods=['GET'])
def download():
    """Download batch results."""
    try:
        result = download_batch_results(session)
        if isinstance(result, tuple):
            return jsonify(result[0]), result[1]
        return result
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/sample', methods=['GET'])
def sample():
    """Get sample metadata from batch processing results."""
    try:
        result, status = get_sample_integrated_data(session)
        return jsonify(result), status
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/events', methods=['GET'])
def events():
    """Get batch processing events via SSE."""
    try:
        from src.services.batch_service import get_processing_events
        return get_processing_events()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/failed-list', methods=['GET'])
def failed_list():
    """Get list of failed employees available for retry."""
    try:
        result = get_failed_list()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/skipped/<batch_id>', methods=['GET'])
def skipped(batch_id):
    """배치 중복(미저장) 평가 목록 + 증거값 조회 (모달 오픈 시 on-demand)."""
    try:
        from src.services.batch_service import get_skipped_evaluations
        result = get_skipped_evaluations(batch_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/work-orders', methods=['GET'])
def work_orders():
    """게시판용 배치 작업서 전체 목록."""
    try:
        from src.services.batch_work_order_service import get_all_work_orders
        orders = get_all_work_orders(limit=20)
        return jsonify({'success': True, 'data': orders})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/resume', methods=['POST'])
def resume():
    """작업서 기반으로 중단된 배치를 이어서 처리."""
    try:
        data = request.json or {}
        batch_id = data.get('batch_id')
        if not batch_id:
            return jsonify({'success': False, 'error': 'batch_id가 필요합니다.'}), 400
        result, status = resume_batch_metadata(batch_id, session)
        return jsonify(result), status
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/retry-failed', methods=['POST'])
def retry_failed():
    """Retry failed employee processing."""
    try:
        data = request.json
        result, status = retry_failed_employees(data, session)
        return jsonify(result), status
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@batch_bp.route('/open-folder', methods=['POST'])
def open_folder_route():
    """탐색기로 산출물 폴더 열기 (화이트리스트 검증)."""
    try:
        if not session.get('admin_logged_in', False):
            return jsonify({'success': False, 'error': '관리자 권한이 필요합니다.'}), 403
        data = request.json
        path = data.get('path', '')
        if not path:
            return jsonify({'success': False, 'error': '경로가 필요합니다.'}), 400
        result = open_folder(path)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500