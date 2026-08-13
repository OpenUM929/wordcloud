# 계획서 G4 — 나침반(Compass) 규약 정밀화 및 지침 린터 도입

> 상태: Done | 작성일: 2026-07-28 | 완료일: 2026-07-28
> 작업 유형: B (기능 개선 — 신규 도구) + C (설계)
> 선행: 07/28_01_guideline-std-prd
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
| 1.1 | 현행 지침에 "80줄 초과 시 분리" 규칙이 문서로 존재하는가? | Y | (미수행) |
| 1.2 | 그 규칙을 위반하는 파일이 실제로 존재하는가? 몇 개인가? | Y, 72개 | (미수행) |
| 1.3 | 하위 폴더로 분리하고도 본문이 그대로인 파일이 존재하는가? | Y | (미수행) |
| 1.4 | 위반을 자동 검출하는 장치가 존재하는가? | N | (미수행) |
| 2.1 | 나침반 판정이 문서 내 선언 문자열이 아니라 **구조**로 되는가? | Y | (미수행) |
| 2.2 | 린터가 위반을 파일:라인 단위로 출력하는가? | Y | (미수행) |

---

## 1. 배경 — 규칙은 있고 집행이 없다

### 1.1 현행 규칙 (원문)

`.clinerules/core/10.project-compass.md:27-29`
> - **나침반 문서**: 80줄 초과 시 해당 주제를 폴더로 분리하고 경로만 나열
> - **상세 문서**: 80줄 이하, 실제 역할·파일 설명·체크리스트 포함
> - **규칙**: 80줄 초과 → 즉시 폴더 생성 후 내용 재분류

`.clinerules/core/08-guideline-modification/03.document-separation.md:3-6`
> 문서 분리 기준 (80줄 초과 시 → 주제 응집성 기준으로 판단)
> 단순히 줄 수가 80줄을 넘는다고 분리하지 않는다. **같은 파일에 서로 다른 작업 유형의 규칙이 혼재**할 때 분리를 고려한다.

→ **두 문서가 서로 다른 말을 한다.** 하나는 "80줄 초과 = 즉시 분리", 하나는 "80줄은 트리거일 뿐, 주제 혼재가 기준". 이 모순이 "잘 안 지켜진다"의 1차 원인이다. 어느 쪽을 따라도 정당화되기 때문이다.

### 1.2 위반 실측 (2026-07-28)

| 범위 | 80줄 초과 파일 수 |
|------|------------------|
| `.clinerules/core/` + `.clinerules/docs/` 전체 | **72** |
| `.clinerules/core/` 만 | **17** |

측정: `find core docs -name "*.md" -exec wc -l {} \; | awk '$1>80' | wc -l`

최악 사례:

| 파일 | 줄수 |
|------|------|
| `core/06.git-rules.md` | 519 |
| `core/02.hallucination-prevention.md` | 287 |
| `core/15.schedule-rules.md` | 266 |
| `core/00-core/03.plan-mode.md` | 222 |
| `core/10-project-compass/03_templates.md` | 190 |
| `core/00-core.md` | 114 ← **나침반 자신이 위반** |

### 1.3 "분리했는데 축소가 안 된" 결정적 사례

`core/00-core/03.plan-mode.md`는 하위 폴더 `03-plan-mode/`(README + type-a~type-f, 7파일)를 **이미 보유**한다. 그런데 본문은 **222줄**이며 16개 항목의 상세 규칙을 그대로 담고 있다.

즉 **폴더는 만들었으나 내용을 옮기지 않았다.** 분리 작업의 "후반부"(나침반 축소)가 빠진 것이다. `03.document-separation.md:15`가 "기존 문서는 나침반 역할로 유지(내용 삭제, 참조 경로 추가)"라고 명시하는데도 그렇다.

### 1.4 나침반 판정 방식의 결함

현재 나침반은 문서에 `> ⚠️ **이 파일은 나침반이다**` 문장이 있는지로만 식별된다. 실측 결과 그 선언을 가진 파일은 **5개뿐**이다:

```
core/00-core.md
core/08.guideline-modification.md
core/10.project-compass.md
docs/common/operator-manual/DEVELOPMENT.md
docs/ui/common/layout-and-components.md
```

그러나 **구조적으로 나침반인 파일**(동명 하위 폴더를 가진 파일)은 더 많다: `core/03.workflow.md`(→`03-workflow/`), `core/04.design-change.md`(→`04-design-change/`), `core/00-core/03.plan-mode.md`(→`03-plan-mode/`). 이들은 선언이 없어 **검사 대상에서 빠진다.** → PRD A6.

### 1.5 부수 발견 — 나침반의 링크가 실제로 깨져 있다

`core/00-core.md` 실측:

| 행 | 링크 | 문제 |
|----|------|------|
| 27 | `[database-naming-standard.md](docs/development/database-naming-standard.md)` | `core/` 기준 상대경로가 `docs/...` → 실제로는 `../docs/...` 여야 해소됨 |
| 34 | `[08.guideline-modification.md](core/08-guideline-modification/01.plan-mode.md)` | `core/`가 중복 (이미 `core/` 안에 있음) |
| 65 | 위와 동일 | 동일 |

→ **나침반이 가리키는 곳으로 갈 수 없다.** 나침반 규약이 무의미해지는 가장 직접적인 형태의 위반이며, 지금까지 아무도 검출하지 못했다. PRD A7.

---

## 2. 규약 정밀화 — 규칙 CMP

### CMP-1. 나침반 판정 (구조 기반)

다음 중 **하나라도** 해당하면 그 파일은 나침반이다. 선언문 유무와 무관하다.

| 조건 | 예 |
|------|-----|
| 동명 하위 폴더가 존재한다 (`X.md` + `X/`) | `03-workflow.md` + `03-workflow/` |
| 파일명이 `00-*.md` 이다 | `common/core/00-core.md` |
| 파일명이 `README.md` 이고 하위에 형제 md가 2개 이상 있다 | `03-workflow/README.md` |
| 저장소/프로젝트 진입점이다 (`CLAUDE.md`, `projects/prj-*/README.md`) | `projects/prj-wordcloud/README.md` |

나침반 파일은 상단에 다음 배지를 **필수**로 둔다(선언은 판정 근거가 아니라 독자 안내용):

```markdown
> 🧭 **나침반 문서** — 내용을 담지 않고 위치만 가리킨다. 상세는 아래 표의 경로에 있다.
```

### CMP-2. 상한 (모순 해소)

`10.project-compass.md`와 `03.document-separation.md`의 충돌을 다음으로 확정한다.

| 문서 종류 | 상한 | 초과 시 |
|-----------|------|---------|
| **나침반** | **60줄** (하드) | **즉시 위반**. 예외 없음. 내용을 하위 문서로 내린다 |
| **상세 문서** | 80줄 (소프트) → 160줄 (하드) | 80~160: 경고. **주제 혼재가 있으면** 분리(기존 `03.document-separation.md` 기준 적용). 160 초과: 위반, 분리 필수 |

**근거**:
- 나침반을 80이 아니라 60으로 낮추는 이유 — 현행 `00-core.md`가 114줄인데 그 내용의 대부분이 표 2개(분류표 27행 + 문서위치표 25행)다. 표만으로 60줄 안에 들어가려면 항목당 1행을 지켜야 하며, 이는 "설명을 쓰지 말고 가리키기만 하라"는 원칙을 물리적으로 강제한다.
- 상세 문서에 160줄 하드 상한을 두는 이유 — 80줄 하드는 실측상 **72건이 위반**이라 현실성이 없어 지금까지 무시되어 왔다. 지켜지지 않는 규칙은 규칙이 아니다. 80을 경고로 낮추고 160을 넘는 것만 강제 위반으로 삼으면 위반 건수가 관리 가능한 규모로 줄고(§3.2 등급표), 그 결과 규칙이 실제로 집행된다.

### CMP-3. 나침반 콘텐츠 규칙

나침반에 **허용**되는 것:

| 허용 | 예 |
|------|-----|
| 제목, 배지(CMP-1) | |
| 트리거 목록 (언제 이 문서군을 여는가) | 최대 10줄 |
| 라우팅 표 (`작업 유형 → 경로`) | 본체 |
| 하위 문서 목록 표 | |

나침반에 **금지**되는 것:

| 금지 | 사유 |
|------|------|
| 절차 서술 (1. 2. 3. 단계) | 상세 문서의 몫 |
| 코드 블록 | 상세 문서의 몫 |
| 체크리스트 | 상세 문서의 몫 |
| 예시/시나리오 | 상세 문서의 몫 |
| 경고·교훈 서술 문단 | 상세 문서의 몫 |

> 현행 `core/00-core.md:88-110`("자산·경로 참조도 동일하게 검증한다" + bash 코드블록 + 실제 발생 사례)은 CMP-3 위반이다. 이 내용은 `common/core/17-hallucination-prevention.md`(G3 신규 번호)로 이관한다.

### CMP-4. 분리 작업의 **완료 조건**

문서를 분리할 때 다음 4단계를 **모두** 마쳐야 완료다. 3·4를 빠뜨린 것이 §1.3의 원인이다.

1. 하위 폴더 생성 (이름 = 나침반 파일명에서 `.md` 제거)
2. 내용을 주제별 파일로 이동
3. **원본에서 이동한 내용을 삭제**하고 라우팅 표로 대체 ← 누락 빈번
4. **원본이 CMP-2 상한(60줄) 이하임을 확인** ← 누락 빈번

### CMP-5. 링크 규칙

| 조항 | 내용 |
|------|------|
| CMP-5-1 | 지침 문서 내 상대 링크는 **해당 문서 위치 기준**으로 해소 가능해야 한다 |
| CMP-5-2 | 저장소 루트 기준 경로를 쓰고 싶으면 상대경로 대신 **백틱 코드 표기**로 적고 링크를 걸지 않는다 (해소 불가 링크 방지) |
| CMP-5-3 | 존재하지 않는 문서로의 링크 금지 (기존 `00-core.md:83-86` 유지) |

---

## 3. 린터 설계 — `tools/lint_guidelines.py`

### 3.1 위치와 실행

| 항목 | 값 |
|------|-----|
| 파일 | `.clinerules/tools/lint_guidelines.py` |
| 언어 | Python 3 (PRD D5) |
| 의존성 | 표준 라이브러리만 (`pathlib`, `json`, `re`, `argparse`) — 내부망 실행 가능해야 함 |
| 실행 | `python .clinerules/tools/lint_guidelines.py` (저장소 루트에서) |
| 옵션 | `--zone common\|projects\|all`, `--severity error\|warn\|all`, `--json`, `--baseline <file>` |
| 종료 코드 | 위반(error) 1건 이상 → `1`, 없으면 `0` |

`.clinerules`를 "md 전용"으로 규정한 기존 문구는 G2 §4에서 개정한다(도구 구역 허용).

### 3.2 검사 항목 (전체)

`P`=project.json, `L`=layout/isolation, `N`=numbering, `C`=compass, `K`=link.

| ID | 검사 | 근거 규칙 | 심각도 |
|----|------|-----------|--------|
| `P1` | `project.json` 존재 + JSON 파싱 + `project_id` 정규식 | G1 §2.2 | error |
| `P2` | `guideline.project_dir` == `projects/prj-<project_id>` | G1/G2 N-PRJ-2 | error |
| `P3` | `paths.*` 값이 실제 존재 | G1 §5-4 | warn |
| `P4` | 문서의 `{{...}}` 플레이스홀더가 스키마에 정의된 키만 사용 | G1 §2.4 | error |
| `P5` | 플레이스홀더 병기값이 `project.json` 해소값과 일치 | G1 §6 | warn |
| `L1` | `common/**`이 `projects/` 경로를 직접 참조하지 않음 | ISO-1 | error |
| `L2` | `common/**`에 `PROJECTS-REGISTRY.md` 등록 프로젝트명 문자열 없음 | ISO-2 | error |
| `L3` | `projects/prj-A/**`가 `prj-B`를 참조하지 않음 | ISO-3 | error |
| `L4` | `projects/` 직하 폴더가 자기 프로젝트 1개뿐 | ISO-4 | error |
| `L5` | 구역(zone) 4개 존재, 정의되지 않은 최상위 폴더 없음 | G2 §2.2 | error |
| `N1` | 폴더별 `NN` 중복 없음 | NUM-7 | error |
| `N2` | 무번호 파일이 NUM-3 예외 목록에만 존재 | NUM-3 | warn |
| `N3` | 파일 시스템 ↔ `NUMBERS.md` 대사 (양방향 누락) | NUM-5 | error |
| `N4` | 파일명 형식 `NN-<slug>.md`, slug ≤ 30자, 구분자 하이픈 | NUM-1 | error |
| `N5` | 나침반 파일명 == 하위 폴더명 | NUM-2 | error |
| `C1` | 나침반(CMP-1 판정) 줄수 ≤ 60 | CMP-2 | error |
| `C2` | 상세 문서 줄수 ≤ 160 (80 초과는 warn) | CMP-2 | error/warn |
| `C3` | 나침반에 금지 콘텐츠(코드블록·번호 절차·체크리스트) 없음 | CMP-3 | error |
| `C4` | 나침반에 배지 존재 | CMP-1 | warn |
| `C5` | 하위 폴더를 가진 파일이 라우팅 표를 보유 | CMP-4-3 | error |
| `K1` | 상대 링크가 실제 파일로 해소됨 | CMP-5-1/5-3 | error |
| `K2` | 이미지·자산 참조 실존 | 기존 `00-core.md:88-98` | error |

### 3.3 출력 형식

```
D:\dev\wordcloud\.clinerules\common\core\00-core.md:27  [K1] error  링크 해소 실패: docs/development/database-naming-standard.md
D:\dev\wordcloud\.clinerules\common\core\00-core.md:1   [C1] error  나침반 60줄 초과 (114줄)
...
요약: error 34 / warn 51  (검사 파일 268)
```

`file:line` 형식을 지켜 편집기에서 클릭 이동이 되게 한다.

### 3.4 baseline 모드

기존 위반 72건을 한 번에 못 고치므로, `--baseline` 파일에 **현재 위반 목록**을 기록해 두고 그 이후 **새로 생긴 위반만** 실패로 처리한다. baseline은 줄여 나가되 절대 늘리지 않는다.

| 파일 | `.clinerules/tools/lint_baseline.txt` |
|------|---------------------------------------|

---

## 4. 기존 72건 위반 처리 정책 (PRD A11 / D4)

| 등급 | 대상 | 조치 | 시점 |
|------|------|------|------|
| 즉시 | 나침반 판정 파일 중 60줄 초과 | 본문 하향 이관 | G4 내 |
| 즉시 | `K1`/`K2` 깨진 링크 전건 | 수리 | G4 내 |
| 1차 | 상세 문서 160줄 초과 | 분리 (CMP-4 4단계 준수) | G5와 병행 |
| 2차 | 상세 문서 80~160줄 | baseline에 등재, 해당 문서를 다음에 손댈 때 분리 | 상시 |

**즉시 대상 확정 목록(실측)** — 나침반 판정 + 60줄 초과:

| 파일 | 줄수 | 판정 근거 |
|------|------|-----------|
| `core/00-core.md` | 114 | `00-*` |
| `core/00-core/03.plan-mode.md` | 222 | 동명 폴더 `03-plan-mode/` 보유 |
| `core/10.project-compass.md` | 61 | 동명 폴더 + 선언 |
| `core/03-workflow/README.md` | 64 | README + 형제 6개 |

> `core/03.workflow.md`·`core/04.design-change.md`·`core/08.guideline-modification.md`는 동명 폴더를 가지나 60줄 이하로 확인됨(실측 상위 30 목록에 부재) — **실행 시 `wc -l`로 재확인**한 뒤 판정한다.

---

## 5. 변경 파일 목록

| # | 파일 | 유형 |
|---|------|------|
| 1 | `.clinerules/tools/lint_guidelines.py` | 신규 |
| 2 | `.clinerules/tools/lint_baseline.txt` | 신규 |
| 3 | `.clinerules/tools/README.md` | 신규 (사용법) |
| 4 | `.clinerules/common/core/23-compass-rule.md` | 신규 (CMP-1~CMP-5 정본) |
| 5 | `.clinerules/common/core/10-project-compass.md` | 수정 (80줄 조항 → CMP-2 참조로 교체, 모순 제거) |
| 6 | `.clinerules/common/core/08-guideline-modification/03-document-separation.md` | 수정 (CMP-4 완료 조건 4단계 추가) |
| 7 | `.clinerules/common/core/00-core.md` | 수정 (60줄로 축소, §1.5 링크 3건 수리, `:88-110` 이관) |
| 8 | `.clinerules/common/core/00-core/03-plan-mode.md` | 수정 (222줄 → 라우팅 표로 축소, 본문을 `03-plan-mode/` 하위로 이관) |
| 9 | `.clinerules/common/core/03-workflow/README.md` | 수정 (60줄 이하) |
| 10 | `.clinerules/common/core/03-workflow/06-post-guideline-change.md` | 수정 (린터 실행 단계 추가 — PRD A9) |

> #8의 이관 대상은 현행 `03.plan-mode.md`의 16개 항목이다. 기존 `03-plan-mode/` 하위는 작업 유형별(type-a~f) 구성이므로, 절차 항목은 **새 하위 파일**(예: `10-storage-naming.md`, `11-index-management.md`, `12-atomization.md`, `13-self-containment.md`)로 나눈다. 정확한 분해 단위는 실행 시 원문을 읽고 주제 응집성 기준으로 결정한다.

---

## 6. 검증 계획

| # | 항목 | 방법 | 기대 |
|---|------|------|------|
| 1 | 린터가 **현행** 위반을 검출 | `python .clinerules/tools/lint_guidelines.py` (baseline 없이) | error ≥ 1 (검출력 확인) |
| 2 | `K1`이 §1.5의 3개 링크를 검출 | 출력에서 `00-core.md:27`, `:34`, `:65` 확인 | 3건 검출 |
| 3 | `C1`이 `00-core.md`(114줄)를 검출 | 출력 확인 | 검출 |
| 4 | `C1`이 `03.plan-mode.md`(222줄)를 검출 | 출력 확인 | 검출 — 선언문이 없는데도 구조로 판정되는지가 핵심 |
| 5 | 즉시 대상 수리 후 재실행 | 동일 명령 | 즉시 등급 error 0건 |
| 6 | baseline 동작 | 신규 위반을 일부러 넣고 `--baseline` 실행 | 신규분만 실패 |
| 7 | 종료 코드 | `echo $?` | error 있으면 1 |

---

## 7. 리스크

| 리스크 | 대응 |
|--------|------|
| 60줄 상한이 너무 빡빡해 오히려 무시됨 | `00-core.md` 실제 축소를 G4 내에서 직접 수행해 **달성 가능함을 실증**한다. 실증 실패 시 상한을 80으로 되돌리고 근거를 기록 |
| 린터 오탐으로 신뢰 상실 | 초기엔 `L2`(금칙어)·`C3`(금지 콘텐츠)를 warn으로 시작하고, 오탐 0 확인 후 error로 승격 |
| `03.plan-mode.md` 분해 중 규칙 유실 | 이관 전후 **항목 번호 16개가 전부 어느 파일에 갔는지** 대응표를 계획서 실행 로그에 남긴다 |
| 린터가 `.clinerules` 서브모듈 안에 있어 프로젝트마다 버전이 갈림 | 정본은 지침 저장소. 롤아웃은 G6에서 서브모듈 업데이트로 처리 |

---

## 8. 완료 기준

- [ ] `common/core/23-compass-rule.md` 존재 (CMP-1~5)
- [ ] `10-project-compass.md`와 `03-document-separation.md`의 80줄 모순 해소됨
- [ ] `tools/lint_guidelines.py` 존재, 검사 22항목 구현
- [ ] 검증 #1~#7 PASS
- [ ] §4 "즉시" 등급 위반 0건
- [ ] `post-guideline-change` 절차에 린터 실행이 필수 단계로 등록

---

## 실행 로그 (2026-07-28)

| 산출물 | 경로 |
|--------|------|
| 규약 정본 | `.clinerules/common/core/23-compass-rule.md` |
| 린터 | `.clinerules/tools/lint_guidelines.py` (검사 21종) |
| baseline | `.clinerules/tools/lint_baseline.txt` (40건 = C2 warn) |
| 사용법 | `.clinerules/tools/README.md` |

### 린터 결과 추이

| 시점 | error | warn |
|------|-------|------|
| 최초 실행 | **139** | 106 |
| 격리·플레이스홀더 처리 후 | 19 | 52 |
| 나침반·분리 처리 후 | **0** | 40 |
| baseline 적용 | 0 | 0 |

### 나침반·상세 문서 축소 실적

| 문서 | 전 | 후 |
|------|-----|-----|
| `common/core/00-core.md` | 113 | 57 |
| `common/core/00-core/03-plan-mode.md` | 222 | 52 (하위 11문서 분해) |
| `common/core/06-git-rules.md` | 519 | 16 (하위 9+3문서) |
| `common/core/17-hallucination-prevention.md` | 287 | 15 (하위 8문서) |
| `common/core/15-schedule-rules.md` | 266 | 13 (하위 7문서) |
| `common/operator-manual/DEVELOPMENT/00-a4-authoring-guide.md` | 275 | 16 (하위 9문서) |
| `common/development/kanban-board-guide.md` | 406 | 12 (하위 6문서) |
| `common/development/kanban-board-api-contract.md` | 251 | 10 (하위 4+3문서) |
| `projects/wordcloud/README.md` | 67 | 47 |

### 린터 자체에서 발견·수정한 결함

| # | 결함 | 영향 |
|---|------|------|
| 1 | L1 루프의 `pid` 변수 섀도잉 | `L3`/`L4` 가 자기 프로젝트를 타 프로젝트로 오판 |
| 2 | 대장 파싱 정규식이 1열만 인식 | `N3` 69건 전부 오탐 |
| 3 | 한글 placeholder 링크 미제외 | `K1` 오탐 |
| 4 | `00-*` 를 사전형 폴더에서도 나침반으로 판정 | `00-a4-authoring-guide.md` 오판 |
| 5 | 동명 상위 나침반이 있는 `README.md` 를 중복 판정 | `03-plan-mode/README.md` 오판 |

### 부수 성과 — 링크

작업 전 깨진 링크 **136건** → **0건**. 계획서가 지목한 `00-core.md:27/34/65` 3건은 실재했고, 나머지 133건은 린터가 새로 찾아냈다.
