"""20_09 §3.2(가명 역변환 배치화) + 계측 T1~T6.

이 계획서의 핵심 위험은 "빠르게 만들다가 복원 결과가 달라지는 것"이다
(가명 관리 절대 규칙 §2 — 조회 시 원본 복원). 그래서 T2·T3은 속도가 아니라
**바꾸기 전 방식(get_real_id 건별 호출)과 결과가 1비트도 다르지 않은지**를 본다.

속도 자체(실제 몇 ms 빨라졌는지)는 서버 기동이 필요해 여기서 재지 않는다 — 서버
로그(STAGE:PERF)와 브라우저 콘솔([PERF])로 사용자가 실측한다.
"""
import pytest


# ---------------------------------------------------------------------------
# T1. get_real_id_map() — 매핑 스냅샷은 읽기 전용 사본이다
# ---------------------------------------------------------------------------
def test_t1_real_id_map_is_defensive_copy(tmp_db, reset_pseudo_mgr):
    import src.services.perspective_service as ps

    mgr = ps._get_pseudo_mgr()
    mgr.link_mapping('평가자_AAA111', 'REAL_1')
    mgr.link_mapping('평가자_BBB222', 'REAL_2')

    snapshot = mgr.get_real_id_map()
    assert snapshot == {'평가자_AAA111': 'REAL_1', '평가자_BBB222': 'REAL_2'}

    # 사본을 오염시켜도 매니저 내부 매핑은 그대로여야 한다(가명 매핑 보호).
    snapshot['평가자_AAA111'] = 'TAMPERED'
    snapshot.pop('평가자_BBB222')
    assert mgr.get_real_id('평가자_AAA111') == 'REAL_1'
    assert mgr.get_real_id('평가자_BBB222') == 'REAL_2'
    assert mgr.get_real_id_map() == {'평가자_AAA111': 'REAL_1', '평가자_BBB222': 'REAL_2'}


# ---------------------------------------------------------------------------
# T2. 배치 해석기 == get_real_id() (경계값 포함 전수 대조)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('value', [
    '평가자_AAA111',      # 매핑 있음
    '  평가자_AAA111  ',  # 앞뒤 공백 — strip 후 조회
    '평가자_ZZZ999',      # 가명 형태지만 매핑 없음
    '개발팀',             # 애초에 가명이 아닌 값(부서 등)
    '',                   # 빈 문자열
    '   ',                # 공백뿐
    None,                 # None
    0,                    # falsy 비문자열
    12345,                # 비문자열
])
def test_t2_resolver_matches_get_real_id(tmp_db, reset_pseudo_mgr, value):
    import src.services.perspective_service as ps

    mgr = ps._get_pseudo_mgr()
    mgr.link_mapping('평가자_AAA111', 'REAL_1')

    resolver = ps._make_real_id_resolver(mgr)
    assert resolver(value) == mgr.get_real_id(value)


# ---------------------------------------------------------------------------
# T3. /meta enrich 결과가 종전(건별 get_real_id) 방식과 동일하다
# ---------------------------------------------------------------------------
def test_t3_meta_enrich_output_unchanged(tmp_db, add_employee, reset_pseudo_mgr, tmp_path):
    import src.services.perspective_service as ps

    mgr = ps._get_pseudo_mgr()
    add_employee('평가자_AAA111', name='평가자_NAME1', dept='평가자_DEPT1', pos='부장')
    add_employee('평가자_BBB222', name='평가자_NAME2', dept='개발팀', pos='사원')
    add_employee('평가자_CCC333', name=None, dept=None, pos=None)
    mgr.link_mapping('평가자_AAA111', 'E0001')
    mgr.link_mapping('평가자_NAME1', '홍길동')
    mgr.link_mapping('평가자_DEPT1', '인사처')
    # BBB222 계열은 일부러 매핑 없음 — 미복원 경로도 같이 대조한다

    meta = ps.get_matrix_meta_light(enrich=True, processed_data_dir=str(tmp_path))
    got = {e['employee_id']: e for e in meta['employees']}

    # 종전 구현과 같은 규칙을 그 자리에서 재계산해 기대값을 만든다
    def old_dr(v):
        if not v:
            return v
        r = mgr.get_real_id(str(v))
        return r if r != v else v

    expected = {}
    for pseudo, name, dept, pos in [
        ('평가자_AAA111', '평가자_NAME1', '평가자_DEPT1', '부장'),
        ('평가자_BBB222', '평가자_NAME2', '개발팀', '사원'),
        ('평가자_CCC333', None, None, None),
    ]:
        real_id = old_dr(pseudo)
        expected[real_id] = {
            'employee_id': real_id,
            'employee_id_real': real_id if real_id != pseudo else None,
            'employee_name': old_dr(name) if name else None,
            'department': old_dr(dept) if dept else dept,
            'position': old_dr(pos) if pos else pos,
            'evaluation_count': 1,
        }

    assert set(got) == set(expected)
    for emp_id, exp in expected.items():
        for key, val in exp.items():
            assert got[emp_id][key] == val, f'{emp_id}.{key}'

    # 실제로 복원이 일어났는지(=대조가 공허하지 않은지) 확인
    assert 'E0001' in got
    assert got['E0001']['employee_name'] == '홍길동'
    assert got['E0001']['department'] == '인사처'
    assert got['평가자_BBB222']['employee_id_real'] is None


# ---------------------------------------------------------------------------
# T4. enrich=False 는 가명 그대로 — 노출 규칙 불변
# ---------------------------------------------------------------------------
def test_t4_meta_without_enrich_keeps_pseudonyms(tmp_db, add_employee, reset_pseudo_mgr, tmp_path):
    import src.services.perspective_service as ps

    add_employee('평가자_AAA111', name='평가자_NAME1')
    ps._get_pseudo_mgr().link_mapping('평가자_AAA111', 'E0001')

    meta = ps.get_matrix_meta_light(enrich=False, processed_data_dir=str(tmp_path))
    entry = meta['employees'][0]
    assert entry['employee_id'] == '평가자_AAA111'
    assert entry['employee_name'] == '평가자_NAME1'
    assert 'employee_id_real' not in entry


# ---------------------------------------------------------------------------
# T5. perf_span 은 흐름을 바꾸지 않는다(반환·예외 그대로)
# ---------------------------------------------------------------------------
def test_t5_perf_span_is_transparent():
    from utils.perf import perf_span

    out = []
    with perf_span('t5.ok', rows=3):
        out.append(1)
    assert out == [1]

    with pytest.raises(ValueError):
        with perf_span('t5.raise'):
            raise ValueError('boom')


# ---------------------------------------------------------------------------
# T6. 요청 계측 훅을 걸어도 응답이 그대로다
# ---------------------------------------------------------------------------
def test_t6_request_timing_hook_preserves_response():
    from flask import Flask, jsonify
    from utils.perf import install_request_timing

    app = Flask(__name__)

    @app.route('/ping')
    def _ping():
        return jsonify({'success': True, 'v': 42})

    @app.route('/boom')
    def _boom():
        raise RuntimeError('boom')

    install_request_timing(app)
    client = app.test_client()

    res = client.get('/ping')
    assert res.status_code == 200
    assert res.get_json() == {'success': True, 'v': 42}

    # 핸들러가 터져도 계측 훅이 2차 예외를 만들지 않는다(500이 그대로 나온다)
    res2 = client.get('/boom')
    assert res2.status_code == 500
