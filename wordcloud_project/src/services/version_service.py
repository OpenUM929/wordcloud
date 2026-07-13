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
                        model_trained, source_commit, build_date, model_status,
                        runtime_sha256, runtime_loaded_at, restart_required

    runtime_sha256 = 서버 프로세스 메모리에 실제 로드된 모델의 지문(로드 시점 기록).
    restart_required = 선언(VERSION.json)과 로드본이 모두 존재하는데 서로 다름
                       → 파일은 교체됐으나 재시작 전이라 추론은 이전 모델로 수행 중.
    """
    info = _read_version_file()
    info['model_status'] = _get_model_status()
    from src.modules.hr_sentiment import model_status
    status = model_status()
    info['runtime_sha256'] = status.get('loaded_sha256')
    info['runtime_loaded_at'] = status.get('loaded_at')
    declared = info.get('model_sha256', '')
    info['restart_required'] = bool(
        info['runtime_sha256'] and declared and declared != '-'
        and info['runtime_sha256'] != declared
    )
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
    """On-demand verify: 선언(VERSION.json)·디스크(model.safetensors)·메모리(로드본) 3자 대조.

    디스크만 검증하면 "파일은 교체됐지만 서버 재시작 전이라 이전 모델로 추론 중"인 상태를
    일치로 오판한다(2026-07 배포 검증 이슈). 메모리 로드본 지문까지 대조해 이를 잡는다.

    Returns:
        dict with keys: match (bool), error (str, optional),
                        restart_required (bool), note (str, optional),
                        declared/disk/loaded (해시 앞 16자리, 진단용)
    """
    from src.config.settings import HR_SENTIMENT_MODEL_PATH
    from src.modules.hr_sentiment import model_status
    import hashlib

    info = _read_version_file()
    declared_hash = info.get('model_sha256', '')

    if not declared_hash or declared_hash == '-':
        return {'match': False, 'restart_required': False,
                'error': 'VERSION.json에 선언된 해시 없음'}

    model_file = os.path.join(HR_SENTIMENT_MODEL_PATH, 'model.safetensors')
    if not os.path.isfile(model_file):
        return {'match': False, 'restart_required': False,
                'error': 'model.safetensors 파일 없음'}

    try:
        sha256 = hashlib.sha256()
        with open(model_file, 'rb') as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha256.update(chunk)
        disk_hash = sha256.hexdigest()
    except Exception as e:
        return {'match': False, 'restart_required': False, 'error': str(e)}

    status = model_status()
    loaded_hash = status.get('loaded_sha256')
    diag = {
        'declared': declared_hash[:16],
        'disk': disk_hash[:16],
        'loaded': loaded_hash[:16] if loaded_hash else None,
    }

    if disk_hash != declared_hash:
        return {'match': False, 'restart_required': False,
                'error': f'디스크 모델이 선언과 불일치 (선언={declared_hash[:16]}..., 디스크={disk_hash[:16]}...) — 모델 파일 반입 확인 필요',
                **diag}

    # 디스크는 선언과 일치 — 메모리 로드본 대조
    if loaded_hash is None:
        # 아직 미로드: 첫 추론 시 현재 디스크 모델이 그대로 로드되므로 일치로 판정
        return {'match': True, 'restart_required': False,
                'note': '디스크 일치 · 모델 미로드(첫 추론 시 현재 디스크 모델 로드)', **diag}

    if loaded_hash != disk_hash:
        return {'match': False, 'restart_required': True,
                'error': f'모델 파일은 교체됐으나 서버가 이전 모델을 메모리에 유지 중 (로드본={loaded_hash[:16]}..., 디스크={disk_hash[:16]}...) — 서버 재시작 필요',
                **diag}

    return {'match': True, 'restart_required': False,
            'note': '선언·디스크·메모리 로드본 모두 일치', **diag}
