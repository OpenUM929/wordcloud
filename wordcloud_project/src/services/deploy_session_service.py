"""Deploy session service — SQLite-based chunked task tracking for large-scale deploy operations."""
import os
import json
import sqlite3
import uuid
from datetime import datetime

_DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '.sessions')
_DB_PATH = os.path.join(_DB_DIR, 'deploy_sessions.db')


def _get_conn():
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS deploy_sessions (
                session_id   TEXT PRIMARY KEY,
                created_at   TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'running',
                options      TEXT NOT NULL,
                total_count  INTEGER NOT NULL,
                completed_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                paused_at    TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS deploy_tasks (
                session_id    TEXT NOT NULL,
                employee_id   TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'pending',
                result_path   TEXT,
                error_message TEXT,
                assigned_at   TEXT,
                completed_at  TEXT,
                PRIMARY KEY (session_id, employee_id)
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_session_status ON deploy_tasks (session_id, status);
        """)
        conn.commit()
    finally:
        conn.close()


_init_db()


def create_session(options, employee_ids):
    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO deploy_sessions (session_id, created_at, status, options, total_count)
            VALUES (?, ?, 'running', ?, ?)
            """,
            (session_id, now, json.dumps(options, ensure_ascii=False), len(employee_ids)),
        )
        rows = [(session_id, eid) for eid in employee_ids]
        conn.executemany(
            "INSERT INTO deploy_tasks (session_id, employee_id) VALUES (?, ?)", rows
        )
        conn.commit()
    finally:
        conn.close()
    return session_id


def cleanup_old_sessions(days=7):
    cutoff = f"datetime('now', '-{days} days')"
    conn = _get_conn()
    try:
        conn.execute(
            f"""
            DELETE FROM deploy_tasks WHERE session_id IN (
                SELECT session_id FROM deploy_sessions
                 WHERE status IN ('completed', 'failed')
                   AND COALESCE(completed_at, paused_at, created_at) < {cutoff}
            )
            """
        )
        conn.execute(
            f"""
            DELETE FROM deploy_sessions
             WHERE status IN ('completed', 'failed')
               AND COALESCE(completed_at, paused_at, created_at) < {cutoff}
            """
        )
        conn.commit()
    finally:
        conn.close()


def _restore_orphans(conn, session_id=None):
    if session_id:
        conn.execute(
            """
            UPDATE deploy_tasks
               SET status = 'pending', assigned_at = NULL
             WHERE session_id = ?
               AND status = 'processing'
               AND assigned_at < datetime('now', '-5 minutes')
            """,
            (session_id,),
        )
    else:
        conn.execute(
            """
            UPDATE deploy_tasks
               SET status = 'pending', assigned_at = NULL
             WHERE status = 'processing'
               AND assigned_at < datetime('now', '-5 minutes')
            """
        )


def allocate_chunk(session_id, count=50):
    conn = _get_conn()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            _restore_orphans(conn, session_id)
            rows = conn.execute(
                """
                SELECT employee_id FROM deploy_tasks
                 WHERE session_id = ? AND status = 'pending'
                 LIMIT ?
                """,
                (session_id, count),
            ).fetchall()
            ids = [r[0] for r in rows]
            if ids:
                placeholders = ','.join('?' * len(ids))
                conn.execute(
                    f"""
                    UPDATE deploy_tasks
                       SET status = 'processing', assigned_at = datetime('now')
                     WHERE session_id = ? AND employee_id IN ({placeholders})
                    """,
                    (session_id, *ids),
                )
        return ids
    finally:
        conn.close()


def report_chunk(session_id, completed_items, failed_items):
    """
    completed_items: list of str (employee_id) or dict {employee_id, result_data}
    """
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        with conn:
            for item in completed_items:
                if isinstance(item, str):
                    eid, result_json = item, None
                else:
                    eid = item.get('employee_id')
                    rd = item.get('result_data')
                    result_json = json.dumps(rd, ensure_ascii=False) if rd else None
                conn.execute(
                    """
                    UPDATE deploy_tasks
                       SET status = 'completed', completed_at = ?,
                           result_path = ?
                     WHERE session_id = ? AND employee_id = ?
                    """,
                    (now, result_json, session_id, eid),
                )
            for item in failed_items:
                eid = item.get('employee_id')
                error = item.get('error', '')
                conn.execute(
                    """
                    UPDATE deploy_tasks
                       SET status = 'failed', error_message = ?, completed_at = ?
                     WHERE session_id = ? AND employee_id = ?
                    """,
                    (error, now, session_id, eid),
                )
            conn.execute(
                """
                UPDATE deploy_sessions
                   SET completed_count = (
                       SELECT COUNT(*) FROM deploy_tasks WHERE session_id = ? AND status = 'completed'
                   ),
                   failed_count = (
                       SELECT COUNT(*) FROM deploy_tasks WHERE session_id = ? AND status = 'failed'
                   )
                 WHERE session_id = ?
                """,
                (session_id, session_id, session_id),
            )
        _update_session_status(session_id)
    finally:
        conn.close()


def _update_session_status(session_id):
    conn = _get_conn()
    try:
        total = conn.execute(
            "SELECT total_count FROM deploy_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM deploy_tasks WHERE session_id = ? AND status = 'pending'",
            (session_id,),
        ).fetchone()[0]
        processing = conn.execute(
            "SELECT COUNT(*) FROM deploy_tasks WHERE session_id = ? AND status = 'processing'",
            (session_id,),
        ).fetchone()[0]

        if pending == 0 and processing == 0:
            conn.execute(
                "UPDATE deploy_sessions SET status = ?, completed_at = ? WHERE session_id = ?",
                ('completed', datetime.now().isoformat(), session_id),
            )
            conn.commit()
    finally:
        conn.close()


def get_active_sessions():
    conn = _get_conn()
    try:
        _restore_orphans(conn)
        conn.commit()
        rows = conn.execute(
            """
            SELECT session_id, created_at, status, options, total_count,
                   completed_count, failed_count, paused_at
              FROM deploy_sessions
             WHERE status IN ('running', 'paused')
             ORDER BY created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resume_session(session_id):
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE deploy_sessions SET status = 'running', paused_at = NULL WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
    finally:
        conn.close()


def cancel_session(session_id):
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE deploy_sessions SET status = 'failed', paused_at = ? WHERE session_id = ?",
            (datetime.now().isoformat(), session_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_session_progress(session_id):
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM deploy_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def get_session_tasks(session_id):
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT employee_id, status, result_path, error_message, completed_at
              FROM deploy_tasks
             WHERE session_id = ?
             ORDER BY rowid
            """,
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def retry_failed_tasks(session_id):
    """세션 내 실패한 태스크를 pending으로 리셋하고 세션을 running 상태로 복원."""
    conn = _get_conn()
    try:
        with conn:
            # failed 태스크를 pending으로 리셋
            conn.execute(
                """
                UPDATE deploy_tasks
                   SET status = 'pending', error_message = NULL, completed_at = NULL, assigned_at = NULL
                 WHERE session_id = ? AND status = 'failed'
                """,
                (session_id,),
            )
            # 세션 상태를 running으로 복원, completed_at 초기화
            conn.execute(
                """
                UPDATE deploy_sessions
                   SET status = 'running', completed_at = NULL
                 WHERE session_id = ?
                """,
                (session_id,),
            )
        return True
    finally:
        conn.close()


def get_recently_completed_sessions(hours=24):
    conn = _get_conn()
    try:
        rows = conn.execute(
            f"""
            SELECT session_id, created_at, status, options, total_count,
                   completed_count, failed_count, completed_at
              FROM deploy_sessions
             WHERE status = 'completed'
               AND completed_at >= datetime('now', '-{hours} hours')
             ORDER BY completed_at DESC
             LIMIT 5
            """,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
