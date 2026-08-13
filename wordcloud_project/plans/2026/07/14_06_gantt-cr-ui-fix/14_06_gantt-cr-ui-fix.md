# 계획서 — 간트·CR 현황 UI 수정

> 상태: Done | 완료일: 2026-07-14 | 작업 유형: B | 에픽: kanban-linkage | 선행: 2026/07/14_05_gantt-chart-rev

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-14 | 최초 작성 | 간트 주차눈금 제거·오늘선 정렬·연도너비 fit, 월별 CR현황에 계획서 종류별 수량 보강 (4건) |
| 2026-07-14 | 구현 중 추가 | work_type 이 자유텍스트(기능 개선/bug fi/type-B 등)로 뒤섞여 A~E 매핑 대다수가 기타로 빠짐 → `_normalize_work_type()` 키워드 정규화 추가(실측 2026: A10 B42 C4 D5 E0 기타32 / 총93) |
| 2026-07-14 | 위치 정정(사용자 지적) | 계획서 수량은 **간트차트** 요약(`/api/plans/gantt` 응답 + `gantt-plansum`)에 둬야 함. CR 패널(월별 CR 현황)에 잘못 넣었던 계획서 info 전부 되돌림 → CR 패널은 CR 전용(수량/FP/공수)으로 원복, `cr-monthly`의 plan_* 필드 제거. |
| 2026-07-14 | 500 수정 | `plans_gantt()`에 `year_param` 정의 누락 → `_plans_by_type_for_year(year_param)` 호출 시 NameError(500). 함수 상단에 `year_param = request.args.get('year','').strip() or _plans_year()` 추가. test_client 호출 → STATUS 200, plan_total 93, milestones 52 확인. |
| 2026-07-14 | 간트 현황 보강 | 요구: 간트차트에 칸반 상태요약(✅완료🔄작업중🔶Pre-Done📋예정📌보류🗑️Drop·총)과 CR 요약이 동일 형태로 표시. `loadGantt()`에서 `tasks` 기준 상태 집계 후 `#ganttSummary`(`.git-summary`=13px)에 CR 요약 옆에 추가. |
| 2026-07-14 | 크기 통일 | 제목: 칸반 `h1` 22→20px(git/trend `h2` 20px와 통일). 현황: 칸반 `.stats` 14→13px, 간트 `.gantt-plansum` 11.5→13px(기준=월별 CR현황 `.git-summary` 13px). 간트 범례 `.gantt-legend`(11.5px)는 차트 키로 유지. |
| 2026-07-14 | 기본 접힘 | 간트차트 시작 시 주제(에픽)별 그룹을 **전체 접힘** 상태로 시작. `loadGantt()`에서 `ganttCache=d` 직후 `ganttCollapsed = new Set(ganttAllGroupKeys())` 로 초기화(기존 빈 Set→전체 접힘). |

## 요구사항 원자화

| # | 원자 질문 | 기대(예측) | 작업 후 답 (근거) |
|---|-----------|------------|------------------|
| 1.1 | 간트차트에서 월 아래 '세부 일자(주차)' 눈금 행을 제거하는가? | Y | 미검증 |
| 1.2 | 제거 후 상단에 월 레이블 행만 남는가? | Y | 미검증 |
| 2.1 | '오늘' 선이 2026-07-14 위치에 표시되는가? (현상: ~8월 말로 밀림) | Y | 미검증 |
| 2.2 | 원인은 그리드 블록 100% 과팽창 + DAY_W `floor` 잉여로 SVG 좌표계가 늘어나서(비율 왜곡) 생긴 것인가? | Y | 미검증 |
| 3.1 | 월별 CR 현황 패널에 계획서 작업유형(A~E)별 수량과 총수량을 추가하는가? | Y | 미검증 |
| 3.2 | 기존 CR 수량·FP·공수 표기는 그대로 유지되는가? | Y | 미검증 |
| 4.1 | 1년 너비가 컨테이너 폭에 비율로 맞춰 꽉 차게(12월 이후 잔여 공간 없음) 표기되는가? | Y | 미검증 |
| 4.2 | 컨테이너가 좁아지면 비율 축소되어 가로 스크롤이 안 생기는가? | Y | 미검증 |

## 1. 배경 및 목적

`/admin/plans` 간트차트(및 월별 CR 현황 탭) 사용성 개선 4건:
1. 월 하단 주차(세부 일자) 눈금이 불필요 → 제거
2. '오늘' 선이 실제 날짜(7.14)보다 한참 오른쪽(~8월 말)에 그려짐 → 정렬 오류 수정
3. 월별 CR 현황 패널이 CR 정보만 보여 불균형 → 계획서 작업유형별 수량·총수량 보강(사용자 확정: 보강 방향)
4. 1년 표기가 컨테이너보다 좁아 12월 이후 빈 공간 발생 → 컨테이너 폭에 비율 fit

## 2. 현재 시스템 분석

대상 파일:
- 프론트: `D:\dev\wordcloud\wordcloud_project\web\templates\plans_kanban.html`
- 백엔드: `D:\dev\wordcloud\wordcloud_project\src\routes\plans_routes.py`

### 2.1 오늘 선 오정렬 / 연도 너비 잔여 (요구 2·4)
- `ganttRender()` — `plans_kanban.html:1003`
  - `DAY_W = Math.max(2, Math.floor(avail / totalDays))` (`:1019`) → `floor`로 인해 `chartWidth = totalDays*DAY_W` 가 `avail` 보다 작아짐(최대 364px 잉여).
  - 그리드 `style="min-width:' + (chartWidth + GANTT_LABEL_W) + 'px"` (`:1080`). 블록 요소는 `min-width` 미만이면 부모 폭(100%)으로 팽창하므로, 실제 그리드 폭 ≥ `avail+250` 이 됨.
  - `.gantt-tcol { flex:1 }` (`:160`) → 그리드가 팽창하면 tcol 도 `chartWidth` 보다 넓어짐.
  - SVG 오버레이 `viewBox="0 0 chartWidth svgHeight"`, `preserveAspectRatio="none"`, `.gantt-ov{position:absolute;inset:0}` (`:161`, `:1167`) → tcol 이 `chartWidth` 보다 넓으면 SVG 가로축이 늘어남(stretch).
  - 결과: 월/막대는 px 좌표 그대로(늘어나지 않음), 오늘 선만 SVG 좌표계 비율(≈1.3x)로 늘어나 우측 오정렬 + 12월 이후 빈 공간. (원인: 2.2)
- `today` var: `plans_kanban.html:1009`, 오늘 선: `:1165-1173` (`todayX = daysBetween(startDate, today) * DAY_W`, `:1168`).

### 2.2 주차 눈금 (요구 1)
- `weeks` 배열 생성: `plans_kanban.html:1035-1044`
- 렌더: `gantt-wrow` div `:1088-1092`
- CSS: `.gantt-wrow`(`:154-157`), sticky 규칙 `:147`(`.gantt-mrow, .gantt-wrow`), `:149`(`.gantt-wrow > .gantt-lead`)

### 2.3 월별 CR 현황 패널 (요구 3)
- 탭/패널: `plans_kanban.html:274`(탭), `:329`(h2), 렌더 `loadCrMonthly()` `:1213`
- 요약(summary) 현재: 총 CR·FP·공수만 표기 `:1237-1240`
- 월별 헤더 통계: `:1264-1269` (FP/공수/누적만). 행 테이블: `:1274-1296`
- 백엔드 API `/api/plans/cr-monthly` — `plans_routes.py:569-582`. 응답: `months`(월별 cr 리스트), `total_crs`, `total_fp`, `total_hours` 만. 계획서 수량 필드 없음.
- 계획서 작업유형(`work_type`, A~E)은 `_parse_index_md()` 가 반환 (`:344-360`, 추출 `:307-324`). 유형 의미: A=버그수정, B=기능개선, C=설계/아키텍처, D=리팩토링, E=DB마이그레이션 (`03.plan-mode.md:195` 유형 테이블).

## 3. 구현 상세

### 3.1 백엔드 (`plans_routes.py`)
- 신규 헬퍼 `_plans_by_type_for_year(year)` 추가(근방 `:158` `_plans_monthly_for_year` 아래):
  - 연도 폴더 `os.path.join(os.path.dirname(PLANS_DIR), str(year), mm)` 순회, 각 월 `_parse_index_md(month_dir)` 호출.
  - 월별 `{A,B,C,D,E,other:count}` 집계 + 전체 `total` 반환.
- `plans_cr_monthly()` (`:569`) 응답 확장:
  - 월별 `months` 각 항목에 `plans_total`(해당 월 계획서 건수)·`plans_by_type`({A..E,other}) 추가.
  - 최상단에 `plan_total`(연간 총 계획서)·`plan_by_type`(연간 유형합계) 추가.
  - 기존 `total_crs/total_fp/total_hours/months` 는 그대로 유지(요구 3.2).

### 3.2 프론트엔드 (`plans_kanban.html`)
**요구 1 (주차 제거)**
- `weeks` 생성 블록(`:1035-1044`) 삭제.
- `gantt-wrow` 렌더(`:1088-1092`) 삭제.
- CSS 정리: `:147` → `.gantt-mrow` 만 남김 / `:149` → `.gantt-mrow > .gantt-lead` 만 / `:154-157`(.gantt-wrow 계열) 전부 삭제.

**요구 2·4 (오늘 선 정렬 + 너비 fit)**
- `DAY_W` 를 부동소수로 변경: `var DAY_W = avail / totalDays;` (`:1019`, `Math.max` 하한 제거 or `Math.max(0.5, ...)`). → `chartWidth = avail` 로 잉여 0.
- 그리드 폭을 명시 고정: `:1080` `style` 에 `width:' + (chartWidth + GANTT_LABEL_W) + 'px;min-width:' + (chartWidth + GANTT_LABEL_W) + 'px'`.
- `.gantt-tcol` 인라인 폭 고정: 그리드 생성 시 tcol div 에 `style="width:' + chartWidth + 'px"` 부여(flex:1 과 충돌 방지). → SVG `viewBox` 폭과 tcol 실폭 1:1 → stretch 소멸, 오늘 선 정렬(요구 2)·잔여 공간 제거(요구 4) 동시 해결.
- `avail` = `content.clientWidth - GANTT_LABEL_W - 2` (`:1016`) 그대로. 컨테이너가 좁아지면 `DAY_W` 자동 축소 → 가로 스크롤 미발생(요구 4.2).

**요구 3 (CR 패널 보강)**
- `loadCrMonthly()` summary(`:1237-1240`) 에 계획서 총수량·유형별 수량 추가:
  - `📋 계획서 <strong>{plan_total}</strong>건 (B:{x} A:{y} C:{z} D:{w} E:{v})` 형태(`plan_by_type` 사용).
- 월별 헤더 통계(`:1264-1269`) 에 계획서 수량 추가:
  - `📋 {plans_total}건(B:x A:y ...)` 를 `mh-stats` 에 삽입.
- 유형 라벨 맵(JS 상수) 추가: `A:'버그수정', B:'기능개선', C:'설계', D:'리팩토링', E:'DB마이그레이션'`.
- 기존 CR 수량·FP·공수 렌더는 변경 없음.

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | 백엔드 `_plans_by_type_for_year` 추가 + `cr-monthly` 응답 확장 (`plans_routes.py`) | - |
| 2 | 프론트 주차 눈금 제거(JS+CSS) (`plans_kanban.html`) | - |
| 3 | 프론트 DAY_W 부동소수 + 그리드/tcol 폭 고정 → 오늘 선 정렬·너비 fit | - |
| 4 | 프론트 `loadCrMonthly` 계획서 유형별 수량·총수량 렌더 보강 | 1 |

## 영향도 분석

- 변경 파일: `web/templates/plans_kanban.html`(간트 렌더·CSS·CR 패널), `src/routes/plans_routes.py`(신규 헬퍼+API 확장)
- 영향 범위: `/admin/plans` 간트탭(요구1·2·4), 월별 CR현황 탭(요구3). 캔반/트렌드 탭은 비변경.
- 역호환: `cr-monthly` 응답에 필드 추가(기존 필드 유지) → 기존 소비자 영향 없음.

## 테스트/검증 계획

1. 서버 기동 후 `/admin/plans` → 간트탭: 주차 행 없음(요구1), 월 레이블만 표시.
2. 오늘 선이 2026-07-14 열에 위치(요구2). 12월 이후 빈 공간 없음(요구4). 브라우저 폭 변경 시 1년이 비율 축소·가로 스크롤 없음(요구4.2).
3. 월별 CR현황 탭: 요약에 계획서 총수량·유형별 수량, 월별 헤더에 계획서 수량 표기. CR 수량/FP/공수 유지(요구3).
4. JS 구문 검증(`node --check`, Flask `{{ }}` 태그 치환 후).

## 리스크 및 제약

- `_parse_index_md` 는 월별 `_index.md` 를 전수 파싱(디스크 I/O). CR API 호출 시점에 연간 12개월 × 파싱 → 경미한 오버헤드. 캐싱 없음(기존 `cr-monthly` 도 매번 스캔). 수용 가능.
- `work_type` 이 빈값이면 `other` 로 집계(라벨 미표시 또는 '기타' 처리).
- DAY_W 부동소수 사용 시 막대 `min-width:20px`(`gantt-bar` CSS `:173`)로 1일 짧은 항목 가시성 보장.
