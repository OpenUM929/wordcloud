"""13_05 배치 범위 필터 T1~T8 (계획서 §6).

서버 기동 없이 임시 sqlite + 격리된 가명 매니저로 검증한다(DL-12).
"""
import json


def insert_evaluation(conn, employee_id, batch_id, fingerprint, evaluator_id='ev1',
                      evaluation_date='2025-01-01', data=None):
    """평가 1건 삽입. data를 주면 블롭을 그대로 저장한다(T8: 컬럼↔블롭 불일치 재현).

    다른 계획 폴더의 conftest와 이름이 겹쳐 `from conftest import ...`가 엉키는 것을
    피하려고(여러 test 폴더를 한 번에 실행할 때) 이 모듈 안에 둔다.
    """
    conn.execute(
        "INSERT OR IGNORE INTO employees (employee_id, name) VALUES (?, ?)",
        (employee_id, employee_id))
    conn.execute("""
        INSERT INTO evaluations (employee_id, evaluator_id, evaluation_date, batch_id, data, fingerprint)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (employee_id, evaluator_id, evaluation_date, batch_id, data or '{}', fingerprint))


def _setup_two_employees_two_batches(db_conn):
    # 직원 A: BATCH_1에만 평가
    insert_evaluation(db_conn, 'EMP_A', 'BATCH_1', 'fpA1', evaluation_date='2025-03-01')
    # 직원 B: BATCH_2에만 평가
    insert_evaluation(db_conn, 'EMP_B', 'BATCH_2', 'fpB1', evaluation_date='2026-05-01')
    db_conn.commit()


# ---------------------------------------------------------------------------
# T1. batch_ids 미지정 — 회귀 확인
# ---------------------------------------------------------------------------
def test_t1_no_batch_ids_matches_legacy_call(tmp_db, db_conn, reset_pseudo_mgr):
    from src.services.perspective_service import get_matrix_meta_light

    _setup_two_employees_two_batches(db_conn)

    meta_legacy = get_matrix_meta_light(employee_id=None, enrich=False)
    meta_new = get_matrix_meta_light(employee_id=None, batch_ids=None, enrich=False)
    meta_empty_list = get_matrix_meta_light(employee_id=None, batch_ids=[], enrich=False)

    for m in (meta_legacy, meta_new, meta_empty_list):
        assert len(m['employees']) == 2
        assert m['total_evaluations'] == 2


# ---------------------------------------------------------------------------
# T2. /meta에 특정 배치 1개만 지정 — 대상 직원 목록이 좁혀짐
# ---------------------------------------------------------------------------
def test_t2_batch_ids_filters_employee_list(tmp_db, db_conn, reset_pseudo_mgr):
    from src.services.perspective_service import get_matrix_meta_light

    _setup_two_employees_two_batches(db_conn)

    meta = get_matrix_meta_light(employee_id=None, batch_ids=['BATCH_1'], enrich=False)
    emp_ids = {e['employee_id'] for e in meta['employees']}
    assert emp_ids == {'EMP_A'}
    assert meta['total_evaluations'] == 1


# ---------------------------------------------------------------------------
# T3. /matrix에 배치 필터 적용 — 다른 배치 평가가 집계에서 빠짐
# ---------------------------------------------------------------------------
def test_t3_matrix_batch_filter_excludes_other_batch(reset_pseudo_mgr):
    from src.services.perspective_service import generate_perspective_matrix

    unified = {
        'employee_results': [{
            'metadata': {
                'target_employee_id': 'EMP_X',
                'target_employee_department': '개발팀',
                'target_employee_position': '사원',
                'evaluations': [
                    {'batch_id': 'BATCH_1', 'evaluation_date': '2025-01-01', 'evaluator_id': 'e1'},
                    {'batch_id': 'BATCH_2', 'evaluation_date': '2025-06-01', 'evaluator_id': 'e2'},
                ],
            }
        }]
    }
    options = {'analysis_types': [], 'generate_png': False}

    result_all = generate_perspective_matrix(unified, 'EMP_X', 'batch_id', 'all', 'nlp', options)
    assert set(result_all['rows']) == {'BATCH_1', 'BATCH_2'}
    assert result_all['matrix']['BATCH_1']['전체']['evaluation_count'] == 1
    assert result_all['matrix']['BATCH_2']['전체']['evaluation_count'] == 1

    options_filtered = {'analysis_types': [], 'generate_png': False, 'batch_ids': ['BATCH_1']}
    result_filtered = generate_perspective_matrix(unified, 'EMP_X', 'batch_id', 'all', 'nlp', options_filtered)
    assert result_filtered['rows'] == ['BATCH_1']
    assert result_filtered['matrix']['BATCH_1']['전체']['evaluation_count'] == 1


# ---------------------------------------------------------------------------
# T4. 배치 필터 + row_field=연도 동시 사용 — 축과 독립적으로 동작
# ---------------------------------------------------------------------------
def test_t4_batch_filter_independent_of_row_field(reset_pseudo_mgr):
    from src.services.perspective_service import generate_perspective_matrix

    unified = {
        'employee_results': [{
            'metadata': {
                'target_employee_id': 'EMP_Y',
                'target_employee_department': '개발팀',
                'target_employee_position': '사원',
                'evaluations': [
                    {'batch_id': 'BATCH_2025', 'evaluation_date': '2025-01-01', 'evaluator_id': 'e1'},
                    {'batch_id': 'BATCH_2026', 'evaluation_date': '2026-01-01', 'evaluator_id': 'e2'},
                ],
            }
        }]
    }
    options = {'analysis_types': [], 'generate_png': False, 'batch_ids': ['BATCH_2025']}

    result = generate_perspective_matrix(unified, 'EMP_Y', 'evaluation_date__year', 'all', 'nlp', options)
    assert result['rows'] == ['2025'], "batch_ids=[BATCH_2025]인데 2026년이 결과 열에 나타남(축과 독립적이지 않음)"


# ---------------------------------------------------------------------------
# T5. 빈 배열과 파라미터 생략이 동일 결과인지
# ---------------------------------------------------------------------------
def test_t5_empty_list_equals_omitted_param(tmp_db, db_conn, reset_pseudo_mgr):
    from src.services.perspective_service import get_matrix_meta_light

    _setup_two_employees_two_batches(db_conn)

    meta_omitted = get_matrix_meta_light(employee_id=None, enrich=False)
    meta_empty = get_matrix_meta_light(employee_id=None, batch_ids=[], enrich=False)

    assert len(meta_omitted['employees']) == len(meta_empty['employees']) == 2
    assert meta_omitted['total_evaluations'] == meta_empty['total_evaluations'] == 2


def _unified_two_batches(emp_id='EMP_DEPLOY'):
    return {
        'employee_results': [{
            'metadata': {
                'target_employee_id': emp_id,
                'target_employee_department': '개발팀',
                'target_employee_position': '사원',
                'target_employee_name': emp_id,
                'evaluations': [
                    {'batch_id': 'BATCH_A', 'evaluation_date': '2025-01-01', 'evaluator_id': 'e1'},
                    {'batch_id': 'BATCH_B', 'evaluation_date': '2025-06-01', 'evaluator_id': 'e2'},
                ],
            }
        }]
    }


# ---------------------------------------------------------------------------
# T6. save_to_deploy() — R-1 실측: 매트릭스 생성 경로와 별개 구현이라 배치
# 필터가 빠질 위험이 실제로 있었음(§4.1 계획에는 없던 추가 발견, 저장 경로에도 적용)
# ---------------------------------------------------------------------------
def test_t6_save_to_deploy_batch_filter(tmp_db, db_conn, reset_pseudo_mgr):
    from src.services.perspective_service import save_to_deploy

    unified = _unified_two_batches()
    options_all = {'output_mode': 'pseudonym'}
    result_all = save_to_deploy(unified, 'EMP_DEPLOY', 'evaluation_date__year', 'all', 'nlp', options_all)
    assert result_all is not None

    options_present = {'output_mode': 'pseudonym', 'batch_ids': ['BATCH_A']}
    result_present = save_to_deploy(unified, 'EMP_DEPLOY', 'evaluation_date__year', 'all', 'nlp', options_present)
    assert result_present is not None, "필터에 해당하는 배치가 남아있는데도 None을 반환함"

    options_absent = {'output_mode': 'pseudonym', 'batch_ids': ['BATCH_NOT_PRESENT']}
    result_absent = save_to_deploy(unified, 'EMP_DEPLOY', 'evaluation_date__year', 'all', 'nlp', options_absent)
    assert result_absent is None, "필터로 모든 평가가 제외됐는데도 결과가 반환됨(배치 필터 미적용)"


# ---------------------------------------------------------------------------
# T7. save_trend_graph_to_deploy() — 동일한 R-1 실측(그래프 저장 경로)
# ---------------------------------------------------------------------------
def test_t7_save_trend_graph_batch_filter(tmp_db, db_conn, reset_pseudo_mgr):
    from src.services.perspective_service import save_trend_graph_to_deploy

    unified = _unified_two_batches('EMP_GRAPH')

    options_absent = {'output_mode': 'pseudonym', 'batch_ids': ['BATCH_NOT_PRESENT']}
    result_absent = save_trend_graph_to_deploy(
        unified, 'EMP_GRAPH', 'evaluation_date__year', None,
        metric='sentence_cnt', unit='pct', options=options_absent,
    )
    assert result_absent is None, "필터로 모든 평가가 제외됐는데도 결과가 반환됨(배치 필터 미적용)"


# ---------------------------------------------------------------------------
# T8. 병합된 배치 회귀 — data 블롭의 batch_id가 낡아도 DB 컬럼(정본)으로 필터된다
#
# batch_merge_service는 evaluations.batch_id 컬럼만 재라벨하고 data 블롭은 그대로
# 둔다(2026-08-20 dev DB 실측: 12행 전부 블롭≠컬럼). 로더가 블롭 값을 그대로
# 쓰면 /meta(컬럼 기준)는 직원을 보여주는데 매트릭스는 전건 제외돼 0건이 된다.
# 로더가 컬럼 값으로 덮어쓰는지 실제 DB→로더→매트릭스 경로로 검증한다.
# ---------------------------------------------------------------------------
def test_t8_merged_batch_uses_column_not_stale_blob(tmp_db, db_conn, reset_pseudo_mgr):
    from src.services.perspective_service import (
        load_employee_batch, get_matrix_meta_light, generate_perspective_matrix,
    )

    stale_blobs = ['BATCH_OLD_1', 'BATCH_OLD_2']
    for i, old_bid in enumerate(stale_blobs):
        blob = json.dumps({
            'batch_id': old_bid,                 # 병합 전 값이 그대로 남아 있는 상태
            'evaluation_date': '2025-01-01',
            'evaluator_id': f'e{i}',
        }, ensure_ascii=False)
        insert_evaluation(db_conn, 'EMP_M', 'BATCH_MERGED', f'fpM{i}', data=blob)
    db_conn.commit()

    # (1) 로더가 컬럼 값을 정본으로 실어야 한다
    unified = load_employee_batch('EMP_M')
    evs = unified['employee_results'][0]['metadata']['evaluations']
    assert len(evs) == 2
    assert {e['batch_id'] for e in evs} == {'BATCH_MERGED'}, \
        "로더가 낡은 블롭 batch_id를 그대로 실었음(병합 배치 필터가 0건이 된다)"

    # (2) /meta(컬럼 기준)와 매트릭스(로더 기준)가 같은 배치 ID로 맞물려야 한다
    meta = get_matrix_meta_light(employee_id=None, batch_ids=['BATCH_MERGED'], enrich=False)
    assert {e['employee_id'] for e in meta['employees']} == {'EMP_M'}

    options = {'analysis_types': [], 'generate_png': False, 'batch_ids': ['BATCH_MERGED']}
    result = generate_perspective_matrix(unified, 'EMP_M', 'batch_id', 'all', 'nlp', options)
    assert result is not None
    assert result['rows'] == ['BATCH_MERGED'], \
        "병합 배치를 선택했는데 매트릭스가 비었음(/meta와 매트릭스의 batch_id 기준 불일치)"
    assert result['matrix']['BATCH_MERGED']['전체']['evaluation_count'] == 2

    # (3) 반대로 병합 전 ID로는 더 이상 잡히지 않아야 한다(정본은 컬럼 하나뿐)
    options_stale = {'analysis_types': [], 'generate_png': False, 'batch_ids': ['BATCH_OLD_1']}
    result_stale = generate_perspective_matrix(unified, 'EMP_M', 'batch_id', 'all', 'nlp', options_stale)
    assert not result_stale['rows']
