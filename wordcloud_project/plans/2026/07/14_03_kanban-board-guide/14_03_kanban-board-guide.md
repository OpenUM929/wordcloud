# 계획서 — 칸반보드 표준 지침화 + Git 서브모듈 저장소 + API 계약

> 상태: Done | 작성일: 2026-07-14 | 현행화: 2026-07-15
> 작업 유형: B (기능 개선/신규 기능)
> 선행: `18_05_plans-kanban-board.md`(초기 칸반), `22_02_kanban-predone.md`(Pre-Done), `14_01_kanban-card-chips.md`(칩+그룹카드), `14_02_kanban-card-sort.md`(정렬), `14_03_kanban-board-guide.md`(본문 1차 — 문서화 완료)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-14 | 전체 | 최초 작성 |
| 2026-07-14 | 전체 | 6개 산출물 모두 생성 완료 + 표준 지침·18_05 최신화·원페이퍼·드리프트 정리 |
| 2026-07-14 | §3 구현 상세 | 2차 — 아키텍처 재정의: API 중심 + Git 서브모듈 저장소로 전환. CLI 질문→분석 결과 반영. 프론트엔드는 'API 소비자'로 일반화, 특정 스택 종속 제거 |
| 2026-07-15 | §전체 현행화 | 소스 확장 반영: API 6→10종, 뷰탭 2→4종(칸반/CR/간트/추세), `_index.md` 7컬럼(관련CR/선행/에픽)+`end_date`. 표준 지침 `kanban-board-guide.md` §2/§3/§4/§6 갱신 + `kanban-board-api-contract.md` **신규 작성**(프레임워크 중립 10엔드포인트 JSON 계약). 상태 Pre-Done→Done |

## 요구사항 원자화

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|-------------------|
| **Phase 1 (문서화 — 완료)** | | | |
| 1.1.1 | 표준 지침 문서가 `.clinerules/docs/development/kanban-board-guide.md`에 생성되는가? | Y | Y — 6개 섹션, 생성 완료 |
| 1.1.2 | 표준 지침이 wordcloud 도메인과 무관한 범용 컴포넌트 명세로 작성되는가? | Y | Y — `wordcloud` 명칭 일절 미사용 |
| 1.1.3 | 18_05 계획서가 현재 소스(6컬럼/월드롭다운/CR탭/칩/정렬/그룹카드)와 일치하도록 최신화되는가? | Y | Y — §수정이력 + §3 전면 정정 |
| 1.1.4 | 22_02·14_02 상태 `Todo`→`Done` 갱신 + _index.md 정리되는가? | Y | Y — 개별 파일 + _index.md 일괄 정리 |
| 1.1.5 | 원페이퍼 보고서가 비전문가 대상 평이한 용어로 작성되는가? | Y | Y — 실제 API 집계값(90plans/53CR/80FP/177.5h) 기입 |
| **Phase 2 (아키텍처 정립 — 본 내용)** | | | |
| 1.2.1 | 아키텍처가 라이브러리(블랙박스)가 아닌 Git 서브모듈(수정 가능) 방식으로 설계되는가? | Y | — 라이브러리 불가 판정(프로젝트별 수정 어려움), 서브모듈 확정 |
| 1.2.2 | 칸반보드가 특정 프론트엔드(Jinja/Next.js)에 종속되지 않고 **API 중심**으로 재구성되는가? | Y | — 프론트엔드는 'API 소비자'로 일반화, Jinja는 참조 예시로만 격하 |
| 1.2.3 | 독립 git 저장소 `kanban-board`가 생성되어 서브모듈로 포함 가능한 구조인가? | Y | — |
| 1.2.4 | 저장소가 wordcloud 결합을 제거(설정 주입형·인증 의존성 주입·CR_DIR 파라미터화)하는가? | Y | — |
| 1.2.5 | API 계약(`docs/api-contract.md`)이 엔드포인트별 JSON 스키마를 프레임워크 중립으로 명시하는가? | Y | Y — `kanban-board-api-contract.md` 신규 작성 (10엔드포인트, 2026-07-15) |
| 1.2.6 | 표준 지침 `kanban-board-guide.md`가 서브모듈·API 계약 중심으로 갱신되는가? | Y | Y — §2(7컬럼 인덱스)/§3(10라우트·신규함수)/§4(4탭·간트·추세·린터)/§6(체크리스트) 갱신 + api-contract 참조 |

## 1. 배경 및 목적

### 1.1 배경

**Phase 1 (완료)**: 칸반보드 초기 설계(18_05)와 소스 간 드리프트 해소 + 표준 지침 문서화 + 분산 계획서 통합 + 원페이퍼 보고서.

**Phase 2 (본 계획서의 새 방향)**: Phase 1 산출물에 대해 "이 정보만으로 다른 환경(Flask+Next.js 등)에서 칸반보드를 만들 수 있는가"라는 검증 질문이 제기됨. 분석 결과:
- 표준 지침이 **백엔드(Flask)는 재사용 가능**하나, **프론트엔드(Jinja/Bootstrap/vanilla JS)는 사용자 스택(Next.js)과 불일치** → 특정 프론트엔드에 종속된 재사용성은 한계
- 해결: **API 중심으로 전환** → 어떤 프론트(Next.js·Jinja·Vue 등)든 API만 호출하면 됨
- 배포 방식: **pip 라이브러리**(블랙박스, 수정 어려움)보다 **Git 서브모듈**(소스가 내 저장소에 있어 수정+upstream 기여 가능)이 적합

### 1.2 목적

**Phase 1 (달성)**:
1. 칸반보드 표준 웹개발 지침 문서화
2. 분산 계획서 통합 명세
3. 계획서↔소스 드리프트 해소
4. 원페이퍼 보고서 작성

**Phase 2 (본 계획서에서 기술)**:
1. 칸반보드 Flask 백엔드를 **독립 Git 저장소(서브모듈)**로 추출 (wordcloud 결합 제거)
2. **프레임워크 중립 API 계약서** 작성 → 어느 프론트(Next.js 등)든 호출 가능
3. 표준 지침을 서브모듈·API 계약 중심으로 갱신 (Jinja 템플릿은 참조 소비자로 격하)
4. 샘플 픽스처 + README + Quickstart → `git submodule add` 후 즉시 사용 가능

## 2. 현재 시스템 분석

### 2.1 대상 파일 (실측)

| 역할 | 파일 경로 | 설명 |
|------|-----------|------|
| 백엔드 라우트 | `D:\dev\wordcloud\wordcloud_project\src\routes\plans_routes.py` | 538줄, 7개 라우트, 12개 함수 |
| 프론트 템플릿 | `D:\dev\wordcloud\wordcloud_project\web\templates\plans_kanban.html` | 879줄, CSS+HTML+JS 통합 |
| 설정 | `D:\dev\wordcloud\wordcloud_project\src\config\settings.py` | PLANS_DIR, PLANS_ROOTS(미사용) |
| base 템플릿 | `D:\dev\wordcloud\wordcloud_project\web\templates\base.html` | nav 링크 `📋 계획 현황` |
| app 등록 | `D:\dev\wordcloud\wordcloud_project\web\app.py` | plans_bp 등록 |
| 상태 표준 | `.clinerules\core\00-core\03.plan-mode.md` | §8 _index.md 포맷 지정 |

### 2.2 드리프트 현황 (계획서 ≠ 소스)

| 항목 | 계획서 기술 | 실제 소스 | 드리프트 |
|------|-----------|-----------|---------|
| 컬럼 수 | 3 (18_05) | 6 | ✓ |
| 폴더 선택 | PLANS_ROOTS 경로 (18_05) | 월 드롭다운 (`?month=`, `parse_all_months`) | ✓ |
| CR현황 탭 | 없음 (18_05) | 있음 (탭 + 2개 API) | ✓ |
| 카드 칩 | 없음 (18_05) | 있음 (월/유형/result/test) | ✓ |
| 정렬 버튼 | 없음 (18_05) | 있음 (sortPlans/toggleSort) | ✓ |
| Done 그룹카드 | 없음 (18_05) | 있음 (renderDoneColumn) | ✓ |
| Pre-Done 상태 | 없음 (18_05) | 있음 (STATUS_MAP) | ✓ |
| 22_02 상태 | Todo | 이미 구현 완료 | ✓ |
| 14_02 상태 | Todo | 이미 구현 완료 | ✓ |
| 14_01 상태 | Done | 확인됨 | — |
| PLANS_ROOTS_LIST | 사용 (18_05) | import만 되고 dead | ✓ |
| 상태값 표기 | DN/PND/분석 정규화 (18_05) | 영문 Todo/Doing/… 직접 사용 | ✓ |
| **[07-15 현행화] API 수** | 문서 6종 (07-14 기준) | 실제 10종 (`trend`·`trend-type`·`gantt`·`lint` 추가) | ✓ → **해소(2026-07-15)** |
| **[07-15 현행화] 뷰 탭** | 2종 (칸반/CR) | 실제 4종 (`gantt`·`trend` 추가) | ✓ → **해소** |
| **[07-15 현행화] `_index.md` 컬럼** | 4컬럼 (항목/요약/상태/작성일) | 실제 7컬럼(관련CR/선행/에픽)+`end_date` | ✓ → **해소** |
| **[07-15 현행화] API 계약서** | 미존재 (Phase-2 산출물 누락) | `kanban-board-api-contract.md` 신규 작성 | ✓ → **해소** |

### 2.3 현재 구현 핵심 구조 (참조용)

```
plans_routes.py (Blueprint: plans_bp, prefix: /admin)  ← 10 라우트
├── /plans                    → plans_page()          — 페이지 렌더링 (4탭)
├── /api/plans/check          → plans_check()          — _index.md mtime 체크
├── /api/plans                → plans_data()           — plan 목록 (상태별 그룹)
├── /api/plans/<id>/content   → plan_content()         — 개별 plan .md 원문
├── /api/plans/cr-monthly     → plans_cr_monthly()     — CR 월별 집계
├── /api/plans/cr/<req_id>    → plans_cr_detail()      — CR 상세
├── /api/plans/trend          → plans_trend()          — 연도별 월 추세(금·전년)
├── /api/plans/trend-type     → plans_trend_type()     — 유형별 집계(monthly/yearly)
├── /api/plans/gantt          → plans_gantt()          — 간트(에픽/task/마일스톤/간선/CR링크)
└── /api/plans/lint           → plans_lint()           — 링크 린터 (UI 미연결)

plans_kanban.html
├── CSS: 6컬럼 색상 토큰, 카드/모달/테이블/아코디언/간트/추세 스타일
├── HTML: 4탭(칸반/CR/간트/추세) + 상세/그룹/CR 모달
└── JS: loadPlans/checkUpdate/makeCard/sortPlans/renderDoneColumn/openDetail/loadCrMonthly/loadGantt/loadTrend/loadGraph/loadMonthlyType/loadYearly
```

## 3. 아키텍처 (Phase 2)

### 3.1 최종 아키텍처 결정

첫 접근(Phase 1: "지침에 Jinja 프론트엔드 예시 포함")이 검증 결과 다음과 같이 **개선 확정**됨:

| 결정 사항 | Phase 1 (초기) | Phase 2 (확정) |
|-----------|---------------|----------------|
| 재사용 단위 | 문서(지침) | **Git 서브모듈 저장소** |
| 프론트엔드 | Jinja 템플릿 명시 | **API 계약만 명시** — 프레임워크 중립 (Next.js·Jinja·Vue 자유) |
| 백엔드 | 지침 내 인라인 설명 | **독립 Flask 패키지** (`kanban/`) — wordcloud 결합 제거 |
| 배포 방식 | 문서 참조 | `git submodule add` → `register_blueprint` → API 호출 |

**아키텍처 다이어그램**:
```
[독립 저장소: kanban-board]
├── kanban/ (Flask 패키지 — 주입형 config)
│   ├── routes.py     ← 6개 API
│   ├── parser.py     ← 파서
│   ├── cr.py         ← CR 파싱
│   └── config.py     ← KanbanConfig (plans_dir/cr_dir/auth)
├── docs/api-contract.md  ← JSON 스키마 (프레임워크 중립)
├── sample_data/          ← 픽스처
└── README.md             ← submodule 포함/마운트/호출

[소비자 프로젝트 (Flask + any frontend)]
├── vendor/kanban-board/  ← git submodule
├── app.py                → kanban_bp 등록 + config 주입
└── frontend/             → API 호출 (Next.js 등 자유)
```

### 3.2 산출물 목록 (Phase 2)

| # | 산출물 | 설명 |
|---|--------|------|
| **1** | 독립 git 저장소 `kanban-board` | Flask 패키지 `kanban/` (wordcloud 결합 제거) |
| **2** | `kanban-board-api-contract.md` | 엔드포인트별 요청/응답 JSON 스키마 (프레임워크 중립, 10종) — `.clinerules/docs/development/` 에 신규 (서브모듈 추출 범위 외로 별도 경로) |
| **3** | `sample_data/` | `_index.md`·plan 폴더·`REQ-001.md` 픽스처 |
| **4** | `README.md` | 서브모듈 포함 → 마운트 → API 호출 Quickstart |
| **5** | 표준 지침 `kanban-board-guide.md` 갱신 | 서브모듈+API 계약 중심으로 재구성 |
| **6** | 14_03 계획서 (본 문서) 갱신 | 최종 아키텍처 반영 (여기까지 완료) |

### 3.3 저장소 구조 상세

```
kanban-board/                  (독립 git 저장소, git init)
├── kanban/                   (importable Python package)
│   ├── __init__.py           → from kanban import kanban_bp
│   ├── routes.py             → 6개 라우트 (plans_routes.py 추출)
│   ├── parser.py             → _parse_index_md, _group_by_status, parse_all_months, _discover_month_dirs
│   ├── cr.py                 → _scan_all_crs, _group_crs_by_month, _parse_cr_file
│   └── config.py             → KanbanConfig dataclass (plans_dir / cr_dir / auth_dependency / url_prefix)
├── templates/                (선택 — 참조 소비자)
│   └── kanban_board.html     → wordcloud의 plans_kanban.html (self-contained, base.html 미의존)
├── sample_data/
│   ├── _index.md
│   ├── sample_plan/
│   │   └── sample_plan.md
│   │   ├── result/
│   │   └── test/
│   └── REQ-001.md
├── docs/
│   └── api-contract.md      → 6개 엔드포인트 JSON 스키마
└── README.md
```

### 3.4 wordcloud 결합 제거 항목

| 현재 결합 (`plans_routes.py`) | 제거 방식 |
|-----------------------------|-----------|
| `from src.config.settings import PLANS_DIR, PLANS_ROOTS_LIST` | `KanbanConfig.plans_dir` env/주입형으로 교체 |
| `admin_required` 하드코딩 (Flask session + login_template) | `KanbanConfig.auth_dependency` 콜백 주입 (호스트 앱이 제공), 기본값: Flask session |
| `CR_DIR` 경로 유도 (__file__ 3단 상위 + .clinerules/docs/cr) | `KanbanConfig.cr_dir` 명시적 설정 (기본 유도 로직은 선택) |
| `templates/plans_kanban.html` → extends `base.html` | 참조 템플릿은 self-contained (base 미의존) |
| `PLANS_DIR` basename = 연도 (하드코딩 아님, 그대로 유지 가능) | 유지 (`_plans_year`는 이미 범용) |

### 3.5 API 계약 (`kanban-board-api-contract.md`) 명세 범위

> **위치 변경(2026-07-15)**: Phase-2 원안은 서브모듈 내 `docs/api-contract.md` 였으나, 본 현행화에서 서브모듈 추출은 범위 외로 결정됨에 따라 **`.clinerules/docs/development/kanban-board-api-contract.md`** 에 프레임워크 중립 계약서로 신규 작성. 표준 지침 `kanban-board-guide.md` §3이 본 계약서를 단일 소스로 참조하도록 개편.

| 라우트 | 요청 파라미터 | 응답 JSON 핵심 필드 |
|--------|--------------|-------------------|
| `GET /admin/api/plans` | `?month=` (선택 — MM 또는 빈값=ALL) | `success`, `grouped{todo[],doing[],predone[],done[],hold[],drop[]}` (각 plan: `related_cr[]`,`depends[]`,`epic`,`end_date` 포함), `stats{total…drop}`, `modified_at` |
| `GET /admin/api/plans/check` | `?month=` | `success`, `modified_at` |
| `GET /admin/api/plans/<id>/content` | `?dir=` (월 폴더 절대경로) | `success`, `raw`(md원문), `folder`, `result_files[]`, `test_files[]` |
| `GET /admin/api/plans/cr-monthly` | 없음 | `success`, `months[]{ym,label,count,crs[],fp_total,hours_total,cum_fp,cum_hours}`, `total_crs`, `total_fp`, `total_hours` |
| `GET /admin/api/plans/cr/<req_id>` | 없음 | `success`, `cr{req_id,type,summary,date,ym,month_label,fp,hours,work_type,raw}` |
| `GET /admin/api/plans/trend` | `?year=` | `success`, `year`,`prev_year`, `series{cr_count,fp,hours,plan_count 각 {cur[12],prev[12]}}`, `totals` |
| `GET /admin/api/plans/trend-type` | `?mode=monthly&year=` / `?mode=yearly&mStart=&mEnd=` | `success`, `cr_by_type{types,cur,prev}`, `plan_by_type{types,cur,prev}`, `work_type_labels` |
| `GET /admin/api/plans/gantt` | `?year=` | `success`, `epics[]`, `tasks[]`, `milestones[]`, `deps[]`, `dep_warnings[]`, `cr_links[]`, `plan_total`, `plan_by_type` |
| `GET /admin/api/plans/lint` | 없음 | `success`, `violations[{type,plan,ref,msg}]`, `pass` |
| 에러 공통 | — | `{success:false, error:"...", status: 401\|404\|500}` |

### 3.6 CR 파싱 정규식 패턴 (계약 정밀도를 위해 명시)

```python
# FP 추출 (4패턴 순서 시도)
FP_PATTERNS = [
    r'FP\s*합계\s*:\s*(\d+)',          # "FP 합계 : 8"
    r'FP\s*:\s*(\d+)\s*\(',             # "FP : 8 (기타)"
    r'기능\s*점수\s*\(FP\)\s*[|]\s*(\d+)',  # "기능 점수(FP) | 8"
    r'FP\s*[|:]\s*(\d+)',               # "FP | 8" / "FP: 8"
]
# 공수 추출 (3패턴 순서 시도)
HOURS_PATTERNS = [
    r'공수\s*:\s*([\d.]+)\s*[Hh]',       # "공수 : 8.0 H"
    r'(\d+)\s*FP\s*=\s*([\d.]+)\s*[Hh]', # "8 FP = 16.0 H" → group2
    r'예상\s*공수\s*[|]\s*([\d.]+)\s*[일Hh]', # "예상 공수 | 8 일" → 8*8
]
```

### 3.7 표준 지침 `kanban-board-guide.md` 갱신 내역

| 섹션 | 변경 |
|------|------|
| §3 백엔드 | 인라인 함수 설명 → "서브모듈 `kanban-board` 사용" 으로 교체, 코드는 저장소 참조 |
| §4 프론트엔드 | Jinja 상세 → **API 계약 링크**로 교체 (Jinja 템플릿은 '참조 소비자 예시'로 격하) |
| §5 보안 | `auth_dependency` 주입 방식 추가 명시 |
| §6 재사용 체크리스트 | 서브모듈 포함 절차로 전면 개편 |
| 신규 | §7 서브모듈 패키징/포함 절차 |

## 4. 영향도 분석

| 대상 | 방식 | 영향 |
|------|------|------|
| `D:\dev\kanban-board\` (신규 git 저장소) | **범위 외(2026-07-15 결정)** | 서브모듈 추출 생략 — 문서+계약서만 현행화 |
| `.clinerules/docs/development/kanban-board-api-contract.md` | **신규 생성** | 프레임워크 중립 10엔드포인트 JSON 계약 |
| `.clinerules/docs/development/kanban-board-guide.md` | 수정 (§2/§3/§4/§6 재구성) | 7컬럼 인덱스·10라우트·4탭·간트·추세·린터·api-contract 참조로 갱신 |
| `src/routes/plans_routes.py` / `plans_kanban.html` (wordcloud) | **변경 없음** | 현상 유지 (문서 현행화만) |
| `plans/2026/07/14_03_kanban-board-guide/14_03_kanban-board-guide.md` | 수정 (본 문서) | 수정이력·드리프트·§2.3·§3.5·§3.2 산출물·상태 Done 갱신 |

**비변경 대상** (Phase 1 완료분 유지): `18_05` 최신화, `22_02`·`14_02` 상태 수정, `_index.md`, 원페이퍼 보고서

## 5. 검증 계획

| # | 시나리오 | 기대 | 방법 |
|---|----------|------|------|
| 1 | 독립 저장소 `kanban-board` `git init` + 정상 clone/import | 저장소 생성, `from kanban.routes import kanban_bp` | Python import |
| 2 | wordcloud 결합 제거 확인 | `PLANS_DIR`·`CR_DIR`·`admin_required`가 주입형으로 변경 | 코드 검토 |
| 3 | API 계약 정합성 | `docs/api-contract.md` JSON 스키마가 실제 `routes.py` 동작과 일치 | 대조 |
| 4 | 샘플 픽스처 포맷 | `sample_data/*`가 실제 `_parse_index_md`·`_parse_cr_file` 파서로 정상 파싱 | 파싱 테스트 |
| 5 | README Quickstart | 서브모듈 추가→마운트→API 호출 절차 누락 없음 | 문서 검토 |
| 6 | 표준 지침 갱신 확인 | §3→서브모듈 참조, §4→API 계약, §6→submodule 체크리스트로 개편 | 문서 대조 |

## 6. 리스크 및 제약

| 리스크 | 대응 |
|--------|------|
| wordcloud 결합 제거 시 뉘앙스 누락(예: CR_DIR 유도 로직의 미묘한 차이) | `KanbanConfig`에 `cr_dir` 기본값 유도 로직을 보존하되 명시적 설정 우선 |
| `admin_required` 기본값(Flask session)이 아닌 환경에서 보안 허점 | `auth_dependency`가 None이면 기본 동작→에러 raise, 사용자가 반드시 설정하도록 문서화 |
| 서브모듈은 소스 변경 가능하나 upstream과 drift 위험 | `README.md`에 "upstream Pull → 충돌 해결 → `git submodule update`" 절차 명시 |
| wordcloud 인라인 소스(`plans_routes.py`)와 서브모듈 간 2중 관리 | 이번 범위는 **신규 저장소만**. wordcloud 마이그레이션은 별도 후속 작업 |
