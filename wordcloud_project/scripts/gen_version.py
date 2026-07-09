# -*- coding: utf-8 -*-
"""VERSION.json 생성 스크립트 — 배포 직전 수동 실행.

사용법:
    python scripts/gen_version.py

출력:
    wordcloud_project/VERSION.json (UTF-8)
    
모델 해시 전략:
    HR_SENTIMENT_MODEL_PATH 내 model.safetensors만 SHA-256 해시.
    나머지 파일(config.json, tokenizer*.json 등)은 model_trained 날짜로 대체.
"""

import json
import hashlib
import os
import subprocess
import sys
from datetime import datetime


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
VERSION_JSON_PATH = os.path.join(PROJECT_ROOT, 'VERSION.json')
HR_SENTIMENT_MODEL_PATH = os.path.join(
    PROJECT_ROOT, '..', 'model', 'hr_sentiment_finetuned'
)


def get_git_commit():
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return 'unknown'


def compute_model_hash():
    model_file = os.path.join(HR_SENTIMENT_MODEL_PATH, 'model.safetensors')
    if not os.path.isfile(model_file):
        return '-'

    sha256 = hashlib.sha256()
    with open(model_file, 'rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def get_model_trained():
    model_dir = os.path.abspath(HR_SENTIMENT_MODEL_PATH)
    if not os.path.isdir(model_dir):
        return '-'
    try:
        mtime = os.path.getmtime(os.path.join(model_dir, 'model.safetensors'))
        return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
    except Exception:
        return '-'


def main():
    version_info = {
        'system_version': '1.1.0',
        'model_version': 'hr-sentiment-v1.0',
        'model_sha256': compute_model_hash(),
        'model_trained': get_model_trained(),
        'source_commit': get_git_commit(),
        'build_date': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    }

    with open(VERSION_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(version_info, f, ensure_ascii=False, indent=2)

    print(f'VERSION.json generated: {VERSION_JSON_PATH}')
    print(json.dumps(version_info, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
