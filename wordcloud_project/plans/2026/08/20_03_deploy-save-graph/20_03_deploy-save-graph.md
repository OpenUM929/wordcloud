# 계획서 — 제출용 저장 시 추이 그래프도 함께 저장

> 상태: Pre-Done | 작성일: 2026-08-20
> 작업 유형: B
> 선행: 12_01(그래프 저장 기능 최초 구현), 20_01(재개 시 태그 분리 버그 — 완료)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-20 | 전체 | 최초 작성 |
| 2026-08-20 | §2, §3.2 | 20_01 구현 완료(선행 처리됨, §4 순서 2 충족) 후 라인 인용 재검증 — `btnSaveDeploy` 실제 위치 정정(`318행대`→`325`, `btnSaveGraph`는 `327`로 원문이 이미 정확), `matrix/save-graph` 호출 라인 정정(`:2007`→`:2057`, 20_01의 재개 지원 삽입으로 이동) |
| 2026-08-20 | 요구사항 원자화, §2, §3.2, §4, §6 | 사용자 명시 요청 반영 — "그래프 포함 저장 시 연도 범위(전체/1~3년치)를 선택할 수 있어야 한다". 원자화 1.5 신설, 화면 ②의 연도 체크박스 메커니즘(`onRowFieldChange`/`getSelectedRowValues`/`_meta.row_options`) 조사 근거 추가, `includeGraphYearRange` 셀렉트 + `_computeGraphYearValues()` 설계 추가 |
| 2026-08-20 | §3.2, §5 | 구현 완료 — 사용자가 원자화 1.2(기본 OFF)·1.3(항목 2개 분리)를 제 판단대로 승인. 구현 중 설계를 한 가지 보강: 그래프 포함 여부·연도범위·metric·unit을 `saveDeploy()`의 세션 시작 시점 DOM 값이 아니라 **세션 `options`에 함께 저장**해, 재개(resume) 시 재개 시점의 체크박스 상태가 아니라 처음 시작할 때의 설정을 그대로 쓰도록 함(20_01이 고친 "재개 시 다른 경로로 처리되는" 버그 클래스를 이 신규 기능이 재도입하지 않도록 하는 조치, §3.2에 반영) |

## 요구사항 원자화

| # | 원자 질문 | 기대(제 이해) | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | "제출용 저장에도 그래프를 저장"은 별도 버튼 클릭 없이 "제출용 저장" 버튼 1번으로 워드클라우드(통합/긍정/부정)와 추이 그래프를 **같이** 저장한다는 뜻인가? | Y | Y로 구현 |
| 1.2 | 항상 같이 저장하는가, 아니면 체크박스로 "그래프 포함" 여부를 매번 선택하는가? | 체크박스로 선택(기본 OFF — 기존 동작 보존, 그래프가 필요 없는 저장까지 매번 시간이 늘어나는 것을 막기 위함) | **사용자 확정(2026-08-20): 기본 OFF로 구현** |
| 1.3 | 저장 갤러리에서 이 결과는 한 항목(entry)에 워드클라우드+그래프가 같이 들어가는가, 아니면 `source='deploy'` 항목과 `source='graph'` 항목 2개로 나뉘어 생성되는가? | 2개로 나뉜다 — 현재 DB 스키마(`gallery_entries`)가 `source` 컬럼 하나로 항목을 구분하고 `_append_to_deploy_manifest`/`_append_trend_graph_to_manifest`가 서로 다른 저장 함수이므로, 한 항목에 억지로 합치기보다 같은 `batch_title`/`timestamp` 대역으로 2개 항목을 만들어 갤러리 필터(20_04 계획서)로 묶어보게 하는 쪽이 기존 구조를 덜 건드림 | **사용자 확정(2026-08-20): 항목 2개 분리로 구현**(신규 엔드포인트 없이 기존 두 엔드포인트 순차 호출) |
| 1.4 | 그래프의 지표(metric)·단위(unit) 선택은 어디서 하는가 — 현재 "그래프 저장" 버튼 옆의 `graphMetric`/`graphUnit` 드롭다운(`perspective_test.html` 그래프 옵션 패널)을 그대로 재사용하는가? | Y — 신규 UI를 만들지 않고 기존 드롭다운 값을 제출 시점에 함께 읽어 전송 | Y로 구현 |
| 1.5 | (사용자 명시 요청) 그래프 포함 저장 시 그래프에 반영할 **연도 범위**를 화면 ②(X축 시간/회차, `rowValuesContainer`)에서 체크된 연도와 **별도로** 선택할 수 있어야 하는가? | Y — "전체 / 최근 1년 / 최근 2년 / 최근 3년" 프리셋 셀렉트를 신설. 화면 ②의 체크 상태(워드클라우드용 연도 선택)와 그래프용 연도 선택을 분리하는 이유: 제출용 워드클라우드는 특정 연도만, 그래프는 전체 추이를 보고 싶은 경우(또는 그 반대)가 흔할 수 있어 하나의 체크박스 그룹으로 억지로 통일하면 둘 중 하나는 항상 재선택이 필요해짐 | Y로 구현(`includeGraphYearRange` 4종) |

> 1.2·1.3·1.5는 사용자가 위 기대값 그대로 확정했습니다(2026-08-20). §3.2·§5에 구현 결과 기재.

## 1. 배경 및 목적

그룹분석(`/perspective_test`) 화면에는 "제출용 저장"(워드클라우드 통합/긍정/부정 3종)과 "그래프 저장"(연도별 긍정/부정 추이 PNG)이 완전히 분리된 별도 버튼·별도 함수로 존재한다. 사용자가 하나의 작업(예: 특정 직원 대상 제출 자료 준비)을 위해 두 버튼을 각각 눌러야 하는 번거로움을 줄이고, 제출용 저장 한 번으로 그래프까지 함께 받을 수 있게 한다.

## 2. 현재 시스템 분석

- **제출용 저장**: `saveDeploy(resumeSessionId = null)`(`wordcloud_project/web/templates/perspective_test.html:1505`), 버튼 `id="btnSaveDeploy"`(325행), 항목별로 `POST /api/perspective/matrix/save-deploy` 호출(1744행), 저장 함수는 `wordcloud_project/src/services/perspective_service.py`의 `_generate_wc_for_items`+결과 dict(3373~3394행) → `_append_to_deploy_manifest` → `gallery_entries.source='deploy'`(기본값), `images`에 `combined`/`positive`/`negative`(+한글 중복 키 `통합`/`긍정`/`부정`) URL 저장.
- **그래프 저장**: `saveGraph(resumeSessionId = null)`(`perspective_test.html:1872`, 20_01로 재개 인자 추가됨), 버튼 `id="btnSaveGraph"`(327행, `toggleGraphOptions()`로 옵션 패널을 열고 그 안의 "그래프 생성" 버튼이 실제 `saveGraph()` 호출), 항목별로 `POST /api/perspective/matrix/save-graph` 호출(2057행, 20_01 반영 후 기준), 저장 함수는 `save_trend_graph_to_deploy`(`perspective_service.py:3772`) → `_append_trend_graph_to_manifest`(3868행) → `gallery_entries.source='graph'`, `images={'graph': url}`.
- **두 함수는 완전히 별개의 옵션 객체를 구성**한다 — `saveDeploy`의 `body`(1534~1554행)는 `row_field/col_mode/analysis_type(s)/row_values/output_mode/...`, `saveGraph`의 `options`(1893~1906행)는 `row_field/row_values/metric/unit/output_mode/...`. 공통 필드(`row_field`, `row_values`, `output_mode`, `include_name`, `include_id`, wordcloud 옵션 일부)는 겹치지만 `col_mode`/`analysis_types`(deploy 전용)와 `metric`/`unit`(graph 전용)은 서로 없다.
- **세션 인프라는 공유**: 두 함수 모두 `/api/perspective/deploy-session/start|chunk|complete`를 그대로 쓴다(20_01 계획서에서 이 공유가 재개 버그의 원인으로 지목됨 — 이번 기능을 얹기 전에 20_01을 먼저 처리하는 것이 안전, 아니면 이번 작업이 태그 분리 버그의 표면적을 더 넓힘).
- **연도(행) 선택 메커니즘(요구사항 원자화 1.5 근거)**: 화면 ②의 연도 체크박스는 `onRowFieldChange()`(`perspective_test.html:604~624`)가 `_meta.row_options`(`/api/perspective/meta` 응답, `field==='evaluation_date__year'`)를 순회해 `class="rowValueCb" value="${v.value}"`로 렌더링하고(617행), `getSelectedRowValues()`(626~629행)가 체크된 값만 배열로 반환한다. `saveGraph()`(1887행)를 포함해 매트릭스·제출용 저장 전부 이 **하나의 전역 체크박스 그룹**을 공유해 연도를 정한다 — 현재 "그래프만 다른 연도 범위로" 저장할 방법이 없다.

## 3. 구현 상세

### 3.1 백엔드

- 신규 엔드포인트를 만들지 않고 기존 두 엔드포인트(`/api/perspective/matrix/save-deploy`, `/api/perspective/matrix/save-graph`)를 그대로 사용한다(요구사항 원자화 1.3의 "항목 분리" 결정에 따름).
- 변경 없음 — 프론트엔드가 같은 `employee_id`에 대해 두 엔드포인트를 순차 호출하도록 조합.

### 3.2 프론트엔드 (구현 완료 — 아래는 실제 적용된 설계)

- `perspective_test.html`의 `btnSaveDeploy`(325행) 옆에 체크박스 `id="includeGraphInDeploy"`(기본 미체크, 요구사항 원자화 1.2)와 `<select id="includeGraphYearRange">`(요구사항 원자화 1.5, 기본 비활성화)를 추가. 옵션: `all`(전체, 기본값) / `1`(최근 1년) / `2`(최근 2년) / `3`(최근 3년). 체크박스 `onchange`로 `_toggleGraphYearRangeEnabled()`가 셀렉트 활성/비활성을 토글.
- `getSelectedRowValues()` 근처(632행)에 신규 함수 `_toggleGraphYearRangeEnabled()`·`_computeGraphYearValues(rangeSel)` 추가. 후자는 `_meta.row_options`에서 `field==='evaluation_date__year'` 항목의 `values[].value`를 숫자 파싱·내림차순 정렬해 `rangeSel==='all'`이면 전체, 숫자면 앞에서 그만큼만 반환(숫자 파싱 실패 시 안전하게 전체 반환).
- **설계 보강(당초 계획 대비 변경)**: 그래프 포함 여부·연도범위·metric·unit을 호출 시점 DOM에서 매번 읽지 않고, `saveDeploy()`의 `body` 객체(1566행)에 `include_graph`/`graph_year_range`/`graph_metric`/`graph_unit`으로 함께 담아 **세션 `options`에 영속화**한다. 신규 세션 생성 시엔 `body` 그대로가 `options`가 되고, 재개(`resumeSessionId` 전달) 시엔 기존 로직(1747~1760행, `progressData.progress.options`로 `options` 재할당)이 그대로 이 필드들도 복원한다. `graphOptions` 객체는 `localStorage.setItem('deploy_session_id', ...)` 직후(1762행 다음)에서 `options.include_graph`를 보고 한 번만 구성 — 재개 시점의 체크박스 상태가 아니라 **최초 시작 시점의 설정**이 항상 쓰인다(20_01이 고친 버그 클래스 재도입 방지).
- `saveDeploy()`의 `processOne(eid)`(1739행대) 안, 기존 `POST /api/perspective/matrix/save-deploy` 성공 처리 직후에 `graphOptions`가 있으면(=세션이 그래프 포함으로 시작됐으면) `POST /api/perspective/matrix/save-graph`를 이어서 호출한다(`row_values`는 `graphOptions.row_values`, 위 `_computeGraphYearValues` 결과). 성공/실패는 `graphDoneCount`/`graphFailCount`로 별도 집계하고, `addLine` 메시지를 구분("완료(워드클라우드)"/"완료(그래프)"). 그래프 호출 실패는 `deploy-session/complete`로 보고하는 `completedIds`/`failedItems`(세션 진행률 추적용)에는 반영하지 않는다 — 그래프는 세션 태스크가 아닌 부가 호출이기 때문.
- 완료 요약(`renderDeployComplete`)에 `summary.graph`가 있으면 "📈 그래프 N건 성공(, M건 실패)" 배지를 추가로 표시.
- 20_02에서 만든 적응형 스로틀(`_workerCount`/`_itemDurations`)을 `saveDeploy()`에도 이식할지는 이 계획서 범위 밖(§8에 언급).

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | 요구사항 원자화 표 사용자 재확인 | - |
| 2 | ~~(권장) 20_01 배포용/그래프 태그 분리 버그 선행 처리~~ **완료**(2026-08-20, Pre-Done) | 20_01 |
| 3 | `perspective_test.html`에 "그래프 포함" 체크박스 + 연도 범위 셀렉트(`includeGraphYearRange`) UI 추가 | 1 |
| 4 | `_computeGraphYearValues()` 함수 구현 | 1, 3 |
| 5 | `saveDeploy()`의 `processOne`에 그래프 저장 호출 조합(연도는 `_computeGraphYearValues()` 결과 사용) | 1, 3, 4 |
| 6 | 실행 확인(서버 기동은 사용자 승인 후) | 5 |

## 5. 영향도 분석

- **구현 완료(2026-08-20)**: §3.2 그대로 적용. `node --check`로 인라인 스크립트 블록 구문 검사 통과. **실제 브라우저 실행 검증은 미수행**(서버 무단 기동 금지, PND) — 다음 서버 기동 시 §6 항목 확인 필요.
- **변경 파일**: `wordcloud_project/web/templates/perspective_test.html`(`saveDeploy()` 함수, `renderDeployComplete()`, 옵션 UI 영역, `_toggleGraphYearRangeEnabled`/`_computeGraphYearValues` 신규 함수)만 변경. 백엔드 라우트·서비스·DB 스키마 변경 없음.
- **영향 범위**: 체크박스 기본값이 OFF이므로 기존 "제출용 저장"만 쓰는 사용자 흐름은 완전히 동일하게 유지됨 — 회귀 위험 낮음. `body`에 `include_graph` 등 4개 필드가 추가되어 `deploy_sessions.options` JSON에 함께 저장되지만, 백엔드 `/matrix/save-deploy`(`perspective_routes.py:468`)는 `data.get(key, default)` 방식이라 모르는 키를 무시함 — 기존 세션·기존 API 동작에 영향 없음(실측 확인).

## 6. 테스트/검증 계획

- 체크박스 미체크 상태에서 제출용 저장 → 기존과 동일하게 워드클라우드만 저장되는지(회귀 확인).
- 체크박스 체크 상태에서 제출용 저장 → 동일 직원에 대해 `source='deploy'`와 `source='graph'` 항목이 모두 갤러리에 생기는지, 그래프 저장이 실패한 직원(해당 연도 평가 없음 등)이 있을 때 워드클라우드 저장 자체는 실패로 처리되지 않는지 확인.
- 연도 범위 셀렉트 4종(전체/최근1년/최근2년/최근3년) 각각에 대해, 생성된 그래프가 실제로 해당 연도 집합만 반영하는지 확인 — 특히 화면 ②에서 선택된 연도(워드클라우드용)와 다른 값을 골라도 그래프 쪽 연도가 영향받지 않는지(원자화 1.5의 분리 요구사항).
- 사용 가능한 연도가 3개 미만인 데이터(예: 2년치만 있는 직원)에서 "최근 3년" 선택 시 에러 없이 있는 만큼만 반영되는지 확인.

## 7. 리스크 및 제약

- 항목당 API 호출이 2배로 늘어나므로 전체 처리 시간이 늘어난다 — 20_02의 저속화 이슈와 맞물려 체감 저하가 커질 수 있음(체크박스 기본 OFF로 완화).
- ~~20_01을 먼저 고치지 않으면 재개 시 태그 혼선 위험~~ **해소됨** — 20_01 구현 완료 + §3.2의 옵션 영속화 설계로, 그래프 포함 여부 자체가 세션 시작 시점에 고정되어 재개 시에도 동일하게 적용된다.
- `saveDeploy()`에는 아직 20_02의 저속화 완화 로직이 없음 — 그래프까지 같이 호출하면 부하가 늘어나므로 필요 시 함께 이식 검토(별도 계획서 대상).
- 그래프 저장은 `deploy_tasks` 세션 진행률에 반영되지 않는 부가 호출이므로, 그래프만 실패한 경우 재개(`resumeDeploySession`) 시 **재시도되지 않는다**(워드클라우드 태스크는 이미 `completed`이므로 재개 대상에서 제외됨). 그래프 실패 재시도가 필요하면 별도 계획서 대상.
