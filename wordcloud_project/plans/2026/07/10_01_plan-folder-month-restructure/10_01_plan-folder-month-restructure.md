# 계획서 — 계획서 폴더 구조 YYYY/MM/DD_NN 개편 + 지침·칸반 동기화

> 상태: Done | 완료일: 2026-07-13 (칸반 월별 _index 동기화 + 전체(ALL) 통합보드·타월 Done 그룹카드 + 카드 클릭 정확 월폴더 해석. 브라우저 수동확인 완료)
> 작업 유형: B (기능 개선/신규 기능) + 지침 수정(08-guideline-modification)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-10 | 전체 | 최초 작성 — 폴더 규칙 `MMDD_NN` → `MM/DD_NN` 개편, 지침·칸반 동기화 |
| 2026-07-13 | §5 칸반보드 변경·§7 검증 | **월별 분할로 인한 Done 가시성 단절 버그 수정**: (1) `parse_all_months()` 추가 → 모든 월 `_index.md` 병합 파싱 (2) 드롭다운 `전체(ALL)` 옵션 + `?month=` 파라미터 (3) 월 보드에서 타월 Done을 "이전 완료(N건)" 그룹카드로 항상 표시 (4) `renderDoneColumn` 비교 기준을 현재실월→선택보드월로 교정 (5) 카드 클릭 시 `plan.month`로 정확 월 폴더 해석 |
| 2026-07-13 | §5 재구현(회귀 복원) | 오염된 핸드오프 요약을 믿고 아코디언(현재월 전개/과거월 접기)으로 잘못 재작성한 회귀를 원복하고, §5.2 명세대로 재구현: 백엔드 `parse_all_months()`+`?month=`+`is_other_month` 그룹카드, 프론트 ALL 보드+`MM월` 배지+타월 Done 그룹카드, `openDetail(planId, month)`→`?dir=plans/2026/MM` 정확 해석(기존 "Plan file not found" 버그 해결). 연도 `_index.md`는 §4.5대로 삭제(월 `_index.md`가 단일 정보원). Playwright 브라우저 검증 통과 |

## 1. 배경 및 목적

### 1.1 문제
- `wordcloud_project/plans/2026/` 에 계획서 폴더가 **74개 평면 배치**되어 탐색기/터미널에서 월 단위 구분이 안 됨(사용자 불편).
- 지침 `03.plan-mode.md` §1·§2·§12는 `MMDD_NN` 평면 구조인데, §8에는 이미 *"월별 폴더 최초 생성 시 `_index.md` 함께 생성"* 문구가 있어 **지침 내부 불일치**.
- 칸반보드 `plans_kanban.html`의 Done 컬럼에는 현재월/과거월 분리 로직이 존재하나, 파일시스템 단위 월 폴더가 없어 구조적 정합이 맞지 않음.

### 1.2 목표
1. 폴더 규칙을 `YYYY/MMDD_NN` → `YYYY/MM/DD_NN` 로 변경(월 단위 폴더 추가).
2. 기존 74개 계획서 전체 이관(전체 이관 방식 확정).
3. 지침 §1·§2·§8·§12를 신규 구조로 정합화.
4. 칸반보드가 월별 `_index.md` 를 월 선택 드롭다운으로 집계하도록 변경.
5. plan_id/파일명을 `DD_NN_작업명` 으로 정리(ID에서 월 prefix 제거, 카드 표시 단축).

## 2. 현황 (사실 기반)

- 파일시스템: `plans/2026/` 직계 계획서 폴더 **74개 평면 배치**, 월 폴더 없음.
- 월별 분포: **04월 1 · 06월 65 · 07월 8** (계 74)
- `_index.md`: 75행(헤더4 + 데이터 71행). plan_id=`MMDD_NN_작업명`, 작성일=`YYYY-MM-DD`.
- 지침 소비자: **`plans_routes.py`만**. `settings.py`는 `PLANS_DIR=plans/2026`(연도 루트)만 제공. `_datasets` 등 타 폴더 영향 없음.
- 칸반: `plans_dir/_index.md` 1개 파싱, `plan_id==폴더명` 가정(`os.path.join(plans_dir, plan_id)`). 드롭다운은 PLANS_DIR의 **형제** dir 중 `_index.md` 보유 폴더 탐색(`plans_routes.py:272-278`). Done 컬럼에 현재월=개별/과거월=그룹 분기 존재(`plans_kanban.html:376-418`).

## 3. 지침 개정안 (Before/After) — `.clinerules/core/00-core/03.plan-mode.md`

| 항목 | Before | After |
|------|--------|-------|
| §1 저장위치 | `YYYY/` → `MMDD_NN_작업명/` | `YYYY/` → `MM/`(2자리) → `DD_NN_작업명/` |
| §2 파일명 | `MMDD_NN_작업명.md` | `DD_NN_작업명.md` (폴더명=파일명 유지) |
| §8 `_index.md` | `YYYY/_index.md` 1개 집계 | **월별** `YYYY/MM/_index.md` 각 생성, plan_id=`DD_NN_…` |
| §12 예시트리 | 월 미분리 | `2026/06/_index.md` + `2026/06/05_03_…/` 형태 |

§3~§7(상태/수정이력), §9(연도고정), §14(원자화)는 불변.

## 4. 폴더 이관 계획 (전체 74개)

1. 폴더명 앞 2자리=MM 추출 → `2026/MM/DD_NN_작업명/` 생성 후 이동.
2. 폴더명 `MMDD_NN_x` → `DD_NN_x` 변경, 내부 메인 `.md`도 rename(파일=폴더 규칙).
3. `_index.md` 71행을 MM별로 분할 → `2026/MM/_index.md` 생성(plan_id 컬럼 `MMDD_NN`→`DD_NN`, 작성일 불변).
4. `_index.md`에 없는 3개 폴더(예: 빈 `0624_03_plan-folder-sequence-rule`)는 이관 후 행 추가 또는 Drop 처리.
5. 연도 `_index.md`(`2026/_index.md`)는 월 파일 완성 후 삭제(드리프트 방지).
6. 본 계획서 자체도 신규 규칙 시범으로 `2026/07/10_01_plan-folder-month-restructure/` 에 생성.

## 5. 칸반보드 변경 (`plans_routes.py` + `plans_kanban.html`)

### 5.1 발생한 버그 (월별 분할 부작용)
- 월별 `_index.md` 분할로 각 월 보드는 **자기 월 `_index.md`만** 파싱 → 타월 Done이 보드에서 완전 누락 (예: `2026/07` 보드에서 `2026/06` Done 61건 소실). 원래 칸반(`18_05`)의 "전체 현황 파악" 목적 훼손.
- `renderDoneColumn`(382-391행)의 과거월 그룹카드 분기가 **현재 실제월(2026-07)** 과 비교 → 월 보드(예:06) 선택 시에도 기준이 07월이라 동작 불일치. `10_01` 최초안은 이걸 "미트리거→제거" 권고했으나, 실제로는 타월 Done을 보여주는 유일한 통로였음.
- 드롭다운 기본값이 연도 루트(`2026`, `_index.md` 없음)라 초기 진입 시 빈 보드.

### 5.2 수정 내용 (구현 완료)
- **백엔드**:
  - `parse_all_months()` 신규 — PLANS_DIR 직계 `MM/` 중 `_index.md` 보유 폴더를 모두 스캔·병합 파싱, 각 plan에 `month`(MM) 태그 부여.
  - `plans_data`(`/admin/api/plans`)에 `?month=` 파라미터 추가:
    - 미지정(기본) → **전체(ALL) 모드**: 모든 월 병합, `is_other_month` 불필요(모두 표시), `board_month=None`.
    - 지정(예: `07`) → 해당 월 활성항목(Todo/Doing/Pre-Done/Hold/Drop) + **타월 Done은 `is_other_month=True`로 태그**하여 그룹카드로 분리, `board_month='2026-07'`.
  - `_default_plans_dir`/`_resolve_plans_dir`은 기존대로 현재월 우선(월 폴더 선택용). `TABLE_RE`/`STATUS_MAP`/`plan_content` 경로조합(`plan_id==폴더명`) 불변.
- **프론트** (`plans_kanban.html`):
  - 드롭다운에 `📊 전체(ALL)` 옵션(`value=""`) 추가, 변경 시 `?month=` 로 갱신.
  - `renderDoneColumn` 비교 기준을 **현재실월 → `data.board_month`(선택 보드월)** 로 교정. 자월 Done=개별카드, 타월 Done=`이전 완료(N건)` 그룹카드(클릭 시 `openGroupList`로 타월 Done 일람).
  - 전체 모드에서 타월 활성항목 카드에 `MM월` 배지 표시(어느 월인지 구분).
  - 카드 클릭 `openDetail`에 `p.month` 전달 → `/api/plans/<id>/content?dir=<month경로>` 로 정확 월 폴더 해석.

## 6. 영향도 분석

| 변경 대상 | 방식 | 영향 |
|-----------|------|------|
| `.clinerules/core/00-core/03.plan-mode.md` | §1·§2·§8·§12 수정 | 향후 계획서 작성 규칙만 영향 |
| `plans/2026/` 74개 폴더 | 이동 + 내부 .md rename | 칸반 경로조합 불변(`plan_id==폴더명`)으로 호환 |
| `plans/2026/_index.md` → `MM/_index.md` | 분할 + 원본 삭제 | 칸반 월별 파싱으로 전환 |
| `src/routes/plans_routes.py` | 발견로직 수정(1~2개소) | 기존 라우트 시그니처 불변 |
| `web/templates/plans_kanban.html` | 드롭다운/그룹카드 정리 | 레이아웃 불변 |

## 7. 테스트/검증 계획

| 시나리오 | 검증 항목 | 방법 |
|----------|-----------|------|
| 폴더 이관 | 74개 모두 `YYYY/MM/DD_NN` 로 이동, 내부 .md rename 완료 | 디렉터리 목록 확인 |
| `_index.md` 분할 | 71행 누락 없이 월 파일에 분배, plan_id `DD_NN` 형 | 월별 행 카운트 합산=71 |
| 칸반 드롭다운 | `2026/06`,`2026/07` 노출, 현재월 기본선택 | `/admin/plans` 확인 |
| 칸반 분류 | 월 선택 시 상태별 정상 분류(약어 파싱 일치) | 브라우저 확인 |
| 카드 상세 | 클릭 시 `DD_NN_x.md` 모달 렌더 | 클릭 확인 |
| 지침 Git | 기존 문맥 보존, 삭제 없음 | `git diff --cached -- .clinerules/` |

## 8. 리스크 및 제약

- 이관 중 경로 깨짐 → PowerShell 스크립트 일괄 이동 후 `_index.md` 행 매칭 검증.
- 지침 Git 충돌 → Append/수정 방식, 기존 문맥 보존(plan-mode §Git 규칙).
- `result/`,`test/`,`__pycache__` 등 하위 폴더는 부모와 함께 이동(별도 처리 불필요).

## 9. 지침 수정 후 의무 절차 (05.post-modification.md)

- `2026-07-10 | 폴더 YYYY/MM/DD_NN 개편 + 칸반 월별 _index 동기화 | ✓ 통과` 기록 예정.

## 요구사항 원자화

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | 74개 폴더가 모두 `plans/2026/MM/DD_NN_작업명/` 형태로 이동되는가? | Y | Y — 스크립트 이관 후 디렉터리 목록 확인 |
| 1.2 | 각 이관 폴더 내 메인 `.md` 파일명이 `DD_NN_작업명.md` 로 rename 되는가? | Y | Y — rename 후 Glob 확인 |
| 2.1 | `plans/2026/_index.md` 의 71행이 월별 파일로 누락 없이 분배되는가? | Y | Y — 월별 행 합산=71 |
| 2.2 | 분할된 `_index.md` plan_id 컬럼이 `DD_NN_작업명` 형인가? | Y | Y — 파싱 확인 |
| 3.1 | 칸반 드롭다운에 `2026/04`,`2026/06`,`2026/07` 월 폴더가 노출되는가? | Y | Y — `/admin/plans` 테스트클라이언트 렌더: 옵션=[`plans/2026`, `plans/2026/07`, `plans/2026/06`, `plans/2026/04`], 기본선택=현재월 `2026/07` (`plans_routes.py` `_default_plans_dir`·`_discover_month_dirs`) |
| 3.2 | 월 선택 시 상태별 카드가 정상 분류되는가? | Y | Y — `/admin/api/plans` 호출: total=14, grouped={doing:7, done:1, predone:2, todo:4, hold:0, drop:0}, sample id=`01_01_nav-hub-version` (TABLE_RE·STATUS_MAP 불변 경로조합 `plans/2026/07/<DD_NN_x>/<DD_NN_x>.md` 매칭) |
| 4.1 | 지침 §1·§2·§8·§12가 신규 `MM/DD_NN` 구조로 정합화되는가? | Y | Y — diff 확인 |
