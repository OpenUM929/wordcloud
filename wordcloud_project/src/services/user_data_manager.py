"""User data manager — evaluation data CRUD via SQLite (employees + evaluations tables).

DB 저장 전제: employee_id는 pseudo_id (batch_processor에서 PseudonymManager를 통해 이미 가명화 완료).
실명 복원은 perspective_service._enrich_with_real_ids() 레이어에서 처리한다.
"""
import os
import json
import hashlib
import sqlite3

from src.config.settings import PROCESSED_DATA_DIR_PATH

_DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '.sessions')
_DB_PATH = os.path.join(_DB_DIR, 'deploy_sessions.db')

USERS_DIR = os.path.join(PROCESSED_DATA_DIR_PATH, 'users')


_db_initialized = False


def _get_eval_conn():
    global _db_initialized
    os.makedirs(_DB_DIR, exist_ok=True)
    if not _db_initialized:
        from src.services.deploy_session_service import _init_db
        _init_db()
        _db_initialized = True
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _fingerprint(ev):
    key = (
        ev.get('evaluator_id', ''),
        ev.get('evaluation_date', ''),
        str(ev.get('evaluation_document', ev.get('content', '')))[:100],
    )
    return hashlib.md5(json.dumps(key, ensure_ascii=False).encode()).hexdigest()


def upsert(employee_id, metadata, evaluations, batch_id):
    """Upsert user data from a batch.

    employee_id는 pseudo_id (batch_processor에서 이미 가명화 완료).
    """
    conn = _get_eval_conn()
    try:
        name = metadata.get('target_employee_name') or employee_id
        dept = metadata.get('target_employee_department') or ''
        pos  = metadata.get('target_employee_position') or ''
        conn.execute("""
            INSERT INTO employees (employee_id, name, department, position, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(employee_id) DO UPDATE SET
                name       = COALESCE(NULLIF(excluded.name, ''), name),
                department = COALESCE(NULLIF(excluded.department, ''), department),
                position   = COALESCE(NULLIF(excluded.position, ''), position),
                updated_at = datetime('now')
        """, (employee_id, name, dept, pos))

        inserted = 0
        for ev in evaluations:
            ev_copy = dict(ev)
            ev_copy['batch_id'] = batch_id
            fp = _fingerprint(ev_copy)
            try:
                conn.execute("""
                    INSERT INTO evaluations
                        (employee_id, evaluator_id, evaluation_date, batch_id, data, fingerprint)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    employee_id,
                    ev_copy.get('evaluator_id', ''),
                    ev_copy.get('evaluation_date', ''),
                    batch_id,
                    json.dumps(ev_copy, ensure_ascii=False),
                    fp,
                ))
                inserted += 1
            except sqlite3.IntegrityError:
                pass  # fingerprint 중복
        conn.commit()
        return inserted
    finally:
        conn.close()


def remove_batch(employee_id, batch_id):
    """Remove evaluations with given batch_id for a specific employee."""
    conn = _get_eval_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM evaluations WHERE employee_id = ? AND batch_id = ?",
            (employee_id, batch_id)
        )
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def remove_batch_from_all(batch_id, employee_ids):
    """Remove batch data from all employees.

    employee_ids는 기존 인터페이스 호환성을 위해 유지되며 무시된다.
    정책: 평가 없는 employee는 삭제하지 않음 (이력 보존).
    """
    conn = _get_eval_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM evaluations WHERE batch_id = ?", (batch_id,)
        )
        # 욕설 데이터 함께 삭제 (일원화)
        try:
            from src.services.profanity_db_service import delete_profanity_by_batch
            delete_profanity_by_batch(batch_id)
        except Exception:
            pass
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def count_users():
    """Quick count of employees in DB."""
    conn = _get_eval_conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    except Exception:
        return 0
    finally:
        conn.close()
