"""Version info service — reads VERSION.json and runtime model status."""

import json
import os
import logging

logger = logging.getLogger(__name__)

VERSION_JSON_PATH = os.path.abspath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'VERSION.json'
))


def get_version_info():
    """Return version info dict with runtime model status.
    
    Returns:
        dict with keys: system_version, model_version, model_sha256,
                        model_trained, source_commit, build_date, model_status
    """
    info = _read_version_file()
    info['model_status'] = _get_model_status()
    return info


def _read_version_file():
    """Read VERSION.json. Return defaults if file missing."""
    default = {
        'system_version': 'dev',
        'model_version': '-',
        'model_sha256': '-',
        'model_trained': '-',
        'source_commit': '-',
        'build_date': '-',
    }
    if not os.path.isfile(VERSION_JSON_PATH):
        return default
    try:
        with open(VERSION_JSON_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for key in default:
            data.setdefault(key, default[key])
        return data
    except Exception as e:
        logger.warning('VERSION.json 읽기 실패: %s', e)
        return default


def _get_model_status():
    """Return 'loaded' or 'fallback' based on runtime model state."""
    from src.modules.hr_sentiment import model_status
    status = model_status()
    if not status.get('enabled'):
        return 'fallback'
    if not status.get('dir_exists'):
        return 'fallback'
    if status.get('loaded'):
        return 'loaded'
    if status.get('load_failed'):
        return 'fallback'
    return 'loaded'


def verify_integrity():
    """On-demand verify: hash model.safetensors and compare to VERSION.json.
    
    Returns:
        dict with keys: match (bool), error (str, optional)
    """
    from src.config.settings import HR_SENTIMENT_MODEL_PATH
    import hashlib

    info = _read_version_file()
    declared_hash = info.get('model_sha256', '')

    if not declared_hash or declared_hash == '-':
        return {'match': False, 'error': 'VERSION.json에 선언된 해시 없음'}

    model_file = os.path.join(HR_SENTIMENT_MODEL_PATH, 'model.safetensors')
    if not os.path.isfile(model_file):
        return {'match': False, 'error': 'model.safetensors 파일 없음'}

    try:
        sha256 = hashlib.sha256()
        with open(model_file, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha256.update(chunk)
        actual_hash = sha256.hexdigest()
        if actual_hash == declared_hash:
            return {'match': True}
        else:
            return {'match': False, 'error': f'해시 불일치 (선언={declared_hash[:16]}..., 실제={actual_hash[:16]}...)'}
    except Exception as e:
        return {'match': False, 'error': str(e)}
