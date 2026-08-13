"""배치 병합 테스트 공통 fixture.

서버 기동 없이 임시 sqlite 파일로 검증한다(DL-12). deploy_session_service·
user_data_manager·batch_merge_service·perspective_service가 각자 계산하는
_DB_PATH(또는 _EVAL_DB_PATH)를 전부 같은 임시 파일로 monkeypatch해 한 DB를
공유하게 만든다 — 실제 서버 기동 시의 결선과 동일한 구성이다.
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
    """4개 모듈의 DB 경로를 동일한 임시 파일로 통일하고 스키마를 v9까지 적용한다."""
    import src.services.deploy_session_service as dss
    import src.services.user_data_manager as udm
    import src.services.batch_merge_service as bms
    import src.services.perspective_service as ps

    db_file = str(tmp_path / "test_deploy_sessions.db")
    monkeypatch.setattr(dss, '_DB_PATH', db_file)
    monkeypatch.setattr(udm, '_DB_PATH', db_file)
    monkeypatch.setattr(bms, '_DB_PATH', db_file)
    monkeypatch.setattr(ps, '_EVAL_DB_PATH', db_file)

    dss._init_db()
    dss._apply_schema_migrations()

    yield db_file


@pytest.fixture
def db_conn(tmp_db):
    """테스트 데이터 세팅/검증용 원시 커넥션."""
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    yield conn
    conn.close()


@pytest.fixture
def processed_dir(tmp_path):
    """batch_merge_service가 물리 폴더(batch_summary.json)를 쓸 임시 루트."""
    d = tmp_path / "processed_data"
    d.mkdir(exist_ok=True)
    return str(d)


def insert_employee(conn, employee_id, name=None):
    conn.execute(
        "INSERT OR IGNORE INTO employees (employee_id, name) VALUES (?, ?)",
        (employee_id, name or employee_id),
    )


def insert_evaluation(conn, employee_id, batch_id, fingerprint, evaluator_id='ev1',
                       evaluation_date='2023-01-01'):
    insert_employee(conn, employee_id)
    conn.execute("""
        INSERT INTO evaluations (employee_id, evaluator_id, evaluation_date, batch_id, data, fingerprint)
        VALUES (?, ?, ?, ?, '{}', ?)
    """, (employee_id, evaluator_id, evaluation_date, batch_id, fingerprint))


def insert_work_order(conn, batch_id, status='completed', success_count=0, total_rows=0):
    conn.execute("""
        INSERT INTO batch_work_orders
            (batch_id, batch_dir, status, settings, file_info, total_employees,
             success_count, total_rows)
        VALUES (?, ?, ?, '{}', '{}', ?, ?, ?)
    """, (batch_id, f'/tmp/{batch_id}', status, success_count, success_count, total_rows))


def insert_work_order_item(conn, batch_id, employee_id):
    conn.execute(
        "INSERT OR IGNORE INTO batch_work_order_items (batch_id, employee_id) VALUES (?, ?)",
        (batch_id, employee_id),
    )


def insert_profanity_employee(conn, batch_id, employee_id, count=1, words='["x"]'):
    conn.execute("""
        INSERT INTO profanity_employees (batch_id, employee_id, profanity_count, profanity_words)
        VALUES (?, ?, ?, ?)
    """, (batch_id, employee_id, count, words))


def insert_acquired_sentence(conn, source_batch_id, text, idx=0):
    conn.execute("""
        INSERT INTO acquired_sentences (sentence_text, source_batch_id, sentence_index)
        VALUES (?, ?, ?)
    """, (text, source_batch_id, idx))
