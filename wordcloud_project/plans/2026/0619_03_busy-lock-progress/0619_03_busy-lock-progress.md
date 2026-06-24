# 계획서 — 배치 이력 조회 속도 개선 + 장시간 작업 전면 차단 오버레이

> 상태: Pre-Done | 작성일: 2026-06-19
> 작업 유형: B (기능 개선/신규 기능) + D 요소(이력 조회 성능 개선)
> 선행: `plans/2026/0619_02_deploy-mem-stream/0619_02_deploy-mem-stream.md` (load_all_batches 직원단위 전환 — 동일 뿌리)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-19 | 전체 | 최초 작성 |
| 2026-06-19 | §8 | 수행 — 구현·단위검증(V1) 완료. 정상 동작 확인 대기로 PND 유지 |
| 2026-06-22 | §3.2, §8 | 코너 배너 방식 확정(전면 차단 유지 + 클릭 차단 영역과 안내 박스 분리) + 실시간 진행 텍스트(단계/인원수) 추가, perspective_test 매트릭스 생성도 동일 적용 |
| 2026-06-22 | §8 | 검토 반영 — 제출용 저장(saveDeploy)에도 실시간 진행 텍스트 적용(4개 차단 작업 전부 일관). renderProgress 2개(generateMatrix/saveDeploy) 구분 명시 |
| 2026-06-22 | §1, §2.1, §3.1, §9 | 요구사항 3 추가 — X축(시간/회차) 메타(/meta)도 동일 병목(load_all_batches) 발견 → 경량 빌더 `get_matrix_meta_light` 신설·교체. 구현·패리티 단위검증(V6) 완료, 정상 동작 확인 대기로 PND 유지 |
| 2026-06-22 | 상태 | Kanban PDN 도입에 따라 PND → PDN 전환. 실서버 검증 대기 중 |

---

## 1. 요구사항

1. **배치 이력 조회 속도 개선 + 로딩 인디케이터** — 그룹분석/배치 이력 조회 시 시간이 오래 걸려 "멈춘 느낌"이 든다. 실제 조회 지연 원인을 점검·완화하고, 조회 진행 중임을 시각적으로 표시한다. (사용자 선택: "조회 속도 개선 + 인디케이터")
   - 단, 이력 조회는 중간 진행률이 없는 단일 호출이므로 "정확한 %" 게이지는 서버 스트리밍 없이는 불가 → **정직한 indeterminate 인디케이터**(스피너/물결 바)로 표시한다.
2. **장시간 작업 중 Nav/버튼 전면 차단 오버레이** — 다음 4개 작업 진행 중에는 Nav 메뉴 이동 및 페이지 버튼 조작을 막는다. (사용자 선택)
   - (a) 그룹분석 제출용 저장
   - (b) 메타데이터 생성(배치)
   - (c) 그룹분석 워드클라우드 생성(매트릭스)
   - (d) 배치 이력/이어서 작업
3. **[추가 2026-06-22] X축(시간/회차) 메타 로딩 속도 개선** — 그룹분석 화면 진입 시 X축(평가 연도/월/일자, 배치 회차) 옵션 채우기가 배치 이력 때와 똑같이 오래 걸린다. 같은 뿌리(`load_all_batches` 전체 적재)이므로 이력과 동일 방식으로 경량화한다.

## 2. 현재 시스템 분석

### 2.1 배치 이력 조회 병목 (요구사항 1)

- **엔드포인트**: `GET /api/perspective/batches` → `api_batch_history()` (`src/routes/perspective_routes.py:797`)
  - 내부에서 `unified = load_all_batches()` 호출 후 **`unified['batches']`와 `unified['batch_info']`만** 반환에 사용한다(`perspective_routes.py:801-808`).
- **`load_all_batches()`** (`src/services/perspective_service.py:792`): `employees ⨝ evaluations` 전 행을 `fetchall()` → 평가별 `json.loads()` → **employee_results(직원별 평가 전체)를 메모리에 적재**한다. 1.7만명 규모에서 수십 초 + 수 GB 소모. → 이력 목록만 필요한 호출에 전체 코퍼스를 적재하는 것이 "멈춘 느낌"의 실제 원인. (0619_02의 제출용 저장과 동일 뿌리)
- **프론트 소비** (`web/templates/perspective_test.html:2841` `loadBatchHistory()`): 사용 필드는 다음뿐이며 `employee_results`는 전혀 쓰지 않는다.
  - `d.batches` (목록) — 각 항목: `display_name`, `batch_id`, `created_at`, `employee_count`, `total_evaluations`
  - `d.batch_info.unique_employees`, `d.batch_info.total_evaluations` (요약 줄 한 줄, `perspective_test.html:2856`)
- **`_load_batch_list()`** (`perspective_service.py:711`): 작업서(`batch_work_orders`) + 레거시 평가 배치 합집합을 만들고, **배치마다 `_batch_display_name()`이 `batch_summary.json` 파일 1건씩 read**(`perspective_service.py:698-708`). 배치 수가 많으면 파일 I/O 누적(2차 지연 요인, 단 employee_results 적재 대비 영향은 작음).
- **로딩 표시 현황**: `loadBatchHistory()`는 `list.innerHTML='로딩...'` 텍스트만 표시(`perspective_test.html:2846`).

#### [추가 2026-06-22] X축(시간/회차) 메타 병목 (요구사항 3) — 이력과 동일 뿌리

- **엔드포인트**: `POST /api/perspective/meta` → `api_get_meta()` (`src/routes/perspective_routes.py:52`)가 **`load_all_batches()`** 호출 후 `get_matrix_meta(unified, ...)` 결과를 반환. → 배치 이력(`/batches`)을 0619_03에서 경량화했지만, **X축 메타(`/meta`)는 같은 무거운 로더를 그대로 사용** 중이어서 증상이 동일하다.
- **프론트 소비**: X축 값은 화면 진입 시 `loadMeta()`(`perspective_test.html:513`)가 `/meta`를 1회 호출해 `_meta.row_options`에 담고, `onRowFieldChange()`(`perspective_test.html:577`)가 `rowValuesContainer`(②번 박스, `:280` "로딩…")를 채운다.
- **실제 필요 필드**: `get_matrix_meta` → `_get_row_value_counts`(`perspective_service.py:1626`) → `_extract_row_values`(`:1252`)가 평가 1건에서 쓰는 값은 **`batch_id`와 `evaluation_date`(연/월 파생) 단 둘뿐**이다.
- **핵심 사실**: 두 필드는 `evaluations` 테이블에 **인덱스된 독립 컬럼**으로 존재(`deploy_session_service.py:84-91` `evaluation_date`, `batch_id`, `idx_ev_batch`)하며, INSERT 시 JSON blob과 동일 값으로 채워진다(`user_data_manager.py:89-90`). → blob 19,000건 `json.loads` 없이 `GROUP BY evaluation_date, batch_id` 집계만으로 row_options 4종(연/월/일/회차)을 동일하게 산출 가능.

### 2.2 장시간 작업 트리거 (요구사항 2)

- **공통 오버레이 패턴 존재**: `web/templates/base.html:417` `globalAuthOverlay`(전면 모달). 동일 패턴으로 busy-overlay 신설 가능. Nav는 `base.html:373` `<nav>` 내 `<a>` 링크 → 높은 z-index 전면 오버레이로 링크·버튼 동시 차단.
- **트리거 함수(실측)**:
  - (a) 제출용 저장: `perspective_test.html:1406` `saveDeploy()` — 청크별 `WORKER_COUNT=4` 병렬 fetch(`/api/perspective/matrix/save-deploy`).
  - (b) 메타데이터 배치: `web/static/js/metadata_batch.js:882` `fetch('/api/batch/process')` + SSE 수신, 진행 플래그 `isProcessing`(`metadata_batch.js:870,877`).
  - (c) 워드클라우드 생성(매트릭스): `perspective_test.html:965` `generateMatrix()`.
  - (d) 이력/이어서: `perspective_test.html:2841` `loadBatchHistory()`, `metadata_batch.js:1263` `resumeWorkOrder()` → `metadata_batch.js:1374` `fetch('/api/batch/resume')`.

## 3. 구현 상세

### 3.1 백엔드 (요구사항 1)

- **신규 함수** `load_batch_history(processed_data_dir=None)` (`src/services/perspective_service.py`, `load_all_batches` 인접 위치 신설):
  - `batches = _load_batch_list(processed_data_dir)` (기존 재사용)
  - `batch_info`는 **employee_results 미적재**, cheap aggregate SQL로만 산출:
    ```python
    row = conn.execute("""
        SELECT COUNT(DISTINCT e.employee_id) AS uniq,
               COUNT(*) AS total
        FROM employees e
        INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
    """).fetchone()
    ```
    `batch_info = {'unique_employees': uniq, 'total_evaluations': total, 'batch_count': _count_batches(...)}`
  - 반환: `{'batches': batches, 'batch_info': batch_info}` (employee_results 키 없음 — 이 함수 소비처는 목록/카운트만 사용).
  - `json.loads` 호출 0건, 평가 본문 비적재 → 메모리·시간 모두 절감.
- **라우트 변경** `api_batch_history()` (`perspective_routes.py:797`): `load_all_batches()` → `load_batch_history()`. 응답 형식(`success`/`batches`/`batch_info`) 불변 → 프론트 무변경 호환.
- **주의**: `load_all_batches()`는 제출용 저장 외 다른 호출처가 있으므로 **변경하지 않는다**(이번 작업은 이력 엔드포인트만 경량 함수로 분기). display_name 파일 I/O 일괄 최적화는 §6에서 후속 보류.

#### [추가 2026-06-22] X축 메타 경량 빌더 (요구사항 3)

- **신규 함수** `get_matrix_meta_light(employee_id=None, enrich=False, processed_data_dir=None)` (`perspective_service.py`, `get_matrix_meta` 인접 신설):
  - row_options: `SELECT evaluation_date, batch_id, COUNT(*) FROM evaluations [WHERE employee_id=?] GROUP BY evaluation_date, batch_id` (소량 그룹). Python에서 연(`date[:4]`)·월(`split('-')[1]`, len>=7)·일자(raw)·회차(batch_id) 버킷으로 가중 합산 — **기존 `_get_eval_field_value`/`_extract_row_values` 의미 그대로** 보존(회귀 0).
  - employees: `SELECT e.employee_id, e.name, e.department, e.position, COUNT(ev.id) ... GROUP BY e.employee_id` (blob 미적재). enrich 시 `get_real_id` 복원 로직은 `get_matrix_meta`와 동일.
  - 반환 구조(`row_options`/`col_modes`/`analysis_types`/`employees`/`position_hierarchy`/`batch_count`/`total_evaluations`)는 `get_matrix_meta`와 동일 → 프론트 무변경 호환.
- **라우트 변경** `api_get_meta()` (`perspective_routes.py:52`): `load_all_batches()`+`get_matrix_meta()` → `get_matrix_meta_light()`. (기존 `if not unified` 분기는 `load_all_batches`가 항상 truthy dict를 반환해 실행되지 않던 dead branch라 제거.)
- **주의**: `get_matrix_meta`/`load_all_batches`는 그대로 보존(다른 경로 영향 0). `/meta`만 경량 함수로 분기.

### 3.2 프론트엔드 (요구사항 1·2)

- **공통 busy-overlay (base.html)**:
  - 오버레이는 두 부분으로 분리:
    - **클릭 차단 레이어** `#globalBusyOverlay`: `position:fixed; inset:0; pointer-events:auto;` 투명 배경(`rgba(255,255,255,0.3)`, 블러 없음)로 **페이지 전체를 덮어 클릭 차단**. 진행 패널은 투명 레이어 뒤에 있으므로 그대로 보임.
    - **안내 박스** `#globalBusyBox`: 우하단 코너에 고정(`position:fixed; bottom:20px; right:20px;`), 흰 배경, 스피너 + 고정 안내 문구(예: "메타데이터 생성 중…") + **실시간 상세 텍스트**(예: "분석 처리 중 (152 / 19,000명)")를 세로로 표시.
  - JS 헬퍼:
    - `showBusyOverlay(message)`: 오버레이 표시 + 고정 메시지 설정 + 상세 텍스트 초기화
    - **신규** `window.updateBusyOverlay(detailText)`: overlay가 `show` 상태일 때만 상세 텍스트 갱신 (SSE/매트릭스 진행 상황 실시간 반영)
    - `hideBusyOverlay()`: 오버레이 숨김 + 텍스트 정리(다음 작업 시 잔상 방지)
- **이력 조회 인디케이터 (요구사항 1)**: `loadBatchHistory()`(`perspective_test.html:2841`)에서 `'로딩...'` → 스피너 마크업으로 교체(조회 중 표시), 완료/실패 시 제거.
- **4개 작업 오버레이 wiring (요구사항 2)**: 각 트리거 시작 시 `showBusyOverlay(<작업명>)`, 종료(성공/실패/finally)에서 `hideBusyOverlay()`.
  - (a) `saveDeploy()` 시작/종료(`perspective_test.html:1406` — 병렬 루프 전체를 감싸는 진입/완료 지점)
  - (b) `metadata_batch.js` 배치 처리: `/api/batch/process` 시작 시 표시, SSE `complete`/`onerror`/`isProcessing=false` 지점에서 해제
  - (c) `generateMatrix()` 시작/종료(`perspective_test.html:965`)
  - (d) `loadBatchHistory()`(이력 조회는 §위 인디케이터로 충분 — 전면 차단은 선택 적용), `resumeWorkOrder`/`/api/batch/resume`(`metadata_batch.js:1374`) 시작/종료
  - 메시지 예: "제출용 저장 중… 완료까지 페이지를 벗어나지 마세요", "메타데이터 생성 중…" 등.

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `perspective_service.load_batch_history()` 신설(cheap COUNT 기반) | - |
| 2 | `api_batch_history()` → `load_batch_history()` 분기 | 1 |
| 3 | `base.html` busy-overlay 마크업 + CSS 스피너 + `showBusyOverlay/hideBusyOverlay` | - |
| 4 | `loadBatchHistory()` 스피너 인디케이터 적용 | 3 |
| 5 | 4개 작업 트리거에 오버레이 wiring (saveDeploy / metadata process / generateMatrix / resume) | 3 |
| 6 | 단위검증(경량 함수 반환 계약) + 정상 동작 확인 체크리스트 작성 | 1-5 |

## 5. 영향도 분석

- **변경 파일**:
  - `src/services/perspective_service.py` — 함수 1개 신설(기존 함수 무변경)
  - `src/routes/perspective_routes.py` — `api_batch_history` 1줄 호출 교체
  - `web/templates/base.html` — busy-overlay 마크업/CSS/JS 헬퍼 추가(전역)
  - `web/templates/perspective_test.html` — `loadBatchHistory` 인디케이터, `saveDeploy`/`generateMatrix` 오버레이
  - `web/static/js/metadata_batch.js` — 배치 process/resume 오버레이
- **영향 범위**: `api_batch_history` 응답 계약 불변 → 프론트 호환. `load_all_batches`는 미변경이라 제출용 저장(0619_02 경로) 영향 없음. busy-overlay는 base.html 전역 추가지만 기본 `display:none` + 명시 호출 시에만 표시 → 다른 페이지 무영향.
- **롤백**: 각 파일 변경이 독립적. 라우트 1줄·프론트 호출만 되돌리면 즉시 원복.

## 6. 테스트/검증 계획

- **V1 (단위)**: `load_batch_history()`가 임시 DB에서 `batches`/`batch_info`(unique_employees·total_evaluations·batch_count)를 반환하고 `employee_results` 키가 없으며 `json.loads`로 평가 본문을 적재하지 않음을 검증. (dev는 실데이터 없음 → 임시 SQLite, [[project_dev_no_batch_csv_only]])
- **V2 (응답 호환)**: `/api/perspective/batches` 응답 키(`success`/`batches`/`batch_info`)가 기존과 동일, 프론트 요약 줄·표가 동일하게 렌더.
- **V3 (성능, 내부망)**: 1.7만명 규모에서 이력 조회 응답 시간·메모리가 종전 `load_all_batches` 대비 크게 감소.
- **V4 (오버레이)**: 4개 작업 각각 시작 시 오버레이로 Nav/버튼 차단, 완료·실패·중단 시 정상 해제(잔류 차단 없음).
- **V5 (인디케이터)**: 이력 조회 중 스피너 표시 → 완료 시 표 전환, 실패 시 오류 메시지.
- **V6 (X축 메타 패리티, 요구사항 3)**: `get_matrix_meta_light`가 기존 `load_all_batches`+`get_matrix_meta`와 `row_options`/`employees`/카운트 동일, 평가 본문 `json.loads`가 평가 건수에 비례하지 않음. (`test/test_get_matrix_meta_light.py`)

## 7. 리스크 및 제약

- 이력 조회의 "정확한 %"는 단일 호출 특성상 제공 불가 → indeterminate 인디케이터로 한정(요구사항 1 단서에 사용자 합의).
- 오버레이 해제 누락 시 화면이 영구 잠길 위험 → 모든 종료 경로(`finally`/SSE `onerror`/`complete`)에서 `hideBusyOverlay()` 보장, 예외 시에도 해제.
- `_load_batch_list`의 배치별 `batch_summary.json` 파일 I/O 최적화(일괄/캐시)는 이번 범위에서 **보류** — employee_results 비적재만으로 주 병목 해소, 잔여 최적화는 후속.

## 8. 실행 결과 — 구현·단위검증 완료, 정상 동작 확인 대기

**적용 변경 (1차: 원 기능)**
- 백엔드: `perspective_service.load_batch_history()` 신설(cheap COUNT, employee_results 미적재) — `perspective_service.py`. `api_batch_history()`가 이를 호출하도록 교체 — `perspective_routes.py`(+ import 추가).
- 공통 오버레이: `base.html`에 `#globalBusyOverlay` 마크업·CSS 스피너(`globalBusySpin`)·전역 `showBusyOverlay/hideBusyOverlay` 추가.
- 이력 인디케이터: `perspective_test.html` `loadBatchHistory()` `'로딩...'` → indeterminate 스피너.
- 오버레이 wiring: `saveDeploy()`·`generateMatrix()`(perspective_test.html, finally 해제), 배치 `startBatchProcessing`/`confirmResume`(metadata_batch.js, 모든 `isProcessing=false` 종료점에서 해제).

**추가 변경 (2차: 사용자 피드백 반영 — 2026-06-22)**
- 공통 오버레이: `base.html` 코너 배너(#globalBusyBox)에 **상세 텍스트 줄** `#globalBusyDetail` 추가. 고정 메시지(예: "메타데이터 생성 중…") + 실시간 상태(예: "분석 처리 중 (152 / 19,000명)") 두 줄로 표시.
- 신규 헬퍼 `updateBusyOverlay(detailText)` — overlay `show` 상태일 때만 상세 텍스트 갱신.
- `metadata_batch.js` 오버레이 wiring: `openSseAndListen()` + `openBatchSse()` 두 핸들러 모두, `statusText` 계산 직후 `updateBusyOverlay(statusText)` 호출 추가.
- `perspective_test.html` 오버레이 wiring(매트릭스 생성): `generateMatrix` 내부 `renderProgress()` 함수에 `updateBusyOverlay(`매트릭스 생성 중 (${current}/${total})`)` 추가.

**추가 변경 (3차: 검토 반영 — 2026-06-22)**
- `perspective_test.html`에는 `renderProgress`가 **2개**(① `generateMatrix` 내부 `:1024`, ② `saveDeploy`(제출용 저장) 내부 `:1479`) 존재. 2차에서 ①만 적용되어 제출용 저장 진행 표시가 누락되었음.
- 제출용 저장도 차단 4개 작업 중 하나(§1 요구사항 2-(a))이므로, `saveDeploy`의 `renderProgress`에도 `updateBusyOverlay(`제출용 저장 중 (${current}/${total})`)` 추가 → **4개 차단 작업 전부 실시간 진행 표시 일관**.
- 초기 `renderProgress(0,'init')`는 `showBusyOverlay` 호출 이전이라 `updateBusyOverlay`가 no-op(배너 미표시) → "(0/0)" 잔상 없음. 청크 루프 진입 전 `total`이 실제값으로 설정된 뒤부터 배너가 갱신됨. 해제는 기존 `finally`의 `hideBusyOverlay()`로 보장(`:1704`).

**검증**
- V1 단위테스트 `test/test_load_batch_history.py` 통과: `employee_results` 키 없음 + `unique_employees=2`/`total_evaluations=3` 정확 + 평가 본문 `json.loads` 0회. (dev 실데이터 없음 → 임시 SQLite)
- `py_compile`(perspective_service/perspective_routes) OK, `node --check metadata_batch.js` OK.

**미검증(사용자 확인 필요)**: 서버 실동작(오버레이 표시/해제·이력 스피너), 내부망 1.7만 규모 이력 조회 시간·메모리 실측. [[feedback_dn_after_runtime_verify]] · [[feedback_no_server_start]]

## 9. 실행 결과 — X축(시간/회차) 메타 경량화 (요구사항 3, 2026-06-22)

**적용 변경**
- 백엔드: `perspective_service.get_matrix_meta_light()` 신설 — `evaluation_date`·`batch_id` 인덱스 컬럼 `GROUP BY` 집계로 row_options/employees 산출, 평가 본문 blob 미적재. `get_matrix_meta`/`load_all_batches`는 무변경 보존.
- 라우트: `api_get_meta()`(`perspective_routes.py`)가 `load_all_batches()`+`get_matrix_meta()` 대신 `get_matrix_meta_light()` 호출(+import 추가). dead였던 `if not unified` 빈 응답 분기 제거.

**검증 (V6 — 패리티 단위테스트)**
- `test/test_get_matrix_meta_light.py` 통과: 임시 SQLite에서 **기존 경로(load_all_batches+get_matrix_meta)와 신규 경로의 `row_options`·`employees`·`total_evaluations`·`batch_count`가 완전 일치**. 빈 날짜/연·월 경계 버킷 포함.
- 평가 본문 `json.loads`: 기존 경로 6회(평가 5건+설정 1) → 경량 빌더 **1회(설정 로드만)**. 평가 건수에 비례하지 않음 확인.
- 기존 `test_load_batch_history.py` 재실행 통과(회귀 없음). `py_compile`(perspective_service/perspective_routes) OK.

**미검증(사용자 확인 필요)**: 서버 실동작(그룹분석 진입 시 X축 ② 박스 "로딩…" → 값 즉시 표시), 내부망 1.9만 규모 `/meta` 응답 시간·메모리 실측. [[feedback_dn_after_runtime_verify]] · [[feedback_no_server_start]] · [[project_batch_scale_19k]]

### 정상 동작 확인 체크리스트 (DN 전환 조건)
- [ ] 서버 기동 후 그룹분석 이력 조회: 스피너 표시 + 목록/카운트 정상, 응답 즉시성 체감
- [ ] **[추가 2026-06-22]** 그룹분석 화면 진입 시 X축 ②번 박스(평가 연도/월/일자·배치 회차)가 "로딩…"에서 즉시 채워짐 + 값/건수가 기존과 동일(회귀 없음)
- [ ] **[추가 2026-06-22]** 내부망 1.9만 규모에서 `/meta`(화면 진입) 응답 시간·메모리가 종전 대비 크게 감소
- [ ] 내부망 1.7만 규모 이력 조회: 메모리 급증·정지 미발생 (V3)
- [ ] 4개 작업 각각: 진행 중 Nav·버튼 차단, 종료 시 해제 (V4)
- [ ] 기존 이력 표/요약 내용 동일(회귀 없음, V2)
- [ ] **[추가 2026-06-22]** 코너 배너 두 번째 줄에 실시간 진행 상황(단계/인원수)이 갱신되는지 확인 — 4개 경로 모두: ① 메타데이터 생성(SSE 0.5초), ② 이어서 처리(SSE 0.5초), ③ 매트릭스 생성(직원별), ④ 제출용 저장(직원별)
