"""0619_02 — load_employee_batch / list_all_employee_ids 단위 검증.

임시 SQLite DB로 perspective_service._get_eval_conn 을 대체하여,
직원 단위 로더가 (1) 1명만 담는지 (2) 반환 구조/_db_id 계약을 지키는지
(3) ID 목록 조회가 평가 미적재로 동작하는지 검증한다.

dev는 실배치 데이터가 없으므로([[project_dev_no_batch_csv_only]]) 임시 DB로 검증한다.
실행: python -m pytest test_load_employee_batch.py -q   (또는 직접 실행)
"""
import json
import os
import sqlite3
import sys
import tempfile

# perspective_service 임포트 경로 확보 (wordcloud_project 루트)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.services import perspective_service as ps


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE employees (employee_id TEXT, name TEXT, department TEXT, position TEXT)")
    conn.execute("CREATE TABLE evaluations (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id TEXT, data TEXT)")
    conn.execute("INSERT INTO employees VALUES ('E1','가명일','생산부','사원')")
    conn.execute("INSERT INTO employees VALUES ('E2','가명이','품질부','대리')")
    conn.execute("INSERT INTO evaluations (employee_id, data) VALUES ('E1', ?)", (json.dumps({'evaluation_id': 'a', 'doc': '문서1'}),))
    conn.execute("INSERT INTO evaluations (employee_id, data) VALUES ('E1', ?)", (json.dumps({'evaluation_id': 'a', 'doc': '문서2'}),))  # eval_id 중복 의도
    conn.execute("INSERT INTO evaluations (employee_id, data) VALUES ('E2', ?)", (json.dumps({'evaluation_id': 'b', 'doc': '문서3'}),))
    conn.commit()
    conn.close()


def _patch(tmp_db, monkeypatch=None):
    def fake_conn():
        return sqlite3.connect(tmp_db)
    ps._get_eval_conn = fake_conn                      # type: ignore
    ps._resolve_to_pseudo = lambda input_id, mgr: input_id   # 가명 변환 우회(항등)
    ps._get_pseudo_mgr = lambda: object()


def run():
    tmp_dir = tempfile.mkdtemp()
    tmp_db = os.path.join(tmp_dir, 'eval.db')
    _make_db(tmp_db)
    _patch(tmp_db)

    # 1) load_employee_batch: E1만 담기는가
    uni = ps.load_employee_batch('E1')
    assert len(uni['employee_results']) == 1, '직원 1명만 포함해야 함'
    meta = uni['employee_results'][0]['metadata']
    assert meta['target_employee_id'] == 'E1', '매칭 키는 가명 ID(E1) 고정'
    assert meta['target_employee_name'] == '가명일'
    evals = meta['evaluations']
    assert len(evals) == 2, 'E1 평가 2건'
    # _db_id 계약: 고유 DB row id가 주입되어야 함(eval_id 중복과 무관)
    db_ids = sorted(e['_db_id'] for e in evals)
    assert db_ids == [1, 2], f'_db_id 주입 실패: {db_ids}'

    # 2) 소비 함수 호환: _get_evaluations_for_employee 가 1명짜리 unified에서 동작
    items = ps._get_evaluations_for_employee(uni, 'E1')
    assert len(items) == 2 and items[0]['employee_id'] == 'E1'

    # 3) 존재하지 않는 직원 → 빈 구조(예외 없이)
    empty = ps.load_employee_batch('NOPE')
    assert empty['employee_results'] == []

    # 4) list_all_employee_ids: 평가 보유 직원 ID만, 정렬
    ids = ps.list_all_employee_ids()
    assert ids == ['E1', 'E2'], f'ID 목록 불일치: {ids}'

    print('OK: load_employee_batch / list_all_employee_ids 검증 통과')


if __name__ == '__main__':
    run()
