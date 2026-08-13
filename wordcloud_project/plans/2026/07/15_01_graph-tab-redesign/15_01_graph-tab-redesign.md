# 계획서 — 그래프 분석(월별/연별 추이) 재구성

> 상태: Doing | 작성일: 2026-07-15
> 작업 유형: B (기능 개선/신규 기능)
> 선행: - (확인된 없음)
> 관련 CR: - (확인된 없음)
> 에픽: plans-graph-analysis

## 백업

> 빌드 수행 전, 수정 대상 소스를 plan 폴더 내 `backup/` 에 복사 완료 (사용자 요청).
> 롤백이 필요하면 `07.recovery-rules.md` 와 이 백업본을 함께 사용.

- 백업 루트: `wordcloud_project/plans/2026/07/15_01_graph-tab-redesign/backup/`
  - `backup/web/templates/plans_kanban.html` (원본 73,927 bytes)
  - `backup/src/routes/plans_routes.py` (원본 30,672 bytes)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-15 | 최초 작성 | 계획서 신규 작성 (지침 03.plan-mode + type-b-feature 준수) |
| 2026-07-15 | 백업 / 지침 | 빌드 전 소스 백업 생성 + 백업 위치 계획서 추가 + 신규 지침 `00-core/15-backup-before-modify.md` 추가(사용자 요청) |
| 2026-07-15 | 검토 정정 | 상태 토큰 `In Progress`→`Doing`(§8 등록 약어), `_index.md` 누락 등재, §2·§3.1 헬퍼 "현재 없음" 표기를 실제 구현분(`plans_routes.py:698·716`) 반영으로 정정. 구현 진행 중이라 본문 `:NNN` 라인 참조는 파일 증가로 일부 드리프트(예: `renderTrendChart`는 현재 :1482) — 최종 실측 시 재확인 |

## 요구사항 원자화

> 재확인 요청: 각 행 `기대`(내 예측 답)가 맞는지 O/X로 교정해 주세요. `작업 후 답`은 구현 후 실측 근거로 채웁니다.

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | `plans_kanban.html:275` 탭 라벨 `월별 추이`가 `그래프 분석`으로 바뀌는가? | Y | - |
| 1.2 | `그래프 분석` 패널 내에 `월별 추이`/`연별 추이` 서브탭 2개가 생성되는가? | Y | - |
| 2.1 | 연별 추이 X축이 유형/주제(CR `요청 유형`·계획서 work_type A~E)인가? | Y | - |
| 2.2 | 연별 추이에서 연도(2024/2025/2026)가 비교 series(그룹 막대/선)로 표시되는가? | Y | - |
| 3.1 | 월범위 게이지가 듀얼 핸들(시작·끝)로 구현되어 최대 2회 조작인가? | Y | - |
| 3.2 | 게이지 기본 범위가 1월~오늘 월인가? | Y | - |
| 3.3 | 지난 연도 집계가 '같은 달'까지만 합산되고 그 이후 달은 숨김/투명인가? | Y | - |
| 4.1 | 게이지·메트릭 버튼·차트 토글이 높이 32px 버튼 크기로 한 줄 좌측에 배치되는가? | Y | - |
| 4.2 | 게이지 눈금(1~12)이 핸들 중심선과 정렬되는가? | Y | - |
| 5.1 | 모든 그래프가 CR 유형별 건수(CR `요청 유형` 필드)를 출력 가능한가? | Y | - |
| 5.2 | 모든 그래프가 계획서 유형(work_type A~E) 추이를 출력 가능한가? | Y | - |
| 5.3 | 계획서 유형 범례/툴팁에 A=버그수정·B=기능개선·C=설계/아키텍처·D=리팩토링·E=DB마이그레이션 의미가 병기되는가? | Y | - |
| 6.1 | 차트 SVG가 `width="100%"`+`viewBox`로 컨테이너 폭에 따라 크기가 변하는가(반응형)? | Y | - |
| 7.1 | 월별 추이 유형계에서 X축 모드 토글(시간누적/유형별)이 제공되는가? | Y | - |
| 7.2 | 월별 추이 유형계에서 전년대비(cur/prev)가 병기되는가? | Y | - |

## 1. 요구사항

1. `계획 현황`의 `월별 추이` 탭을 **`그래프 분석`** 으로 개명.
2. 하위에 **`월별 추이` / `연별 추이`** 서브탭 분리.
3. 모든 그래프가 **CR 유형별 건수**(CR `요청 유형`)와 **계획서 유형 추이**(work_type A~E)를 출력.
4. 연별 추이: **X축=유형/주제, Y축=수량**, 연도별 비교 series.
5. 연별 추이에 **월범위 게이지**(듀얼 핸들, 기본 1~오늘 월), 지난 연도는 같은 달까지만 합산(이후 숨김).
6. 게이지는 버튼 크기(높이 32px)·한 줄 좌측 배치, 눈금(1~12) 정렬.
7. 차트 **막대/선 토글** 공통 적용.
8. 월별 추이도 유형계(CR 유형별·계획서 유형) 제공 + 축모드 토글(시간누적/유형별) + 전년대비.
9. 차트는 화면 크기에 따라 크기 변화(반응형, **확인됨**: `renderTrendChart` 가 SVG `width="100%" viewBox preserveAspectRatio` 사용, `plans_kanban.html:1436`).
10. 계획서 유형 A~E 각 알파벳 의미를 설명에 포함.

## 2. 현재 시스템 분석

- **탭/패널(프론트)**: `plans_kanban.html:275` `data-view="trend"` 라벨 `월별 추이`. 패널 `view-trend`(`plans_kanban.html:360-382`) — 컨트롤 `trendYear`(`:365`), `trendMetrics` 버튼 4종(`:371-374`), 차트 컨테이너 `trendChart`(`:381`). `loadTrend()`(`:1354`)가 `/admin/api/plans/trend?year=` 호출, `renderTrendChart()`(`:1410`)가 SVG 생성(반응형 확인됨, `:1436`). `TREND_METRIC_LABELS`(`:1352`).
- **백엔드**: `plans_trend()`(`plans_routes.py:638`) — 인자 `year`만 받음. `_cr_monthly_for_year`(`:139`), `_plans_monthly_for_year`(`:158`)로 `cr_count/fp/hours/plan_count` + `totals` 반환. **유형별 집계 헬퍼는 계획서에만 존재**: `_plans_by_type_for_year`(`:203`, `(table{ym:{A..E,other}}, total)` 반환, `_parse_index_md`+`_normalize_work_type` 사용). ~~CR 유형별 헬퍼는 존재하지 않음~~ → **현재는 구현 완료: `_cr_by_type_for_year`(`:698`)·`plans_trend_type`(`:732`)·`_available_years`(`:716`) 존재.**
- **CR 유형 필드**: CR 파서 `_parse_cr_file`(`:33`)가 정규식 `요청\s*유형\s*: (.+)`(`:46`)로 `cr['type']`(`:84`)에 저장. → 신규 CR 유형 헬퍼는 `cr['type']` 기준 집계.
- **work_type 의미**: `_normalize_work_type`(`:176-200`) 주석(`:179`)에 **A=버그수정 B=기능개선 C=설계/아키텍처 D=리팩토링 E=DB마이그레이션**, 미분류=other 명시. 계획서 범례/툴팁은 이 값 재사용.
- **디자인 시스템**: Modern Minimal, 주색 `#6366f1`(`00-overview.md:8`). 인라인 스타일 지양·클래스 사용 원칙(`00-overview.md:38-41`). 기존 trend 차트는 `#3b82f6`(cur)/`#c9d6e3`(prev) 사용 — 신규 렌더러는 디자인토큰 주색 `#6366f1` 계열로 정렬하되 기존과 시각 일관성 유지.

## 3. 구현 상세

### 3.1 백엔드 (`plans_routes.py`)

- `plans_trend()`(`:638`)에 `mode` 파라미터 추가(`monthly` 기본 / `yearly`). 기존 `monthly` 응답 형태 유지(하위 호환).
- **헬퍼 `_cr_by_type_for_year(year)`** (구현 완료 `:698`): `_scan_all_crs()` 순회, `cr['ym'].startswith(str(year)+'-')` 필터, `{mm:{type:count}}` + `types=set()` 집계 반환.
- **헬퍼 `_available_years()`** (구현 완료 `:716`): CR 연도(`cr['ym'][:4]`) ∪ plans 연도 폴더(`os.path.dirname(PLANS_DIR)` 하위 `YYYY/`) 합집합, 정렬 리스트 반환.
- **yearly 모드 응답**:
  - 요청 인자 `mStart`,`mEnd`(1~12, 기본 1~현재월). `year < 현재연도`인 경우 윈도우 끝을 현재월로 clamp(미래 달 숨김/투명 → "같은 달까지만" 구현).
  - `series`: `cr_count/fp/hours/plan_count` = 연도별 윈도우 합산; `cr_by_type` = `{types:[...], data:{year:{type:count}}}`; `plan_by_type` = `{types:['A','B','C','D','E','other'], data:{year:{type:count}}}`(`_plans_by_type_for_year`의 `table`에서 윈도우 월 합산).
  - `years` 배열 포함.

### 3.2 프론트엔드 (`plans_kanban.html`)

- **라벨 개명**: `:275` `📉 월별 추이` → `📊 그래프 분석`.
- **서브탭**: `view-trend`(`:360`) 상단에 `[월별 추이][연별 추이]` 서브탭(기본=월별). `switchView` 패턴 재사용, `loadTrend(mode)` 분기.
- **월별 추이 컨트롤**: 기존 `trendYear`+`trendMetrics` 유지 + **유형 메트릭 버튼**(CR 유형별/계획서 유형) + **축모드 토글**(시간누적/유형별) + **차트 토글**(막대/선). `trendChart` 컨테이너 재사용.
- **연별 추이 컨트롤**(신규 `yearlyChart` 컨테이너):
  - **커스텀 듀얼핸들 게이지**: 네이티브 `<input type=range>` 미사용. 트랙+핸들+채움+눈금을 **단일 좌표계** `pct(v)=(v-1)/11*100` 로 매핑. 핸들 `top:50%; transform:translate(-50%,-50%)`(중심선 정확 배치), 눈금(1~12)은 `pct(m)` 위치에 표시(핸들·눈금 정렬 보장). pointer 드래그(시작/끝 핸들), 트랙 클릭 시 가장 가까운 핸들 이동(최대 2회 조작).
  - 게이지·메트릭 버튼·차트 토글을 **높이 32px 버튼 크기로 한 줄 좌측 flex 배치**(`.trend-metric`, `.form-select-sm` 높이 준용).
- **신규 렌더러 `renderTypeChart(container, mode, data, opts)`**:
  - 월별/시간누적: X=월(1~12), 유형 누적 stack, 당년(cur) solid + 전년(prev) 저투명 오버레이.
  - 월별/유형별: X=유형, Y=당년 합산.
  - 연별: X=유형, 연도별 그룹 막대(또는 선 토글 시 연도별 line).
  - **반응형**: SVG `width="100%" viewBox preserveAspectRatio`(`renderTrendChart:1436` 미러).
- **계획서 유형 범례/툴팁**: `A 버그수정 · B 기능개선 · C 설계/아키텍처 · D 리팩토링 · E DB마이그레이션 · 기타`(`_normalize_work_type:176-180` 값 재사용).
- **디자인 시스템 준수**: 주색 `#6366f1` 계열(cur/active), muted `#c9d6e3`(prev); 게이지/유형 스타일은 `<style>` 블록에 클래스로 정의(인라인 스타일 지양, `00-overview.md:38-41`).

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `plans_routes.py`: `_cr_by_type_for_year`, `_available_years` 신규 추가 | - |
| 2 | `plans_trend()`(`:638`) `mode=yearly` 분기 + 응답 스키마 확장 | 1 |
| 3 | `plans_kanban.html:275` 라벨 개명 + 서브탭 추가 | - |
| 4 | 커스텀 듀얼핸들 게이지(좌표계 통일) + 컨트롤 한 줄 배치 CSS/JS | 3 |
| 5 | `renderTypeChart` 추가(월별 축토글·연별 그룹·막대/선 토글·반응형) | 3 |
| 6 | `loadTrend(mode)` 리팩터 + 게이지→API(`mStart/mEnd`) 연동 | 2,4,5 |
| 7 | Flask 기동 `/admin/plans` 동작 확인 | 1~6 |

## 영향도 분석

- **변경 파일**: `wordcloud_project/web/templates/plans_kanban.html`(탭 라벨·view-trend 패널·JS 렌더러·`<style>`), `wordcloud_project/src/routes/plans_routes.py`(`plans_trend`·신규 헬퍼 2종).
- **DB/스키마 변경**: 없음.
- **하위 호환**: `mode` 미지정 시 기존 `monthly` 응답과 동일 → 기존 월별 추이 동작 유지. 간트차트/칸반 등 타 화면 영향 없음.
- **백업**: 빌드 전 `plans/2026/07/15_01_graph-tab-redesign/backup/` 에 원본 보관.

## 테스트/검증 계획

- **디자인변경 체크리스트**(04-design-change/checklist.md): 규모판단(표준)·대상파일분석·일관성검토·계획승인 완료.
- **원자화 검증**: §요구사항 원자화 10행 각각 O/X 재확인 후, 구현·실측로 `작업 후 답` 채움(근거: `파일:라인`/실측 로그). 기대와 불일치 시 Done 불가.
- **기능 시나리오**: ① 탭명·서브탭 전환 ② 연별 게이지 정렬(핸들 중심선=눈금)·기본범위 1~오늘월 ③ 지난 연도 미래 달 숨김 ④ CR 유형별/계획서 유형 출력 + A~E 범례 병기 ⑤ 막대/선 토글 ⑥ 월별 유형계 축모드 토글+전년대비 ⑦ **창 크기 변경 시 차트 폭 반응**(반응형).
- **자기완결성 점검**(03.plan-mode §15): 경로 전체기재·수치 재집계 가능·`[[링크]]` 잔존 없음.

## 리스크 및 제약

- **게이지 정렬**: 목업에서 반복 보정했으나 실제 DOM에서 최종 재확인 필요(단일 좌표계로 mitigate).
- **"주제" 차원**: CR/계획서에 별도 subject 필드가 없음 → 연별 X축은 **유형(요청유형/작업유형)만** 사용. 주제 차원 추가는 파서 확장이 필요해 본 계획 범위 외(향후).
- **성능**: `_scan_all_crs()`가 헬퍼별 호출 — 관리자 페이지라 허용 가능. 필요 시 캐싱 검토.
- **연도 폴더 부재**: `_plans_by_type_for_year`(`:212`)가 `isdir` 가드하므로 안전.
