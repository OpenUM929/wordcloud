"""Batch merge service — 복수 배치를 하나의 통합 배치로 재라벨한다.

계획서: plans/2026/08/13_01_batch-merge/13_01_batch-merge.md §4.2

병합은 데이터 복사가 아니라 batch_id 재라벨이다. idx_ev_fp UNIQUE(employee_id,
fingerprint) 제약(스키마 v3, deploy_session_service.py) 때문에 복사는 애초에
불가능하다 — 동일 직원의 동일 평가는 배치가 달라도 한 행만 존재한다.

DB 접근은 deploy_session_service와 동일한 파일(.sessions/deploy_sessions.db)을
가리키되, 이 모듈 자체의 커넥션으로 단일 트랜잭션을 구성한다. batch_work_order_
service.create_work_order() 등 기존 헬퍼는 각자 별도 커넥션으로 즉시 commit하므로,
이미 쓰기 트랜잭션이 열려 있는 이 서비스 안에서 호출하면 동일 DB 파일에 대한
쓰기 잠금 경합(SQLITE_BUSY)이 발생할 수 있다. 그래서 batch_work_orders INSERT/
UPDATE는 이 파일의 커넥션으로 직접 수행한다(batch_work_order_service.py는
수정하지 않는다 — 계획서 §5.1).
"""
import os
import json
import shutil
import sqlite3
from datetime import datetime

from src.config.settings import PROCESSED_DATA_DIR_PATH

_DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '.sessions')
_DB_PATH = os.path.join(_DB_DIR, 'deploy_sessions.db')


class BatchMergeError(Exception):
    """입력 검증 실패 — status_code는 라우트가 그대로 HTTP 상태 코드로 쓴다."""

    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _get_conn():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _backup_db():
    """병합 실행 전 DB 파일 백업 (18-backup-before-modify.md)."""
    if not os.path.exists(_DB_PATH):
        return None
    backup_dir = os.path.join(os.path.dirname(_DB_PATH), 'backup')
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    dest = os.path.join(backup_dir, f'deploy_sessions_{ts}.db')
    shutil.copy2(_DB_PATH, dest)
    return dest


def _batch_status_info(conn, batch_id):
    """존재 여부와 작업서 status를 반환한다.

    작업서(batch_work_orders)가 없어도 evaluations에 행이 있으면 레거시 배치로
    존재한다고 본다 — _load_batch_list()와 동일한 존재 판정 기준(계획서 §4.2-1).
    """
    row = conn.execute(
        "SELECT status FROM batch_work_orders WHERE batch_id = ?", (batch_id,)
    ).fetchone()
    if row is not None:
        return True, row['status']
    count = conn.execute(
        "SELECT COUNT(*) FROM evaluations WHERE batch_id = ?", (batch_id,)
    ).fetchone()[0]
    return (count > 0), None


def _generate_new_batch_id(conn, processed_data_dir):
    """batch_YYYYMMDD_NN 형식으로 신규 배치 ID를 생성한다 (D-2).

    당일 NN은 batch_work_orders·evaluations·물리 폴더 존재 여부를 모두 확인해
    충돌 없는 최소값을 고른다 — batch_processor.initialize_batch_directory()의
    번호 부여 방식과 동일한 규약(0부터 증가, 폴더/DB 어느 쪽에 있어도 건너뜀).
    """
    current_date = datetime.now().strftime('%Y%m%d')
    prefix = f'batch_{current_date}_'
    existing = set()
    for row in conn.execute(
        "SELECT batch_id FROM batch_work_orders WHERE batch_id LIKE ?", (prefix + '%',)
    ):
        existing.add(row['batch_id'])
    for row in conn.execute(
        "SELECT DISTINCT batch_id FROM evaluations WHERE batch_id LIKE ?", (prefix + '%',)
    ):
        existing.add(row['batch_id'])

    num = 0
    while True:
        candidate = f'{prefix}{num}'
        batch_dir = os.path.join(processed_data_dir, 'batch', candidate)
        if candidate not in existing and not os.path.isdir(batch_dir):
            return candidate
        num += 1


def _write_batch_summary(processed_data_dir, batch_id, display_name,
                          employee_count, total_evaluations, source_batch_ids):
    """tdata·tmeta 양쪽에 batch_summary.json 생성 (D-5, §2.2 경로 불일치 대응).

    DL-9: 직원 식별 정보(이름·ID 목록)는 쓰지 않는다 — 집계 수치와 배치 ID만.
    """
    now_iso = datetime.now().isoformat() + 'Z'
    summary = {
        'batch_info': {
            'batch_id': batch_id,
            'display_name': display_name or '',
            'created_at': now_iso,
            'processed_at': now_iso,
            'unique_employees': employee_count,
            'total_evaluations': total_evaluations,
            'merged_from': list(source_batch_ids),
        },
    }
    batch_dir = os.path.join(processed_data_dir, 'batch', batch_id)
    for sub in ('tdata', 'tmeta'):
        d = os.path.join(batch_dir, sub)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'batch_summary.json'), 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


def merge_batches(source_batch_ids, display_name='', new_batch_id=None, processed_data_dir=None):
    """복수 배치를 하나의 통합 배치로 재라벨한다.

    Args:
        source_batch_ids: 병합할 원본 배치 ID 목록 (2개 이상)
        display_name: 통합 배치 표시 명칭
        new_batch_id: 통합 배치 ID를 강제 지정할 때 사용(생략 시 자동 생성, D-2)
        processed_data_dir: 물리 폴더 루트(생략 시 PROCESSED_DATA_DIR_PATH)

    Returns:
        {'success': True, 'batch_id': str, 'moved': int,
         'employee_count': int, 'total_evaluations': int, 'sources': [...]}

    Raises:
        BatchMergeError: 입력 검증 실패(status_code 400/404)
    """
    if processed_data_dir is None:
        processed_data_dir = PROCESSED_DATA_DIR_PATH

    if not source_batch_ids or len(source_batch_ids) < 2:
        raise BatchMergeError(400, '병합하려면 배치를 2개 이상 선택해야 합니다.')
    if len(set(source_batch_ids)) != len(source_batch_ids):
        raise BatchMergeError(400, '동일한 배치가 중복 선택되었습니다.')

    conn = _get_conn()
    try:
        # 1. 입력 검증 — 존재 여부·진행 중 여부 (읽기 전용, 아직 쓰기 없음)
        missing, running = [], []
        for bid in source_batch_ids:
            exists, status = _batch_status_info(conn, bid)
            if not exists:
                missing.append(bid)
            elif status == 'running':
                running.append(bid)
        if missing:
            raise BatchMergeError(404, f"존재하지 않는 배치: {', '.join(missing)}")
        if running:
            raise BatchMergeError(
                400, f"진행 중인 배치는 병합할 수 없습니다: {', '.join(running)}"
            )

        # 쓰기 작업 진입 전 백업 (18-backup-before-modify.md)
        _backup_db()

        # 2. 배치 ID 생성
        merged_batch_id = new_batch_id or _generate_new_batch_id(conn, processed_data_dir)

        moved_counts = {}
        source_statuses = {}
        for bid in source_batch_ids:
            wo_row = conn.execute(
                "SELECT status FROM batch_work_orders WHERE batch_id = ?", (bid,)
            ).fetchone()
            source_statuses[bid] = wo_row['status'] if wo_row is not None else ''

            # 행 단위 원본 추적: 이미 orig_batch_id가 있으면(재병합 대상) 건드리지 않는다
            # — R-1 대안 채택안(원본은 항상 최초 배치를 가리킨다).
            conn.execute("""
                UPDATE evaluations
                   SET orig_batch_id = CASE
                       WHEN orig_batch_id IS NULL OR orig_batch_id = '' THEN batch_id
                       ELSE orig_batch_id
                   END
                 WHERE batch_id = ?
            """, (bid,))

            # 3. evaluations 재라벨
            cur = conn.execute(
                "UPDATE evaluations SET batch_id = ? WHERE batch_id = ?",
                (merged_batch_id, bid)
            )
            moved_counts[bid] = cur.rowcount

            # 4. batch_work_order_items 병합 (PK 충돌은 OR IGNORE로 흡수)
            conn.execute("""
                INSERT OR IGNORE INTO batch_work_order_items (batch_id, employee_id)
                SELECT ?, employee_id FROM batch_work_order_items WHERE batch_id = ?
            """, (merged_batch_id, bid))
            conn.execute(
                "DELETE FROM batch_work_order_items WHERE batch_id = ?", (bid,)
            )

            # 5. 욕설 집계 재라벨
            conn.execute(
                "UPDATE profanity_employees SET batch_id = ? WHERE batch_id = ?",
                (merged_batch_id, bid)
            )

            # 6. 적립 문장 출처 재라벨 (학습 라벨 값은 건드리지 않는다)
            conn.execute(
                "UPDATE acquired_sentences SET source_batch_id = ? WHERE source_batch_id = ?",
                (merged_batch_id, bid)
            )

        # 집계 확정 — 추정 금지, 실측
        agg = conn.execute("""
            SELECT COUNT(DISTINCT employee_id) AS employee_count,
                   COUNT(*) AS total_evaluations
              FROM evaluations WHERE batch_id = ?
        """, (merged_batch_id,)).fetchone()
        employee_count = agg['employee_count'] or 0
        total_evaluations = agg['total_evaluations'] or 0

        # 7. 통합 작업서 생성 (batch_work_order_service.create_work_order()는 별도
        #    커넥션으로 즉시 commit하므로 여기서는 재사용하지 않고 직접 INSERT한다
        #    — 이 트랜잭션이 열려 있는 동안 별도 커넥션 쓰기는 SQLITE_BUSY 위험)
        batch_dir = os.path.join(processed_data_dir, 'batch', merged_batch_id)
        settings_json = json.dumps({'merged_from': list(source_batch_ids)}, ensure_ascii=False)
        file_info_json = json.dumps({'merge': True}, ensure_ascii=False)
        conn.execute("""
            INSERT INTO batch_work_orders
                (batch_id, batch_dir, status, settings, file_info,
                 total_employees, processed_employees, success_count, error_count,
                 total_rows, completed_employees, created_at, updated_at, completed_at)
            VALUES (?, ?, 'completed', ?, ?, ?, ?, ?, 0, ?, '[]',
                    datetime('now','localtime'), datetime('now','localtime'),
                    datetime('now','localtime'))
        """, (
            merged_batch_id, batch_dir, settings_json, file_info_json,
            employee_count, employee_count, employee_count, total_evaluations,
        ))

        # 8. 원본 작업서 status='merged'
        placeholders = ','.join('?' * len(source_batch_ids))
        conn.execute(f"""
            UPDATE batch_work_orders
               SET status = 'merged', updated_at = datetime('now','localtime')
             WHERE batch_id IN ({placeholders})
        """, tuple(source_batch_ids))

        # 9. batch_merges 이력 기록
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for bid in source_batch_ids:
            conn.execute("""
                INSERT INTO batch_merges
                    (merged_batch_id, source_batch_id, moved_count, source_status, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (merged_batch_id, bid, moved_counts.get(bid, 0), source_statuses.get(bid, ''), now_str))

        # 10. 물리 폴더 batch_summary.json (tdata + tmeta)
        _write_batch_summary(
            processed_data_dir, merged_batch_id, display_name,
            employee_count, total_evaluations, source_batch_ids,
        )

        # 11. commit
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        'success': True,
        'batch_id': merged_batch_id,
        'moved': sum(moved_counts.values()),
        'employee_count': employee_count,
        'total_evaluations': total_evaluations,
        'sources': list(source_batch_ids),
    }
