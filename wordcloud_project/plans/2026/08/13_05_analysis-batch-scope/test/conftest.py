"""13_05 테스트 fixture — 13_01/test/conftest.py(DB) + 04_01_deploy-resume/test/conftest.py
(가명 매니저 격리) 패턴을 결합해 복제한다. 서버 기동 없이 검증한다(DL-12).
"""
import os
import sys
import sqlite3
import pytest

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """perspective_service가 읽는 DB 경로를 임시 파일로 통일하고 스키마를 적용한다."""
    import src.services.deploy_session_service as dss
    import src.services.perspective_service as ps
    import src.services.gallery_db_service as gdb

    db_file = str(tmp_path / "test_deploy_sessions.db")
    monkeypatch.setattr(dss, '_DB_PATH', db_file)
    monkeypatch.setattr(ps, '_EVAL_DB_PATH', db_file)
    monkeypatch.setattr(gdb, '_DB_PATH', db_file)

    dss._init_db()
    dss._apply_schema_migrations()

    yield db_file


@pytest.fixture(autouse=True)
def isolate_outputs(monkeypatch, tmp_path):
    """산출물 경로를 임시 폴더로 격리한다.

    _build_save_path('user', ...)는 호출만으로 USER_OUTPUT_DIR 하위에 폴더를 만든다
    (os.makedirs). 격리하지 않으면 테스트가 운영 outputs/유저/ 에 EMP_X 같은 잔재
    폴더를 남긴다(2026-08-20 실측·정리). autouse로 전 테스트에 적용한다.
    """
    import src.services.perspective_service as ps
    out_root = tmp_path / 'outputs'
    monkeypatch.setattr(ps, 'OUTPUTS_DIR_PATH', str(out_root))
    monkeypatch.setattr(ps, 'USER_OUTPUT_DIR', str(out_root / '유저'))
    monkeypatch.setattr(ps, 'DEPLOY_OUTPUT_DIR', str(out_root / '배포'))
    monkeypatch.setattr(ps, 'DEPLOY_MANIFEST_PATH', str(out_root / 'deploy_manifest.json'))
    yield


@pytest.fixture
def db_conn(tmp_db):
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    yield conn
    conn.close()


@pytest.fixture
def reset_pseudo_mgr(monkeypatch, tmp_path):
    """전역 PseudonymManager 싱글턴을 임시 매핑 파일로 격리(운영 매핑 파일 미접촉)."""
    import src.services.perspective_service as ps
    monkeypatch.setattr(ps, '_pseudo_mgr_instance', None)
    monkeypatch.setattr(ps, 'PSEUDONYM_MAPPINGS_PATH', str(tmp_path / 'test_pseudonym_mappings.enc'))
    yield
    monkeypatch.setattr(ps, '_pseudo_mgr_instance', None)


def insert_employee(conn, employee_id, name=None):
    conn.execute(
        "INSERT OR IGNORE INTO employees (employee_id, name) VALUES (?, ?)",
        (employee_id, name or employee_id),
    )


def insert_evaluation(conn, employee_id, batch_id, fingerprint, evaluator_id='ev1',
                       evaluation_date='2025-01-01', data=None):
    """data를 주면 그대로(블롭) 저장한다 — 컬럼과 블롭의 batch_id 불일치 재현용(T8)."""
    insert_employee(conn, employee_id)
    conn.execute("""
        INSERT INTO evaluations (employee_id, evaluator_id, evaluation_date, batch_id, data, fingerprint)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (employee_id, evaluator_id, evaluation_date, batch_id, data or '{}', fingerprint))
