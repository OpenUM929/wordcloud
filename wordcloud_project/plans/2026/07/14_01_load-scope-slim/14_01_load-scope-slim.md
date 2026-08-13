# 계획서 — 그룹분석 로드 범위 슬림화 (선택분만 적재)

> 상태: Done | 작성일: 2026-07-14 | 완료일: 2026-07-14
> 작업 유형: D (리팩토링/성능 개선 — 동작 보존)
> 선행: 0619_02(load_employee_batch 도입), 0619_03(load_batch_history·get_matrix_meta_light 경량화)

> ⚠️ 경로 규약: 이 문서의 모든 경로는 저장소 루트(`D:\dev\wordcloud\`) 기준이다.
> 축약: `SVC = wordcloud_project/src/services/perspective_service.py`, `RT = wordcloud_project/src/routes/perspective_routes.py`.

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-14 | 전체 | 최초 작성 — 사실관계 확인 후 구현·검증 완료분을 문서화(계획서 사후 정리) |

---

## 요구사항 원자화

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | 그룹분석 "배치 이력"(`/batches`) 조회가 전 직원 평가 본문을 적재하는가? | N | N — 이미 `load_batch_history`가 COUNT 집계만 수행(SVC:1716, 0619_03). 사실무근 |
| 1.2 | 같은 화면의 ID 매칭 `/csv-parse`가 전 직원 평가 본문을 적재했는가? | Y | Y였음 → 수정. `list_all_employee_ids()`로 교체(RT:94), 본문 미적재 |
| 1.3 | 같은 화면의 ID 매칭 `/parse-ids`가 전 직원 평가 본문을 적재했는가? | Y | Y였음 → 수정. `list_employee_roster()`로 교체(RT:140), 본문 미적재 |
| 2.1 | 1명만 선택해 매트릭스 생성 시 전 직원(1.9만) 본문을 적재했는가? | Y | Y였음 → 수정. 단일은 `load_employee_batch(employee_id)`(RT:428) |
| 2.2 | 소수(employee_ids) 선택 시 전 직원 본문을 적재했는가? | Y | Y였음 → 수정. `load_employees_batch(employee_ids)`(RT:426), 선택분만 IN 조회 |
| 2.3 | 전원(all_employees) 선택 시에는 전량 적재가 필요한가? | Y | Y — `load_all_batches()` 유지(RT:424) |
| 2.4 | `/matrix/regenerate`(단일 재생성)도 전량 적재했는가? | Y | Y였음 → 수정. `load_employee_batch(employee_id)`(RT:829) |
| 3.1 | `/users`가 전 직원 본문을 json.loads로 적재했는가? | Y | Y였음 → 수정. `list_users_with_batch_counts()` SQL 집계(RT:949) |
| 4.1 | 수정 후 매트릭스 결과가 기존(전량 적재)과 동일한가? | Y | Y — 단일 `OLD==NEW: True`, 소수 3명 키 일치(§테스트) |
| 4.2 | 수정 후 `/users` 출력이 기존과 동일한가? | Y | Y — 44명 deep-equal `IDENTICAL: True`(§테스트) |

---

## 1. 배경 및 목적

그룹분석 화면(`wordcloud_project/web/templates/perspective_test.html`)은 약 1.9만명 규모의 평가 데이터를 다룬다. 사용자 보고: (1) 배치 이력 조회가 전 데이터를 불러오는 것 같다, (2) 1인/소수 직원 매트릭스 생성 시에도 유사하게 느리다.

사실관계 확인 결과, `/batches`·`/meta`는 이미 경량화(0619_03)되어 있었으나, **같은 화면이 호출하는 다른 엔드포인트들이 `load_all_batches()`로 전 직원 평가 본문을 `json.loads`로 적재**하고 있었다. 목적은 "필요한 만큼만 적재"로 동작 변경 없이 지연·메모리를 줄이는 것이다.

## 2. 현재 코드 분석 (수정 전)

`SVC:load_all_batches()`(SVC:1646)는 `employees INNER JOIN evaluations` 전 행을 읽고 각 `ev.data` blob을 `json.loads`한다 — 직원 수 × 평가 수만큼 역직렬화(1.9만 규모에서 수십 초·수 GB).

이를 무조건 호출하던 지점(수정 전):

- `RT` `/csv-parse`: ID 소속 여부만 필요한데 전량 적재
- `RT` `/parse-ids`: id/이름/부서/직급/건수만 필요한데 전량 적재
- `RT` `/matrix`: `all_employees`·`employee_ids`·단일 무관하게 전량 적재 (소비 함수 `generate_perspective_matrix`는 `_get_evaluations_for_employee`/`_get_employee_metadata`가 `target_employee_id`로 1명만 필터, `generate_all_employee_matrix`는 `employee_ids`로 선택분만 처리 → 전량은 순수 낭비)
- `RT` `/matrix/regenerate`: 단일 직원 대상인데 전량 적재
- `RT` `/users`: 전 직원 순회하며 배치별 카운트 — `batch_id`는 `evaluations`의 인덱스 컬럼이라 SQL 집계로 대체 가능(json.loads 불필요)

## 3. 변경 설계

### 3-1. 신규 경량 로더 (SVC)

- `load_employees_batch(employee_ids)` (SVC:1815) — `load_employee_batch`의 다건판. 입력 ID를 가명 resolve 후 `WHERE employee_id IN (...)` 단일 쿼리. 반환 구조·매칭 키(`target_employee_id`=가명)는 `load_all_batches`와 동일.
- `list_employee_roster()` (SVC:1890) — 평가 본문 없이 명부(id/name/department/position/evaluation_count)만 `GROUP BY employee_id` 집계.
- `list_users_with_batch_counts()` (SVC:1919) — `GROUP BY employee_id, ev.batch_id` 집계로 `/users` 출력 구조(total_evaluations + batches[{batch_id,evaluation_count}])를 본문 적재 없이 산출. `total_evaluations`는 batch_id 빈/NULL 평가도 포함, batches 목록에서는 제외(기존 동작 보존).

### 3-2. 라우트 선택적 적재 (RT)

`/matrix`(RT:383): `all_employees`→`load_all_batches`(RT:424), `employee_ids`→`load_employees_batch`(RT:426), 단일→`load_employee_batch`(RT:428). 에러 응답 의미 보존을 위해 가드는 `if not unified:`로 유지(단일 미존재 시 후속 `generate_perspective_matrix`가 기존 400 메시지 반환).

## 4. 변경 파일 목록 (영향도)

| 파일 | 변경 유형 | 현재 방식 | 변경 방식 |
|------|-----------|-----------|-----------|
| SVC | 신규 함수 3개 | — | `load_employees_batch`·`list_employee_roster`·`list_users_with_batch_counts` |
| RT | import | 기존 | 신규 3함수 import 추가(RT:11~13) |
| RT `/csv-parse` | 수정 | `load_all_batches()` | `list_all_employee_ids()`(RT:94) |
| RT `/parse-ids` | 수정 | `load_all_batches()` | `list_employee_roster()`(RT:140) |
| RT `/matrix` | 수정 | `load_all_batches()` 무조건 | 선택 범위별 분기(RT:424~428) |
| RT `/matrix/regenerate` | 수정 | `load_all_batches()` | `load_employee_batch()`(RT:829) |
| RT `/users` | 수정 | `load_all_batches()`+파이썬 순회 | `list_users_with_batch_counts()`(RT:949) |

**미변경(의도적)**: `RT` `/matrix`의 `all_employees` 경로는 전원 대상이므로 `load_all_batches()` 유지. `/batches`·`/meta`는 이미 경량(0619_03) — 변경 없음.

## 5. 테스트/검증 계획 및 결과

dev DB 실측(직원 44명 보유). 서버 미실행(지침: 무단 서버 실행 금지).

- **T1 컴파일**: `python -m py_compile SVC RT` → `COMPILE OK`.
- **T2 로더 스모크**: `list_employee_roster()`=44행, `list_all_employee_ids()`=44, `load_employees_batch([2 ids])`=2명·89평가, 빈 입력→빈 구조. → PASS.
- **T3 매트릭스 동치(2.1/4.1)**: 동일 직원에 대해 `load_all_batches`+`generate_perspective_matrix`(OLD) vs `load_employee_batch`+동일(NEW) 비교 → `single OLD==NEW: True`. 소수 3명 `generate_all_employee_matrix` 키 일치 → `few OLD keys==NEW keys: True`. → PASS.
- **T4 /users 동치(4.2)**: 기존 라우트 로직(전량 적재 순회)과 `list_users_with_batch_counts()` 결과 deep-equal → `IDENTICAL: True`(44명). → PASS.

## 6. 효과 예상

| 항목 | 현재(수정 전) | 변경 후 |
|------|------|---------|
| 1명 매트릭스 생성 시 json.loads 대상 | 전 직원(약 1.9만) 평가 | 해당 1명 평가만 |
| 소수 N명 매트릭스 | 전 직원 | N명만(IN 조회) |
| `/csv-parse`·`/parse-ids` | 전 직원 본문 | 본문 0(ID/명부 집계만) |
| `/users` | 전 직원 본문 json.loads | 0(SQL GROUP BY) |
| 출력 정확성 | 기준 | 동일(T3·T4로 확인) |

## 7. 리스크 및 제약

- **가명/원본 혼재 ID**: 신규 로더는 기존과 동일하게 `_resolve_to_pseudo`로 가명 정규화 후 조회 — 매칭 키 일관성 유지(0615_06 회귀 방지 규약 준수).
- **에러 응답 의미**: `/matrix` 단일 미존재 시 404가 아닌 기존 400("조건에 맞는 평가가 없습니다")을 유지하도록 가드를 `if not unified:`로 둠(로더가 빈 dict를 truthy로 반환하므로 후속 판정에 위임).
- **batch_id 소스 동일성**: `/users`·`list_users_with_batch_counts`는 `evaluations.batch_id` 인덱스 컬럼을 사용 — 기존 코드가 읽던 JSON 본문의 `batch_id`와 동일 값(get_matrix_meta_light·_load_batch_list와 같은 컬럼). T4로 동치 확인.
- **범위 밖**: dev 환경은 배치 데이터 제한(원데이터 내부 전용). 대규모(1.9만) 실측은 내부망에서 사용자 확인 필요 — 로직 동치는 dev 44명으로 검증했으나 대규모 체감 지연 개선은 내부망 재기동 후 확인 권장.

## 8. 배포 참고

`.clinerules/docs/project_wordcloud/deployment.md` 절차로 재빌드·반입 필요(소스 변경). 변경은 `SVC`/`RT` 2개 파일에 국한.
