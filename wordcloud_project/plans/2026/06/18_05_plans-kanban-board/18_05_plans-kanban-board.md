# 계획서 — Plans Kanban Board + 폴더 선택형 프레임워크

> 상태: Done — 2026-07-14 소스 진화 반영(아래 §수정이력) | 작성일: 2026-06-18
> 작업 유형: B (기능 개선/신규 기능)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-18 | 전체 | 최초 작성 |
| 2026-07-14 | §3 구현 상세 | 소스 진화 반영 전면 정정 — 6컬럼·월드롭다운·CR현황탭·칩·정렬·Done그룹카드. 현재 상태 실측 기준은 `kanban-board-guide.md`(표준지침) 및 `14_03_kanban-board-guide.md`(통합계획서) 참조 |

## 1. 배경 및 목적

### 1.1 문제
- `plans/2026/` 폴더에 48개 계획서가 누적되었지만 **현황 파악이 어려움** (폴더명으로만 확인)
- `_index.md`의 **상태 표기가 불일치** (`DN`/`✅ DN`/`🟡 PND`/`PND` 혼용)
- 각 계획서 문서를 열어야만 **상세 내용 확인 가능**
- **타 프로젝트에서 재사용 불가** — 현재 구조가 wordcloud 프로젝트에 강결합

### 1.2 목표
1. `plans/` 폴더를 **Kanban 보드** 형태로 시각화 (Todo → Doing → Done)
2. **폴더 경로를 선택 가능**하게 하여 타 프로젝트에서도 동일 컴포넌트 사용 가능
3. `_index.md` 포맷을 **표준화**하여 파싱 안정성 확보
4. 개별 계획서 **상세 내용을 모달로 바로 확인**

## 2. 현재 시스템 분석

### 2.1 _index.md 포맷 (현재)
```markdown
| 계획서 | 작업 요약 | 상태 | 작성일 |
|--------|-----------|------|--------|
| 0421_01_batch-scalability-plan | 배치 처리 대용량 최적화 | PND | 2026-04-21 |
```
- **문제점**: 상태 컬럼에 `PND`, `🟡 PND`, `DN`, `✅ DN`, `📄 분석` 혼용 → 파싱 복잡도 증가
- **개선 방향**: 상태는 **약어만** 사용 (`PND`/`DN`/`분석`), 표시용 emoji는 UI에서 처리

### 2.2 개별 계획서 포맷 (현재)
```markdown
> 상태: Todo | 작성일: 2026-06-18
> 작업 유형: B
```
- **문제점**: `_index.md`의 `작업 요약`과 중복 정보. Kanban 카드에 필요한 제목/요약을 파싱하려면 두 파일을 모두 읽어야 함
- **개선 방향**: `_index.md`를 **단일 정보 원천(Single Source of Truth)** 으로 사용

### 2.3 관련 파일/함수
- `src/routes/admin_routes.py` — admin_bp 패턴 (참조용)
- `src/config/settings.py` — 설정 추가 위치
- `web/app.py` — blueprint 등록 위치
- `web/templates/base.html` — nav 링크 추가 위치
- `mistune==3.1.4` — `.md` → HTML 변환용 (requirements.txt에 존재)

> ⚠️ **2026-07-14 진화**: 아래 구현 상세는 2026-07-14 기준 소스(`plans_routes.py` 538줄 / `plans_kanban.html` 877줄)로 **전면 정정**되었다.
> 초기 설계(3컬럼 + PLANS_ROOTS 선택기)는 Pre-Done 컬럼·카드 칩·월 드롭다운·월별 CR현황 탭·Done 그룹카드·정렬 기능이 추가되어 확장되었다.
> **현재 상태의 실측 기준**: `.clinerules/docs/development/kanban-board-guide.md`(표준지침) 및 `plans/2026/07/14_03_kanban-board-guide/`(통합계획서)

## 3. 구현 상세

### 3.1 설정 계층 (`src/config/settings.py`)

```python
# Plans directory (칸반보드 대상 베이스 폴더)
PLANS_DIR = os.getenv('PLANS_DIR', os.path.join(PROJECT_ROOT, '..', 'plans', '2026'))
```

- `PLANS_DIR`: `{BASE}/{YYYY}` 형식. 칸반보드는 `PLANS_DIR/MM/_index.md` (월별 인덱스)를 병합하여 표출
- `PLANS_ROOTS`(다중 프로젝트 경로 선택): 설정만 남아있으나 **현재 월 드롭다운으로 대체되어 미사용**. 필요시 재활성화 가능

### 3.2 백엔드 (`src/routes/plans_routes.py`)

**6개 라우트** + **2개 CR 라우트**:

| 라우트 | 메서드 | 설명 |
|--------|--------|------|
| `GET /admin/plans` | HTML | 칸반보드 페이지 (서버사이드 렌더링) |
| `GET /admin/api/plans/check?month=<MM>` | JSON | `{modified_at}` — `_index.md` 수정시각만 반환 (10초 폴링용) |
| `GET /admin/api/plans?month=<MM>` | JSON | 전체 plan 목록 (상태별 그룹, `parse_all_months`로 월별 `_index.md` 병합) |
| `GET /admin/api/plans/<plan_id>/content?dir=<path>` | JSON | 특정 plan 메인 `.md` 원문 반환 |
| `GET /admin/api/plans/cr-monthly` | JSON | CR 월별 집계 (별도 CR 문서 폴더 연동) |
| `GET /admin/api/plans/cr/<req_id>` | JSON | 특정 CR 상세 |

**데이터 추출 로직** (`parse_all_months()` → `_parse_index_md()`):
1. `PLANS_DIR/MM/` 하위 모든 월 폴더 스캔 (`_discover_month_dirs`)
2. 각 월의 `_index.md` 읽어 마크다운 테이블 파싱 (`_parse_index_md`, 정규식 `TABLE_RE`)
3. 각 plan 폴더 스캔: 메인 `.md` 존재여부, `result/`·`test/` 폴더 파일 카운트, 작업 유형(메인 `.md` 헤더 파싱)
4. 상태 매핑: `STATUS_MAP`에 정의된 6개 상태로 직접 매핑 (정규화 없음 — `_index.md` 표준 준수)
5. 상태별 그룹핑 + 통계 (완료/작업중/Pre-Done/예정/보류/폐기/총계)

### 3.3 프론트엔드 (`web/templates/plans_kanban.html`)

**레이아웃**:
```
┌────────────────────────────────────────────────────────────┐
│ [📋 칸반보드] [📊 월별 CR 현황]  ← 탭                     │
├────────────────────────────────────────────────────────────┤
│ 📋 Plans Kanban  ✅ 26완료  🔄 5작업중  📋 13예정  · 총 48│
│ [▼ 월 선택] 2026/07                                        │
├─────────┬──────────┬──────────┬─────────┬───────┬─────────┤
│ 📋 Todo│ 🔄 Doing │ 🔶 Pre-  │ ✅ Done │ 📌Hold│ 🗑️ Drop│
│ (13)   │ (5)      │ Done (2) │ (26)    │ (1)   │ (1)     │
│ ┌─────┐│ ┌──────┐ │ ┌──────┐ │ ┌─────┐ │ ┌───┐ │ ┌─────┐│
│ │card ││ │card  │ │ │card  │ │ │card │ │ │card│ │ │card ││
│ └─────┘│ └──────┘ │ └──────┘ │ └─────┘ │ └───┘ │ └─────┘│
└─────────┴──────────┴──────────┴─────────┴───────┴─────────┘
```

**카드** (칩 5종, 클릭 시 모달):
```
┌─────────────────────────────────────┐
│ 0617_01                             │  ← plan_id (bold)
│ emotion-rule-mining                 │  ← summary (muted)
│ [07월] [✅ Done] [B] [📄3] [🧪1]   │  ← 칩 5종
└─────────────────────────────────────┘
```

- 칩 순서: 월(MM월) → 상태 배지 → 작업 유형(있을 때만) → result 카운트(0이면 생략) → test 카운트(0이면 생략)

**Done 컬럼 월별 그룹카드**:
- 현재월 Done: 개별 카드로 펼쳐서 표시
- 과거월 Done: 그룹카드 `📦 MM월 완료 (N건)` 1장/월 (클릭 시 해당 월 일람 모달)
- 그룹카드에는 월 칩을 붙이지 않음

**정렬 버튼**:
- 각 컬럼 헤더 우측 `↓`/`↑` 버튼
- 모든 컬럼 동일 방향 공유 (date 기준)
- 내림차순(최신순)이 기본값

**모달** (클릭 시, JS 마크다운 렌더):
```
┌─────────────────────────────────────────────────────┐
│ 📄 0617_01_emotion-rule-mining               [✕]    │
├─────────────────────────────────────────────────────┤
│  (JS 마크다운 → HTML — 코드블록·테이블·리스트 등)   │
│                                                     │
│  📁 폴더 열기  ·  📄 result/ (파일수)  ·  🧪 test/   │
├─────────────────────────────────────────────────────┤
│                                        [닫기]        │
└─────────────────────────────────────────────────────┘
```

**자동 갱신**:
- JS 10초 간격 `GET /admin/api/plans/check?month=MM` → `_index.md` 수정시각 확인
- 변경 감지 시에만 `GET /admin/api/plans?month=MM` 호출 → 카드 재렌더링(renderCards)
- 월 선택 변경 시 전체 페이지 리로드 없이 카드 교체

**월 선택기**:
- 상단 `<select>` 드롭다운 — `_discover_month_dirs()`가 반환한 월 목록
- `ALL`(전체) 또는 특정 월 선택
- 변경 시 `?month=` 파라미터 업데이트 + 칸반 재렌더링

**월별 CR 현황 탭**:
- CR 문서 폴더(`.clinerules/docs/cr/`) 내 `REQ-*.md` 파싱
- 월별 아코디언, 각 CR 행(REQ-ID/유형/변경요약/FP/공수)
- 행 클릭 시 CR 상세 모달
- 최신월 자동 오픈, 누적 FP/공수 표시

### 3.4 _index.md 포맷 표준화

`_index.md` 포맷은 `03.plan-mode.md §8`에서 별도 규정한다. 현재 규칙을 요약하면:

**포맷**:
```markdown
# 2026 계획서 인덱스

| 계획서 | 작업 요약 | 상태 | 작성일 |
|--------|-----------|------|--------|
| 0618_04_batch-resume-progress | 배치 이어서 처리 진행 현황 수정 | Done | 2026-06-18 |
| 0618_03_deploy-wc-parallel | 제출용 저장 워드클라우드 생성 병렬화 | Todo | 2026-06-18 |
| 0618_02_wordcloud-opt-feasibility | 0617_07 기법의 워드클라우드 적용 가능성 분석 | Doing | 2026-06-18 |
```

**규칙**:
- 상태값은 **영문 약어 6종**만 사용: `Todo` / `Doing` / `Pre-Done` / `Done` / `Hold` / `Drop`
- Emoji(`✅`, `🔄`, `📋` 등)를 상태 컬럼에 **절대 포함 금지** — Kanban UI 레이어가 자동 부여
- `_index.md` 수정 시 10초 내 Kanban에 자동 반영 (폴링)
- 상세: `03.plan-mode.md §8` 참조

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `settings.py` — `PLANS_DIR`, `PLANS_ROOTS` 추가 | 없음 |
| 2 | `src/routes/plans_routes.py` 생성 — `_index.md` 파서 + 4개 라우트 | 1 |
| 3 | `web/templates/plans_kanban.html` 생성 — 칸반보드 + 모달 + JS 폴링 | 2 |
| 4 | `web/app.py` — `plans_bp` 등록 | 2 |
| 5 | `web/templates/base.html` — 네비 링크 추가 | 4 |
| 6 | `03.plan-mode.md` — _index.md 포맷 지침 업데이트 | 없음 |
| 7 | `_index.md` — 오염된 상태값 정리 + 신규 항목 추가 | 6 |

## 5. 영향도 분석

| 변경 파일 | 영향 범위 | 리스크 |
|-----------|-----------|--------|
| `src/config/settings.py` | 설정 2개 추가 | 기본값 있으므로 기존 코드 변경 없음 |
| `src/routes/plans_routes.py` | 신규 파일 | 기존 라우트와 충돌 없음 (`/admin/plans` 새 경로) |
| `web/templates/plans_kanban.html` | 신규 파일 | 단독 페이지, 기존 템플릿 의존 없음 |
| `web/app.py` | 블루프린트 1줄 추가 | 단순 등록, 사이드 이펙트 없음 |
| `web/templates/base.html` | nav 링크 1줄 추가 | 디자인 영향 없음 |
| `.clinerules/core/00-core/03.plan-mode.md` | _index.md 규칙 업데이트 | 향후 계획서 작성에만 영향 |
| `plans/2026/_index.md` | 상태값 정규화 | 48개 엔트리 상태값 일괄 수정 필요 |

## 6. 테스트/검증 계획

| 시나리오 | 검증 항목 | 방법 |
|----------|-----------|------|
| 칸반보드 페이지 로드 | 3개 컬럼에 카드가 올바르게 분류되는가 | 브라우저 확인 |
| 폴더 선택 변경 | 다른 `_index.md`로 전환 시 카드가 교체되는가 | 드롭다운 조작 |
| 카드 클릭 | 모달에 `.md` 내용이 HTML로 표시되는가 | 클릭 확인 |
| `_index.md` 수정 | 10초 내 자동 갱신되는가 | `_index.md` 수정 후 대기 |
| 상태값 혼용 내성 | `✅ DN`/`DN`/`🟡 PND`/`PND` 모두 정상 파싱되는가 | 혼용 상태 입력 후 확인 |
| 타 프로젝트 폴더 | 다른 구조의 `_index.md`도 동일하게 표시되는가 | 경로 변경 테스트 |
| 존재하지 않는 폴더 | 에러 메시지 표시 + 빈 보드 | 유효하지 않은 경로 입력 |

## 7. 리스크 및 제약

- **`_index.md` 테이블 파싱은 행 수와 포맷 일관성에 의존** — 형식이 크게 달라지면 파싱 실패
- **파일시스템 기반이므로 WAS 여러 개일 때 동기화 문제 없음** (stateless)
- `.md` 파일이 매우 클 경우 모달 렌더링 성능 저하 가능 — mistune은 스트리밍 미지원, 전체 로드
- **PLANS_ROOTS 경로는 보안 검증 필요** — 임의 경로 접근 가능하므로 관리자 전용

---

> **2026-07-14 현재**: 위 구현은 소스에 반영 완료. 이후 Pre-Done 컬럼·카드 칩(월/유형/result/test)·Done 월별 그룹카드·정렬 버튼·월별 CR 현황 탭이 추가되어 **컬럼 6개·라우트 6개+CR 2개**로 확장되었다.
> 현재 상태의 실측 기준 및 재사용 지침:
> - 표준 지침: `.clinerules/docs/development/kanban-board-guide.md`
> - 통합 명세: `wordcloud_project/plans/2026/07/14_03_kanban-board-guide/14_03_kanban-board-guide.md`
