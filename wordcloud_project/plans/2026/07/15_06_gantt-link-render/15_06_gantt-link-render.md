# 계획서 — 간트차트 CR연결선·선행화살표·CR마일스톤 자동 렌더링

> 상태: Todo | 작성일: 2026-07-15 | 작업 유형: B (기능 개선/신규 기능) | 에픽: kanban-linkage | 선행: 2026/07/14_06_gantt-cr-ui-fix
> 관련 문서: `.clinerules/docs/development/kanban-board-guide.md`(§4.10 간트차트·§4.12 링크린터 '예정/UI 미연결'), `.clinerules/docs/development/kanban-board-api-contract.md`(§간트 API계약:186-208), `wordcloud_project/src/routes/plans_routes.py`(`plans_gantt:944`), `wordcloud_project/web/templates/plans_kanban.html`(`ganttRender()`)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-15 | 전체 | 최초 작성 — 간트차트 `cr_links`/`deps`/`milestones` 프론트엔드 렌더링(지침상 '예정/UI 미연결' → 구현) |

## 1. 배경 및 목적

`_index.md` 양식(관련 CR·선행 컬럼)에 담긴 링크 데이터가 있으면, 간트차트(관계도)가 이를 **읽어 알아서 연결선·화살표를 자동으로 그려야** 한다. 현재 백엔드는 값을 정상 반환하나 프론트엔드가 선·화살표를 그리지 않아, 양식에 데이터가 있어도 차트에 연결이 표시되지 않는다. 본 계획은 **데이터는 양식대로 두고, 차트가 그 데이터를 자동 렌더링**하도록 프론트엔드를 구현한다(한 번 구현하면 양식 데이터만 있으면 모든 plan이 자동 연결).

## 2. 요구사항

- (사용자 요청) 양식(`_index.md` 관련CR/선행) 데이터를 기반으로 간트차트가 CR연결선·선행화살표를 **자동** 으로 그릴 것.
- (지침 명세) `kanban-board-guide.md:356-358`의 간트차트 명세 — 마일스톤(◆)/선행간선(DAG)/CR링크 — 를 UI에 실제 반영(현재 '예정/UI 미연결', `:208,368,372`).
- (범례 일치) 연결선 스타일은 기존 범례(`:141` 회색 실선 선행, `:143` 보라 점선 CR)와 동일하게.

## 3. 현재 시스템 분석

- **백엔드 `plans_gantt`(`:944`)는 이미 정확히 반환** — `milestones`(`:1019`, crs의 `date`/`req_id`), `deps`(`:1020`, `{from,to}` plan id, `:993`), `cr_links`(`:1022`, `{plan,cr}`, `:1005`). 선행은 `parse_all_months`로 실존 검증(`:989-995`). lint=0(15_03 백필 후 확인).
- **프론트엔드 `ganttRender()`(`plans_kanban.html:1098`) 결함(코드 검증 완료)**:
  - `crLinks`는 **칩 라벨용만** 소비(`:1145-1148`, `:1226`) — 연결**선** 미드로잉.
  - `deps`는 **프론트에서 0회 참조** — 선행 화살표 미구현.
  - `milestones`는 **합계용만** 소비(`:1057-1059`) — CR 다이아몬드가 차트에 **그려지지 않음**(`gantt-pt` CSS `:180-185`는 plan point용 `:1231`뿐).
  - SVG 오버레이(`:1248-1256`)는 **"오늘" 선 하나만** 그림. `cr_links`/`deps` 순회 드로잉 코드 없음.
- **좌표 계산**(`:1110-1132`): x = `daysBetween(startDate, date) * DAY_W`; 행높이 38px(`:157,164,170`), 바 top 9px(`:172`); SVG `viewBox="0 0 chartWidth svgHeight"`, `svgHeight = rowIndex*38 + 30`(`:1249`).
- 범례(`:1161-1163`)는 CR연결(보라 점선 `.gantt-cr-key`)/선행의존(회색 `.gantt-dep-key`)를 이미 표시 → 렌더링 의도 확인됨.

## 4. 구현 상세

### 4.1 백엔드

- **변경 없음.** `plans_gantt`가 이미 `milestones`/`deps`/`cr_links`를 정확히 반환. 선행 실존·DAG 순환은 이미 `parse_all_months`+`_link_linter`로 검증. 추가 API 없음.

### 4.2 프론트엔드 (`plans_kanban.html` `ganttRender()`)

- **UI 변경**:
  1. **CR 마일스톤 레인(상단) 추가** — `milestones[]`를 다이아몬드(`.gantt-pt` 보라 `#6f42c1`, 범례 `:1161` 일치)로 배치. x = `getPlanX(cr.date)`, 상단 전용 레인(row)에 표시. `svgHeight`/`viewBox` 보정에 레인 높이(38px) 포함.
  2. **위치 맵 축적**(룹프 내): `planPos[id] = {x: getPlanX(t.date), row, yc: row*38 + 19}` 및 `crPos[req_id] = {x, yc}`. collapsed 그룹은 밴드 1행으로 맵핑(`:1197-1213`).
  3. **SVG 오버레이(`:1248-1256`) today 선 이후 드로잉**:
     - `cr_links` 각 항목 → 보라 **점선** `<line>`(`stroke:#6f42c1; stroke-dasharray:3 3`) plan바중심(x+w/2, yc) → CR 다이아몬드(x, yc).
     - `deps` 각 항목 → 회색 **실선 + `<marker>` 화살표**(`stroke:#8a94a6`, 범례 `:141` 일치) `from`→`to`. `<defs><marker>` 화살표 정의 추가.
  4. **범위 이탈 클립/스킵**: x<0 또는 x>chartWidth 인 항목(연도 밖 CR/plan)은 선 미드로잉.
- **연동 방식**: 기존 `fetch('/admin/api/plans/gantt')` 응답 그대로 소비(추가 호출 없음). 기존 CR 칩(`:1147`)은 유지(라벨 + 선 모두 표시).

## 5. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | CR 마일스톤 레인(상단) 렌더 + `crPos` 맵 축적, `svgHeight`/`viewBox` 보정 | - |
| 2 | `planPos` 맵 축적(룹프 내 `rowIndex` 추적, collapsed 밴드 맵핑) | 1 |
| 3 | SVG에 `cr_links` 보라 점선 / `deps` 회색 화살표 드로잉 + `<defs><marker>` 정의 | 1, 2 |
| 4 | 연도 이탈 클립/스킵(깨짐 방지) | 3 |

## 6. 영향도 분석

- **간트차트 탭만 변경**(`plans_kanban.html` `ganttRender`). 칸반보드/월별 CR현황/월별 추이 뷰는 `plans_gantt` 미사용 → 무영향(15_03 §8 실측과 동일: 관련CR/선행은 간트·린터만 소비).
- **백엔드 미변경** → API 계약(`kanban-board-api-contract.md:186-208`) 그대로. 15_03 백필 데이터가 그대로 자동 연결됨.
- **lint 영향 없음**(데이터 변경 아님, 프론트만).

## 7. 테스트/검증 계획

- [ ] 1. `/admin/api/plans/gantt` 응답에 `milestones`/`deps`/`cr_links` 포함 확인(이미 반환됨)
- [ ] 2. 간트 탭: CR 다이아몬드(◆) 상단 레인에 표시
- [ ] 3. `14_04_gantt-chart`(관련CR 6건) 행에서 CR연결선(보라 점선)이 해당 CR 다이아몬드로 그려짐
- [ ] 4. 선행 화살표 표시(예: `15_02→15_01`, `11_01→15_01`, `13_01→10_01`)
- [ ] 5. 연도 이탈 CR/plan 링크 스킵되어 선이 깨지지 않음
- [ ] 6. lint=0 유지, 칸반/CR현황/추이 정상

## 8. 리스크 및 제약

| 리스크 | 영향 | 조치 |
|---|---|---|
| collapsed 그룹 내 plan 링크 | 밴드 1행으로 맵핑되어 화살표가 밴드행 향함 | 허용(그룹 단위 표시). 필요시 밴드 내 우선순위 plan으로 맵핑 |
| 연도 이탈 항목 | x 음수/초과로 선 깨짐 | 범위 클립/스킵(구현순서 4) |
| 마일스톤 레인 높이 추가 | `svgHeight`/`rowIndex` 불일치로 선 y좌표 어긋 | 마일스톤 레인도 `rowIndex`에 포함시켜 `svgHeight` 통일(구현순서 1) |
| `deps` 미사용으로 화살표 미표시(현상) | 연결 안 보임 | `deps` 순회 드로잉 추가(구현순서 3) |
