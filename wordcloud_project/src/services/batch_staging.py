"""Batch staging module - per-batch 임시 SQLite로 원문 평가를 디스크에 스트리밍.

Phase 1(수집)에서 CSV 청크를 읽어 직원별 원문 평가를 staging.db에 INSERT하고,
Phase 2(분석)에서 직원 1명씩 SELECT하여 분석한다. 종료 시 파일을 삭제한다.
최종 DB(deploy_sessions.db)와 분리된 batch_dir/staging.db를 사용해
스키마 오염·락 경합을 피한다.
"""

import os
import json
import sqlite3
import threading


def open_staging(batch_dir):
    """batch_dir/staging.db 쓰기 커넥션을 열고 스키마를 보장한다."""
    path = os.path.join(batch_dir, 'staging.db')
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS staging (
            employee_id TEXT NOT NULL,
            data        TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_staging_emp ON staging(employee_id)")
    conn.commit()
    return conn


def insert_evaluations(conn, rows):
    """rows: list[(employee_id, json_str)] 를 배치 INSERT한다."""
    conn.executemany("INSERT INTO staging (employee_id, data) VALUES (?, ?)", rows)
    conn.commit()


def distinct_employee_ids(conn):
    """staging에 존재하는 고유 employee_id 목록."""
    return [r[0] for r in conn.execute("SELECT DISTINCT employee_id FROM staging")]


def load_employee_evaluations(conn, employee_id):
    """단일 직원의 원문 평가 dict 리스트를 로드한다."""
    cur = conn.execute("SELECT data FROM staging WHERE employee_id = ?", (employee_id,))
    return [json.loads(r[0]) for r in cur]


# ── Phase 2 워커용 read 커넥션 캐싱 ──────────────────────────────
_tls = threading.local()


def get_reader(batch_dir):
    """ThreadPoolExecutor 워커 스레드당 read 커넥션 1개를 재사용한다.

    19,000명 규모에서 직원마다 open/close를 반복하지 않도록 스레드 로컬에 캐싱한다.
    """
    conn = getattr(_tls, 'conn', None)
    if conn is None:
        path = os.path.join(batch_dir, 'staging.db')
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA query_only=ON")
        _tls.conn = conn
    return conn


def close_reader():
    """현재 스레드의 캐싱된 read 커넥션을 닫는다."""
    conn = getattr(_tls, 'conn', None)
    if conn is not None:
        try:
            conn.close()
        finally:
            _tls.conn = None


def remove_staging_files(batch_dir):
    """커넥션 없이 staging.db(+wal/shm)만 삭제한다(처리 실패 경로 정리용)."""
    if not batch_dir:
        return
    for suffix in ('', '-wal', '-shm'):
        p = os.path.join(batch_dir, 'staging.db' + suffix)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def close_and_remove(conn, batch_dir):
    """쓰기 커넥션을 닫고 staging.db(+wal/shm)를 삭제한다.

    Windows 파일 잠금으로 삭제 실패 시 예외를 무시한다(잔존 파일은 다음 정리에서 제거).
    """
    try:
        conn.close()
    finally:
        for suffix in ('', '-wal', '-shm'):
            p = os.path.join(batch_dir, 'staging.db' + suffix)
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
