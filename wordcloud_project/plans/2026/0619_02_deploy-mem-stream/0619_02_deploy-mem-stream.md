# 계획서 — 제출용 저장 메모리 폭증 해소 (직원 단위 스트리밍 로딩)

> 상태: Pre-Done (구현·단위검증 완료 · **정상 동작 확인 대기** — 서버 실동작 + 내부망 풀스케일 메모리 실측 후 DN) | 작성일: 2026-06-19
> 작업 유형: D (리팩토링/성능 개선)
> 선행: `plans/2026/0618_03_deploy-wc-parallel/0618_03_deploy-wc-parallel.md` (DN — 스트림 ThreadPool 병렬화), `plans/2026/0609_02_evaluation-db-migration/0609_02_evaluation-db-migration.md` (DN — JSON→DB, "인터페이스 보존"으로 전체 로드 형태 유지·페이징 보류)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-19 | 전체 | v1 초안: 내부망 17,000명 그룹 제출용 저장 시 메모리 29~30GB 폭증·정지 원인(전체 코퍼스 일괄 적재 + 전원 결과 누적 + 병렬 워커 증폭) 진단 및 직원 단위 스트리밍 로딩 설계 |
| 2026-06-19 | §2-4, §3, §10 | v2(구현·확정): **실제 핫패스 재확인** — 프론트(`perspective_test.html:1623`)는 청크 세션으로 직원을 1명씩 **비스트리밍 `api_save_deploy`** 에 보내며 브라우저 4워커로 동시 호출한다. 즉 매 요청이 `load_all_batches()`(전체 적재)를 호출하고 동시 호출로 곱해진 것이 30GB 폭증의 직접 원인. 따라서 `api_save_deploy`(단일/배치)와 `api_save_deploy_stream`(미사용이나 동반 수정) **양쪽**을 직원 단위 로딩으로 전환. 구현·단위테스트 통과·`py_compile` 통과. |
| 2026-06-19 | 상태 | v2에서 DN 표기했으나 **정상 동작 확인 전 DN은 부적절**(사용자 지적) → PND로 환원. 코드 적용·단위검증은 완료, 서버 실동작 + 내부망 풀스케일 메모리 실측(V3) 통과 후 DN 전환. |
| 2026-06-22 | 상태 | Kanban PDN 도입에 따라 PND → PDN 전환. 실서버 검증 대기 중 |

---

## 1. 배경 및 목적

내부망에서 **그룹분석 → 17,000명 제출용 저장**을 실행하면 프로세스 메모리가 **29~30GB / 31GB**까지 치솟으며 동작이 멈춘다(물리 메모리 한계 도달 → 스와핑/스래싱). 소수 인원에서는 드러나지 않다가 풀스케일에서 임계치를 넘어 발현됐다.

근본 원인은 단일 버그가 아니라 **"전체 코퍼스를 한 번에 RAM에 적재 + 전원 결과를 한 번에 누적 + 병렬 워커가 순간 할당을 곱한다"** 는 세 구조가 동시에 살아 있는 설계다. 이 중 **지배적 원인은 전체 적재**(`load_all_batches()`)이며, 직원 1명만 사용하는 제출용 저장 경로가 17,000명 전원을 메모리에 펼친 뒤 1명씩 슬라이스한다.

**목적**: 제출용 저장(스트리밍) 경로를 **직원 단위 스트리밍 로딩 + 결과 비누적**으로 전환하여, 피크 메모리를 전체 코퍼스 크기에서 **(워커 수 × 직원 1명분)** 수준으로 낮춘다. **출력 이미지/문장 데이터 내용은 변경하지 않는다(동작 동일, 메모리만 개선).**

> 선행 `0618_03`(DN)은 **속도**(벽시계 시간)만을 목표로 했고, 전체 `unified` 공유를 ThreadPool 선택의 전제로 고정해 메모리 구조는 손대지 않았다(§8 ProcessPool 배제 주근거 = `unified` 전체 pickle 비용). 본 계획은 그 전제 자체를 직원 단위로 깨뜨려 메모리를 해결한다.

---

## 2. 현재 코드 분석

### 2-1. 문제 코드 ① 전체 코퍼스 일괄 적재 (지배적 원인)

`load_all_batches()` (`src/services/perspective_service.py:792`)

```python
rows = conn.execute("""
    SELECT e.employee_id, e.name, e.department, e.position, ev.data, ev.id
    FROM employees e
    INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
    ORDER BY e.employee_id, ev.id
""").fetchall()                              # L798-803 — 전 직원·전 평가를 한 번에 materialize
...
ev_obj = json.loads(data)                    # L820 — 평가 1건마다 dict 파싱
emp_evals[emp_id].append(ev_obj)             # L823 — unified 한 덩어리에 누적 보관
```

- `fetchall()`로 17,000명 × 전 평가를 한 번에 가져온 뒤, 각 평가 JSON(`nlp_analysis_results.meaningful_words_with_pos`, `sentence_emotion_cache` 등 무거운 필드 포함)을 파이썬 객체로 펼친다.
- 파이썬 dict/list는 원본 JSON 텍스트 대비 통상 **3~10배** 메모리를 점유한다.
- 이 `unified`는 라우트 진입부(`perspective_routes.py:698`)에서 만들어져 작업 종료까지 **해제되지 않고** 점유된다.

**원인(역사적)**: `load_all_batches()`는 원래 `users/*.json`을 통째 읽던 함수이고, `0609_02` DB 마이그레이션 시 **"반환 형식 유지 → 9개 호출부 변경 없음(인터페이스 보존)"** 원칙으로 "전체 읽기" 형태를 그대로 옮겼다. 직원별 쿼리로 바꿀 기회였으나 보류됐고(§리스크: *"이후 캐싱·페이징 별도 계획"*), 그 계획이 나오지 않은 채 현재에 이름.

### 2-2. 문제 코드 ② 전원 결과 누적

`api_save_deploy_stream()`의 `generate()` (`src/routes/perspective_routes.py:714`)

```python
success_list = []                            # L715
...
result['profanity_summary'] = build_profanity_summary(unified, eid)   # L737
success_list.append(result)                  # L738 — 문장 상세 포함 result를 전원분 끝까지 누적
```

각 `result`에는 단어별 추출 문장·pos/neg/neutral details가 들어 있다. 클라이언트로 yield(L739)된 뒤에도 `success_list`에 계속 쌓여 **입력(`unified`)과 별개의 두 번째 거대 구조**가 된다. 최종 `log_action`(L747) 집계에만 쓰이는데 본문 전체를 보관한다.

### 2-3. 문제 코드 ③ 병렬 워커 증폭 (0618_03 적용분)

`ThreadPoolExecutor(max_workers=min(cpu, 8))` (`perspective_routes.py:720,727`)가 직원별 `save_to_deploy`를 동시 실행한다. 각 워커가 워드클라우드 3장(통합/긍정/부정, 800×600) PIL+numpy 캔버스를 순간 보유 → 피크가 최대 8배. `0618_03` §7은 이를 "워커 상한 + 모니터링"으로만 완화했고 구조는 그대로 둠.

### 2-4. 핵심 관찰 — 소비처는 이미 "직원 1명" 단위로 동작한다

제출용 저장 워커가 `unified`에서 실제로 읽는 함수는 모두 **`employee_results`를 employee_id로 필터링**한다. 즉 **전체가 아니라 해당 직원 1명만** 사용한다.

| 함수 | 위치 | unified 사용 방식 |
|------|------|------------------|
| `_get_evaluations_for_employee` | `perspective_service.py:1587` | `target_employee_id != employee_id` 인 항목 skip → 1명만 |
| `_get_employee_metadata` | `:1136` | 동일 — 1명 메타만 반환 |
| `build_profanity_summary` | `:1405` | 동일 — 1명 평가만 순회 |
| `_load_corrections_map` | `:942` | `unified` 미사용 — `WHERE employee_id = ?` 자체 DB 조회(L950) |

→ **`unified`에 17,000명이 들어 있을 필요가 없다.** 해당 직원 1명만 담은 동일 형태(dict)를 넘기면 위 함수들이 전부 그대로 동작한다(드롭인). 직원별 쿼리 선례는 이미 `_load_corrections_map`(L950)에 존재한다.

---

## 3. 변경 설계

### 작업 1 (핵심) — 직원 단위 로더 신규 추가

**대상**: `src/services/perspective_service.py` — 신규 함수 (현재 미존재, 신규 생성 필요)

`load_all_batches()`와 **동일한 반환 형태**를 유지하되, `employee_results`에 **해당 직원 1명만** 담는다.

```python
def load_employee_batch(employee_id):
    """단일 직원의 평가만 담은 unified 형태 dict 반환.
    load_all_batches()와 동일 구조(employee_results/batch_info/batches)이나
    employee_results는 1명만 포함 → 기존 소비 함수(_get_evaluations_for_employee 등)
    가 그대로 동작한다. 제출용 저장 스트림의 워커별 로딩에 사용."""
    conn = _get_eval_conn()
    try:
        rows = conn.execute("""
            SELECT e.employee_id, e.name, e.department, e.position, ev.data, ev.id
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            WHERE e.employee_id = ?
            ORDER BY ev.id
        """, (employee_id,)).fetchall()
    finally:
        conn.close()

    if not rows:
        return {'employee_results': [], 'batch_info': {}, 'batches': []}

    name = dept = pos = ''
    evals = []
    for emp_id, nm, dp, ps, data, ev_db_id in rows:
        name, dept, pos = nm or '', dp or '', ps or ''
        if data:
            ev_obj = json.loads(data)
            ev_obj['_db_id'] = ev_db_id        # 보정값 키(_db_id) 계약 동일 — [[project_eval_id_not_unique]]
            evals.append(ev_obj)

    return {
        'employee_results': [{
            'metadata': {
                'target_employee_id': employee_id,   # 가명 ID 매칭 키 계약 유지 (REQ-2606-032 회귀 방지)
                'target_employee_name': name,
                'target_employee_department': dept,
                'target_employee_position': pos,
                'evaluations': evals,
            }
        }],
        'batch_info': {},
        'batches': [],
    }
```

> ⚠️ **매칭 키 계약**: `target_employee_id`는 반드시 **가명 ID(`emp_id`)** 로 둔다. 실명으로 바꾸면 `0615_06`/REQ-2606-032와 동일한 전원 매칭 실패 회귀가 발생한다. (실명 복원은 상위 `save_to_deploy`의 enrich/'real' 모드가 자체 수행 — `perspective_service.py:1875`.)

### 작업 2 (핵심) — 전 직원 ID 목록 경량 조회

**대상**: `src/services/perspective_service.py` — 신규 함수 (현재 미존재)

현재 `all_employees` 분기는 전체 `unified`를 적재한 뒤 ID를 추려낸다(`perspective_routes.py:702-710`). ID만 필요하므로 평가 데이터를 적재하지 않는 경량 쿼리로 대체한다.

```python
def list_all_employee_ids():
    """전 직원 ID 목록만 반환(평가 데이터 미적재). all_employees 일괄 저장용."""
    conn = _get_eval_conn()
    try:
        rows = conn.execute("""
            SELECT DISTINCT e.employee_id
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            ORDER BY e.employee_id
        """).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]
```

### 작업 3 (핵심) — 스트림 라우트: 전체 적재 제거 + 워커별 로딩 + 결과 비누적

**대상**: `src/routes/perspective_routes.py` `api_save_deploy_stream` (L664~) / `generate()` (L714~)

```python
# AS-IS: 라우트 진입부에서 전체 적재 (L698)
unified = load_all_batches()
...
if all_employees and not employee_ids:        # L702-710 — unified에서 ID 추출
    employee_ids = [er...target_employee_id ...]

# TO-BE: 전체 적재 제거. all_employees는 ID만 경량 조회
if all_employees and not employee_ids:
    employee_ids = list_all_employee_ids()     # 작업2
ids = employee_ids if employee_ids else [employee_id]
```

```python
def generate():
    fail_list = []
    success_count = 0                          # 본문 누적 대신 카운트만
    total = len(ids)
    _setup_korean_font()                        # 루프 밖 1회 (0618_03 작업4 유지)
    num_workers = min(multiprocessing.cpu_count(), 8)
    completed = 0

    def _work(eid):
        emp_unified = load_employee_batch(eid)  # 작업1 — 워커가 자기 직원분만 로딩
        result = save_to_deploy(emp_unified, eid, row_field, col_mode, analysis_type, options, None)
        if result is not None:
            result['profanity_summary'] = build_profanity_summary(emp_unified, eid)
        return result
        # emp_unified는 _work 종료 시 참조 소멸 → 직원 1명분 즉시 회수

    with ThreadPoolExecutor(max_workers=num_workers) as ex:
        futures = {ex.submit(_work, eid): eid for eid in ids}
        for fut in as_completed(futures):
            eid = futures[fut]
            completed += 1
            try:
                result = fut.result()
                if result:
                    result['employee_id'] = eid
                    success_count += 1
                    yield json_lib.dumps({'employee': eid, 'name': result.get('name', eid),
                                          'status': 'done', 'result': result,
                                          'current': completed, 'total': total}) + '\n'
                    # yield 직후 result 참조 소멸 → success_list 누적 안 함
                else:
                    fail_list.append({'employee_id': eid, 'error': '평가 데이터 없음'})
                    yield json_lib.dumps({'employee': eid, 'status': 'fail', 'error': '평가 데이터 없음',
                                          'current': completed, 'total': total}) + '\n'
            except Exception as exc:
                fail_list.append({'employee_id': eid, 'error': str(exc)})
                yield json_lib.dumps({'employee': eid, 'status': 'fail', 'error': str(exc),
                                      'current': completed, 'total': total}) + '\n'

    log_action('csv_batch_save_deploy_stream', {
        'total': total, 'success': success_count, 'fail': len(fail_list),
        'failed_employees': [f['employee_id'] for f in fail_list],
    }, request)
    # complete 메시지는 success_count/total 기반으로 기존과 동일하게 구성
```

**변경 핵심 3가지**:
1. 라우트 진입부 `load_all_batches()` **삭제** → 17,000명 일괄 적재 제거.
2. 워커가 `load_employee_batch(eid)`로 **자기 직원 1명분만** 로딩하고, `_work` 종료 시 회수.
3. `success_list`(본문 누적) → `success_count`(정수)로 대체. yield된 `result`는 즉시 회수.

> ℹ️ **`save_to_deploy` 시그니처 무변경**: 인자 `unified`에 1명짜리 dict를 넘길 뿐 함수 내부는 수정하지 않는다. `_load_corrections_map`(L1928)은 원래 `unified` 미사용·자체 DB 조회라 영향 없음.

### 작업 4 (동반, 선택) — 비스트리밍 경로 동일 적용

**대상**: `src/routes/perspective_routes.py` `api_save_deploy` 배치 루프 (L500-505)

비스트리밍 단일/배치 저장(L484 `load_all_batches()` → L502 `save_to_deploy(unified, eid, ...)`)도 동일 패턴이다. 우선순위는 낮으나(스트림이 실제 버튼 경로) 동일하게 `load_employee_batch(eid)`로 교체하면 메모리 일관성이 확보된다. 단, `_setup_korean_font()` 1회 호출 위치(0618_03 §작업4)는 유지.

---

## 4. 변경 파일 목록

| 파일 | 변경 유형 | 현재 방식 | 변경 방식 |
|------|-----------|-----------|-----------|
| `src/services/perspective_service.py` | 신규 | — | `load_employee_batch(employee_id)` 추가 (작업1) |
| `src/services/perspective_service.py` | 신규 | — | `list_all_employee_ids()` 추가 (작업2) |
| `src/routes/perspective_routes.py` | 수정 | `api_save_deploy_stream` 진입부 전체 적재 + `success_list` 누적 | 전체 적재 제거, 워커별 `load_employee_batch`, 결과 비누적 (작업3) |
| `src/routes/perspective_routes.py` | 수정(선택) | `api_save_deploy` 배치 루프 전체 적재 | 동일 직원 단위 로딩 (작업4) |

> `load_all_batches()` 자체는 **수정하지 않는다.** 나머지 8개 호출처(매트릭스 미리보기 등 전체가 필요한 경로)의 계약을 보존한다.

---

## 5. 효과 예상

| 항목 | 현재 (AS-IS) | 변경 후 (TO-BE) |
|------|-------------|-----------------|
| 입력 적재 메모리 | 17,000명 전 평가 dict 일괄 (다수 GB) | 워커당 직원 1명분 (수 MB~수십 MB) |
| 결과 누적 메모리 | 17,000명 result 본문(문장 상세) 누적 | 정수 카운트 + 실패 ID만 |
| 피크 메모리 | **29~30GB → 정지** | **≈ (워커 수 × 직원 1명분) + 캔버스** → 1GB 미만 목표 [측정 필요] |
| 출력 이미지/문장 내용 | — | **동일**(회귀 없음 목표) |
| 벽시계 시간 | 0618_03 병렬화 수준 | 동등(워커별 소량 DB 조회 N회 추가 — 인덱스 조회라 무시 가능) [측정 필요] |

> DB 부하: 1회 대형 JOIN+fetchall → 직원별 `WHERE employee_id = ?` 인덱스 조회 N회로 분산. 각 조회는 인덱스 기반 소량이라 O(n) 유지([[project_batch_scale_19k]] O(n) 이하 원칙 부합). `employees.employee_id` / `evaluations.employee_id` 인덱스 존재 확인을 검증 항목에 포함.

---

## 6. 영향도 분석

- **계약 보존**: `load_all_batches()` 무수정 → 나머지 8개 호출처(`perspective_routes.py:54,91,138,417,643,768,814`) 무영향. 본 계획은 스트림 경로(+선택적 비스트림)만 직원 단위로 분기.
- **소비 함수 호환**: `save_to_deploy`/`_get_evaluations_for_employee`/`_get_employee_metadata`/`build_profanity_summary`는 `employee_results`를 id로 필터링하므로 1명짜리 unified와 완전 호환(§2-4 확인 완료).
- **NDJSON 프로토콜 무변경**: `done`/`fail`/`complete` 메시지 형식·`employee` 키 추적 동일. 프론트(`perspective_test.html`) 무영향(0618_03 §4 확인 결과 재확인).
- **0618_03와의 관계**: ThreadPool 병렬화(작업3)·지역 RNG·getextrema는 유지. 본 계획은 워커에 넘기는 데이터를 "공유 전체"에서 "워커별 1명"으로 바꿀 뿐 병렬 구조는 보존.
- **가명/실명 계약**: `target_employee_id=가명` 유지로 REQ-2606-032/0615_06 회귀 방지.

---

## 7. 테스트/검증 계획

작업 폴더 `test/`·`result/` 사용 (03.plan-mode.md §10).

- [ ] V1 (동치성, dev/CSV): 동일 입력 직원에 대해 `load_employee_batch(eid)` 경로와 기존 `load_all_batches()`→슬라이스 경로가 **동일 evaluations·_db_id·메타**를 산출(유닛 테스트). [[project_dev_no_batch_csv_only]] — dev는 CSV 반입만.
- [ ] V2 (회귀, dev): 제출용 저장 전/후 생성 PNG·문장 상세가 시각/내용 동일(소수 직원).
- [ ] V3 (메모리, 내부망): N=1,000 / 5,000 / 17,000 일괄 저장 시 프로세스 피크 메모리 측정. AS-IS 대비 대폭 감소 및 **OOM/정지 미발생** 확인.
- [ ] V4 (스트리밍): `done`/`fail` 직원당 1건, `complete`의 success+fail == total, 진행률 `current/total` 정상.
- [ ] V5 (동시성): 워커 2~8개에서 예외 없음, gallery DB 엔트리 수 == 성공 직원 수, `database is locked` 미발생.
- [ ] V6 (DB 인덱스): `employees.employee_id` / `evaluations.employee_id` 인덱스 존재 확인(`EXPLAIN QUERY PLAN`), 직원별 조회가 풀스캔이 아님 확인.

---

## 8. 리스크 및 제약

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 직원별 DB 조회 N회로 분산 | 인덱스 부재 시 풀스캔 N회 → 느려짐 | V6에서 인덱스 확인. 없으면 인덱스 추가(별도 핫픽스) |
| `load_employee_batch` 반환 형태 불일치 | 소비 함수 오작동 | 반환 dict를 `load_all_batches()`와 동일 키로 구성(작업1), V1 동치성 테스트 |
| `target_employee_id` 실명 혼입 | 전원 매칭 실패 회귀 | 가명 ID 고정(§3 작업1 경고), V2 회귀 |
| 워커당 캔버스 동시 보유(잔존) | 피크에 캔버스분 가산 | 입력 적재가 사라져 절대량은 급감. 워커 상한 `min(cpu,8)` 유지 |
| 비스트림 경로 미적용(작업4 선택) | 비스트림 배치 저장은 여전히 전체 적재 | 동일 패턴이므로 후속 적용 가능. 실버튼은 스트림 경로 |

## 9. 제외/후속 결정

| 항목 | 사유 |
|------|------|
| `load_all_batches()` 직접 수정 | 9개 호출처 계약 보존 위해 무수정. 매트릭스 등 전체 필요 경로 존재 |
| ProcessPoolExecutor 전환 | 본 계획으로 워커 인자가 "전체 unified"→"직원 1명분"으로 축소되면 `0618_03` §8의 ProcessPool 배제 주근거(전체 pickle 비용)가 사라져 **재검토 가치 발생**. 단 GIL 우회는 별도 속도 과제이므로 본 계획(메모리) 범위 외 — 후속 |
| `load_all_batches()` 페이징/캐싱(매트릭스 경로) | `0609_02`가 보류한 항목. 매트릭스 미리보기 메모리는 본 계획 범위 외 — 필요 시 별도 계획 |

---

## 10. 실행 결과 (2026-06-19 — 구현·단위검증 완료, 정상 동작 확인 대기)

### 적용 내역
| 파일 | 적용 | 내용 |
|------|------|------|
| `src/services/perspective_service.py` | 신규 | `load_employee_batch(employee_id)`, `list_all_employee_ids()` 추가(load_all_batches 직후) |
| `src/routes/perspective_routes.py` | 수정 | import에 신규 2함수 추가 |
| `src/routes/perspective_routes.py` `api_save_deploy` | 수정 | **실제 핫패스** — `load_all_batches()` 제거. 단일/배치/all_employees 모두 `load_employee_batch`·`list_all_employee_ids`로 전환 |
| `src/routes/perspective_routes.py` `api_save_deploy_stream` | 수정 | 동반 — 진입부 전체 적재 제거, `_work`가 직원 1명분 로딩 + profanity_summary를 워커 내부로 이동 |

### 검증
- 단위 테스트 `test/test_load_employee_batch.py` **통과(exit 0)**: ①1명만 적재 ②`_db_id` 고유성(eval_id 중복과 무관) ③`_get_evaluations_for_employee` 호환 ④미존재 직원 빈 구조 ⑤`list_all_employee_ids` 정렬 ID.
- `python -m py_compile` 양 파일 통과.
- 가명 계약: `target_employee_id`=가명(`_resolve_to_pseudo` 내부 변환), REQ-2606-032/0615_06 회귀 없음.
- 미적용(범위 외): `complete` 메시지의 `success_list`(스트림)는 외부 계약 보존 위해 유지 — 스트림은 현재 프론트 미사용 경로라 영향 적음. 실버튼 경로(`api_save_deploy` 단일)는 애초에 결과 누적 없음.

### 메타데이터 생성 경로 영향 확인 (사용자 질문)
**동일 현상 없음.** 배치 메타데이터 생성(`batch_processor.py:773 process_single_employee`)은 워커가 `batch_staging.load_employee_evaluations(conn, employee_id)`로 **직원 1명분만** staging DB에서 로드하고(L778), 생성 즉시 `upsert`로 DB 영구 저장 후 `employee_results.append({... 'metadata': None ...})`로 **메타 객체를 즉시 메모리 해제**한다(L894, 주석 "저장 완료 후 메모리 해제"). 워커 수도 `_calc_adaptive_workers`(RAM 실측)로 캡. 즉 메타 생성은 처음부터 직원 단위 스트리밍 구조라 `load_all_batches` 류의 전체 적재가 없다. 본 수정으로 제출용 저장이 메타 생성과 동일한 직원 단위 구조로 정렬되었다.

---

### 정상 동작 확인 체크리스트 (DN 전환 조건)
- [ ] 서버 기동 후 제출용 저장 단일 직원 1명 정상 저장(이미지·문장 카드 표시)
- [ ] 그룹(다수 직원) 저장 정상 완료 + 갤러리 반영
- [ ] 내부망 N=1k/5k/17k 일괄 저장 시 피크 메모리 대폭 감소 + OOM/정지 미발생 (V3)
- [ ] 기존 출력과 PNG·문장 내용 동일(회귀 없음, V2)

*상태: PND — 코드 적용·단위검증(`test_load_employee_batch.py` 통과)·구문 검증 완료. 위 체크리스트(서버 실동작 + 내부망 풀스케일 메모리 실측) 통과 확인 후 DN 전환한다. 풀스케일 실측은 dev 데이터 제약상 내부망에서 수행.*
