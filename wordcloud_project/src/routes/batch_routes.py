"""Batch processing routes for the WordCloud application."""

from flask import Blueprint, request, jsonify, session
from src.services.batch_service import (
    upload_batch_file,
    start_preprocessing,
    process_batch_metadata,
    get_batch_list,
    delete_batch,
    download_batch_results,
    get_sample_metadata,
    get_failed_list,
    retry_failed_employees
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
        result, status = process_batch_metadata(data, session)
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
        result, status = get_sample_metadata(session)
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


@batch_bp.route('/retry-failed', methods=['POST'])
def retry_failed():
    """Retry failed employee processing."""
    try:
        data = request.json
        result, status = retry_failed_employees(data, session)
        return jsonify(result), status
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500