"""배치 작업서(Work Order) 서비스.

배치 메타데이터 생성의 설정 스냅샷과 진행 상황을 SQLite(deploy_sessions.db)에 영구
보존하여, 중단된 배치를 이어서(Resume) 처리할 수 있도록 한다.

DB 접근은 deploy_session_service의 연결 헬퍼(_get_conn/_init_db)를 재사용하여
순환 임포트와 중복 초기화를 방지한다. (batch_work_orders 테이블 DDL은 _init_db에 포함)
"""
import json
import sqlite3

from src.services.deploy_session_service import _get_conn, _init_db

_initialized = False


def _conn():
    """초기화를 보장한 뒤 연결 반환 (row_factory=Row, WAL)."""
    global _initialized
    if not _initialized:
        _init_db()
        _initialized = True
    return _get_conn()


def _row_to_dict(row):
    return {k: row[k] for k in row.keys()} if row else None


def create_work_order(batch_id, batch_dir, settings, file_info, total_employees=0):
    """새 작업서 생성. 동일 batch_id 존재 시 카운터 초기화 후 재시작(방어층).

    initialize_batch_directory()가 DB를 이중 확인하므로 정상 흐름에서는
    ON CONFLICT가 발생하지 않는다. 여기서도 카운터를 0으로 리셋하고 items를
    삭제해, 혹시라도 충돌이 발생했을 때 이전 배치 데이터가 섞이지 않도록 한다.
    """
    conn = _conn()
    try:
        conn.execute("""
            INSERT INTO batch_work_orders
                (batch_id, batch_dir, status, settings, file_info, total_employees)
            VALUES (?, ?, 'running', ?, ?, ?)
            ON CONFLICT(batch_id) DO UPDATE SET
                batch_dir           = excluded.batch_dir,
                status              = 'running',
                settings            = excluded.settings,
                file_info           = excluded.file_info,
                total_employees     = excluded.total_employees,
                processed_employees = 0,
                success_count       = 0,
                error_count         = 0,
                total_rows          = 0,
                completed_at        = NULL,
                updated_at          = datetime('now','localtime')
        """, (
            batch_id, batch_dir,
            json.dumps(settings, ensure_ascii=False),
            json.dumps(file_info, ensure_ascii=False),
            total_employees,
        ))
        conn.execute("DELETE FROM batch_work_order_items WHERE batch_id = ?", (batch_id,))
        conn.commit()
        cur = conn.execute("SELECT id FROM batch_work_orders WHERE batch_id = ?", (batch_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def update_work_order_progress(batch_id, processed_employees, success_count,
                               error_count, total_rows):
    """헤더 카운트(진행/성공/실패/행수) 갱신. 완료 직원 목록은 별도 items 테이블에서 관리.

    updated_at은 DEFAULT가 INSERT 전용이므로 UPDATE SQL에서 명시적으로 갱신한다.
    """
    conn = _conn()
    try:
        conn.execute("""
            UPDATE batch_work_orders
            SET processed_employees = ?,
                success_count       = ?,
                error_count         = ?,
                total_rows          = ?,
                updated_at          = datetime('now','localtime')
            WHERE batch_id = ?
        """, (processed_employees, success_count, error_count, total_rows, batch_id))
        conn.commit()
    finally:
        conn.close()


def add_completed_employees(batch_id, employee_ids):
    """완료(DB 저장)된 직원 ID들을 items 테이블에 append (INSERT OR IGNORE, O(델타)).

    대용량 배치(수만 명)에서도 JSON 배열 통째 재기록 없이 신규 분만 추가한다.
    """
    if not employee_ids:
        return
    conn = _conn()
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO batch_work_order_items (batch_id, employee_id) VALUES (?, ?)",
            [(batch_id, str(e)) for e in employee_ids]
        )
        conn.commit()
    finally:
        conn.close()


def get_completed_employee_ids(batch_id):
    """items 테이블에서 완료 직원 ID 목록 조회 (Resume skip 대상)."""
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT employee_id FROM batch_work_order_items WHERE batch_id = ?",
            (batch_id,)
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def complete_work_order(batch_id):
    """작업서 완료 처리."""
    conn = _conn()
    try:
        conn.execute("""
            UPDATE batch_work_orders
            SET status       = 'completed',
                completed_at = datetime('now','localtime'),
                updated_at   = datetime('now','localtime')
            WHERE batch_id = ?
        """, (batch_id,))
        conn.commit()
    finally:
        conn.close()


def fail_work_order(batch_id):
    """전체 배치 중단 시 작업서를 failed로 표시. (직원 단위 오류는 호출하지 않음)"""
    conn = _conn()
    try:
        conn.execute("""
            UPDATE batch_work_orders
            SET status     = 'failed',
                updated_at = datetime('now','localtime')
            WHERE batch_id = ?
        """, (batch_id,))
        conn.commit()
    finally:
        conn.close()


def get_all_work_orders(limit=20):
    """게시판용 최신순 전체 목록."""
    conn = _conn()
    try:
        cur = conn.execute("""
            SELECT * FROM batch_work_orders
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        """, (limit,))
        return [_row_to_dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_latest_incomplete_work_order():
    """가장 최근의 재개 가능한(interrupted/failed) 작업서 1건.
    
    running 상태는 서버가 살아있어 직접 처리 중이므로 Resume 대상에서 제외한다.
    """
    conn = _conn()
    try:
        cur = conn.execute("""
            SELECT * FROM batch_work_orders
            WHERE status IN ('interrupted', 'failed')
            ORDER BY created_at DESC, id DESC
            LIMIT 1
        """)
        return _row_to_dict(cur.fetchone())
    finally:
        conn.close()


def get_work_order_by_batch_id(batch_id):
    conn = _conn()
    try:
        cur = conn.execute(
            "SELECT * FROM batch_work_orders WHERE batch_id = ?", (batch_id,)
        )
        return _row_to_dict(cur.fetchone())
    finally:
        conn.close()
