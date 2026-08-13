# PRD — AI 지침 하네스 표준화 (공통 지침 / 프로젝트 지침 분리 체계)

> 상태: Done | 작성일: 2026-07-28 | 완료일: 2026-07-28
> 작업 유형: C (설계) — 후속 실행은 28_02~28_07 세부 계획서
> 선행: 07/23_01_clinerules-msys-decontaminate (Done)
> 에픽: guideline-standard

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-28 | 전체 | 초안 작성 (실측 조사 기반) |

---

## 0. 이 문서의 범위

이 PRD는 **무엇을 왜 바꾸는가**만 정의한다. **어떻게 바꾸는가**는 아래 6개 세부 계획서가 담당한다.

| 그룹 | 계획서 | 담당 범위 |
|------|--------|-----------|
| G1 | `28_02_prj-identity` | 프로젝트 식별 체계 (`project.json` + 폴더명 폴백) |
| G2 | `28_03_repo-layout-std` | 저장소 레이아웃 표준 + 프로젝트 지침 폴더 명칭 표준 + 격리 규칙 |
| G3 | `28_04_doc-numbering-std` | 문서 넘버링·파일명·폴더명 표준 + 채번 대장 |
| G4 | `28_05_compass-rule` | 나침반(Compass) 규약 정밀화 + 자동 검사(린터) |
| G5 | `28_06_common-promotion` | 공통↔프로젝트 재분류 이관 (승격/강등) |
| G6 | `28_07_multi-prj-rollout` | 타 프로젝트 적용(롤아웃) 가이드 |

전체 경로 기준(저장소 루트 = `D:\dev\wordcloud`):
`wordcloud_project/plans/2026/07/28_0N_*/28_0N_*.md`

---

## 1. 배경 — 실측된 현재 상태

### 1.1 두 저장소는 이미 별개로 분기했다 (2026-07-28 실측)

| 프로젝트 | `.clinerules` origin | 최상위 레이아웃 |
|----------|----------------------|-----------------|
| wordcloud (`D:\dev\wordcloud`) | `https://github.com/OpenUM929/clinerules` | `core/`, `docs/` |
| msys (`D:\dev\msys`) | `https://github.com/feelmydream80-sys/clinerules` | `CLAUDE.md`, `common/`, `docs/`, `projects/` |

측정 방법: 각 `.clinerules` 폴더에서 `git remote -v`, `ls -1`.

> **핵심 시사점**: "같은 서브모듈을 공유하다 섞였다"가 아니라 **서로 다른 저장소가 서로를 오염시킨 채 각자 진화**했다. 따라서 표준화는 파일 정리가 아니라 **정본(canonical) 저장소 재정의**를 포함해야 한다.

### 1.2 오염은 양방향이며 현재도 잔존한다

| 방향 | 실측 |
|------|------|
| wordcloud 정보 → msys **공통** 지침 | `D:\dev\msys\.clinerules\common\` 하위 **14개 파일**에 `wordcloud` 문자열 존재. 특히 `common/core/00-core.md`는 "현재 프로젝트 = `docs/project_wordcloud/README.md`", "wordcloud 관련 작업", "`build_deploy.ps1` → `wordcloud-project.zip`"을 **공통 나침반에 하드코딩** |
| msys 정보 → wordcloud 저장소 | `D:\dev\wordcloud\.clinerules\docs\msys\` **199개 파일** 잔존. 추가로 `core/`·`docs/common/`·`docs/development/` 중 **7개 파일**이 msys를 참조 |

측정 방법:
```
grep -rln "wordcloud" D:/dev/msys/.clinerules/common          → 14
find D:/dev/wordcloud/.clinerules/docs/msys -type f | wc -l   → 199
grep -rln "docs/msys\|projects/msys" core docs/common docs/development docs/project_wordcloud → 7
```

### 1.3 오염의 근본 원인 3가지

| # | 원인 | 근거 |
|---|------|------|
| C1 | **프로젝트 식별을 AI의 수기 편집에 의존** — 공통 나침반 `00-core.md` 상단 "현재 프로젝트" 줄을 사람/AI가 직접 고쳐 쓴다. 템플릿을 복사할 때 치환을 빠뜨리면 그대로 오염 | msys `common/core/00-core.md:11`이 wordcloud를 가리킴. wordcloud `core/00-core.md:11`도 동일 구조 |
| C2 | **공통/프로젝트 물리 분리 부재(wordcloud)** — 공통 규칙(`core/`, `docs/development/`, `docs/ui/`)과 프로젝트 규칙(`docs/project_wordcloud/`, `docs/msys/`)이 같은 `docs/` 아래 평평하게 섞여 있어 경로만으로 소속을 판별할 수 없다 | `docs/` 1-depth: `common`(12), `cr`(39), `design`(4), `development`(15), `msys`(199), `project_wordcloud`(37), `ui`(10), `verification`(3) — 공통·프로젝트·산출물이 동급 |
| C3 | **격리 규칙 부재** — "다른 프로젝트 지침을 읽지/쓰지 않는다"는 명문 규칙이 없다. 23_01에서 한 번 청소했으나 재발 방지 장치는 "치환 필수화" 문장 한 줄뿐이고 자동 검사가 없다 | `07/23_01_clinerules-msys-decontaminate.md:51` "재발 방지 — 향후 프로젝트 템플릿 복사 시 프로젝트명 치환 필수화" |

### 1.4 넘버링·명명 붕괴 (실측)

`D:\dev\wordcloud\.clinerules\core\` 최상위 md 19개 기준:

| 증상 | 실측 |
|------|------|
| 구분자 혼재 | 점(`01.legacy-protection.md`) 12개 / 하이픈(`11-performance-optimization-plan.md`) 7개 |
| 하위 폴더는 또 다른 구분자 | `10-project-compass/01_scan.md` — **언더스코어** |
| 무번호 혼재 | `03-workflow/precheck.md`, `04-design-change/checklist.md` 등 번호 없음 |
| 번호 중복 | `02.documentation.md` ↔ `02.hallucination-prevention.md`, `15-backup-before-modify.md` ↔ `15.schedule-rules.md` |
| 나침반 파일명과 폴더명 불일치 | `03.plan-mode.md`(점) ↔ `03-plan-mode/`(하이픈) |

→ **구분자 4종(`.`, `-`, `_`, 없음)이 한 저장소에 공존하고, 채번 규칙이 없어 신규 문서가 기존 번호를 덮어쓴다.**

### 1.5 나침반 규약 미준수 (실측)

기존 규칙: `core/10.project-compass.md:27-29` — "나침반 문서는 80줄 초과 시 폴더로 분리하고 경로만 나열", "80줄 초과 → 즉시 폴더 생성 후 내용 재분류".

| 실측 | 값 |
|------|-----|
| `core/` + `docs/` 전체 중 80줄 초과 md | **72개** |
| `core/` 만 | **17개** |
| 최악 사례 | `core/06.git-rules.md` **519줄**, `core/02.hallucination-prevention.md` 287줄, `core/15.schedule-rules.md` 266줄 |
| **분리했는데도 축소 안 된 사례** | `core/00-core/03.plan-mode.md` **222줄** — 하위 폴더 `03-plan-mode/`(7파일)를 이미 갖고 있으면서 본문을 그대로 보유 |
| 나침반 선언 파일("이 파일은 나침반이다") | 5개 (`core/00-core.md`, `core/08.guideline-modification.md`, `core/10.project-compass.md`, `docs/common/operator-manual/DEVELOPMENT.md`, `docs/ui/common/layout-and-components.md`) — 이 중 `00-core.md`는 114줄로 자체 규칙 위반 |

측정 방법: `find core docs -name "*.md" -exec wc -l {} \; | awk '$1>80' | wc -l`

→ **규칙은 있으나 (a) 나침반 판정 기준이 선언문 문자열에 의존하고 (b) 위반을 검출하는 장치가 없어** 실효가 없다.

---

## 2. 목표

| # | 목표 | 성공 지표 |
|---|------|-----------|
| O1 | 프로젝트 식별을 **파일 데이터**로 결정한다 | 어떤 지침 문서에도 특정 프로젝트명이 하드코딩되지 않는다. 공통 지침의 "현재 프로젝트"는 `project.json`을 읽어 해소한다 |
| O2 | 공통/프로젝트 지침을 **경로로 구분**한다 | 임의 지침 파일의 경로만 보고 공통인지 어느 프로젝트인지 100% 판별 가능 |
| O3 | 프로젝트 간 지침 혼입 **0건** | 자동 검사에서 교차 참조 0건 |
| O4 | 문서 번호·파일명 규칙을 **단일화**하고 채번 절차를 명문화 | 구분자 1종, 번호 중복 0건, 신규 채번 근거가 대장에 남는다 |
| O5 | 나침반 규약을 **검사 가능**하게 만든다 | 나침반 파일 상한 위반 0건, 위반 시 린터가 실패 |
| O6 | wordcloud를 **정본**으로 만들고 타 프로젝트에 이식 가능하게 한다 | msys에 동일 체계를 적용하는 절차서가 존재하고, 이식 시 프로젝트 고유값은 `project.json`만 바꾸면 된다 |

**우선순위**: 사용자 지시에 따라 **wordcloud 지침이 최우선**이다. 충돌 시 wordcloud 쪽 결정을 정본으로 삼고 msys는 뒤따른다.

---

## 3. 요구사항

### 3.1 필수 요구 (사용자 명시)

| # | 요구 | 확정 사항 | 담당 |
|---|------|-----------|------|
| R1 | 프로젝트 정보를 AI가 고치지 말고 파일에서 읽는다 | **`project.json`** 채택 (사용자 지정). 저장소 루트에 위치 | G1 |
| R1.1 | root 폴더명을 프로젝트명으로 쓰는 안도 검토 | **폴백(fallback)으로만 채택** — `project.json` 부재 시에만 폴더명 사용. 사유는 §4.1 | G1 |
| R2 | 프로젝트별 별도 폴더로 관리하고, 어느 프로젝트인지 R1으로 판단 | `projects/prj-<project_id>/` — `project_id`는 `project.json`이 정한다 | G2 |
| R2.1 | 타 프로젝트 적용 가이드 필요 | 별도 롤아웃 절차서 작성 | G6 |
| R3 | 프로젝트 지침 폴더 **표준 명칭 정의** | 접두사 **`prj-`** 사용 (사용자 선호: "앞에 project 또는 prj 등을 표시") | G2 |
| R4 | 공통 지침 넘버링·명명 정의 (신규/기존 채번 방법 포함) | 구분자 하이픈 단일화 + 번호 대역 + 채번 대장 | G3 |
| R5 | 나침반 확장 규칙 미준수 검토 | 규약 정밀화 + 자동 검사 | G4 |
| R6 | 프로젝트 지침 중 공통으로 옮길 것 이관 | 전수 재분류(승격/강등 양방향) | G5 |
| R7 | 추가 개선 사항 발굴·반영 | §5에 목록화, 등급별 배분 | 전 그룹 |
| R8 | 문서명 표준화 | 지침 문서뿐 아니라 계획서·보고서 문서명 규칙도 대사 | G3 |

### 3.2 비기능 요구

| # | 요구 |
|---|------|
| N1 | 이관 시 **내용 무손실** — 삭제가 아니라 이동. 삭제는 "타 프로젝트 전용이라 이 저장소에 있을 이유가 없는 것"에 한정하고 git 이력으로 복구 가능함을 명시 |
| N2 | 모든 변경은 **사용자 승인 후** 실행. 계획서 단계에서 파일을 옮기지 않는다 |
| N3 | `.clinerules`는 서브모듈이므로 상위 저장소와 **분리 커밋** |
| N4 | 링크 깨짐 **0건** — 이관 후 전수 대사 (`core/00-core.md:98` "깨진 참조 0건 대사" 규칙 준용) |

---

## 4. 설계 결정 (근거 포함)

### 4.1 왜 `.env`가 아니라 `project.json`인가

사용자가 `project.json`을 지정했고, 실측 근거도 이를 뒷받침한다.

| 항목 | `.env` | `project.json` |
|------|--------|----------------|
| 실제 내용 | `D:\dev\msys\.env`는 `DB_PASSWORD`, `MASTER_PASSWORD`, `TEST_USER_PASSWORD` 등 **비밀값** 보유 | 비밀 없음 |
| git 추적 | 비밀 때문에 통상 `.gitignore` 대상 → **팀/타 프로젝트 공유 불가** | 추적 가능 |
| 구조 | 평평한 key=value, 중첩 불가 | 중첩·배열 가능 (별칭, 경로 맵) |
| 파서 | 도구마다 다름 | 표준 JSON |
| 현황 | wordcloud 루트에 `.env` **없음** (실측) | 신설 |

**결론**: `project.json` 채택. `.env`는 런타임 비밀 전용으로 남긴다.

### 4.2 왜 폴더명은 폴백인가

| 근거 | 내용 |
|------|------|
| 이름 충돌 | wordcloud 루트 폴더명은 `wordcloud`지만 실제 앱 루트는 `wordcloud_project/`, 배포물은 `wordcloud-internal/`, `wordcloud-source/` — 폴더명만으로는 어느 것이 프로젝트 식별자인지 확정 불가 |
| rename 취약 | 사본 폴더(`D:\dev\wordcloud-backup` 등)를 만들면 다른 프로젝트로 오인 |
| 워크트리/서브모듈 | git worktree나 다른 경로 체크아웃 시 폴더명이 달라짐 |

**결론**: 1순위 `project.json`, 2순위 git 저장소 루트 폴더명(정규화), 둘 다 실패하면 **작업 중단 후 사용자에게 질문**(추측 금지).

### 4.3 왜 `prj-` 접두사인가

사용자 선호가 1차 근거다. 부가 근거:

| 근거 | 내용 |
|------|------|
| 문자열 검색 격리 | `grep -r "prj-"`로 프로젝트 지침 참조를 한 번에 색출 → 격리 위반 자동 검사가 단순해진다 |
| 오인 방지 | 현행 `docs/msys/`는 폴더명만 보면 "msys라는 주제 문서"인지 "msys 프로젝트 지침"인지 모호. `projects/prj-msys/`는 모호하지 않다 |
| 기존 규칙과의 충돌 해소 | `core/08-guideline-modification/04.folder-naming.md:87`은 "프로젝트 접두사는 불필요"라고 명시 — 이 조항은 **분리 폴더(나침반 하위)** 대상이고, **프로젝트 루트 폴더**와는 대상이 다르다. G2에서 두 규칙의 적용 대상을 분리 명시해 모순을 없앤다 |

### 4.4 목표 레이아웃 (요약 — 상세는 G2)

```
D:\dev\wordcloud\
├── project.json                  ← 신규. 프로젝트 식별 단일 정보원
├── CLAUDE.md                     ← 나침반 (project.json을 읽으라는 지시 포함)
└── .clinerules\                  ← 서브모듈
    ├── CLAUDE.md                 ← 저장소 안내 나침반 (msys 쪽에는 이미 존재, wordcloud엔 없음)
    ├── common\                   ← 모든 프로젝트 공통. 프로젝트명 하드코딩 금지 구역
    │   ├── core\
    │   ├── development\
    │   ├── ui\
    │   └── verification\
    ├── projects\
    │   └── prj-wordcloud\        ← 이 프로젝트 전용
    └── tools\                    ← 린터 등 (md 전용 원칙의 예외 구역)
```

`docs/cr/`(39개)는 지침이 아니라 **산출물**이므로 별도 처리 — G5에서 판정.

---

## 5. 추가 개선 사항 (R7) — 발굴 목록

| # | 항목 | 근거 | 등급 | 담당 |
|---|------|------|------|------|
| A1 | wordcloud `.clinerules`에 저장소 안내 `CLAUDE.md` 부재 | msys 쪽에는 존재(`D:\dev\msys\.clinerules\CLAUDE.md`)하나 wordcloud 쪽은 `core/`, `docs/` 두 폴더뿐 | 필수 | G2 |
| A2 | 지침 린터 부재 | 규칙은 있고 검사가 없어 §1.5처럼 72건 위반이 누적됨 | 필수 | G4 |
| A3 | 채번 대장 부재 | 번호 중복 2쌍 발생의 직접 원인 | 필수 | G3 |
| A4 | `docs/msys/` 199파일이 wordcloud 저장소에 잔존 | §1.2 | 필수 | G5 |
| A5 | `core/08-guideline-modification/04.folder-naming.md`의 예시가 **msys 경로**(`docs/msys/`)로 작성됨 | 공통 규칙 문서가 특정 프로젝트 예시를 사용 → 오염 재생산 | 권장 | G5 |
| A6 | 나침반 판정이 "이 파일은 나침반이다" 문자열에 의존 | 선언을 빠뜨리면 검사 대상에서 빠짐 → 구조(하위 폴더 보유)로 판정해야 | 권장 | G4 |
| A7 | `core/00-core.md`의 분류표에 상대경로 오류 존재 | 예: `27행`은 `docs/development/database-naming-standard.md`를 `core/` 기준 상대경로 `docs/...`로 적어 실제로는 해소되지 않음(`../docs/...`여야 함). `34·65행`도 `core/08-guideline-modification/...`으로 `core/` 중복 | 필수 | G4 (린터가 검출) |
| A8 | 계획서 규약(`plan-mode`)이 공통 규칙 안에 wordcloud 전용 경로를 담고 있음 | `core/00-core/03.plan-mode.md:12` "`wordcloud_project/plans/YYYY/MM/`" 하드코딩 → `project.json`의 `plans_root`로 치환해야 공통화 가능 | 필수 | G1+G5 |
| A9 | 지침 변경 후 절차(`03-workflow/post-guideline-change.md`)에 린터 실행 단계 없음 | A2 도입 시 연결 필요 | 권장 | G4 |
| A10 | `.claude/agents/`(11개)에도 프로젝트 전용 경로가 하드코딩되어 있을 수 있음 | wordcloud와 msys의 `.claude/agents/` 파일명이 10개 동일 — 복사 이식된 흔적. 오염 검사 범위에 포함 필요 | 권장 | G5 |
| A11 | 문서 상한 위반 72건에 대한 **일괄 처리 정책** 부재 | 전부 즉시 분해하면 리스크가 큼 → 등급별 단계 처리 필요 | 권장 | G4 |

---

## 6. 범위 밖 (Non-goals)

| 항목 | 사유 |
|------|------|
| msys 소스 코드 수정 | 지침 체계 작업이다 |
| `docs/cr/` 과거 CR 보고서 내용 수정 | 위치 재배치만 검토. 내용은 이력이므로 보존 |
| 운영자 메뉴얼 본문 재작성 | 27_01에서 이미 공용화 완료. 이번엔 **위치**만 표준에 맞춘다 |
| 지침 저장소 통합(두 origin 병합) 실행 | G6에서 **선택지와 리스크만** 제시하고 결정은 사용자 몫 |

---

## 7. 리스크

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 대규모 파일 이동으로 링크 대량 파손 | 지침 자체가 열리지 않음 | 이동 전 링크 인벤토리 작성 → 이동 → 린터 0건 확인 (G4 선행, G5 후행) |
| 서브모듈 커밋 누락으로 배포 갭 재발 | 워킹트리엔 반영, 배포엔 미반영 | `.clinerules` 분리 커밋 + 상위 포인터 갱신을 G5 완료 조건에 포함 |
| msys 저장소가 이미 자체 진화 → 정본 선정 충돌 | 이식 시 msys 쪽 변경 유실 | G6에서 두 저장소 차분(diff) 먼저 산출 후 결정 |
| 규칙만 늘고 안 지켜짐(현 상태 반복) | 표준화 실패 | 모든 신설 규칙은 **린터 검사 항목과 1:1 대응**시킨다. 검사 불가능한 규칙은 채택하지 않는다 |

---

## 8. 실행 순서와 게이트

```
G1 (project.json)  ──┐
G3 (넘버링 표준)   ──┼──> G2 (레이아웃·격리)  ──> G5 (재분류 이관) ──> G6 (타 프로젝트 롤아웃)
G4 (나침반+린터)   ──┘                              ▲
                        린터는 G5 이전에 동작해야 함 ┘
```

| 게이트 | 통과 조건 |
|--------|-----------|
| GATE-1 (G1·G3·G4 완료) | `project.json` 존재 + 린터가 현행 위반을 **검출**한다(아직 고치지 않아도 됨) |
| GATE-2 (G2 완료) | 새 레이아웃 규칙 문서 확정 + as-is→to-be 매핑표 승인 |
| GATE-3 (G5 완료) | 린터 위반 0건 + 링크 깨짐 0건 + 교차 프로젝트 참조 0건 |
| GATE-4 (G6 완료) | msys에 절차서만으로 이식 가능 (실제 이식 실행 여부는 사용자 결정) |

---

## 9. 완료 정의 (Definition of Done)

- [ ] `D:\dev\wordcloud\project.json` 존재, 스키마 문서화됨
- [ ] `.clinerules`가 `common/` + `projects/prj-*/` + `tools/`로 재편됨
- [ ] 공통 지침 파일에서 `grep -i "wordcloud\|msys"` → **0건**
- [ ] 번호 중복 0쌍, 구분자 1종
- [ ] 나침반 파일 상한 위반 0건
- [ ] 린터 실행 결과 전 항목 PASS
- [ ] 타 프로젝트 롤아웃 절차서 존재
- [ ] `.clinerules` 서브모듈 커밋 + 상위 포인터 갱신 (사용자 요청 시)

---

## 10. 확인이 필요한 결정 사항

작업 진행을 막지는 않는다. 세부 계획서는 아래 기본값으로 작성하되, 사용자가 뒤집으면 해당 계획서만 수정한다.

| # | 결정 사항 | 기본값(가정) | 영향 계획서 |
|---|-----------|--------------|-------------|
| D1 | 지침 정본 저장소 | wordcloud의 `OpenUM929/clinerules`를 정본으로, msys를 뒤따르게 함 (사용자: "wordcloud 우선") | G6 |
| D2 | `docs/msys/` 199파일 처리 | wordcloud 저장소에서 **제거**(정본은 msys 저장소). git 이력 보존 | G5 |
| D3 | `docs/cr/` 39파일 위치 | `projects/prj-wordcloud/cr/`로 이동 (지침 아닌 산출물이나 이력 가치 있음) | G5 |
| D4 | 80줄 상한 위반 72건 | 나침반 파일은 즉시 교정, 상세 문서는 등급별 단계 처리(일괄 분해 안 함) | G4 |
| D5 | 린터 실행 언어 | Python (프로젝트 표준 스택) | G4 |

---

## 11. 참조

| 문서 | 경로 |
|------|------|
| 선행 오염 제거 계획 | `wordcloud_project/plans/2026/07/23_01_clinerules-msys-decontaminate/23_01_clinerules-msys-decontaminate.md` |
| 메뉴얼 공용화 계획 | `wordcloud_project/plans/2026/07/27_01_manual-guide-common/` |
| 현행 공통 나침반 | `.clinerules/core/00-core.md` |
| 현행 나침반 규칙 | `.clinerules/core/10.project-compass.md`, `.clinerules/core/10-project-compass/04_split_rule.md` |
| 현행 폴더 명칭 규칙 | `.clinerules/core/08-guideline-modification/04.folder-naming.md` |
| 현행 문서 분리 기준 | `.clinerules/core/08-guideline-modification/03.document-separation.md` |
| msys 참조 레이아웃 | `D:\dev\msys\.clinerules\CLAUDE.md` |

---

## 실행 로그 (2026-07-28)

PRD 역할 완료. G1~G5 실행 완료, G6 는 절차서만 작성(msys 마이그레이션 미실행).

### 계획 대비 변경된 결정

| PRD 항목 | 계획 | 실제 | 사유 |
|----------|------|------|------|
| 프로젝트 폴더명 | `projects/prj-<id>` | **`projects/<id>`** | 사용자 지시(2026-07-28): "projects 폴더 안에 있으면 prj 접두사 불필요" |
| D2 `docs/msys` 199파일 | 삭제 | **`outputs/_transfer-msys/` 격리 보관** | 삭제 게이트 FAIL — 아래 참조 |
| NUM-3 번호 필수 범위 | 전 구역 | **`common/core/` 만 필수, 사전형 폴더는 선택** | 전 구역 강제 시 링크 파손 위험 대비 실익 없음 |
| C2 상한 | 80줄 하드 | **80 경고 / 160 하드** | 실측 위반 72건으로 80 하드는 이미 사문화 |

### 삭제 게이트 결과 (D2)

`docs/msys`(199) vs `D:\dev\msys\.clinerules\projects\msys`(246) 대사:

| 항목 | 값 |
|------|-----|
| wordcloud 에만 있는 파일 | **30** (탭 분리본 10, data-flow 다이어그램 12, `gen_flow_diagrams.py`, 통합빌드 산출물, `msys-specifics.md` 등) |
| 양쪽 공통 | 169 |
| 그중 내용 상이(줄바꿈 정규화 후) | **49** |
| msys 저장소의 `common/`+`projects/` 재편 | **미커밋 워킹트리 상태** (`git ls-files projects` → 0건) |

→ 삭제 시 유실이 확정적이므로 **삭제 금지**. 격리 후 msys 이관은 G6 별도 승인 작업으로 이월.
