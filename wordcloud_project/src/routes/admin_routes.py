from flask import Blueprint, request, jsonify, session, render_template
from functools import wraps
from src.config.settings import ADMIN_PASSWORD, PSEUDONYM_MAPPINGS_PATH, POSITION_HIERARCHY_PATH
from src.modules.pseudonym_manager import PseudonymManager
from src.services.audit_service import log_action, get_audit_logs
from src.services.perspective_service import load_position_hierarchy, save_position_hierarchy

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

_pseudo_mgr = None


def _get_manager():
    global _pseudo_mgr
    if _pseudo_mgr is None:
        _pseudo_mgr = PseudonymManager(PSEUDONYM_MAPPINGS_PATH, ADMIN_PASSWORD)
    return _pseudo_mgr


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
            return render_template('admin_login.html', error='로그인이 필요합니다.')
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('admin_login.html')

    data = request.get_json(silent=True) or {}
    password = data.get('password', '')
    if password == ADMIN_PASSWORD:
        session['admin_logged_in'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': '비밀번호가 올바르지 않습니다.'}), 403


@admin_bp.route('/logout', methods=['POST'])
def logout():
    session.pop('admin_logged_in', None)
    return jsonify({'success': True})


@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    return render_template('admin_dashboard.html')


@admin_bp.route('/batch-management')
@admin_required
def batch_management():
    return render_template('admin_batch_management.html')


@admin_bp.route('/api/check', methods=['GET'])
def check_session():
    return jsonify({'admin_logged_in': session.get('admin_logged_in', False)})


@admin_bp.route('/api/deanonymize', methods=['POST'])
@admin_required
def deanonymize():
    data = request.get_json(silent=True) or {}
    pseudonym = data.get('pseudonym', '').strip()
    if not pseudonym:
        return jsonify({'success': False, 'error': '가명을 입력해주세요.'}), 400
    mgr = _get_manager()
    real_id = mgr.get_real_id(pseudonym)
    return jsonify({
        'success': True,
        'pseudonym': pseudonym,
        'real_id': real_id,
        'found': real_id != pseudonym
    })


@admin_bp.route('/api/mappings', methods=['GET'])
@admin_required
def list_mappings():
    mgr = _get_manager()
    mappings = mgr.get_all_mappings()
    result = [{'real_id': r, 'pseudonym': p} for r, p in mappings]
    return jsonify({
        'success': True,
        'total': len(result),
        'mappings': result
    })


@admin_bp.route('/api/mapping/link', methods=['POST'])
@admin_required
def link_mapping():
    data = request.get_json(silent=True) or {}
    pseudonym = data.get('pseudonym', '').strip()
    real_id = data.get('real_id', '').strip()
    if not pseudonym or not real_id:
        return jsonify({'success': False, 'error': 'pseudonym과 real_id가 필요합니다.'}), 400

    mgr = _get_manager()
    mgr.link_mapping(pseudonym, real_id)

    log_action('mapping_link', {'pseudonym': pseudonym, 'real_id': real_id}, request)
    return jsonify({'success': True, 'pseudonym': pseudonym, 'real_id': real_id})


@admin_bp.route('/api/audit-log', methods=['GET'])
@admin_required
def audit_log():
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    action_type = request.args.get('action_type')
    logs = get_audit_logs(limit=limit, offset=offset, action_type=action_type)
    return jsonify({'success': True, 'total': len(logs), 'logs': logs})


@admin_bp.route('/api/positions', methods=['GET'])
@admin_required
def get_positions():
    hierarchy = load_position_hierarchy(POSITION_HIERARCHY_PATH)
    return jsonify({'success': True, 'hierarchy': hierarchy})


@admin_bp.route('/api/positions', methods=['POST'])
@admin_required
def save_positions():
    data = request.get_json(silent=True) or {}
    hierarchy = data.get('hierarchy', [])
    if not hierarchy:
        return jsonify({'success': False, 'error': '직책 목록이 비어있습니다.'}), 400
    for i, entry in enumerate(hierarchy):
        if not entry.get('name'):
            return jsonify({'success': False, 'error': f'{i+1}번째 직책 이름이 필요합니다.'}), 400
        entry['level'] = i + 1
        if 'grade' not in entry:
            entry['grade'] = i + 1
    save_position_hierarchy(hierarchy, POSITION_HIERARCHY_PATH)
    log_action('positions_update', {'count': len(hierarchy)}, request)
    return jsonify({'success': True, 'hierarchy': hierarchy})
