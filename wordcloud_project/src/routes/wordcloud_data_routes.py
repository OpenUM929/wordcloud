"""Wordcloud data API routes - serves JSON for SVG animation rendering."""

from flask import Blueprint, jsonify
from src.services.wordcloud_data_service import (
    get_employee_wordcloud_data,
    get_batch_aggregate_data,
    get_batch_employee_list,
)

wordcloud_data_bp = Blueprint('wordcloud_data', __name__, url_prefix='/api/wordcloud')


@wordcloud_data_bp.route('/data/<batch_id>/<employee_id>', methods=['GET'])
def employee_data(batch_id, employee_id):
    data, err = get_employee_wordcloud_data(batch_id, employee_id)
    if err:
        return jsonify({'success': False, 'error': err}), 404
    return jsonify({'success': True, 'data': data})


@wordcloud_data_bp.route('/data/batch/<batch_id>', methods=['GET'])
def batch_aggregate(batch_id):
    data, err = get_batch_aggregate_data(batch_id)
    if err:
        return jsonify({'success': False, 'error': err}), 404
    return jsonify({'success': True, 'data': data})


@wordcloud_data_bp.route('/preview/employees/<batch_id>', methods=['GET'])
def batch_employees(batch_id):
    employee_ids, err = get_batch_employee_list(batch_id)
    if err:
        return jsonify({'success': False, 'error': err}), 404
    return jsonify({'success': True, 'employee_ids': employee_ids})
