# 계획서 G5 — 공통↔프로젝트 지침 재분류 및 이관 (승격/강등)

> 상태: Pre-Done | 작성일: 2026-07-28 | 완료일: 2026-07-28
> 작업 유형: D (리팩토링)
> 선행: 07/28_03_repo-layout-std, 07/28_04_doc-numbering-std, 07/28_05_compass-rule
> 에픽: guideline-standard

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-28 | 전체 | 초안 작성 |

---

## 요구사항 원자화

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | "공통"의 판별 기준이 문서로 정의되어 있는가? | 현재 N → 도입 후 Y | (미수행) |
| 1.2 | 공통 후보 구역에 프로젝트 고유어가 남아 있는 파일이 몇 개인가? | 17개 | (미수행) |
| 1.3 | 프로젝트 지침 중 공통으로 올릴 것이 실제로 존재하는가? | Y | (미수행) |
| 1.4 | 공통 지침 중 프로젝트로 내릴 것이 실제로 존재하는가? | Y | (미수행) |
| 2.1 | 이관 후 `common/`에서 프로젝트 고유어 검색 시 0건인가? | Y | (미수행) |

---

## 1. 공통성 판별 기준 (선행 정의)

이관을 시작하기 전에 **기준을 문서로 먼저 못 박는다.** 기준 없이 옮기면 다음 사람이 다시 뒤섞는다.

### 규칙 COM — 공통 지침의 자격

한 문서가 `common/`에 있으려면 **아래 4개를 모두** 만족해야 한다.

| # | 조건 | 반례 |
|---|------|------|
| COM-1 | **도메인 비의존** — 규칙의 타당성이 특정 업무 도메인(인사평가·설비관리 등)에 의존하지 않는다 | "감정 분석 시 긍↔부 오분류 방지 우선" → wordcloud 전용 |
| COM-2 | **2개 이상 프로젝트 적용 가능** — 최소한 wordcloud와 msys 양쪽에서 말이 된다 | "KoTE 모델 파인튜닝 절차" |
| COM-3 | **고유값 외재화 가능** — 문서에 남는 프로젝트 고유값이 `project.json` 키로 전부 치환 가능하다 | 치환 불가한 고유 구조 설명(테이블 스키마 등) |
| COM-4 | **기술 스택 중립 또는 명시적 스택 문서** — 스택에 의존한다면 문서 제목·상단에 그 스택을 명시하고, 다른 스택 프로젝트가 "적용 대상 아님"을 판단할 수 있어야 한다 | 스택 의존인데 그 사실이 안 적혀 있는 문서 |

### 규칙 DEM — 프로젝트 지침으로 강등할 것

COM 중 하나라도 불만족이면 `projects/prj-<id>/`로 내린다. **부분 위반이면 문서를 쪼갠다** — 공통 부분만 남기고 프로젝트 부분을 떼어 내린다.

---

## 2. 현황 실측 — 이관 대상 후보

### 2.1 공통 후보 구역에 남은 프로젝트 고유어 (2026-07-28)

측정: `grep -rc -i "msys\|wordcloud\|KoTE\|jandi" core docs/development docs/ui docs/verification --include=*.md | grep -v ":0$"`

| 파일 | 히트 | 1차 판정 |
|------|------|----------|
| `core/00-core.md` | 7 | 플레이스홀더화 (G1) |
| `core/00-core/03.plan-mode.md` | 6 | 플레이스홀더화 (G1) — `plans_root` |
| `core/08-guideline-modification/04.folder-naming.md` | 5 | **예시 교체** — 예시가 `docs/msys/` 경로 (PRD A5) |
| `core/01.legacy-protection.md` | 3 | 내용 확인 후 판정 |
| `core/08-guideline-modification/05.post-modification.md` | 3 | 내용 확인 후 판정 |
| `core/16-report-writing.md` | 2 | 내용 확인 후 판정 |
| `docs/ui/common/screen-domain.md` | 2 | 내용 확인 후 판정 |
| `docs/development/status-code-extension-guide.md` | 2 | 내용 확인 후 판정 |
| `core/02.documentation.md` / `core/04-design-change/scale.md` / `core/05.testing.md` / `core/09.question-rules.md` / `core/14.comment-log-removal.md` / `core/15-backup-before-modify.md` | 각 1 | 내용 확인 후 판정 |
| `docs/development/{kanban-board-api-contract,kanban-board-guide,server-reload-guide}.md` | 각 1 | 내용 확인 후 판정 |

합계 **17개 파일**. (`core/04-design-change/scenarios.md`는 도메인어 히트만 있고 프로젝트명 히트 0 → 별도 확인)

> ⚠️ **1차 판정은 grep 결과일 뿐 결론이 아니다.** 히트 1건이 "예시 문장에 프로젝트명이 나온 것"인지 "규칙 자체가 그 프로젝트 전용"인지는 **파일을 열어야** 안다. 실행 시 17개 파일을 전건 Read 하고 §5 표를 채운 뒤 이관한다.

### 2.2 승격 후보 — 프로젝트 지침 → 공통

| 대상 | 현재 위치 | 승격 근거 | COM 충족 |
|------|-----------|-----------|----------|
| `docs/design/common/system-design.md` (14줄) | `docs/design/common/` | "Python 3.11+ / Flask / SQLite" 스택 규약. wordcloud·msys 양쪽 다 Flask+Python | COM-1 ✅ COM-2 ✅ COM-3 ✅ COM-4 — **스택 명시 필요** |
| `docs/design/common/api-design.md` (9줄) | 동일 | RESTful 원칙·응답 포맷 — 도메인 무관 | ✅ |
| `docs/design/common/architecture.md` (14줄) | 동일 | "Flask Application Factory + Blueprint" — 양 프로젝트 공통 패턴 | ✅ (스택 명시 필요) |
| `docs/design/common/database-design.md` (27줄) | 동일 | **`instance/app.db` 등 구체 경로 포함** — COM-3 검증 필요 | ⚠️ 확인 필요 |

> `docs/design/`은 폴더명이 `design/common/`으로 이미 "공통"을 자칭하나, 새 레이아웃에는 `design` 구역이 없다. 4개 모두 `common/development/`로 흡수하거나(스택 규약), COM 불충족분은 `projects/prj-wordcloud/`로 내린다.

**추가 승격 후보 (실행 시 판정)**: `projects/prj-wordcloud/`로 갈 37개 파일 중, 프로젝트 무관한 절차가 섞여 있는지 전건 확인한다. 특히 `docs/project_wordcloud/operator-manual/DEVELOPMENT.md`는 27_01에서 공용분을 이미 `docs/common/operator-manual/`로 뺐으므로 **잔여가 프로젝트 전용인지**만 확인하면 된다.

### 2.3 강등 후보 — 공통 → 프로젝트

| 대상 | 강등 근거 | 확인 방법 |
|------|-----------|-----------|
| `core/15.schedule-rules.md` (266줄) | "스케줄"이 msys의 수집 스케줄 도메인 규칙일 가능성 | 파일 Read 후 COM-1 판정 |
| `core/06.git-rules.md` (519줄) 중 CR 절차 부분 | CR 번호 체계(`REQ-YYMM-NNN`)는 공통이나, CR 저장 경로·FP 산정은 프로젝트 규약일 수 있음 | 파일 Read 후 부분 분리 판단 |
| `docs/development/kanban-board-*.md` (2개) | 칸반보드는 wordcloud `plans/` UI 전용 기능(`src/routes/plans_routes.py`) | 프로젝트 전용이면 강등 |
| `docs/development/status-code-extension-guide.md` | 상태코드 체계가 msys `sts_cd` 테이블 규약이면 강등 | Read 후 판정 |

---

## 3. 삭제 대상

| 대상 | 파일수 | 사유 | 근거 |
|------|--------|------|------|
| `docs/msys/**` | **199** | 타 프로젝트 지침. 정본은 `D:\dev\msys\.clinerules\projects\msys\`(246파일)에 존재 | ISO-4. PRD D2 |

**삭제 전 필수 절차**:
1. `D:\dev\msys\.clinerules\projects\msys\`와 **파일 목록 대사** — wordcloud 쪽에만 있는 파일이 있으면 msys 저장소로 **먼저 이관**한 뒤 삭제한다. (wordcloud 199 vs msys 246으로 개수가 달라, 단순 삭제 시 유실 가능)
2. 삭제 커밋 해시를 본 계획서 실행 로그에 기록.

---

## 4. 산출물 이동

| 대상 | 파일수 | 이동처 | 사유 |
|------|--------|--------|------|
| `docs/cr/**` | 39 | `outputs/cr/` | 규칙이 아니라 이력 기록 (PRD D3) |
| `docs/scenario-test-report.md` | 1 | `outputs/` | 산출물 |

이동 후 `common/core/06-git-rules.md`의 CR 저장 경로 기술을 함께 갱신한다(G2 §7 리스크 항목).

---

## 5. 실행 절차

### Phase 0 — 기준 문서화 (선행, 필수)

1. `common/core/24-common-criteria.md` 신규 작성 — §1의 COM/DEM 규칙 수록. (번호는 `NUMBERS.md`에서 채번; G3 §4.2 기준 다음 번호는 24)
2. `00-core.md` 분류표에 "지침을 공통/프로젝트 중 어디에 둘 것인가" 행 추가 → 이 문서로 라우팅.

### Phase 1 — 판정표 작성 (파일 이동 없음)

§2.1의 17개 + §2.2의 4개 + §2.3의 후보 전건을 Read 하고 아래 표를 채운다. **표가 승인되기 전에는 파일을 옮기지 않는다.**

| 파일 | 히트 내용(인용) | COM-1 | COM-2 | COM-3 | COM-4 | 판정 | 조치 |
|------|----------------|-------|-------|-------|-------|------|------|
| (실행 시 작성) | | | | | | 공통 유지 / 플레이스홀더화 / 예시교체 / 문서분리 / 강등 | |

산출물: `wordcloud_project/plans/2026/07/28_06_common-promotion/result/classification_260728.md`

### Phase 2 — 구조 이동 (G2 매핑표 실행)

G2 §3 매핑표 #1~#8을 `git mv`로 실행. 순서:

1. `core/` → `common/core/` (G3 rename과 **동시** 수행 — 두 번 옮기지 않는다)
2. `docs/development/` → `common/development/`
3. `docs/ui/` → `common/ui/`
4. `docs/verification/` → `common/verification/`
5. `docs/common/operator-manual/` → `common/operator-manual/`
6. `docs/project_wordcloud/` → `projects/prj-wordcloud/`
7. `docs/cr/` → `outputs/cr/`
8. `docs/design/` → Phase 1 판정에 따라 분배
9. `docs/msys/` → §3 절차 후 삭제

### Phase 3 — 내용 이관 (Phase 1 판정 실행)

- 플레이스홀더화: G1 §2.4 문법 적용
- 예시 교체: 프로젝트 경로 예시 → 중립 예시(`projects/prj-example/`)
- 문서 분리: 공통부 유지 + 프로젝트부를 `projects/prj-wordcloud/`로 신규 파일 생성
- 강등: 파일 통째 이동

### Phase 4 — 링크·참조 수리

1. 이동·rename에 따른 링크 전량 치환 (`.clinerules/**/*.md`, 루트 `CLAUDE.md`, `.claude/agents/*.md`)
2. 린터(G4) 실행 → `K1`/`K2` 0건까지 반복

### Phase 5 — 에이전트 정의 대사 (PRD A10)

`.claude/agents/` 11개 파일에서 `.clinerules/` 경로 참조를 전수 확인하고 신규 경로로 갱신한다. wordcloud와 msys의 에이전트 파일명 10개가 동일해(복사 이식 흔적) **타 프로젝트 경로가 섞여 있는지**도 함께 검사한다.

---

## 6. 변경 파일 목록 (요약)

| 구분 | 대상 | 규모 |
|------|------|------|
| 신규 | `common/core/24-common-criteria.md` | 1 |
| 이동 | `core/**` → `common/core/**` | 19 + 하위 ~30 |
| 이동 | `docs/{development,ui,verification}` → `common/**` | 28 |
| 이동 | `docs/common/operator-manual` → `common/operator-manual` | 12 |
| 이동 | `docs/project_wordcloud` → `projects/prj-wordcloud` | 37 |
| 이동 | `docs/cr` → `outputs/cr` | 39 |
| 분배 | `docs/design/common` | 4 |
| 삭제 | `docs/msys` | 199 |
| 수정 | 링크 보유 md 전량 + `.claude/agents/*.md` | 다수 |

---

## 7. 검증 계획

| # | 항목 | 방법 | 기대 |
|---|------|------|------|
| 1 | `common/`에 프로젝트 고유어 | `grep -rin "wordcloud\|msys\|kote\|jandi" .clinerules/common` | **0건** |
| 2 | 플레이스홀더 유효성 | 린터 `P4` | 미정의 키 0 |
| 3 | 격리 | 린터 `L1`~`L4` | 0건 |
| 4 | 링크 | 린터 `K1`,`K2` | 0건 |
| 5 | `docs/` 소멸 | `ls .clinerules/docs` | 없음 |
| 6 | msys 삭제 전 유실 없음 | wordcloud `docs/msys` 목록 − msys `projects/msys` 목록 | 차집합 0 (아니면 선(先) 이관) |
| 7 | 파일 총수 보존 | 이동 전후 md 개수 대사 (삭제분 199 제외) | 일치 |
| 8 | 서브모듈 커밋 | `git -C .clinerules status` + 상위 포인터 | 정상 |

---

## 8. 리스크

| 리스크 | 대응 |
|--------|------|
| `docs/msys` 199 삭제로 wordcloud에만 있던 문서 유실 | 검증 #6을 **삭제 전 게이트**로 삼는다. 차집합이 0이 아니면 삭제 금지 |
| Phase 1 판정을 grep 결과로 대충 끝냄 | 판정표에 **인용문 컬럼을 필수**로 두어, 파일을 열지 않으면 채울 수 없게 한다 |
| 이동과 rename을 따로 해 링크를 두 번 깨뜨림 | Phase 2-1에서 G3 rename과 **한 번에** 수행 |
| `06.git-rules.md` 519줄 분리 중 CR 절차 유실 | 분리 전후 조항 대응표를 실행 로그에 기록 (G4 CMP-4 준용) |
| 배포 갭 재발(서브모듈 미커밋) | 검증 #8을 완료 조건에 포함 |

---

## 9. 완료 기준

- [ ] `common/core/24-common-criteria.md` 존재 (COM/DEM 규칙)
- [ ] `result/classification_260728.md` 판정표 전건 작성 + 승인
- [ ] 검증 #1~#8 전부 PASS
- [ ] 린터 전 항목 error 0건
- [ ] `.clinerules` 서브모듈 커밋 + 상위 저장소 포인터 갱신 (사용자 요청 시)

---

## 실행 로그 (2026-07-28)

| 산출물 | 경로 |
|--------|------|
| 공통 자격 기준 | `.clinerules/common/core/24-common-criteria.md` |
| 레지스트리 | `.clinerules/common/PROJECTS-REGISTRY.md` |

### 재분류 결과

| 대상 | 판정 | 조치 |
|------|------|------|
| `docs/design/common/` 4파일 | **승격** (COM-1~4 충족: Flask/SQLite 스택 규약, 프로젝트 고유값 없음) | `common/development/design/` + 적용범위 고지 |
| `common/ui/common/screen-domain.md` | **부분 위반 → 분할** | 공통(목적·정의 양식·분석 경로) 잔류, 화면 매핑표·시나리오는 `projects/wordcloud/templates/screen-domain.md` 로 강등 |
| `projects/wordcloud/README.md` §PseudonymManager | 나침반 비대 | `projects/wordcloud/modules/pseudonym-manager.md` 로 분리 |
| `common/core/01-legacy-protection.md` 배포파일 목록 | 프로젝트 전용 | `{{guideline.project_dir}}/deployment.md` 위임으로 교체 |
| `common/development/status-code-extension-guide.md` | 예시가 특정 프로젝트 | 중립 예시로 교체 |
| `common/core/08-guideline-modification/04-folder-naming.md` | 예시가 타 프로젝트 경로 | `projects/example/` 중립 예시로 교체 |
| 나머지 `common/` 고유어 | 플레이스홀더화 | `{{paths.plans_root}}` 등 |

측정: `common/` 프로젝트 고유어 67행 → **0행**.

### 미완 — Pre-Done 사유

`docs/msys` 199파일을 **삭제하지 못했다**(게이트 FAIL). `outputs/_transfer-msys/` 로 격리만 했으며, msys 저장소로의 실제 이관은 `28_07` 승인 후 수행한다. 이 항목이 닫히기 전에는 Done 으로 올리지 않는다.
