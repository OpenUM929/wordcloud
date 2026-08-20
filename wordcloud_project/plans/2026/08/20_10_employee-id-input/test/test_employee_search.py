"""20_10 직원 검색 엔드포인트 T1~T6 (계획서 §6).

프론트 교체(입력창·제안 UI)는 브라우저 검증(PND) 대상이라, 여기서는 그 UI가 의존하는
검색 계약(부분일치·limit·배치 스코프·노출 규칙)을 서버 기동 없이 검증한다.
"""


def _ids(results):
    return {r['employee_id'] for r in results}


# ---------------------------------------------------------------------------
# T1. 사번 부분일치 — 일부만 입력해도 찾힌다
# ---------------------------------------------------------------------------
def test_t1_partial_id_match(tmp_db, add_employee, reset_pseudo_mgr):
    from src.services.perspective_service import search_employees

    add_employee('A1001')
    add_employee('A1002')
    add_employee('B2001')

    assert _ids(search_employees('A10')) == {'A1001', 'A1002'}
    assert _ids(search_employees('2001')) == {'B2001'}
    assert _ids(search_employees('1002')) == {'A1002'}


# ---------------------------------------------------------------------------
# T2. 이름 부분일치 + 건수 반환
# ---------------------------------------------------------------------------
def test_t2_name_match_and_counts(tmp_db, add_employee, reset_pseudo_mgr):
    from src.services.perspective_service import search_employees

    add_employee('A1001', name='pseudo-kim', evals=3)
    add_employee('A1002', name='pseudo-lee', evals=1)

    res = search_employees('kim')
    assert len(res) == 1
    assert res[0]['employee_id'] == 'A1001'
    assert res[0]['evaluation_count'] == 3
    assert res[0]['department'] == '개발팀'


# ---------------------------------------------------------------------------
# T3. limit — 기본/상한/하한
# ---------------------------------------------------------------------------
def test_t3_limit_is_enforced(tmp_db, add_employee, reset_pseudo_mgr):
    from src.services.perspective_service import search_employees

    for i in range(30):
        add_employee(f'A{1000 + i}')

    assert len(search_employees('A10')) == 20           # 기본 limit
    assert len(search_employees('A10', limit=5)) == 5
    assert len(search_employees('A10', limit=0)) == 1   # 하한 clamp
    assert len(search_employees('A10', limit=9999)) == 30  # 상한(100) clamp — 전체 30건
    assert len(search_employees('A10', limit='xx')) == 20  # 잘못된 값은 기본값


# ---------------------------------------------------------------------------
# T4. 빈 쿼리는 아무것도 반환하지 않는다(전 직원 덤프 방지)
# ---------------------------------------------------------------------------
def test_t4_empty_query_returns_nothing(tmp_db, add_employee, reset_pseudo_mgr):
    from src.services.perspective_service import search_employees

    add_employee('A1001')
    assert search_employees('') == []
    assert search_employees('   ') == []
    assert search_employees(None) == []


# ---------------------------------------------------------------------------
# T5. 배치 범위(13_05)와 동일 규칙 — 그 배치에 평가가 있는 직원만
# ---------------------------------------------------------------------------
def test_t5_batch_scope_applies(tmp_db, add_employee, reset_pseudo_mgr):
    from src.services.perspective_service import search_employees

    add_employee('A1001', batch_id='BATCH_1')
    add_employee('A1002', batch_id='BATCH_2')

    assert _ids(search_employees('A10')) == {'A1001', 'A1002'}
    assert _ids(search_employees('A10', batch_ids=['BATCH_1'])) == {'A1001'}
    assert _ids(search_employees('A10', batch_ids=['BATCH_9'])) == set()


# ---------------------------------------------------------------------------
# T6. 노출 규칙 — 원본 사번 검색은 관리자(enrich)만, 비관리자에겐 가명만
# ---------------------------------------------------------------------------
def test_t6_real_id_search_admin_only(tmp_db, add_employee, reset_pseudo_mgr):
    import src.services.perspective_service as ps

    add_employee('PSEUDO_X', name='pseudo-name')
    ps._get_pseudo_mgr().link_mapping('PSEUDO_X', 'REAL9999')

    # 비관리자: 원본 사번으로는 찾히지 않고, 결과에 원본 값도 실리지 않는다
    plain = ps.search_employees('REAL9999', enrich=False)
    assert plain == []
    by_pseudo = ps.search_employees('PSEUDO_X', enrich=False)
    assert by_pseudo[0]['employee_id'] == 'PSEUDO_X'
    assert 'employee_id_real' not in by_pseudo[0]

    # 관리자: 원본 사번으로 찾히고, 결과는 원본 값으로 복원된다
    admin = ps.search_employees('REAL9999', enrich=True)
    assert len(admin) == 1
    assert admin[0]['employee_id'] == 'REAL9999'
    assert admin[0]['employee_id_real'] == 'REAL9999'
