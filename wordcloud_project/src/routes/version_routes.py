"""Version API routes — version info and integrity verification."""

from flask import Blueprint, jsonify, session
from src.services.version_service import get_version_info, verify_integrity

version_bp = Blueprint('version', __name__, url_prefix='/api/version')


def _is_admin():
    return session.get('admin_logged_in', False)


@version_bp.route('')
def version_info():
    """Return version info as JSON."""
    info = get_version_info()
    return jsonify(info)


@version_bp.route('/verify')
def version_verify():
    """On-demand integrity check. Admin-only."""
    if not _is_admin():
        return jsonify({'match': False, 'error': '관리자만 접근 가능'}), 403
    result = verify_integrity()
    return jsonify(result)
