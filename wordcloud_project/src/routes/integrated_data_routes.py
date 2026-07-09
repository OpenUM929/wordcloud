"""Integrated data routes for the WordCloud application."""

from flask import Blueprint, request, jsonify
from src.services.integrated_data_service import (
    generate_integrated_data,
    get_batch_integrated_data,
    load_config,
    save_config
)

integrated_bp = Blueprint('metadata', __name__, url_prefix='/api/integrated')


@integrated_bp.route('/generate', methods=['POST'])
def generate():
    """Generate metadata from evaluation data."""
    try:
        data = request.json
        result = generate_integrated_data(data)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@integrated_bp.route('/batch', methods=['GET'])
def get_batch():
    """Get metadata for a specific batch."""
    try:
        batch_path = request.args.get('path')
        if not batch_path:
            return jsonify({'success': False, 'error': '배치 경로가 필요합니다.'}), 400
            
        metadata_list = get_batch_integrated_data(batch_path)
        return jsonify({'success': True, 'data': metadata_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@integrated_bp.route('/config', methods=['GET'])
def get_config():
    """Get current configuration."""
    try:
        config = load_config()
        return jsonify({'success': True, 'data': config})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@integrated_bp.route('/config', methods=['POST'])
def update_config():
    """Update configuration."""
    try:
        data = request.json
        save_config(data)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500