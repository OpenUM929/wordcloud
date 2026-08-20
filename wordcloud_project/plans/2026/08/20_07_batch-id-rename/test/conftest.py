"""20_07 테스트 fixture — 서버 기동 없이 검증한다(DL-12).

배치 명칭 정본(processed_data/batch/<id>/tdata/batch_summary.json)을 임시 폴더에
만들어 쓰고, 라우트는 Flask test_client 로만 호출한다(실 서버 미기동).
"""
import os
import sys
import json

import pytest

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


@pytest.fixture
def processed_dir(tmp_path):
    d = tmp_path / 'processed_data'
    (d / 'batch').mkdir(parents=True)
    return str(d)


@pytest.fixture
def write_summary(processed_dir):
    """batch_summary.json 에 display_name 을 심어 두는 헬퍼."""
    def _write(batch_id, display_name):
        tdata = os.path.join(processed_dir, 'batch', batch_id, 'tdata')
        os.makedirs(tdata, exist_ok=True)
        with open(os.path.join(tdata, 'batch_summary.json'), 'w', encoding='utf-8') as f:
            json.dump({'batch_info': {'batch_id': batch_id, 'display_name': display_name}},
                      f, ensure_ascii=False)
    return _write
