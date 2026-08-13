"""0619_03 후속 — get_matrix_meta_light 경량 메타 빌더 단위/패리티 검증.

X축(시간/회차) 메타(/api/perspective/meta)가 전체 코퍼스 적재(load_all_batches +
get_matrix_meta) 없이, evaluations의 인덱스 컬럼(evaluation_date·batch_id)을
GROUP BY 집계만으로 동일한 row_options/employees/카운트를 만드는지 검증한다.

검증 항목:
  1) 기존 경로(load_all_batches+get_matrix_meta)와 row_options 완전 일치(패리티)
  2) employees 목록·total_evaluations·batch_count 일치
  3) 경량 빌더는 평가 본문 json.loads를 0회 수행(data blob 미적재)

dev는 실배치 데이터가 없으므로([[project_dev_no_batch_csv_only]]) 임시 DB로 검증한다.
실행: python test_get_matrix_meta_light.py
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


# (employee_id, name, dept, pos, evaluation_date, batch_id) — 컬럼과 blob을 동일 값으로 채운다
_ROWS = [
    ('E1', '가명일', '생산부', '사원', '2026-06-19', 'B1'),
    ('E1', '가명일', '생산부', '사원', '2026-06-19', 'B1'),
    ('E1', '가명일', '생산부', '사원', '2025-05-10', 'B2'),
    ('E2', '가명이', '품질부', '대리', '2026-07-01', 'B1'),
    ('E2', '가명이', '품질부', '대리', '', 'B2'),  # 빈 날짜 — '' 버킷/year·month 스킵 경계
]


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE employees (employee_id TEXT, name TEXT, department TEXT, position TEXT)")
    conn.execute(
        "CREATE TABLE evaluations (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "employee_id TEXT, evaluator_id TEXT, evaluation_date TEXT, batch_id TEXT, "
        "data TEXT, fingerprint TEXT, created_at TEXT)"
    )
    seen_emp = set()
    for emp_id, name, dept, pos, ev_date, batch_id in _ROWS:
        if emp_id not in seen_emp:
            seen_emp.add(emp_id)
            conn.execute("INSERT INTO employees VALUES (?,?,?,?)", (emp_id, name, dept, pos))
        # blob은 실제 insert(user_data_manager)처럼 evaluation_date·batch_id 키를 포함
        blob = json.dumps({'evaluation_date': ev_date, 'batch_id': batch_id, 'doc': '문서'})
        conn.execute(
            "INSERT INTO evaluations (employee_id, evaluation_date, batch_id, data) VALUES (?,?,?,?)",
            (emp_id, ev_date, batch_id, blob),
        )
    conn.execute("CREATE TABLE batch_work_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT, success_count INTEGER, total_rows INTEGER, created_at TEXT)")
    conn.execute("INSERT INTO batch_work_orders (batch_id, success_count, total_rows, created_at) VALUES ('B1', 3, 3, '2026-06-19')")
    conn.execute("INSERT INTO batch_work_orders (batch_id, success_count, total_rows, created_at) VALUES ('B2', 2, 2, '2025-05-10')")
    conn.commit()
    conn.close()


def run():
    tmp_dir = tempfile.mkdtemp()
    tmp_db = os.path.join(tmp_dir, 'eval.db')
    _make_db(tmp_db)

    def fake_conn():
        c = sqlite3.connect(tmp_db)
        c.row_factory = sqlite3.Row
        return c
    ps._get_eval_conn = fake_conn  # type: ignore
    from src.services import user_data_manager as udm
    udm._get_eval_conn = fake_conn  # type: ignore

    # json.loads 호출 감시 — 평가 본문 적재량이 평가 건수에 비례하는지 비교
    import json as _json_mod
    _orig_loads = _json_mod.loads
    counter = {'n': 0}
    def _watch_loads(*a, **k):
        counter['n'] += 1
        return _orig_loads(*a, **k)

    # 기존 경로(무거운): load_all_batches + get_matrix_meta — 평가 1건당 json.loads 1회
    _json_mod.loads = _watch_loads
    counter['n'] = 0
    try:
        unified = ps.load_all_batches(processed_data_dir=tmp_dir)
        meta_old = ps.get_matrix_meta(unified, employee_id=None, enrich=False)
    finally:
        _json_mod.loads = _orig_loads
    old_loads = counter['n']

    # 신규 경로(경량): get_matrix_meta_light — 평가 본문 미적재(설정 로드 외 호출 없음)
    _json_mod.loads = _watch_loads
    counter['n'] = 0
    try:
        meta_new = ps.get_matrix_meta_light(employee_id=None, enrich=False, processed_data_dir=tmp_dir)
    finally:
        _json_mod.loads = _orig_loads
    new_loads = counter['n']

    # 1) row_options 패리티 (X축 핵심)
    assert meta_new['row_options'] == meta_old['row_options'], (
        f"row_options 불일치:\n  old={meta_old['row_options']}\n  new={meta_new['row_options']}"
    )

    # 2) employees / 카운트 패리티
    assert meta_new['employees'] == meta_old['employees'], (
        f"employees 불일치:\n  old={meta_old['employees']}\n  new={meta_new['employees']}"
    )
    assert meta_new['total_evaluations'] == meta_old['total_evaluations'] == 5, (
        f"total_evaluations: old={meta_old['total_evaluations']} new={meta_new['total_evaluations']}"
    )
    assert meta_new['batch_count'] == meta_old['batch_count'], (
        f"batch_count: old={meta_old['batch_count']} new={meta_new['batch_count']}"
    )

    # 3) 경량 빌더는 평가 본문을 적재하지 않는다 — 평가 건수(5)에 비례하지 않음.
    #    기존 경로는 평가 1건당 json.loads(>=5회), 경량 빌더는 평가 본문 0회(설정 로드 외).
    assert old_loads >= len(_ROWS), f'기존 경로 json.loads({old_loads})가 평가 건수 미만 — 테스트 전제 오류'
    assert new_loads < len(_ROWS), f'경량 빌더 json.loads({new_loads})가 평가 건수에 비례 — blob 적재 의심'
    assert new_loads <= 1, f'경량 빌더 json.loads {new_loads}회 — 설정 로드 외 호출 발생'

    # X축 버킷 내용 sanity(회차/연/월)
    ro = {r['field']: r['values'] for r in meta_new['row_options']}
    years = {v['value']: v['count'] for v in ro['evaluation_date__year']}
    assert years == {'2026': 3, '2025': 1}, f"연도 버킷: {years}"   # 빈 날짜 1건은 year 스킵
    batches = {v['value']: v['count'] for v in ro['batch_id']}
    assert batches == {'B1': 3, 'B2': 2}, f"회차 버킷: {batches}"
    months = {v['value']: v['count'] for v in ro['evaluation_date__month']}
    assert months == {'06': 2, '05': 1, '07': 1}, f"월 버킷: {months}"

    print(f'OK: get_matrix_meta_light 패리티 통과 '
          f'(row_options/employees/카운트 기존 경로와 동일, json.loads {old_loads}→{new_loads}회)')


if __name__ == '__main__':
    run()
