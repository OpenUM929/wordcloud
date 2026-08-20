"""20_05 테스트 fixture — 서버 기동 없이 임시 sqlite로 검증한다(DL-12)."""
import os
import sys
import sqlite3

import pytest

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


@pytest.fixture
def gallery_db(tmp_path, monkeypatch):
    import src.services.gallery_db_service as gdb
    db_file = str(tmp_path / 'gallery_test.db')
    monkeypatch.setattr(gdb, '_DB_PATH', db_file)
    gdb.init_gallery_db()
    yield db_file


@pytest.fixture
def add_entry(gallery_db):
    """timestamp(YYYYMMDD_HHMM)만 지정해 갤러리 항목을 넣는 헬퍼."""
    def _add(entry_id, timestamp, employee_id='EMP1', source='deploy', output_mode='pseudonym'):
        conn = sqlite3.connect(gallery_db)
        try:
            conn.execute("""
                INSERT INTO gallery_entries (id, employee_id, deploy_name, batch_title,
                                             timestamp, output_mode, source)
                VALUES (?, ?, ?, NULL, ?, ?, ?)
            """, (entry_id, employee_id, employee_id, timestamp, output_mode, source))
            conn.commit()
        finally:
            conn.close()
    return _add
