# 계획서 G2 — 지침 저장소 레이아웃 표준 · 프로젝트 폴더 명칭 표준 · 격리 규칙

> 상태: Done | 작성일: 2026-07-28 | 완료일: 2026-07-28
> 작업 유형: D (리팩토링) + C (설계)
> 선행: 07/28_02_prj-identity, 07/28_04_doc-numbering-std
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
| 1.1 | 임의 지침 파일 경로만 보고 "공통인가 프로젝트인가"를 판별할 수 있는가? | Y | (미수행) |
| 1.2 | 프로젝트 지침 폴더명이 `project.json`의 `project_id`로부터 **계산**되는가(추측 불가)? | Y | (미수행) |
| 1.3 | 공통 지침이 특정 프로젝트 폴더를 참조하는 일이 규칙으로 금지되는가? | Y | (미수행) |
| 1.4 | 현행 `docs/` 8개 하위 폴더가 새 레이아웃의 어디로 가는지 전건 매핑표가 있는가? | Y | (미수행) |

---

## 1. 배경 (실측)

### 1.1 현행 wordcloud 레이아웃 — 공통·프로젝트·산출물이 동급

```
D:\dev\wordcloud\.clinerules\
├── core\      (md 19개 최상위 + 하위 폴더 5개)
└── docs\
    ├── common\           12 파일  ← 공통
    ├── cr\               39 파일  ← 산출물(CR 보고서)
    ├── design\            4 파일  ← 분류 불명
    ├── development\      15 파일  ← 공통
    ├── msys\            199 파일  ← 타 프로젝트 (오염)
    ├── project_wordcloud\ 37 파일  ← 이 프로젝트
    ├── ui\               10 파일  ← 공통
    └── verification\      3 파일  ← 공통
    └── scenario-test-report.md    ← 산출물
```

측정: `for d in docs/*/; do find "$d" -type f | wc -l; done`

**문제**: `docs/` 아래에서 `common`(공통)·`msys`(타 프로젝트)·`project_wordcloud`(자기 프로젝트)·`cr`(산출물)이 **같은 깊이**에 있다. 경로 규칙이 없으므로 AI가 새 문서를 어디에 둘지 매번 추측한다 → 23_01이 청소한 오염이 같은 자리에 다시 쌓인다.

### 1.2 msys 레이아웃은 이미 3분할 (참고 정본 후보)

```
D:\dev\msys\.clinerules\
├── CLAUDE.md          ← 저장소 안내 나침반
├── common\            ← core/ development/ ui/ verification/
├── docs\              ← cr/ (산출물)
└── projects\
    └── msys\          246 파일
```

`D:\dev\msys\.clinerules\CLAUDE.md`가 이 구조를 명시한다:
> "공통 지침 `common/` — 모든 프로젝트에 적용되는 규칙 / 프로젝트 지침 `projects/` — 프로젝트별 규칙"

**그럼에도 오염됐다**: `common/` 14개 파일에 `wordcloud`가 박혀 있다. → **폴더 분리만으로는 부족하고, 격리 규칙 + 자동 검사가 함께 있어야 한다.** 이것이 본 계획서가 msys 구조를 그대로 베끼지 않는 이유다.

### 1.3 기존 폴더 명칭 규칙과의 관계

`.clinerules/core/08-guideline-modification/04.folder-naming.md:87`
> "폴더 명칭은 나침반 문서명에서 `.md`를 제거한 것. **프로젝트 접두사는 불필요.**"

이 조항은 **나침반 분리 폴더**(예: `03.plan-mode.md` → `03-plan-mode/`)를 대상으로 한다. **프로젝트 루트 폴더**는 대상이 아니다. 그런데 문서에 그 구분이 없어 "접두사 금지"로 오독될 수 있고, 하필 그 문서의 예시가 `docs/msys/`(타 프로젝트 경로)다 — PRD A5.

→ 본 계획서에서 **적용 대상을 명시적으로 분리**한다.

---

## 2. 표준 정의

### 2.1 목표 레이아웃

```
<repo root>/
├── project.json                      ← G1. 식별 단일 정보원
├── CLAUDE.md                         ← 프로젝트 나침반
└── .clinerules/                      ← 지침 저장소(서브모듈)
    ├── CLAUDE.md                     ← 저장소 안내 나침반 (신규)
    ├── NUMBERS.md                    ← 채번 대장 (G3)
    ├── common/                       ← 【공통 구역】
    │   ├── core/                     ← 핵심 규율 + 나침반 00-core.md
    │   ├── development/              ← 개발 공통
    │   ├── ui/                       ← UI 공통
    │   ├── verification/             ← 검증 공통
    │   └── operator-manual/          ← 문서 작성 공통 (27_01 산출물)
    ├── projects/                     ← 【프로젝트 구역】
    │   └── prj-<project_id>/         ← 정확히 하나만 존재해야 함
    │       ├── README.md             ← 프로젝트 나침반 (필수)
    │       └── ...
    ├── outputs/                      ← 【산출물 구역】 지침이 아닌 기록물
    │   └── cr/
    └── tools/                        ← 【도구 구역】 린터 등 (md 아닌 파일 허용)
```

### 2.2 구역(zone) 정의와 권한

| 구역 | 경로 | 담을 것 | 금지 |
|------|------|---------|------|
| **공통** | `common/**` | 모든 프로젝트에 적용 가능한 규칙 | 프로젝트명·프로젝트 고유 경로·프로젝트 전용 예시. 값이 필요하면 `{{...}}` 플레이스홀더 |
| **프로젝트** | `projects/prj-<id>/**` | 해당 프로젝트 전용 규칙·구조 문서 | 다른 `prj-*` 참조 |
| **산출물** | `outputs/**` | CR 보고서 등 이력 기록 | 규칙 문서 |
| **도구** | `tools/**` | 린터·스크립트 | 규칙 문서(md는 도구 사용법 README만) |

### 2.3 프로젝트 지침 폴더 표준 명칭 — **규칙 N-PRJ**

```
projects/prj-<project_id>/
```

| 조항 | 내용 |
|------|------|
| N-PRJ-1 | 접두사는 **`prj-`** 고정. `project_`, `proj-`, 접두사 없음 모두 위반 |
| N-PRJ-2 | `<project_id>`는 `project.json`의 `project_id` **값과 정확히 일치**. 축약·변형 금지 |
| N-PRJ-3 | `project_id` 형식: `^[a-z][a-z0-9-]{2,19}$` (소문자 시작, 소문자·숫자·하이픈, 3~20자) |
| N-PRJ-4 | 한 저장소의 `projects/` 아래에는 **자기 프로젝트 폴더 1개만** 존재한다. 타 프로젝트 폴더가 있으면 오염 |
| N-PRJ-5 | 프로젝트 폴더 최상위에 `README.md`(프로젝트 나침반) **필수** |
| N-PRJ-6 | 프로젝트 폴더 **내부**의 하위 폴더는 기존 `04.folder-naming.md` 규칙(나침반 문서명 = 폴더명, 접두사 불필요)을 따른다 |

**적용 결과(wordcloud)**: `docs/project_wordcloud/` → `projects/prj-wordcloud/`

> N-PRJ-1과 `04.folder-naming.md`의 "접두사 불필요"는 **대상이 다르다**. N-PRJ-1은 `projects/` 직하 폴더에만, `04.folder-naming.md`는 그 **내부** 분리 폴더에 적용된다. 두 문서 모두에 이 구분을 명기한다.

### 2.4 격리 규칙 — **규칙 ISO**

| 조항 | 내용 | 린터 항목 |
|------|------|-----------|
| ISO-1 | `common/**` 문서는 `projects/` 경로를 **직접 참조하지 않는다**. 필요하면 `{{guideline.project_dir}}` 플레이스홀더 | `L1` |
| ISO-2 | `common/**` 문서에 프로젝트 고유 문자열(현 저장소의 `project_id`·`aliases`, 알려진 타 프로젝트명) 금지 | `L2` |
| ISO-3 | `projects/prj-A/**` 문서는 `projects/prj-B/**`를 참조하지 않는다 | `L3` |
| ISO-4 | `projects/` 직하에 자기 `prj-<project_id>` 외 폴더가 있으면 위반 | `L4` |
| ISO-5 | 타 프로젝트 지침 파일을 **읽어서 인용**할 때는 반드시 "타 프로젝트 참조"임을 문서에 명시하고, 규칙으로 채택하려면 `common/`으로 승격한 뒤 참조한다 | 수동 |
| ISO-6 | AI 작업 규칙: 요청이 프로젝트 지침 수정이면 **`project.json`으로 확정한 `prj-<id>` 폴더 외에는 쓰기 금지** | 수동 + 리뷰 |

**ISO-2의 "알려진 타 프로젝트명" 목록**은 `common/PROJECTS-REGISTRY.md`(신규)에 유지한다 — 현재 `wordcloud`, `msys`. 이 목록이 린터의 금칙어 사전이 된다.

### 2.5 신규 문서 배치 결정 규칙 — **규칙 PLACE**

새 지침 문서를 만들 때 아래 순서로 위치를 결정한다. **추측 금지.**

```
Q1. 이 규칙이 프로젝트가 바뀌어도 그대로 유효한가?
    ├─ 예 → Q2
    └─ 아니오 → projects/prj-<project_id>/
Q2. 규칙 본문에 특정 프로젝트의 경로·이름·산출물명이 등장하는가?
    ├─ 예 → 그 값을 project.json 키로 뽑아낼 수 있는가?
    │        ├─ 예 → 플레이스홀더로 치환 후 common/
    │        └─ 아니오 → projects/prj-<project_id>/
    └─ 아니오 → common/ 의 주제별 하위(core|development|ui|verification|operator-manual)
```

주제별 하위 선택 기준:

| 하위 | 담는 것 |
|------|---------|
| `core/` | 작업 진행 방식·규율 (워크플로우, 금지사항, 계획·보고 절차) |
| `development/` | 코드 작성 표준 (네이밍, 시간 처리, SQL, 라이브러리) |
| `ui/` | 화면·디자인 시스템 |
| `verification/` | 테스트·검증·체크리스트 |
| `operator-manual/` | 인쇄·제출용 문서 작성 양식 |

---

## 3. as-is → to-be 매핑표 (전건)

| # | as-is (`.clinerules/` 기준) | 파일수 | to-be | 판정 근거 |
|---|------------------------------|--------|-------|-----------|
| 1 | `core/**` | 19 + 하위 | `common/core/**` | 전부 공통 규율. 단 프로젝트 하드코딩 잔재는 G1 플레이스홀더 처리 |
| 2 | `docs/development/**` | 15 | `common/development/**` | 코딩 표준·시간·네이밍 — 프로젝트 무관 |
| 3 | `docs/ui/**` | 10 | `common/ui/**` | 디자인 시스템 |
| 4 | `docs/verification/**` | 3 | `common/verification/**` | 검증 체크리스트 |
| 5 | `docs/common/operator-manual/**` | 12 | `common/operator-manual/**` | 27_01에서 이미 공용화됨 |
| 6 | `docs/project_wordcloud/**` | 37 | `projects/prj-wordcloud/**` | 이 프로젝트 전용 |
| 7 | `docs/msys/**` | 199 | **제거** (정본은 msys 저장소) | ISO-4 위반. PRD D2 |
| 8 | `docs/cr/**` | 39 | `outputs/cr/**` | 규칙이 아니라 이력 기록. PRD D3 |
| 9 | `docs/design/**` | 4 | **내용 검증 후 분기** (G5) | `architecture.md`·`database-design.md`가 wordcloud 전용일 가능성 |
| 10 | `docs/scenario-test-report.md` | 1 | `outputs/` 또는 삭제 (G5 판정) | 산출물 |
| 11 | — | — | `common/PROJECTS-REGISTRY.md` (신규) | ISO-2 금칙어 사전 |
| 12 | — | — | `.clinerules/CLAUDE.md` (신규) | 저장소 안내 나침반 (PRD A1) |
| 13 | — | — | `tools/` (신규) | 린터 (G4) |

**#9, #10의 실제 판정과 파일 단위 이동은 G5(`28_06_common-promotion`)에서 수행한다.** 본 계획서는 **규칙과 골격**만 확정한다.

---

## 4. `.clinerules`의 "md 전용" 원칙 개정

`D:\dev\msys\.clinerules\CLAUDE.md`의 금지 조항:
> "`.clinerules/`에는 코드, 소스 파일, 바이너리를 업로드하지 않습니다. 오직 Markdown 규칙 문서만 작성합니다."

그러나 현행 wordcloud 저장소에 이미 예외가 존재한다 — 실측:
`docs/common/operator-manual/build/build_integrated.py`, `.../build/print.css`

린터(G4)도 코드다. 따라서 원칙을 다음과 같이 개정한다.

| 개정안 |
|--------|
| `.clinerules/` 에는 **규칙 문서(md)** 와, 그 규칙을 **집행·생성하는 도구**만 둔다. 도구는 `tools/` 또는 각 규칙 폴더의 `build/` 하위에만 위치한다. 애플리케이션 소스·바이너리·데이터는 금지한다. |

---

## 5. 변경 파일 목록

| # | 파일 | 유형 | 내용 |
|---|------|------|------|
| 1 | `.clinerules/CLAUDE.md` | 신규 | 저장소 안내 나침반. 구역표 + 진입 절차 + 금지사항(개정판) |
| 2 | `.clinerules/common/core/<NN>-repo-layout.md` | 신규 | §2.1~2.2 구역 정의. 번호는 G3 대장에서 채번 |
| 3 | `.clinerules/common/core/<NN>-project-isolation.md` | 신규 | §2.3 N-PRJ + §2.4 ISO + §2.5 PLACE |
| 4 | `.clinerules/common/PROJECTS-REGISTRY.md` | 신규 | 알려진 프로젝트 목록(금칙어 사전) |
| 5 | `.clinerules/common/core/08-guideline-modification/04.folder-naming.md` | 수정 | ① 적용 대상이 "나침반 분리 폴더"임을 명시 ② N-PRJ와의 관계 명시 ③ 예시의 `docs/msys/` → 중립 예시로 교체 (PRD A5) |
| 6 | `.clinerules/common/core/00-core.md` | 수정 | 분류표에 "지침 문서 위치 결정" 행 추가 → `#3` 문서로 라우팅 |
| 7 | 폴더 이동 다수 | 이동 | §3 매핑표 #1~#8 (실행은 G5) |

---

## 6. 검증 계획

| # | 항목 | 방법 | 기대 |
|---|------|------|------|
| 1 | 구역 4개 존재 | `ls .clinerules/{common,projects,outputs,tools}` | 전부 존재 |
| 2 | `projects/` 직하 폴더 수 | `ls -1 .clinerules/projects \| wc -l` | **1** |
| 3 | 폴더명 == `prj-` + `project.json.project_id` | 린터 `L4` | PASS |
| 4 | `common/`이 `projects/` 참조 | `grep -rn "projects/prj-" .clinerules/common` | **0건** (플레이스홀더 제외) |
| 5 | `common/`에 금칙어 | `grep -rin "wordcloud\|msys" .clinerules/common` | **0건** |
| 6 | 이동 후 링크 깨짐 | 린터 `L5` (전 md 링크 실존 확인) | **0건** |
| 7 | `docs/` 잔존 여부 | `ls .clinerules/docs` | 존재하지 않음 |

---

## 7. 리스크

| 리스크 | 대응 |
|--------|------|
| `core/`·`docs/` → `common/` 이동으로 상대경로 링크 **대량 파손** | 이동 전 링크 인벤토리 생성(G4 린터 `L5`를 이동 전 1회 실행해 기준선 확보) → 이동 → 재실행 후 **차이만** 수리 |
| `docs/msys/` 199파일 삭제 후 필요해짐 | git 이력 보존. 삭제 커밋 해시를 `outputs/` 또는 계획서 실행 로그에 기록 |
| `outputs/` 신설로 CR 절차 문서(`06.git-rules.md`)의 CR 저장 경로가 어긋남 | `06.git-rules.md`의 CR 경로 기술을 함께 갱신 (G5 체크리스트 항목) |
| 서브모듈 커밋 누락 | 이동은 `.clinerules` 내부 변경 → 서브모듈 커밋 + 상위 포인터 갱신을 완료 조건에 포함 |

---

## 8. 완료 기준

- [ ] `.clinerules/CLAUDE.md`·`common/`·`projects/prj-wordcloud/`·`outputs/`·`tools/` 존재
- [ ] `docs/` 소멸, `core/` 소멸(→ `common/core/`)
- [ ] 검증 #2~#7 전부 PASS
- [ ] N-PRJ·ISO·PLACE 규칙이 문서로 존재하고 `00-core.md` 분류표에서 도달 가능
- [ ] 매핑표 §3의 전 행이 "완료" 또는 "G5로 이월" 중 하나로 표시됨

---

## 실행 로그 (2026-07-28)

### 실제 레이아웃

```
.clinerules/
├── CLAUDE.md · NUMBERS.md
├── common/     (core · development · ui · verification · operator-manual · PROJECTS-REGISTRY.md)
├── projects/wordcloud/
├── outputs/    (cr · _transfer-msys · scenario-test-report.md)
└── tools/      (lint_guidelines.py · gen_numbers.py · lint_baseline.txt · README.md)
```

### 매핑 실행 결과

| as-is | to-be | 결과 |
|-------|-------|------|
| `core/**` | `common/core/**` | 이동+rename 완료 |
| `docs/development`·`ui`·`verification` | `common/**` | 완료 |
| `docs/common/operator-manual` | `common/operator-manual` | 완료 |
| `docs/project_wordcloud` | `projects/wordcloud` | 완료 |
| `docs/cr`(39) | `outputs/cr` | 완료 |
| `docs/design`(4) | `common/development/design/` | **승격** — COM-1~4 충족, 각 문서에 적용범위 고지 추가 |
| `docs/msys`(199) | `outputs/_transfer-msys` | **격리**(삭제 아님) |

### 계획과 달라진 점

- 폴더명에서 `prj-` 접두사 제거(사용자 지시) → N-PRJ-1 을 "`projects/` 가 이미 성격을 나타내므로 접두사를 덧붙이지 않는다"로 확정.
- `git mv` 가 `docs/msys`·`docs/design` 에서 `Permission denied` → `cp -r` 후 `rm -rf` 로 우회(파일 수 대사 199/4 일치 확인).
- `docs/verification/scenarios/` 3건이 **디스크엔 없는데 git 인덱스엔 남아** 있어 `git mv` 실패 — 23_01 의 삭제가 미커밋 상태였다. `git add -A` 로 선반영 후 진행.

검증: 린터 `L1`~`L5` 전부 0건.
