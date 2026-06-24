"""0619_03 — load_batch_history 경량 로더 단위 검증.

이력 조회 엔드포인트가 전체 코퍼스 적재(load_all_batches) 없이
batches 목록 + batch_info 카운트만 cheap COUNT 쿼리로 반환하는지,
employee_results를 적재하지 않는지(평가 본문 json.loads 미수행) 검증한다.

dev는 실배치 데이터가 없으므로([[project_dev_no_batch_csv_only]]) 임시 DB로 검증한다.
실행: python test_load_batch_history.py
"""
import json
import os
import sqlite3
import sys
import tempfile

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.services import perspective_service as ps


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE employees (employee_id TEXT, name TEXT, department TEXT, position TEXT)")
    conn.execute("CREATE TABLE evaluations (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id TEXT, data TEXT, batch_id TEXT, created_at TEXT)")
    conn.execute("INSERT INTO employees VALUES ('E1','가명일','생산부','사원')")
    conn.execute("INSERT INTO employees VALUES ('E2','가명이','품질부','대리')")
    conn.execute("INSERT INTO evaluations (employee_id, data, batch_id, created_at) VALUES ('E1', ?, 'B1', '2026-06-19')", (json.dumps({'evaluation_id': 'a', 'doc': '문서1'}),))
    conn.execute("INSERT INTO evaluations (employee_id, data, batch_id, created_at) VALUES ('E1', ?, 'B1', '2026-06-19')", (json.dumps({'evaluation_id': 'a', 'doc': '문서2'}),))
    conn.execute("INSERT INTO evaluations (employee_id, data, batch_id, created_at) VALUES ('E2', ?, 'B1', '2026-06-19')", (json.dumps({'evaluation_id': 'b', 'doc': '문서3'}),))
    # 작업서 테이블(이력 목록 소스). _load_batch_list가 조회한다.
    conn.execute("CREATE TABLE batch_work_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT, success_count INTEGER, total_rows INTEGER, created_at TEXT)")
    conn.execute("INSERT INTO batch_work_orders (batch_id, success_count, total_rows, created_at) VALUES ('B1', 2, 3, '2026-06-19')")
    conn.commit()
    conn.close()


def run():
    tmp_dir = tempfile.mkdtemp()
    tmp_db = os.path.join(tmp_dir, 'eval.db')
    _make_db(tmp_db)

    # _get_eval_conn은 sqlite3.Row 팩토리를 쓰는 _load_batch_list와 호환되도록 row_factory 설정
    def fake_conn():
        c = sqlite3.connect(tmp_db)
        c.row_factory = sqlite3.Row
        return c
    ps._get_eval_conn = fake_conn  # type: ignore
    # user_data_manager._get_eval_conn 도 _load_batch_list/_count_batches가 직접 import 하므로 패치
    from src.services import user_data_manager as udm
    udm._get_eval_conn = fake_conn  # type: ignore
    # display_name 파일 I/O 우회(임시 디렉토리에 summary 파일 없음 → '' 반환, 호출만 검증)

    # json.loads 호출 감시: 평가 본문을 적재하지 않아야 함
    import json as _json_mod
    calls = {'n': 0}
    _orig_loads = _json_mod.loads
    def _watch_loads(*a, **k):
        calls['n'] += 1
        return _orig_loads(*a, **k)
    _json_mod.loads = _watch_loads
    try:
        result = ps.load_batch_history(processed_data_dir=tmp_dir)
    finally:
        _json_mod.loads = _orig_loads

    # 1) employee_results 키가 없어야 한다(경량 로더)
    assert 'employee_results' not in result, 'employee_results를 적재하면 안 됨'

    # 2) batch_info 카운트 정확성
    info = result['batch_info']
    assert info['unique_employees'] == 2, f"unique_employees: {info['unique_employees']}"
    assert info['total_evaluations'] == 3, f"total_evaluations: {info['total_evaluations']}"

    # 3) batches 목록 반환(작업서 기준 B1)
    bids = [b['batch_id'] for b in result['batches']]
    assert 'B1' in bids, f'배치 목록 누락: {bids}'

    # 4) 평가 본문 json.loads 미수행(employee 평가 적재 안 함)
    assert calls['n'] == 0, f'평가 본문 json.loads가 호출됨({calls["n"]}회) — 경량 로더 위반'

    print('OK: load_batch_history 경량 로더 검증 통과 (employee_results 미적재, 카운트 정확, json.loads 0회)')


if __name__ == '__main__':
    run()
