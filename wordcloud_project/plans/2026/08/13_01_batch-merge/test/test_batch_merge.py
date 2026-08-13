"""배치 병합 기능 T1~T9 (계획서 §7).

서버 기동 없이 임시 sqlite 파일로 검증한다(DL-12, conftest.tmp_db).
"""
import os
import sqlite3
import pytest

from conftest import (
    insert_employee, insert_evaluation, insert_work_order,
    insert_work_order_item, insert_profanity_employee, insert_acquired_sentence,
)


# ---------------------------------------------------------------------------
# T1. 스키마 v9 적용
# ---------------------------------------------------------------------------
def test_t1_schema_v9(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        max_version = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_version"
        ).fetchone()[0]
        assert max_version == 9, f"schema_version 최대값이 9가 아님: {max_version}"

        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert 'batch_merges' in tables

        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )}
        assert 'idx_bm_merged' in indexes
        assert 'idx_bm_source' in indexes

        cols = {r[1] for r in conn.execute("PRAGMA table_info(evaluations)")}
        assert 'orig_batch_id' in cols
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# T2. 2개 배치 병합 — 평가 보존
# ---------------------------------------------------------------------------
def test_t2_merge_preserves_evaluation_count(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches

    for i in range(3):
        insert_evaluation(db_conn, f'EMP_A{i}', 'BATCH_A', f'fpA{i}')
    for i in range(2):
        insert_evaluation(db_conn, f'EMP_A{i}', 'BATCH_A', f'fpA{i}_2')  # 3명 중 2명 다건
    for i in range(2):
        insert_evaluation(db_conn, f'EMP_B{i}', 'BATCH_B', f'fpB{i}')
    for i in range(1):
        insert_evaluation(db_conn, f'EMP_B{i}', 'BATCH_B', f'fpB{i}_2')
    insert_work_order(db_conn, 'BATCH_A', success_count=3, total_rows=5)
    insert_work_order(db_conn, 'BATCH_B', success_count=2, total_rows=3)
    db_conn.commit()

    total_before = db_conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
    assert total_before == 8

    result = merge_batches(['BATCH_A', 'BATCH_B'], display_name='통합테스트',
                            new_batch_id='BATCH_MERGED_T2', processed_data_dir=processed_dir)

    assert result['success'] is True
    assert result['batch_id'] == 'BATCH_MERGED_T2'
    assert result['total_evaluations'] == 8

    conn2 = sqlite3.connect(tmp_db)
    try:
        merged_count = conn2.execute(
            "SELECT COUNT(*) FROM evaluations WHERE batch_id = ?", ('BATCH_MERGED_T2',)
        ).fetchone()[0]
        assert merged_count == 8

        a_count = conn2.execute(
            "SELECT COUNT(*) FROM evaluations WHERE batch_id = ?", ('BATCH_A',)
        ).fetchone()[0]
        b_count = conn2.execute(
            "SELECT COUNT(*) FROM evaluations WHERE batch_id = ?", ('BATCH_B',)
        ).fetchone()[0]
        assert a_count == 0
        assert b_count == 0

        total_after = conn2.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
        assert total_after == 8, "총 행수가 불변이어야 함(삭제·복제 없음)"
    finally:
        conn2.close()


# ---------------------------------------------------------------------------
# T3. 직원 중복 흡수
# ---------------------------------------------------------------------------
def test_t3_employee_dedup(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches

    for i in range(3):
        insert_evaluation(db_conn, f'EMP{i}', 'BATCH_A', f'fpA{i}')
    # BATCH_B: 2명, 그중 EMP0는 BATCH_A에도 있음(동일 직원, 다른 평가 → fingerprint 다르게)
    insert_evaluation(db_conn, 'EMP0', 'BATCH_B', 'fpB0')
    insert_evaluation(db_conn, 'EMP3', 'BATCH_B', 'fpB1')
    insert_work_order(db_conn, 'BATCH_A', success_count=3, total_rows=3)
    insert_work_order(db_conn, 'BATCH_B', success_count=2, total_rows=2)
    db_conn.commit()

    result = merge_batches(['BATCH_A', 'BATCH_B'], new_batch_id='BATCH_MERGED_T3',
                            processed_data_dir=processed_dir)

    assert result['employee_count'] == 4, "3+2-1(중복 EMP0)=4 이어야 함"

    conn2 = sqlite3.connect(tmp_db)
    try:
        distinct = conn2.execute(
            "SELECT COUNT(DISTINCT employee_id) FROM evaluations WHERE batch_id = ?",
            ('BATCH_MERGED_T3',)
        ).fetchone()[0]
        assert distinct == 4
    finally:
        conn2.close()


# ---------------------------------------------------------------------------
# T4. 작업서 items 병합
# ---------------------------------------------------------------------------
def test_t4_work_order_items_merge(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches

    insert_evaluation(db_conn, 'EMP0', 'BATCH_A', 'fpA0')
    insert_evaluation(db_conn, 'EMP1', 'BATCH_B', 'fpB0')
    insert_work_order(db_conn, 'BATCH_A', success_count=1, total_rows=1)
    insert_work_order(db_conn, 'BATCH_B', success_count=1, total_rows=1)
    insert_work_order_item(db_conn, 'BATCH_A', 'EMP0')
    insert_work_order_item(db_conn, 'BATCH_A', 'EMP_SHARED')
    insert_work_order_item(db_conn, 'BATCH_B', 'EMP1')
    insert_work_order_item(db_conn, 'BATCH_B', 'EMP_SHARED')  # 겹치는 직원
    db_conn.commit()

    merge_batches(['BATCH_A', 'BATCH_B'], new_batch_id='BATCH_MERGED_T4',
                  processed_data_dir=processed_dir)

    conn2 = sqlite3.connect(tmp_db)
    try:
        merged_items = {r[0] for r in conn2.execute(
            "SELECT employee_id FROM batch_work_order_items WHERE batch_id = ?",
            ('BATCH_MERGED_T4',)
        )}
        assert merged_items == {'EMP0', 'EMP1', 'EMP_SHARED'}, "PK 충돌 없이 중복 직원 1건으로 흡수돼야 함"

        remaining_a = conn2.execute(
            "SELECT COUNT(*) FROM batch_work_order_items WHERE batch_id = ?", ('BATCH_A',)
        ).fetchone()[0]
        remaining_b = conn2.execute(
            "SELECT COUNT(*) FROM batch_work_order_items WHERE batch_id = ?", ('BATCH_B',)
        ).fetchone()[0]
        assert remaining_a == 0
        assert remaining_b == 0
    finally:
        conn2.close()


# ---------------------------------------------------------------------------
# T5. 욕설·적립 문장 동반 이동
# ---------------------------------------------------------------------------
def test_t5_profanity_and_acquired_sentences_follow(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches

    insert_evaluation(db_conn, 'EMP0', 'BATCH_A', 'fpA0')
    insert_evaluation(db_conn, 'EMP1', 'BATCH_B', 'fpB0')
    insert_work_order(db_conn, 'BATCH_A', success_count=1, total_rows=1)
    insert_work_order(db_conn, 'BATCH_B', success_count=1, total_rows=1)
    insert_profanity_employee(db_conn, 'BATCH_A', 'EMP0', count=2)
    insert_profanity_employee(db_conn, 'BATCH_B', 'EMP1', count=1)
    insert_acquired_sentence(db_conn, 'BATCH_A', '문장 A')
    insert_acquired_sentence(db_conn, 'BATCH_B', '문장 B')
    db_conn.commit()

    merge_batches(['BATCH_A', 'BATCH_B'], new_batch_id='BATCH_MERGED_T5',
                  processed_data_dir=processed_dir)

    conn2 = sqlite3.connect(tmp_db)
    try:
        pe_merged = conn2.execute(
            "SELECT COUNT(*) FROM profanity_employees WHERE batch_id = ?", ('BATCH_MERGED_T5',)
        ).fetchone()[0]
        assert pe_merged == 2

        pe_orig = conn2.execute(
            "SELECT COUNT(*) FROM profanity_employees WHERE batch_id IN ('BATCH_A','BATCH_B')"
        ).fetchone()[0]
        assert pe_orig == 0

        acq_merged = conn2.execute(
            "SELECT COUNT(*) FROM acquired_sentences WHERE source_batch_id = ?",
            ('BATCH_MERGED_T5',)
        ).fetchone()[0]
        assert acq_merged == 2

        acq_orig = conn2.execute(
            "SELECT COUNT(*) FROM acquired_sentences WHERE source_batch_id IN ('BATCH_A','BATCH_B')"
        ).fetchone()[0]
        assert acq_orig == 0
    finally:
        conn2.close()


# ---------------------------------------------------------------------------
# T6. 목록에서 원본 숨김
# ---------------------------------------------------------------------------
def test_t6_hidden_from_batch_list(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches
    from src.services.perspective_service import _load_batch_list

    insert_evaluation(db_conn, 'EMP0', 'BATCH_A', 'fpA0')
    insert_evaluation(db_conn, 'EMP1', 'BATCH_B', 'fpB0')
    insert_work_order(db_conn, 'BATCH_A', success_count=1, total_rows=1)
    insert_work_order(db_conn, 'BATCH_B', success_count=1, total_rows=1)
    db_conn.commit()

    merge_batches(['BATCH_A', 'BATCH_B'], new_batch_id='BATCH_MERGED_T6',
                  processed_data_dir=processed_dir)

    batches = _load_batch_list(processed_dir)
    batch_ids = [b['batch_id'] for b in batches]
    assert 'BATCH_MERGED_T6' in batch_ids
    assert 'BATCH_A' not in batch_ids
    assert 'BATCH_B' not in batch_ids
    assert batch_ids.count('BATCH_MERGED_T6') == 1


# ---------------------------------------------------------------------------
# T7. 실패 시 롤백
# ---------------------------------------------------------------------------
def test_t7_rollback_on_failure(tmp_db, db_conn, processed_dir, monkeypatch):
    import src.services.batch_merge_service as bms

    insert_evaluation(db_conn, 'EMP0', 'BATCH_A', 'fpA0')
    insert_evaluation(db_conn, 'EMP1', 'BATCH_B', 'fpB0')
    insert_work_order(db_conn, 'BATCH_A', success_count=1, total_rows=1)
    insert_work_order(db_conn, 'BATCH_B', success_count=1, total_rows=1)
    insert_profanity_employee(db_conn, 'BATCH_A', 'EMP0', count=1)
    db_conn.commit()

    # 병합 전 상태 스냅샷
    def _snapshot():
        rows_ev = sorted(
            (r['employee_id'], r['batch_id'], r['orig_batch_id'])
            for r in db_conn.execute("SELECT employee_id, batch_id, orig_batch_id FROM evaluations")
        )
        rows_wo = sorted(
            (r['batch_id'], r['status'])
            for r in db_conn.execute("SELECT batch_id, status FROM batch_work_orders")
        )
        rows_pe = sorted(
            (r['batch_id'], r['employee_id'])
            for r in db_conn.execute("SELECT batch_id, employee_id FROM profanity_employees")
        )
        bm_count = db_conn.execute("SELECT COUNT(*) FROM batch_merges").fetchone()[0]
        return rows_ev, rows_wo, rows_pe, bm_count

    before = _snapshot()

    # 10단계(물리 폴더 기록) 직전에 강제 예외 주입 — 그 앞의 모든 UPDATE/INSERT가
    # 같은 트랜잭션 안에 있으므로 rollback 시 전부 원복돼야 한다.
    def _boom(*args, **kwargs):
        raise RuntimeError('강제 주입 실패(T7)')
    monkeypatch.setattr(bms, '_write_batch_summary', _boom)

    with pytest.raises(RuntimeError, match='강제 주입 실패'):
        bms.merge_batches(['BATCH_A', 'BATCH_B'], new_batch_id='BATCH_MERGED_T7',
                           processed_data_dir=processed_dir)

    after = _snapshot()
    assert before == after, "실패 시 모든 테이블이 병합 전 상태와 동일해야 함(rollback)"

    merged_wo = db_conn.execute(
        "SELECT COUNT(*) FROM batch_work_orders WHERE batch_id = ?", ('BATCH_MERGED_T7',)
    ).fetchone()[0]
    assert merged_wo == 0, "통합 작업서 행도 rollback으로 사라져야 함"


# ---------------------------------------------------------------------------
# T8. 배치 ID 형식 호환 — integrated_data_service.get_batch_list()의 파싱 규칙 통과
# ---------------------------------------------------------------------------
def test_t8_generated_id_format_compatible(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches

    insert_evaluation(db_conn, 'EMP0', 'BATCH_A', 'fpA0')
    insert_evaluation(db_conn, 'EMP1', 'BATCH_B', 'fpB0')
    insert_work_order(db_conn, 'BATCH_A', success_count=1, total_rows=1)
    insert_work_order(db_conn, 'BATCH_B', success_count=1, total_rows=1)
    db_conn.commit()

    result = merge_batches(['BATCH_A', 'BATCH_B'], processed_data_dir=processed_dir)
    new_id = result['batch_id']

    # integrated_data_service.get_batch_list()가 쓰는 필터·파싱을 그대로 재현
    assert new_id.startswith('batch_'), "item.startswith('batch_') 필터를 통과해야 함(D-2)"
    parts = new_id.split('_')
    assert len(parts) >= 3
    date_str = parts[1]
    assert len(date_str) == 8 and date_str.isdigit()
    batch_num = int(parts[2])  # 예외 없이 int 변환되어야 함
    assert batch_num >= 0


# ---------------------------------------------------------------------------
# T9. 입력 검증 (400/404/400)
# ---------------------------------------------------------------------------
def test_t9_validation_too_few(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches, BatchMergeError

    insert_evaluation(db_conn, 'EMP0', 'BATCH_A', 'fpA0')
    insert_work_order(db_conn, 'BATCH_A', success_count=1, total_rows=1)
    db_conn.commit()

    with pytest.raises(BatchMergeError) as exc_info:
        merge_batches(['BATCH_A'], processed_data_dir=processed_dir)
    assert exc_info.value.status_code == 400


def test_t9_validation_missing_batch(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches, BatchMergeError

    insert_evaluation(db_conn, 'EMP0', 'BATCH_A', 'fpA0')
    insert_work_order(db_conn, 'BATCH_A', success_count=1, total_rows=1)
    db_conn.commit()

    with pytest.raises(BatchMergeError) as exc_info:
        merge_batches(['BATCH_A', 'BATCH_NOT_EXIST'], processed_data_dir=processed_dir)
    assert exc_info.value.status_code == 404


def test_t9_validation_duplicate_batch(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches, BatchMergeError

    insert_evaluation(db_conn, 'EMP0', 'BATCH_A', 'fpA0')
    insert_work_order(db_conn, 'BATCH_A', success_count=1, total_rows=1)
    db_conn.commit()

    with pytest.raises(BatchMergeError) as exc_info:
        merge_batches(['BATCH_A', 'BATCH_A'], processed_data_dir=processed_dir)
    assert exc_info.value.status_code == 400


def test_t9_validation_running_batch_rejected(tmp_db, db_conn, processed_dir):
    """부록 — R-6: status='running'인 배치가 섞이면 병합을 거부한다."""
    from src.services.batch_merge_service import merge_batches, BatchMergeError

    insert_evaluation(db_conn, 'EMP0', 'BATCH_A', 'fpA0')
    insert_evaluation(db_conn, 'EMP1', 'BATCH_B', 'fpB0')
    insert_work_order(db_conn, 'BATCH_A', status='running', success_count=1, total_rows=1)
    insert_work_order(db_conn, 'BATCH_B', status='completed', success_count=1, total_rows=1)
    db_conn.commit()

    with pytest.raises(BatchMergeError) as exc_info:
        merge_batches(['BATCH_A', 'BATCH_B'], processed_data_dir=processed_dir)
    assert exc_info.value.status_code == 400
