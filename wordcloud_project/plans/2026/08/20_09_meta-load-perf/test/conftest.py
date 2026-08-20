"""20_09 fixture — 임시 sqlite + 격리된 가명 매니저(운영 매핑 파일 미접촉).

서버는 기동하지 않는다(DL-12). 운영 DB·매핑 파일·outputs 어디에도 쓰지 않는다.
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
    import src.services.deploy_session_service as dss
    import src.services.perspective_service as ps

    db_file = str(tmp_path / 'test_deploy_sessions.db')
    monkeypatch.setattr(dss, '_DB_PATH', db_file)
    monkeypatch.setattr(ps, '_EVAL_DB_PATH', db_file)
    dss._init_db()
    dss._apply_schema_migrations()
    yield db_file


@pytest.fixture
def db_conn(tmp_db):
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def reset_pseudo_mgr(monkeypatch, tmp_path):
    import src.services.perspective_service as ps
    monkeypatch.setattr(ps, '_pseudo_mgr_instance', None)
    monkeypatch.setattr(ps, 'PSEUDONYM_MAPPINGS_PATH', str(tmp_path / 'test_pseudonym_mappings.enc'))
    yield
    monkeypatch.setattr(ps, '_pseudo_mgr_instance', None)


@pytest.fixture
def add_employee(db_conn):
    def _add(employee_id, name=None, dept='개발팀', pos='사원', batch_id='BATCH_1', evals=1):
        # name/department/position 은 받은 값을 그대로 넣는다 — None 은 NULL 로 저장되어야
        # "가명이 아예 없는 직원" 경로(복원 대상 없음)를 대조할 수 있다.
        db_conn.execute(
            "INSERT OR IGNORE INTO employees (employee_id, name, department, position) VALUES (?,?,?,?)",
            (employee_id, name, dept, pos))
        for i in range(evals):
            db_conn.execute("""
                INSERT INTO evaluations (employee_id, evaluator_id, evaluation_date, batch_id, data, fingerprint)
                VALUES (?, ?, '2025-01-01', ?, '{}', ?)
            """, (employee_id, f'ev{i}', batch_id, f'fp_{employee_id}_{batch_id}_{i}'))
        db_conn.commit()
    return _add
