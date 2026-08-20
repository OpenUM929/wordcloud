"""13_04 배치 병합 원본 삭제 옵션 T1~T4 (계획서 §5).

서버 기동 없이 임시 sqlite 파일로 검증한다(DL-12, conftest.tmp_db).
"""
import os
import sqlite3

from conftest import insert_evaluation, insert_work_order


def _setup_two_batches(db_conn):
    for i in range(2):
        insert_evaluation(db_conn, f'EMP_A{i}', 'BATCH_A', f'fpA{i}')
    for i in range(2):
        insert_evaluation(db_conn, f'EMP_B{i}', 'BATCH_B', f'fpB{i}')
    insert_work_order(db_conn, 'BATCH_A', success_count=2, total_rows=2)
    insert_work_order(db_conn, 'BATCH_B', success_count=2, total_rows=2)
    db_conn.commit()


# ---------------------------------------------------------------------------
# T1. delete_sources=False(기본) — 회귀 확인
# ---------------------------------------------------------------------------
def test_t1_default_keeps_source_as_merged(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches

    _setup_two_batches(db_conn)
    result = merge_batches(['BATCH_A', 'BATCH_B'], display_name='병합테스트',
                            new_batch_id='BATCH_M1', processed_data_dir=processed_dir)
    assert result['deleted_sources'] is False

    conn = sqlite3.connect(tmp_db)
    try:
        row = conn.execute(
            "SELECT status FROM batch_work_orders WHERE batch_id = 'BATCH_A'"
        ).fetchone()
        assert row is not None
        assert row[0] == 'merged'
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# T2. delete_sources=True — 원본 작업서 행 삭제, batch_merges 이력은 유지
# ---------------------------------------------------------------------------
def test_t2_delete_sources_removes_work_order_row(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches

    _setup_two_batches(db_conn)
    result = merge_batches(['BATCH_A', 'BATCH_B'], display_name='병합테스트',
                            new_batch_id='BATCH_M2', processed_data_dir=processed_dir,
                            delete_sources=True)
    assert result['deleted_sources'] is True

    conn = sqlite3.connect(tmp_db)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM batch_work_orders WHERE batch_id IN ('BATCH_A','BATCH_B')"
        ).fetchone()
        assert row[0] == 0, "원본 작업서 행이 남아있음"

        hist = conn.execute(
            "SELECT COUNT(*) FROM batch_merges WHERE merged_batch_id = 'BATCH_M2'"
        ).fetchone()
        assert hist[0] == 2, "병합 이력(batch_merges)이 원본별로 남아있어야 함"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# T3. 물리 폴더 삭제
# ---------------------------------------------------------------------------
def test_t3_delete_sources_removes_physical_folder(tmp_db, db_conn, processed_dir):
    from src.services.batch_merge_service import merge_batches

    _setup_two_batches(db_conn)
    src_dir = os.path.join(processed_dir, 'batch', 'BATCH_A')
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(src_dir, 'dummy.txt'), 'w') as f:
        f.write('x')
    assert os.path.isdir(src_dir)

    merge_batches(['BATCH_A', 'BATCH_B'], display_name='병합테스트',
                  new_batch_id='BATCH_M3', processed_data_dir=processed_dir,
                  delete_sources=True)

    assert not os.path.isdir(src_dir), "원본 물리 폴더가 삭제되지 않음"


# ---------------------------------------------------------------------------
# T4. 폴더 삭제 실패해도 API(함수) 전체는 성공
# ---------------------------------------------------------------------------
def test_t4_folder_delete_failure_does_not_fail_merge(tmp_db, db_conn, processed_dir, monkeypatch):
    from src.services import batch_merge_service
    from src.services.batch_merge_service import merge_batches

    _setup_two_batches(db_conn)

    def _fake_rmtree(path, ignore_errors=False):
        # 실제 shutil.rmtree(ignore_errors=True)는 내부 예외를 스스로 삼킨다.
        # 여기서는 코드가 실제로 ignore_errors=True를 넘기는지를 검증한다 —
        # 그렇지 않다면(True가 아니면) 예외를 던져 상위 merge_batches가 깨지는지 확인한다.
        if not ignore_errors:
            raise OSError("simulated rmtree failure — ignore_errors was not True")

    monkeypatch.setattr(batch_merge_service.shutil, 'rmtree', _fake_rmtree)

    src_dir = os.path.join(processed_dir, 'batch', 'BATCH_A')
    os.makedirs(src_dir, exist_ok=True)

    result = merge_batches(['BATCH_A', 'BATCH_B'], display_name='병합테스트',
                            new_batch_id='BATCH_M4', processed_data_dir=processed_dir,
                            delete_sources=True)
    assert result['success'] is True
    assert result['deleted_sources'] is True
