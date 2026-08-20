# 계획서 — 그룹분석 화면에 배치 범위 선택 기능 추가

> 상태: Pre-Done | 작성일: 2026-08-13
> 작업 유형: B (기능 개선/신규 기능)
> 선행: 없음 (13_01 배치 병합과는 별개 — 병합 없이도 "이번엔 이 배치만 보고 싶다"는 요구를 해결한다)

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-13 | 전체 | 최초 작성 |
| 2026-08-20(2차) | §2, §4.1, §6, §7 | **재검토(Opus)에서 §2 "핵심 사실"의 전제 오류 발견·수정.** 계획서는 "매트릭스 루프의 `ev`는 이미 `batch_id` 키를 갖고 있으니 거르기만 하면 된다"고 했으나, **그 값이 `/meta`·배치이력 패널이 쓰는 DB 컬럼 값과 같다는 보장이 없다** — 배치 병합(`batch_merge_service.py:201`)은 `evaluations.batch_id` **컬럼만** 재라벨하고 `data` 블롭은 그대로 두는데, 로더 3종은 블롭만 파싱했다. 실측(dev DB, 읽기 전용): 12행 전부 블롭≠컬럼(컬럼 `batch_20260813_2` vs 블롭 `batch_20260813_0/1`, 병합 작업서 2건). 결과적으로 **병합 배치를 체크하면 `/meta`는 직원을 보여주는데 매트릭스·제출용 저장은 전건 제외돼 0건**이 되는 상태였다(T1~T7이 `unified_data`를 손으로 만들어 블롭=컬럼으로 맞춰 놓아 미검출). 수정: `load_employee_batch`·`load_employees_batch`·`load_all_batches` 가 `ev.batch_id` 컬럼을 SELECT해 `json.loads` 직후 `ev_obj['batch_id']`를 컬럼 값으로 덮어쓰도록 해 **DB 컬럼을 단일 정본화**(원본 추적은 `orig_batch_id` 컬럼에 보존되어 손실 없음). 부수 효과로 기존 "X축=배치(회차)" 우회 경로의 동일 병합 버그(13_05 이전부터 존재)도 함께 해소. T8(병합 배치 회귀, 실제 DB→로더→매트릭스 전 경로) 추가 — 8건 전건 통과. 또한 §6의 "운영 파일 미영향" 주장이 부정확했음: T3·T4가 `_build_save_path`로 운영 `outputs/유저/`에 `EMP_X`·`EMP_Y` 빈 폴더를 생성하고 있었다(gitignore라 `git status`에 미포착). 잔재 정리 + conftest에 `OUTPUTS_DIR_PATH`/`USER_OUTPUT_DIR`/`DEPLOY_OUTPUT_DIR`/`DEPLOY_MANIFEST_PATH` autouse 격리 추가 |
| 2026-08-20 | §4, §6 | 착수 전 §2·§4의 백엔드 라인 참조(perspective_service.py `:2843`·`:3001`·`:3927`, perspective_routes.py `:62`·`:387`)는 전부 정확히 일치해 계획 그대로 구현. 단 프론트엔드(`perspective_test.html`) 라인 참조는 20_01~20_04 작업으로 파일이 커져 상당히 밀렸음(예: `loadBatchHistory` 계획서 `:3431`→실제 3604, 173행 드리프트) — 함수명으로 재탐색해 동일 함수에 배선(내용 자체는 안 바뀜, 20_05 사례와 달리 "계획 수정 필요"에 해당 안 함). §2.2가 우려한 "매트릭스 생성 호출 후보 지점"을 실측한 결과 `/matrix` 실제 호출은 `generateMatrix()`의 단일 지점(`baseOptions` 스프레드)뿐이었음 — 나머지는 `rowFieldSelect.value` 를 읽는 무관한 지점. **R-1 실측으로 계획에 없던 추가 발견**: `save_to_deploy()`·`save_trend_graph_to_deploy()`(제출용 저장·그래프 저장)는 `generate_perspective_matrix()`와 별개 구현이라 그 함수에 넣은 필터가 적용되지 않음 — 두 함수에도 동일한 `batch_ids` 사전 필터를 추가(§4.1 계획 대비 확장). `/matrix/regenerate`·`/matrix/save-deploy-stream` 2개 라우트는 어떤 템플릿에서도 호출되지 않는 죽은 라우트로 확인되어 배선 대상에서 제외. T1~T7(계획 T1~T5 + 추가 T6·T7) 임시 sqlite+격리된 가명 매니저로 전건 통과(pytest, 서버 미기동, 프로덕션 DB/파일 무영향 확인). 브라우저 실동작 검증만 PND |

---

## 요구사항 원자화

| # | 원자 질문 | 기대 (사용자 확인) | 작업 후 답 (근거) |
|---|-----------|--------------------|------------------|
| 1.1 | "그룹 분석"은 좌측 메뉴 「📊 그룹분석」(`/perspective_test`, `perspective_test.html`)을 가리키는가? | Y — `base.html:193` | |
| 1.2 | "배치 이력"은 이 화면 안의 접이식 패널(`batchHistoryArea`, `:357-369`)을 가리키는가? | Y — 명칭 편집(✏️)·삭제 버튼만 있고 **선택/필터 기능은 없음**(실측) | |
| 1.3 | 지금도 특정 배치만 골라 분석할 방법이 전혀 없는가? | 부분적으로 있음(단, 매우 우회적) — ②X축 셀렉트(`rowFieldSelect`)를 「배치(회차)」로 바꾸면 `rowValuesContainer`에 배치별 체크박스가 뜨고 특정 배치만 체크할 수 있다(`perspective_service.py:52` `ROW_FIELDS['batch_id']`, JS `:604-620`). 그러나 이 방식은 ①**X축이 강제로 "배치별 열"이 되어** 원래 보고 싶던 "연도별 열" 등을 동시에 쓸 수 없고 ②**대상 직원 목록(①영역)은 전혀 필터링되지 않아** 선택한 배치에 평가가 없는 직원을 고르면 결과가 빈 값이 된다. 사용자가 "선택할 수가 없다"고 느끼는 지점이 바로 이것 | |
| 1.4 | 사용자가 원하는 건 "배치 이력" 패널에서 바로 체크박스로 배치를 고르고, 그게 X축이 뭐든 상관없이 **분석 대상 데이터 자체를 줄이는** 방식인가? | Y — 요청 원문 "X축과 Y축 등에 영향을 주는 사항으로 사용자가 사용할 데이터를 선택하게 해야함" — 축 선택과는 **독립적인 사전 필터**로 해석 | |
| 1.5 | 배치 범위를 고르면 ①대상 직원 드롭다운도 그 배치에 실제 평가가 있는 직원만 나와야 하는가? | Y — 요청 2항 그대로 | |
| 1.6 | 배치 범위 선택은 「전체 직원 대상」/CSV 업로드/사번 직접입력 등 기존 대상 선택 방식과 **동시에 적용**되는가(교집합), 배타적인가? | 교집합 — 배치 범위는 "어떤 평가를 볼지"의 필터, 대상 선택은 "어떤 직원을 볼지"의 필터. 예: CSV로 50명을 올리고 배치 범위를 1개로 좁히면 "그 50명 중 그 배치에 평가가 있는 사람"만 집계된다 | |
| 1.7 | 미선택(전체) 상태의 기본 동작은 지금과 동일해야 하는가? | Y — 배치 범위를 하나도 체크하지 않으면(=전체) 기존 동작과 100% 동일해야 한다(회귀 방지) | |

---

## 1. 배경 및 목적

그룹분석(`/perspective_test`) 화면은 배치가 여러 개 쌓여도 항상 **전 배치를 합친 데이터**를 대상으로 X/Y축을 만든다. "배치 이력" 패널은 배치 목록을 보여주고 이름 수정·삭제만 할 수 있을 뿐, 그 목록에서 실제로 "이번 분석은 이 배치만 쓰겠다"를 고를 방법이 없다(우회 경로 1건 있으나 §2에서 보듯 축 선택과 뒤엉켜 있고 대상 직원 목록에는 아예 반영되지 않는다). 배치 범위를 독립적인 필터로 만들어 X/Y축·대상 직원 목록 양쪽에 일관되게 적용한다.

---

## 2. 현재 시스템 분석 (실측)

### 2.1 데이터 흐름

| 단계 | 함수/엔드포인트 | 배치 스코프 지원 여부 |
|------|------------------|----------------------|
| 대상 직원 목록 로드 | `POST /api/perspective/meta` → `get_matrix_meta_light(employee_id=None, enrich=...)` (`perspective_service.py:2843`) | **없음** — `employees` 조회 SQL(`:2883-2888`)이 전 직원·전 배치 `GROUP BY e.employee_id`. `employee_id` 파라미터만 받고 batch 필터 파라미터 자체가 없다 |
| X축 옵션(row_options) 로드 | 위와 동일 함수(`:2867-2880` facet_rows) | **`batch_id` 축 값 자체는 이미 있음**(ROW_FIELDS에 포함) — 다만 employee_id로만 좁힐 수 있고 batch로 좁힐 수는 없음 |
| 매트릭스 생성(단일/다중/전체 직원) | `POST /api/perspective/matrix` → `generate_perspective_matrix()`(`:3001`) / `generate_all_employee_matrix()`(`:3927`) | **없음** — `for item in all_items:` 루프(`:3020`)에서 `row_field`/`row_values`로만 걸러내고, evaluation 자체가 어느 배치인지는 걸러내지 않는다 |

핵심 사실(중요): 매트릭스 루프가 다루는 개별 평가 딕셔너리 `ev`는 **이미 `batch_id` 키를 갖고 있다** — `_extract_row_values()`(`:2400-2402`) 가 `ev.get('batch_id', '?')` 로 값을 뽑는 코드가 이미 존재한다(13_01 계획서에서도 확인됨). 즉 **배치 스코프 필터를 넣기 위해 새 데이터를 추가로 적재할 필요가 없다** — 이미 메모리에 있는 값을 거르기만 하면 된다.

> ⚠️ **2026-08-20 정정(중요)**: 위 문단은 "키가 있다"까지만 맞고, **그 값이 `/meta`·배치이력 패널이 쓰는 `evaluations.batch_id` 컬럼과 일치한다는 전제는 틀렸다.** 저장 시점에 블롭에 복사된 값(`user_data_manager.py:79`)은 배치 병합 후에도 갱신되지 않는다 — 병합은 컬럼만 재라벨한다(`batch_merge_service.py:201`). 따라서 로더가 컬럼 값을 정본으로 실어주지 않으면 병합 배치에서 필터가 전건을 걸러낸다. 현재는 로더 3종(`load_employee_batch`·`load_employees_batch`·`load_all_batches`)이 `ev.batch_id` 컬럼을 SELECT해 `ev_obj['batch_id']`를 덮어쓰므로 **컬럼이 단일 정본**이다. 이 불변식이 깨지면 배치 범위 필터와 X축=배치가 동시에 깨진다(회귀 감시: T8).

### 2.2 프론트엔드 — 관련 요소

| 요소 | 위치 | 현재 역할 |
|------|------|----------|
| 배치 이력 패널 | `:357-369` `batchHistoryArea`/`loadBatchHistory()`(`:3431`) | 읽기 전용 목록(명칭 편집·삭제만) |
| 대상 직원 드롭다운 | `:252` `employeeSelect`, 채움 로직 `loadMeta()`(`:540-558`) | `/meta` 응답의 `employees`를 그대로 렌더 — 배치 무관 |
| X축(②) 셀렉트 | `:281` `rowFieldSelect`, `onRowFieldChange()`(`:604`) | `ROW_FIELDS`를 그대로 노출(연도/월/배치(회차)/일자) — 배치를 "축"으로 쓸 수는 있어도 "필터"로는 못 씀 |
| 매트릭스 생성 호출 | `generateMatrix()`(`:1041`) 외 유사 옵션 구성부 다수(`grep` 확인: `:1322`,`:1386-1387`,`:1434`,`:1466-1468`,`:1516`,`:1876`,`:1894`) | `row_field`/`row_values`/`employee_ids` 등을 담아 `/matrix` 호출 — **배치 범위 파라미터가 들어갈 자리가 없음** |

**주의(구현 시 반드시 재확인)**: 위 표의 "매트릭스 생성 호출" 줄은 `rowFieldSelect.value`를 읽는 지점을 grep으로 찾은 목록이며, 전부가 실제로 `/matrix`를 호출하는지(vs. 상태 저장/복원용 코드인지)는 구현 착수 시 개별 확인이 필요하다 — 지금은 "배치 범위 파라미터를 빠뜨리기 쉬운 후보 지점"으로만 기재한다.

---

## 3. 결정 필요 사항 (채택안 제시)

| # | 결정 | 선택지 | 채택안과 근거 |
|---|------|--------|---------------|
| D-1 | 배치 범위를 구현하는 방식 | (A) 독립 필터 파라미터(`batch_ids`)를 신설해 축 선택과 분리 / (B) 기존 X축=배치(회차) 메커니즘을 그대로 쓰되 UI만 "배치 이력" 패널과 동기화 | **A 채택.** B는 "연도별로 보면서 특정 배치만" 같은 조합이 불가능(축을 배치로 강제 전환해야 함) — 원자 질문 1.4가 요구하는 "축과 무관하게 데이터를 줄임"과 배치된다. A는 `ev.get('batch_id')`로 미리 거르기만 하면 되므로 기존 축 로직·`ROW_FIELDS`를 전혀 건드리지 않는다(회귀 위험 최소) |
| D-2 | 필터 적용 위치 | (A) `generate_perspective_matrix()`의 `for item in all_items:` 루프 진입부에서 스킵 / (B) `load_employee_batch`/`load_all_batches` 등 DB 로드 단계에서부터 제외 | **A 채택.** B는 배치별 재로드 캐시·기존 함수 시그니처를 다수 건드려야 하고, 로드 단계는 "직원 단위" 최적화(0714 개선사항 — 선택 직원만 적재)와 얽혀 있어 손대면 회귀 위험이 크다. A는 이미 메모리에 있는 `ev`를 한 줄 조건으로 거르는 것이라 가장 국소적 |
| D-3 | 대상 직원 목록 필터링 위치 | (A) `get_matrix_meta_light()`에 `batch_ids` 파라미터 추가, SQL `WHERE ev.batch_id IN (...)` / (B) 프론트에서 `/meta` 전체 응답을 받은 뒤 JS로 걸러냄 | **A 채택.** B는 "그 배치에 평가가 있는 직원"을 판정하려면 결국 배치별 카운트 데이터가 필요한데 지금 `/meta`는 그 정보를 안 준다(전체 합산 `evaluation_count`만 있음) — 어차피 백엔드 SQL을 다시 타야 하므로 A가 더 정확하고 가볍다 |
| D-4 | "배치 이력" 패널의 UI 형태 | (A) 각 행에 체크박스 추가, 헤더에 "선택 배치만 분석에 사용" 안내 문구 — 하나도 체크 안 하면 전체 | (B) 별도의 "적용" 버튼 필요 | **A 채택**(체크 즉시 반영). 배치 개수가 보통 수십 개 이내(관리자 화면 기준)라 즉시 반영해도 `/meta` 재호출 비용이 크지 않다. 단, 체크 변경마다 매번 호출하면 다다닥 눌렀을 때 요청이 겹칠 수 있어 **디바운스(300ms)** 를 둔다(기존 코드에도 `:1038` 근방에 유사 디바운스 패턴 존재 — 그 관례를 따른다) |

---

## 4. 구현 상세

### 4.1 백엔드

**`src/services/perspective_service.py` `get_matrix_meta_light()`(`:2843`)**

```python
def get_matrix_meta_light(employee_id=None, batch_ids=None, enrich=False, processed_data_dir=None):
```

- `facet_rows` 쿼리(`:2869-2880`)와 `emp_rows` 쿼리(`:2883-2888`) 양쪽에 `batch_ids`가 주어지면 `AND ev.batch_id IN (...)` 조건을 추가(파라미터 바인딩, SQL 인젝션 방지 — `','.join('?'*len(batch_ids))` 플레이스홀더 패턴은 `batch_merge_service.py:252-257`에 이미 있는 관례를 따른다).
- `total_evals`(`:2890`)도 동일 조건 적용.
- 반환 구조·키는 기존과 동일(하위 호환 — `batch_ids` 미지정 시 지금과 100% 동일한 SQL, 원자 질문 1.7).

**`src/routes/perspective_routes.py` `api_get_meta()`(`:62`)**

```python
batch_ids = data.get('batch_ids') or None
meta = get_matrix_meta_light(employee_id=employee_id, batch_ids=batch_ids, enrich=_is_admin())
```

**`src/services/perspective_service.py` `generate_perspective_matrix()`(`:3001`)**

`options.get('batch_ids')`를 읽어 `:3020` 루프 진입부에 추가:

```python
batch_ids = options.get('batch_ids')
for item in all_items:
    ev = item['evaluation']
    if batch_ids and ev.get('batch_id') not in batch_ids:
        continue
    ...
```

`generate_all_employee_matrix()`(`:3927`)는 `options`를 그대로 `generate_perspective_matrix()`에 전달하므로(`:3952`) **수정 불필요** — D-2에서 선택한 위치가 전체/다중 직원 경로까지 자동으로 포괄한다.

**`src/routes/perspective_routes.py` `api_generate_matrix()`(`:387`)**

`options` 딕셔너리(`:402-418`)에 `'batch_ids': data.get('batch_ids')` 한 줄 추가.

### 4.2 프론트엔드

`web/templates/perspective_test.html`

- 전역 상태 `let _selectedBatchIds = [];` 추가(빈 배열 = 전체, 원자 질문 1.7).
- `loadBatchHistory()`(`:3431`) 각 행에 체크박스 열 추가. 변경 시 `_selectedBatchIds` 갱신 → 디바운스 후 `loadMeta()` 재호출(D-4).
- `loadMeta()`(`:540`) 요청 body에 `_selectedBatchIds.length ? {batch_ids: _selectedBatchIds} : {}` 병합.
- §2.2에서 나열한 "매트릭스 생성 호출" 후보 지점 전부에 `batch_ids: _selectedBatchIds.length ? _selectedBatchIds : undefined`를 옵션 객체에 추가 — **구현 착수 시 각 지점이 실제로 `/matrix`를 호출하는지 먼저 확인 후 반영**(§2.2 주의사항).
- 패널 요약 문구(`batchHistorySummary`)에 "N개 선택됨" 표시를 추가해 사용자가 필터가 걸려 있는지 한눈에 알 수 있게 한다(전체 선택 시 문구 없음 — 기존과 동일).

### 4.3 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `get_matrix_meta_light(batch_ids=...)` + `/meta` 라우트 파라미터 | — |
| 2 | `generate_perspective_matrix()` 루프에 `batch_ids` 필터 + `/matrix` 라우트 파라미터 | — |
| 3 | 배치 이력 패널 체크박스 UI | 1 |
| 4 | `loadMeta()`/매트릭스 호출 지점 전체에 `batch_ids` 배선(지점별 실사용 여부 확인 포함) | 1,2,3 |
| 5 | 테스트 스크립트(§6) 작성·실행 | 1,2 |
| 6 | 사용자 실동작 검증 → Pre-Done → Done | 3,4,5 |

---

## 5. 영향도 분석

| 파일 | 변경 | 성격 |
|------|------|------|
| `src/services/perspective_service.py` | `get_matrix_meta_light()` 파라미터 추가, `generate_perspective_matrix()` 필터 1줄, `save_to_deploy()`·`save_trend_graph_to_deploy()` 사전 필터(R-1), 로더 3종의 `batch_id` 컬럼 정본화(2차 정정) | 수정 |
| `src/routes/perspective_routes.py` | `api_get_meta()`·`api_generate_matrix()` 파라미터 전달 | 수정 |
| `web/templates/perspective_test.html` | 배치 이력 패널 체크박스, 전역 상태, 다수 호출 지점 배선 | 수정 |

- `generate_all_employee_matrix()`, `ROW_FIELDS`, X축 셀렉트(`rowFieldSelect`) 로직은 **무변경**(D-1) — 기존 "축을 배치로 쓰는" 우회 경로는 그대로 남겨둔다(제거하지 않음, 하위 호환).
- `/users`(`list_users_with_batch_counts`, 관리자 전용 다른 화면)는 이 계획과 무관 — 그룹분석 화면은 `/meta`만 쓴다(실측, §2.1).
- 도메인 잠금: DL-3(배치 복잡도) — SQL `IN (...)` 필터는 인덱스(`idx_ev_batch`) 사용, 파이썬 루프 O(n) 유지(기존과 동일 복잡도, batch_ids 유무와 무관). DL-8(공통 모듈 침범) — 수정 함수 3개 모두 이 화면 전용 소비처만 가짐(재확인 필요: `get_matrix_meta_light`가 다른 화면에서도 쓰이는지 구현 착수 시 grep 재확인).

---

## 6. 테스트/검증 계획

`test/` 폴더: `plans/2026/08/13_05_analysis-batch-scope/test/`

| # | 시나리오 | 방법 | 기대 |
|---|----------|------|------|
| T1 | `batch_ids` 미지정 — 회귀 확인 | `get_matrix_meta_light()` 기존 호출과 신규 호출(파라미터 생략) 결과 비교 | 완전 동일(원자 질문 1.7) — **PASS** |
| T2 | `/meta`에 특정 배치 1개만 지정 | 해당 배치에만 평가가 있는 직원 A, 다른 배치에만 있는 직원 B로 임시 DB 구성 | `employees`에 A만 포함, B 미포함 — **PASS** |
| T3 | `/matrix`에 배치 필터 적용 | 직원 1명, 배치 2개(각 다른 평가) 구성 후 `batch_ids=[배치1]`로 매트릭스 생성 | 배치2의 평가가 집계에서 빠짐(`result['rows']`·셀 `evaluation_count`로 확인) — **PASS** |
| T4 | 배치 필터 + row_field=연도 동시 사용 | 배치1(2025년), 배치2(2026년) 구성, `batch_ids=[배치1]` + `row_field=evaluation_date__year` | 결과 열에 2026년이 나타나지 않음(D-1이 실제로 축과 독립적으로 동작하는지 확인하는 핵심 케이스) — **PASS** |
| T5 | 전체 미체크(빈 배열)와 파라미터 자체 생략이 동일 결과인지 | `batch_ids=[]` vs `batch_ids` 키 없음 | 둘 다 전체 결과와 동일(프론트가 빈 배열을 보낼 가능성 대비) — **PASS** |
| T6(추가) | `save_to_deploy()`(제출용 저장) 배치 필터 — R-1 실측 | 배치 A·B 평가 보유 직원으로 `batch_ids=['A']`(잔존)·`['미존재배치']`(전부 제외) 각각 호출 | 잔존 시 결과 반환, 전부 제외 시 `None` 반환 — **PASS** |
| T7(추가) | `save_trend_graph_to_deploy()`(그래프 저장) 배치 필터 — R-1 실측 | 동일 구성, `batch_ids=['미존재배치']`로 호출 | 전부 제외되어 `None` 반환(차트 생성 단계 도달 전 차단 확인) — **PASS** |

| T8(추가) | **병합 배치 회귀** — 블롭이 낡아도 컬럼(정본)으로 필터되는지 | 컬럼 `BATCH_MERGED` / 블롭 `BATCH_OLD_1·2`인 평가 2건을 실제 DB에 넣고 `load_employee_batch` → `get_matrix_meta_light` → `generate_perspective_matrix` 전 경로 통과 | 로더가 `batch_id`를 컬럼 값으로 싣고, `/meta`와 매트릭스가 같은 ID로 맞물리며(`rows == ['BATCH_MERGED']`, 건수 2), 병합 전 ID로는 잡히지 않음 — **PASS** |

2026-08-20 실행: `python -m pytest plans/2026/08/13_05_analysis-batch-scope/test/` → **8 passed**. 가명 매니저는 임시 매핑 파일로 격리(운영 매핑 파일 미접촉), `gallery_db_service`/`deploy_session_service`/`perspective_service` DB 경로 전부 임시 sqlite로 통일, 산출물 경로(`OUTPUTS_DIR_PATH`/`USER_OUTPUT_DIR`/`DEPLOY_OUTPUT_DIR`/`DEPLOY_MANIFEST_PATH`)도 autouse fixture로 임시 폴더 격리.

> 격리 이력: 1차 실행분은 `outputs/유저/EMP_X`·`EMP_Y` 빈 폴더를 운영 트리에 남겼다(`_build_save_path`가 호출만으로 `makedirs`). gitignore 대상이라 `git status`에는 잡히지 않아 최초 보고 시 "운영 파일 미영향"으로 잘못 판정했다. 잔재 제거 후 위 autouse 격리를 추가했고, 재실행 시 `outputs/` 신규 생성물 0건을 확인했다(실계정 폴더 44개 무손상).

**실동작 검증(사용자 승인 후, 사용자가 서버 기동)**

1. 배치 이력 패널에서 배치 1개만 체크 → 대상 직원 드롭다운이 그 배치 관련 인원으로 줄어드는지 확인.
2. 그 상태로 X축을 「평가 연도」로 두고 매트릭스 생성 → 다른 배치의 데이터가 섞이지 않는지(문장 수·건수) 확인.
3. 체크 전부 해제 → 기존과 동일하게 전체 데이터가 나오는지 확인(회귀 없음).

위 3항 통과 전에는 상태를 `Done`으로 올리지 않는다(DL-10).

---

## 7. 리스크 및 제약

| # | 리스크 | 영향 | 대응 |
|---|--------|------|------|
| R-1 | §2.2에서 나열한 매트릭스 호출 지점 중 일부를 빠뜨리면 그 지점만 배치 필터가 안 먹음 | 화면 일부 기능(예: 그래프 저장, 배포 저장)에서만 필터가 조용히 무시됨 | 구현 시 지점별 실제 `/matrix`·`/matrix/save-*` 호출 여부를 개별 확인하고 T3~T4를 각 저장 경로에도 적용 |
| R-2 | 배치를 축(②)으로도 쓰고 필터로도 쓰는 두 메커니즘이 공존해 사용자가 헷갈릴 수 있음(D-1에서 기존 축 방식을 남겨두기로 함) | UX 혼선 | 배치 이력 패널에 "이 선택은 X축 설정과 별개로 분석 대상 데이터를 좁힙니다" 안내 문구 추가 |
| R-3 | 대상 직원 목록이 배치 필터로 줄어든 상태에서 「전체 직원 대상」 체크 시 무엇을 "전체"로 볼지 모호 | 의도치 않게 필터된 소수만 "전체"로 처리될 수 있음(원자 질문 1.6의 교집합 원칙과 일관되면 정상 동작) | T2로 "필터된 employees 목록 = 전체 직원 대상의 모집단"임을 명시적으로 검증 |

**제약**

- 「배치(회차)」를 X축으로 쓰는 기존 우회 경로는 유지하되 개선하지 않는다(중복 UI, 후속 과제로 남김).
- 이 계획은 그룹분석(`/perspective_test`) 화면 1곳만 다룬다. 워드클라우드 배치 트리(`wordcloud.html`) 등 다른 화면의 배치 선택 UX는 범위 밖.
