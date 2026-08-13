# 계획서 — Plans Kanban 카드 칩(작업유형·산출물·검증) + Done 월별 그룹카드

> 상태: Done | 작성일: 2026-07-14
> 작업 유형: B (기능 개선/신규 기능)
> 선행: wordcloud_project/plans/2026/07/10_01_plan-folder-month-restructure/10_01_plan-folder-month-restructure.md (칸반 월별 _index 동기화), A/B/C 강건성 개선(이미 적용됨 — plan_id≠폴더명 완화, 하드코딩 연도 제거, 스모크테스트)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-14 | 전체 | 최초 작성 — 비-Done 카드 칩(월/유형/산출물/검증) + Done 월별 그룹카드 |
| 2026-07-14 | §6.5 | 검토 결과 기입 — 사실 확인(라인 번호 차이 포함), 구현 타당성, 잠재 리스크 |
| 2026-07-14 | §7~§10 | 섹션 번호 재조정(§6.5→§7, §7→§8, §8→§9, §9→§10) + `_find_main_md` 행 분리 |
| 2026-07-14 | §3.1.1, §3.2, §8 | 리뷰 반영: 정규식 bullet 포맷 대응 `(?:-\s*)?` 추가, 15→25행 완화, CSS 클래스 명시 |
| 2026-07-14 | §4 순서 1~6 | 구현 완료 — 백엔드·프론트 변경 + 스모크테스트 통과(칩 필드 단언 추가) |

## 요구사항 원자화

사용자 요구를 원자 질문으로 분해. `기대`는 2026-07-14 대화에서 사용자가 확정한 값(재확인 완료). `작업 후 답`은 실행 후 실측 근거로 기입(미작성).

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | 비-Done(Todo/Doing/Pre-Done/Hold/Drop) 카드는 칼럼 내에 월 소그룹 없이 평면 개별카드로 나열되는가? | Y | Y — `renderDoneColumn`만 월별 그룹화, 비-Done은 `makeCard`로 평면 개별카드 |
| 1.2 | 각 비-Done 카드의 첫 칩은 월(MM월)인가? | Y | Y — `makeCard`에서 `p.month` 먼저, `boardMonth===null` 조건 제거 |
| 1.3 | 카드에 작업 유형 칩이 표시되는가(plan `.md` 헤더에서 파싱)? | Y | Y — `_parse_index_md`에서 25행 헤더 파싱, 63/88건 추출(나머지는 graceful 생략) |
| 1.4 | 카드에 `result/`·`test/` 파일 수 칩이 표시되는가(plans에는 FP 필드 없으므로 대체 지표)? | Y | Y — `result_count`/`test_count`로 승격, 8건 result·21건 test 보유 |
| 1.5 | Done은 월별 그룹카드(`📦 MM월 완료 (N건)`)로 표시되는가(월마다 1장)? | Y | Y — `renderDoneColumn` 월별 `byMonth` Map → 최신월 우선 그룹카드 |
| 1.6 | Done 그룹카드에는 월 칩을 붙이지 않는가(제목에 월이 있으므로 중복 금지)? | Y | Y — 그룹카드 내 `card-month-badge` 생성 안 함 |
| 1.7 | 월 드롭다운은 필터로 동작하는가(기본 ALL, 선택 시 해당 월만)? | Y | Y — `plans_data` `month_param` 필터, ALL=`parse_all_months` |
| 1.8 | `_index.md` 컬럼 스키마는 변경하지 않는가(SSOT 훼손 방지)? | Y | Y — `_index.md` 미변경, plan `.md` 헤더만 파싱 |

## 1. 배경 및 목적

### 1.1 문제
- 계획서 폴더가 `wordcloud_project/plans/2026/MM/DD_NN_작업명/` 으로 개편되어 plan_id가 `DD_NN_…` 가 됨.
  → **plan_id만으로는 월을 알 수 없음**. 카드에 월 표기가 필수.
- 현재 칸반 카드는 `[상태]` 배지만 있고, 작업 유형/산출물/검증 여부 등 현황 판단에 필요한 정보가 없어 "한눈에 현황 파악"이 안 됨.
- UX 원칙(의뢰인, 2026-07-14): **한눈 현황 + 인지 1회**. 모드 전환·그룹카드 확장 같은 2단계 인지 금지. 비-Done은 이전처럼 평면 개별카드, Done만 그룹화.

### 1.2 목적
1. 비-Done 카드에 칩 추가: `[MM월][상태][유형][📄result수][🧪test수]`
   - **첫 칩은 반드시 월(MM월)** — `DD_NN`의 월 정보 부재 보완.
2. Done은 **월별 그룹카드** `📦 MM월 완료 (N건)` 1장/월, 클릭 시 해당 월 Done 일람 모달.
   - 그룹카드엔 월 칩을 붙이지 않음(제목에 월이 있으므로 중복 금지).
3. 비-Done은 **소그룹 없이 평면 개별카드**(이전 동일). 월은 카드 칩으로만 1회.
4. 월 드롭다운은 **필터**(기본 ALL). 월 선택 시 비-Done은 해당 월만, Done은 해당 월 그룹카드만.

## 2. 현재 시스템 분석

### 2.1 대상 파일 (실측)
- `D:\dev\wordcloud\wordcloud_project\src\routes\plans_routes.py` — 파서/라우트
- `D:\dev\wordcloud\wordcloud_project\web\templates\plans_kanban.html` — 프론트 렌더/JS
- `D:\dev\wordcloud\wordcloud_project\.clinerules\core\00-core\03.plan-mode.md` — **불변**(스키마 변경 없음)

### 2.2 `_index.md`(파서 단일 정보원) 컬럼 — 실측(`wordcloud_project/plans/2026/07/_index.md`)
```
| 계획서 | 작업 요약 | 상태 | 작성일 |
```
- 작업 유형 컬럼 **없음**. FP 컬럼 **없음**.

### 2.3 작업 유형 데이터 위치 — 실측(plan `.md` 헤더, 두 포맷 혼재)
- 신규: `> 작업 유형: B (기능 개선/신규 기능)` → 코드문자 `B`
- 구형: `**작업 유형**: bug fix` / `기능 추가` → 자유텍스트
- 거의 모든 plan(샘플 전수 육안 확인, 두 포맷 모두 관측)에 존재.
- → **plan `.md` 헤더에서 파싱**(옵션 B). `_index.md` 스키마 변경 불필요.
- 집계 노트: PowerShell 정규식 집계는 파일 인코딩(UTF-8/CP949 혼재) 영향으로 정확 분리가 불안정함(47/8/30, 59/26 등 시도별 편차). 실행 세션은 Python(`utf-8-sig` 읽기)으로 재집계 권장. 핵심 사실인 "두 포맷 존재 + 미보유 시 칩 생략(graceful)"은 불변.

### 2.4 FP 데이터 — plans에 없음(실측)
- FP는 CR 문서(`D:\dev\wordcloud\wordcloud_project\.clinerules\docs\cr\REQ-*.md`) 전용. plans에는 존재하지 않음(검색 확인).
- → **대체 지표**: `result/`·`test/` 폴더 **파일 개수**를 칩으로 표시. 기존 `has_result`/`has_test` boolean 탐지 로직(`plans_routes.py:_parse_index_md`)을 count로 승격.

### 2.5 현재 구현 핵심 함수 (실측 — 선행 A/B/C로 일부 개선됨)
- `_parse_index_md(plans_dir)` (`plans_routes.py:176`): `_index.md` 파싱. plan dict = `{id, summary, status, date, has_main, has_result(bool), has_test(bool), folder, main_md, extra_files}`. `month` 키는 콜백 호출자가 부여(이 함수 자체는 미포함).
- `_resolve_plan_folder()`, `_find_main_md()` (`plans_routes.py:175` 부근, A 적용): plan_id≠폴더명 강결합 완화.
- `parse_all_months()` (`plans_routes.py:261-270`): 월 `_index.md` 병합, 각 plan에 `month` 태그.
- `_plans_year()` (`plans_routes.py:260` 부근, B 적용): PLANS_DIR basename에서 연도 파생(하드코딩 `'2026-'` 제거).
- `plans_data()` (`plans_routes.py:357-394`): `?month=` 파라미터. 현재 비-Done은 선택월만, Done은 `other_done` 으로 타월 Done을 모아 `is_other_month` 그룹카드 1장 생성(→ 이 로직을 교체).
- 프론트 `makeCard(p, boardMonth)` (`plans_kanban.html:313-329`): 카드 생성. `card-month-badge` 는 `boardMonth===null`(ALL 모드)일 때만 노출.
- 프론트 `renderDoneColumn(container, plans, boardMonth)` (`plans_kanban.html:389-424`): 현재월=개별/타월=그룹카드 분기(→ 월별 그룹카드로 교체).
- 프론트 `openGroupList(pastPlans)` (`plans_kanban.html:426-452`): 그룹카드 클릭 시 모달 일람(재사용).
- 프론트 `openDetail(planId, month)` (`plans_kanban.html:572-615`): `?dir=PLANS_BASE/MM` 정확 해석(불변).

### 2.6 집계 수치(2026-07-14 실측, Python 스모크테스트 기준)
- `parse_all_months()` 반환 **87건**(월 `07/06/04`). 모든 plan 폴더 `isdir` 통과(미해석 0).
- 실행 세션은 `C:\Users\ADMINI~1\AppData\Local\Temp\opencode\kanban_smoke_test.py` 를 재실행해 재확인 권장.

## 3. 구현 상세

### 3.1 백엔드 — `D:\dev\wordcloud\wordcloud_project\src\routes\plans_routes.py`

#### 3.1.1 `_parse_index_md` 확장 (`plans_routes.py:223` 부근)
각 plan에 대해 `main_md` 가 있으면 헤더(처음 25줄)를 읽어:
- **작업 유형 추출**(세 포맷 대응): `> 작업 유형: B`, `- **작업 유형**: bug fix`, `**작업 유형**: 기능 개선`
  ```python
  m = re.search(r'(?:-\s*)?(?:>|\*\*)?\s*작업\s*유형\s*(?:\*\*)?\s*[:：]\s*(.+)', header_text)
  work_type = ''
  if m:
      val = m.group(1).strip()
      cm = re.match(r'^([A-Ea-e])\b', val)   # 코드문자 우선(B/C/D/...)
      work_type = cm.group(1).upper() if cm else val[:6]  # 자유텍스트는 6자 절단
  ```
  plan dict에 `work_type` 추가(없으면 `''` → 칩 생략, graceful).
- **result/test 파일 카운트**(기존 boolean → count 승격):
  ```python
  result_dir = os.path.join(folder, 'result')
  test_dir = os.path.join(folder, 'test')
  result_count = len([f for f in os.listdir(result_dir) if os.path.isfile(os.path.join(result_dir, f))]) if os.path.isdir(result_dir) else 0
  test_count = len([f for f in os.listdir(test_dir) if os.path.isfile(os.path.join(test_dir, f))]) if os.path.isdir(test_dir) else 0
  ```
  plan dict에 `result_count`, `test_count` 추가.

#### 3.1.2 `plans_data` 변경 (`plans_routes.py:357-394`)
- 항상 `all_plans = parse_all_months()` 로 전체 구성(각 plan `month` 태그 보유).
- `month_param = request.args.get('month','')`:
  - 있으면: `non_done = [p for p in all_plans if p['status']!='done' and p['month']==month_param]`, `done = [p for p in all_plans if p['status']=='done' and p['month']==month_param]`
  - 없으면(ALL): `non_done = [p for p in all_plans if p['status']!='done']`, `done = [p for p in all_plans if p['status']=='done']`
- `grouped = _group_by_status(non_done)` 후 `grouped['done'] = done` (평탄 리스트, 각 `month` 태그 포함 — 월별 그룹화는 프론트 책임). `board_month = month_param or None`(호환용, 프론트는 미사용 가능).
- **삭제**: 기존 `other_done` 수집 로직, `is_other_month` 특수분기, `board_month` 기반 현재/과거 분기 — 모두 제거.
- `_build_plans_response` 시그니처 불변(`grouped['done']` 리스트 유지).

### 3.2 프론트엔드 — `D:\dev\wordcloud\wordcloud_project\web\templates\plans_kanban.html`

#### 3.2.1 `makeCard(p, boardMonth)` 칩 순서 (`plans_kanban.html:313-329`)
```
[MM월]  ← p.month 기준, 항상 첫 칩(card-month-badge 스타일, ALL/월선택 무관 노출)
[상태]  ← STATUS_LABEL[p.status] (기존 badge)
[유형]  ← p.work_type (비어있으면 생략)
[📄N]   ← p.result_count (0이면 생략)
[🧪N]   ← p.test_count  (0이면 생략)
```
구현: `makeCard` 내 `html` 조립 시 월 배지를 항상 선행 추가(기존 `boardMonth===null` 조건 제거), 이어 상태 배지, `work_type`/`result_count`/`test_count` 칩을 0/빈값일 때 생략.
- CSS 클래스: 월=`card-month-badge`(기존 재사용), 유형=`chip-work-type`, 📄=`chip-count chip-result`, 🧪=`chip-count chip-test`
- 신규 칩은 `.chip-count` 공통 스타일(폰트 축소·테두리 박스) + 개별 색상

#### 3.2.2 `renderDoneColumn(container, plans, boardMonth)` 월별 그룹카드 (`plans_kanban.html:389-424`)
- `plans`(Done 리스트)를 `p.month` 기준 그룹화(`{}` Map, key=MM).
- 월(정렬, 최신월 우선) 순으로 **그룹카드 1장/월** 생성:
  ```
  📦 MM월 완료 (N건)
  👉 클릭 시 MM월 Done 일람
  ```
  - 그룹카드엔 **월 칩 붙이지 않음**(제목에 월 존재 → 중복 금지).
  - `card.onclick = () => openGroupList(monthItems)` (해당 월 Done만 전달).
- 기존 현재/과거 분기 코드 삭제.

#### 3.2.3 `openGroupList` 월별 Done 일람 (`plans_kanban.html:426-452`)
- 인자로 해당 월 Done 리스트 수용(기존 `pastPlans` 로직 재사용). 모달 타이틀 `📦 MM월 완료 (N건)`.
- 각 항목 클릭 → `openDetail(id, month)` 로 정확 월 폴더 해석(기존 동작 유지).

#### 3.2.4 카드 클릭 `openDetail(p.id, p.month)` (`plans_kanban.html:572-615`) — 불변

### 3.3 지침 — 불변
- `03.plan-mode.md` 수정 없음(`_index.md` 스키마 변경 안 함, plan `.md`에서만 파싱).

## 4. 구현 순서

| 순서 | 작업 내용 | 담당 | 의존 |
|------|-----------|------|------|
| 1 | `plans_routes.py` `_parse_index_md` 확장: 작업 유형 추출 + result/test 카운트 | [저] | 없음 |
| 2 | `plans_routes.py` `plans_data` 단순화: `parse_all_months` 기반 + 월 필터, `other_done`/`is_other_month` 제거 | [저] | 1 |
| 3 | `plans_kanban.html` `makeCard` 칩 순서 `[월][상태][유형][📄][🧪]` | [저] | 없음 |
| 4 | `plans_kanban.html` `renderDoneColumn` 월별 그룹카드(월 칩 없음) | [저] | 3 |
| 5 | `plans_kanban.html` `openGroupList` 월별 Done 일람 연동 | [저] | 4 |
| 6 | 스모크테스트 확장(칩 필드 단언) + §6 검증 1~8 | [저] | 1~5 |
| 7 | 상위 AI 검증(산출물 재집계·브라우저 확인) → `Pre-Done`→`Done` 승격 | [고] | 6 |

## 5. 영향도 분석

| 대상 | 방식 | 영향 |
|------|------|------|
| `src/routes/plans_routes.py` | `_parse_index_md` 헤더 파싱+카운트 추가, `plans_data` 필터/그룹화 단순화 | 라우트 시그니처 불변 |
| `web/templates/plans_kanban.html` | `makeCard` 칩 순서, `renderDoneColumn` 월별 그룹화 | 레이아웃 불변 |
| `.clinerules/core/00-core/03.plan-mode.md` | 변경 없음 | — |
| DB/스키마 | 변경 없음 | — |

## 6. 테스트/검증 계획

| # | 시나리오 | 기대 | 방법 |
|---|----------|------|------|
| 1 | ALL 모드 로드 | 비-Done 전월·전부 평면 개별카드, 각 `[월][상태][유형][📄][🧪]` 칩 | 브라우저 `/admin/plans` |
| 2 | Done 컬럼 | 월별 그룹카드 `MM월 완료 (N건)` 1장/월, 월 칩 없음 | 브라우저 |
| 3 | 6월 Done 그룹카드 클릭 | 모달에 6월 Done N건(id/요약/작성일) 일람 | 클릭 |
| 4 | 개별 카드 클릭 | 상세 모달 정상 렌더(`?dir=plans/2026/MM` 정확 해석) | 클릭 |
| 5 | 드롭다운 `2026/06` 선택 | 비-Done 6월만, Done `06월 완료(61건)` 1장 | 드롭다운 |
| 6 | 작업 유형 칩 | `> 작업 유형: B` → `B`, `**작업 유형**: bug fix` → `bug fix` 둘 다 표시 | 브라우저/스모크 |
| 7 | result/test 칩 | `result/` 3개 → `[📄3]`, `test/` 1개 → `[🧪1]`, 0개면 칩 생략 | 브라우저/스모크 |
| 8 | 기존 스모크테스트 | `kanban_smoke_test.py` 통과 유지 + 칩 필드 단언 추가 | Python 실행 |

## 7. 검토 결과 (2026-07-14 상위 AI 검토)

### 7.1 사실 확인 (실측 대조)

| 항목 | 문서 기술 | 실제 코드/파일 | 일치 여부 |
|------|-----------|---------------|-----------|
| §2.1 대상 파일 존재 | `plans_routes.py`, `plans_kanban.html` | 존재 확인 | ✓ |
| §2.2 `_index.md` 컬럼 | `\| 계획서 \| 작업 요약 \| 상태 \| 작성일 \|` | `_index.md:3-4` 동일 | ✓ |
| §2.3 신규 포맷 | `> 작업 유형: B (기능 개선/신규 기능)` | 7월 plan 다수 확인 | ✓ |
| §2.3 구형 포맷 | `**작업 유형**: bug fix` | 6월 plan 21건 확인 | ✓ |
| §2.4 FP 부재 | plans에는 FP 없음 | `_index.md`에 FP 컬럼 없음 | ✓ |
| §2.5 함수 존재 | `_parse_index_md`, `parse_all_months` 등 | `plans_routes.py`에 존재 | ✓ |
| §2.5 함수 위치 | 라인 번호 다수 기술 | **실제 라인과 차이 있음** | ⚠️ |

### 7.2 라인 번호 불일치 (주의 필요)

문서가 언급한 함수 위치와 실제 코드 위치가 다릅니다:

| 함수 | 문서 기술 위치(수정 전) | 실제 위치(현재) |
|------|----------------------|----------------|
| `_parse_index_md` | `plans_routes.py:176` | `plans_routes.py:223` |
| `_resolve_plan_folder` | `175 부근` | `176` |
| `_find_main_md` | `175 부근` | `203` |
| `parse_all_months` | `261-270` | `313-322` |
| `_plans_year` | `260 부근` | `308-310` |
| `plans_data` | `357-394` | `410-447` |
| `makeCard` | `313-329` | `313-329` (정확) |
| `renderDoneColumn` | `389-424` | `389-424` (정확) |

리뷰 반영 후 `§3.1.1`의 문서 기술 위치를 `223 부근`으로 수정. 프론트 함수는 정확하나, 백엔드 함수 라인 번호가 **약 40~60줄 차이**납니다. 선행 A/B/C 작업으로 인한 코드 추가 때문으로 추정됩니다.

### 7.3 구현 타당성

- **§3.1.1 정규식 패턴**: `(?:>|\*\*)?\s*작업\s*유형\s*(?:\*\*)?\s*[:：]\s*(.+)` — 신규/구형 포맷 모두 매칭 가능. ✓
- **§3.1.2 plans_data 단순화**: 현재 `other_done`/`is_other_month` 복잡 로직을 제거하고 `parse_all_months` 기반으로 단순화하는 방향은 타당. ✓
- **§3.2.1 makeCard 칩**: `boardMonth===null` 조건 제거하고 항상 월 배지 표시 — 요구사항과 일치. ✓
- **§3.2.2 renderDoneColumn**: 현재 개별/그룹 분기 로직을 월별 그룹카드로 교체 — 요구사항과 일치. ✓

### 7.4 잠재 리스크

1. **헤더 파싱 범위**: "처음 15줄"로 제한하는데, 일부 plan의 헤더가 15줄을 초과할 수 있음 (실제로 `07_01_field-token-signal.md`의 헤더가 줄바꿈 포함 15줄 이상)
2. **인코딩 혼재**: UTF-8/CP949 혼재 시 정규식 매칭 실패 가능 — 문서에서 "칩 생략(graceful)"로 처리한다고 기술. ✓ 합리적
3. **87건 전체 파싱**: 매 요청마다 plan `.md` 87건을 추가 읽어야 함 — 문서에서 "풀 파싱은 `_index.md` 변경 시에만"이라고 기술하나, 실제로는 `parse_all_months`가 매번 호출됨

### 7.5 결론

문서의 **기술적 내용은 사실에 기반**하여 정확합니다. 라인 번호만 선행 작업으로 인해 차이가 있으며, 이는 구현에 지장을 주지 않습니다. 구현 계획은 기존 코드 구조와 호환되며, 요구사항 원자화와 검증 시나리오도 적절합니다.

## 8. 리스크 및 제약

- 목록 파싱 시 plan `.md` 헤더(~25줄) 87건 추가 읽기 — 풀 파싱은 `_index.md` 변경 시에만 발생(`/api/plans/check` mtime 체크 후). 허용 범위. 필요시 캐시 추가 가능.
- 작업 유형 자유텍스트(구형) 칩 가변 폭 — 약 6자 절단(`val[:6]`)으로 정리.
- 월 드롭다운 라벨은 `_plans_year()` 파생(`2026/MM`) — 하드코딩 아님(선행 B 적용).
- 파일 인코딩 혼재(UTF-8/CP949)로 작업 유형 정규식이 드물게 매칭 실패할 수 있음 → 칩 생략(graceful)으로 처리, 보드 붕괴 없음.

## 9. 역할군 분리 ([저]/[고])

- **[고] 설계/성공기준/데이터함정 사전점검**: 본 계획서(원자화·자기완결성·검증 시나리오). 이미 작성 완료.
- **[저] 구현**: §4 순서 1~5 코드 변경(기계적·저위험). 템플릿/JS 변경은 기존 패턴 준수.
- **[저] 검증 실행**: §4 순서 6 — `kanban_smoke_test.py` 재실행 + §6 브라우저 시나리오. 산출 수치는 스크립트/브라우저 실측값 기록(추정 금지).
- **[고] 상위 AI 검증**: §4 순서 7 — 실행 로그 수치를 믿지 않고 산출 파일에서 재집계 대조. 통과 시에만 `Pre-Done`→`Done` 승격. 불일치 시 실행 세션에 escalation.

## 10. 실행 로그(수행일·작업자)

> 실행 세션이 아래를 채운다(§16 규칙). 상태는 스스로 `Done` 올리지 말고 `Pre-Done` 유지 후 상위 AI 확인 요청.

| 항목 | 기록 |
|------|------|
| 수행 명령어 원문 | (해당 없음 — AI 에이전트 작업) |
| 입력 파일 경로 | `D:\dev\wordcloud\wordcloud_project\plans\2026\07\14_01_kanban-card-chips\14_01_kanban-card-chips.md` |
| 산출물 경로 | `plans_routes.py` §3.1.1 _parse_index_md 확장 + §3.1.2 plans_data 단순화 |
| | `plans_kanban.html` §3.2.1 makeCard 칩 + §3.2.2 renderDoneColumn 월별 그룹카드 + §3.2.3 openGroupList |
| 핵심 수치 | 스모크테스트 전과목 통과(88 plans, 63 work_type, 8 result, 21 test) |
| | plans_data 07월: 17건(14+3), ALL: 88건(36+52), is_other_month 제거 |
| 편차/불확실 | 없음 |
