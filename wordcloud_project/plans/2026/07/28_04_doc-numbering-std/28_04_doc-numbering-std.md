# 계획서 G3 — 지침 문서 넘버링·명명 표준 및 채번 절차

> 상태: Done | 작성일: 2026-07-28 | 완료일: 2026-07-28
> 작업 유형: C (설계) + D (리팩토링)
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
| 1.1 | 현재 `common/core` 최상위에 번호가 중복된 파일 쌍이 존재하는가? | Y (2쌍) | (미수행) |
| 1.2 | 번호 구분자가 2종 이상 혼재하는가? | Y (`.` `-` `_` + 무번호) | (미수행) |
| 2.1 | 신규 문서 채번 시 "다음 번호"를 계산할 단일 근거 파일이 존재하는가? | 현재 N → 도입 후 Y | (미수행) |
| 2.2 | 삭제된 문서의 번호를 재사용하는가? | N (결번 유지) | (미수행) |
| 2.3 | 개정 시 번호가 바뀌는가? | N (주제 변경 시만 새 번호) | (미수행) |

---

## 1. 배경 — 실측된 붕괴 상태

### 1.1 구분자 4종 혼재

`D:\dev\wordcloud\.clinerules\core\` 실측:

| 구분자 | 예시 | 개수(최상위 md 19개 중) |
|--------|------|------------------------|
| 점 `.` | `01.legacy-protection.md` | 12 |
| 하이픈 `-` | `11-performance-optimization-plan.md` | 7 |
| 언더스코어 `_` | `10-project-compass/01_scan.md` | 하위 폴더 4파일 |
| 번호 없음 | `03-workflow/precheck.md`, `04-design-change/checklist.md` | 하위 폴더 다수 |

추가로 **나침반 파일명과 분리 폴더명의 구분자가 다르다**: `03.plan-mode.md` ↔ `03-plan-mode/`, `10.project-compass.md` ↔ `10-project-compass/`.

### 1.2 번호 중복 2쌍 (git 이력으로 선후 확정)

| 번호 | 파일 | 최초 추가일 | 커밋 |
|------|------|-------------|------|
| 02 | `core/02.documentation.md` | 2026-04-29 | `08ff970` |
| 02 | `core/02.hallucination-prevention.md` | **2026-07-22** | `6abcce2` |
| 15 | `core/15.schedule-rules.md` | 2026-07-22 | `91609d3` |
| 15 | `core/15-backup-before-modify.md` | **2026-07-22 (더 나중)** | `6abcce2` |

측정: `git log --diff-filter=A --format="%ad %h" --date=short -1 -- <file>`
`6abcce2`는 `91609d3`보다 뒤 커밋(`git log --oneline` 순서).

→ **채번 대장이 없어 신규 문서가 기존 번호를 그대로 다시 썼다.** 3항의 "뒤죽박죽"의 직접 원인.

### 1.3 결번 여부

01~16 연속, 결번 없음. 즉 **번호는 "다음 빈 자리"가 아니라 "직전 최대값+1" 방식으로 자랐으나, 두 사람(세션)이 동시에 같은 값을 취한 셈**이다.

---

## 2. 표준 정의 — 규칙 NUM

### NUM-1. 파일명 형식

```
NN-<slug>.md
```

| 요소 | 규칙 |
|------|------|
| `NN` | 2자리 숫자, 0 패딩 (`00`~`99`) |
| 구분자 | **하이픈 `-` 단 하나**. 점·언더스코어 금지 |
| `<slug>` | 소문자 영문·숫자·하이픈. 한글 금지. **최대 30자** |
| 확장자 | `.md` |

예: `02-documentation.md`, `16-report-writing.md`

### NUM-2. 폴더명 형식

| 대상 | 규칙 |
|------|------|
| 나침반 분리 폴더 | 나침반 파일명에서 `.md`를 제거한 것과 **정확히 동일**. 예: `03-plan-mode.md` → `03-plan-mode/` (기존 `04.folder-naming.md` 원칙 유지, 구분자만 통일) |
| 주제 폴더(번호 없음) | 소문자 케밥. 예: `development/`, `operator-manual/` |
| 프로젝트 폴더 | `prj-<project_id>` (G2 규칙 N-PRJ) |

### NUM-3. 번호 없는 파일이 허용되는 경우

| 파일 | 허용 |
|------|------|
| `README.md` | ✅ 폴더 나침반 |
| `CLAUDE.md` | ✅ 저장소/프로젝트 진입점 |
| `NUMBERS.md`, `PROJECTS-REGISTRY.md` | ✅ 대장·레지스트리 (전부 대문자 = 메타 문서) |
| 그 외 | ❌ 번호 필수 |

> 현행 `03-workflow/precheck.md`, `04-design-change/checklist.md` 등 무번호 파일은 NUM-3 위반 → §4에서 채번한다.

### NUM-4. 번호 대역

| 대역 | 용도 | 비고 |
|------|------|------|
| `00` | 그 폴더의 **나침반** | 폴더당 1개. `00-core.md`, 하위 폴더는 `README.md`로 대체 가능 |
| `01`–`09` | **불변 규율** — 모든 작업의 전제가 되는 규칙 | 신규 추가 시 사용자 승인 필수 |
| `10`–`29` | **절차·산출물 규칙** — 계획서·보고서·분석·검증 절차 | 통상 신규는 여기 |
| `30`–`89` | **예비** | 10~29가 포화하면 개방 |
| `90`–`99` | **폐기 예정(deprecated)** | 삭제 전 유예 구역. 이동 시 문서 상단에 `> ⚠️ DEPRECATED — 대체: <경로>` 명시 |

### NUM-5. 채번 절차 (신규 문서)

1. `.clinerules/NUMBERS.md`(채번 대장)를 **Read** 한다.
2. 대상 폴더·대역을 §NUM-4로 결정한다.
3. 그 대역에서 **대장에 기록된 최대 번호 + 1**을 취한다. 파일 목록이 아니라 **대장**을 근거로 한다(삭제된 번호도 대장에 남아 있으므로 재사용을 막는다).
4. 대장에 한 행을 **먼저** 추가한다(번호 선점).
5. 파일을 생성한다.
6. 나침반(`00-core.md` 등)의 분류표·문서 위치표에 링크를 추가한다.

> 4번이 핵심이다. 파일부터 만들면 §1.2 같은 충돌이 재발한다.

### NUM-6. 기존 문서 개정 시

| 상황 | 번호 |
|------|------|
| 내용 보완·수정 | **유지** |
| 문서 분리(나침반화) | **유지**. 하위 폴더는 같은 번호+같은 slug |
| 주제 자체가 바뀜 | 새 번호로 신규 생성 + 구 문서는 `90`대로 이동 후 DEPRECATED 표기 → 다음 정리 때 삭제 |
| 폐기 | 파일 삭제, **번호는 결번으로 영구 보존**(대장에 `삭제` 상태로 기록) |

### NUM-7. 번호 중복 발견 시 해소

**나중에 추가된 쪽**(git `--diff-filter=A` 최초 추가 커밋 기준)이 새 번호로 이동한다. 먼저 있던 문서의 번호를 지켜야 기존 링크·기억이 유지된다.

### NUM-8. 계획서·보고서 문서명 (R8)

지침 문서와 **다른 체계**임을 명시한다. 혼동 방지를 위해 표로 고정한다.

| 문서 종류 | 형식 | 정본 규칙 위치 |
|-----------|------|----------------|
| 지침 문서 | `NN-<slug>.md` | 본 문서 (NUM-1) |
| 계획서 | `DD_NN_<slug>.md` (폴더명과 동일) | `common/core/00-core/03-plan-mode.md` |
| CR 보고서 | `REQ-YYMM-NNN[-r].md` | `common/core/06-git-rules.md` |
| 운영자 메뉴얼 | `NN-<menu>[.tabN].md` | `common/operator-manual/DEVELOPMENT/01-structure.md` |
| 메타 문서 | `UPPERCASE.md` | 본 문서 (NUM-3) |

> 계획서가 언더스코어(`_`)를 쓰는 것은 **의도된 차이**다. 파일명만 보고 "지침인가 계획서인가"를 구분할 수 있어야 하므로 통일하지 않는다. 이 근거를 두 문서 모두에 명시한다.

---

## 3. 채번 대장 `NUMBERS.md` 설계

위치: `.clinerules/NUMBERS.md`

```markdown
# 지침 문서 채번 대장

> 신규 문서는 이 대장의 **최대 번호 + 1**로 채번한다. 파일 목록이 아니라 이 대장이 근거다.
> 삭제된 번호는 재사용하지 않는다(결번 유지).

## common/core/

| NN | slug | 상태 | 최초 채번일 | 비고 |
|----|------|------|-------------|------|
| 00 | core | 활성 | 2026-04-29 | 나침반 |
| 01 | legacy-protection | 활성 | 2026-04-29 | |
| ... | | | | |
| 17 | hallucination-prevention | 활성 | 2026-07-22 | 02 중복 해소로 이동(구 `02.hallucination-prevention.md`) |
```

상태값: `활성` / `삭제` / `이동(→NN)` / `DEPRECATED`.

폴더별 섹션을 둔다: `common/core/`, `common/core/00-core/`, `common/development/`, `common/ui/`, `common/verification/`, `projects/prj-wordcloud/`.

---

## 4. as-is → to-be 파일명 매핑표

### 4.1 `common/core/` 최상위 (19개)

| as-is | to-be | 변경 사유 |
|-------|-------|-----------|
| `00-core.md` | `00-core.md` | 변경 없음 |
| `01.legacy-protection.md` | `01-legacy-protection.md` | 구분자 |
| `02.documentation.md` | `02-documentation.md` | 구분자 (번호 유지 — 선(先) 채번) |
| `02.hallucination-prevention.md` | **`17-hallucination-prevention.md`** | 번호 중복 해소 (NUM-7: 후행 추가분 이동) |
| `03.workflow.md` | `03-workflow.md` | 구분자 |
| `04.design-change.md` | `04-design-change.md` | 구분자 |
| `05.testing.md` | `05-testing.md` | 구분자 |
| `06.git-rules.md` | `06-git-rules.md` | 구분자 |
| `07.recovery-rules.md` | `07-recovery-rules.md` | 구분자 |
| `08.guideline-modification.md` | `08-guideline-modification.md` | 구분자 |
| `09.question-rules.md` | `09-question-rules.md` | 구분자 |
| `10.project-compass.md` | `10-project-compass.md` | 구분자 |
| `11-performance-optimization-plan.md` | `11-performance-optimization.md` | slug 30자 초과 정리(`-plan` 제거) |
| `12-impact-analysis-report.md` | `12-impact-analysis-report.md` | 변경 없음 |
| `13-requirements-clarification.md` | `13-requirements-clarification.md` | 변경 없음 |
| `14.comment-log-removal.md` | `14-comment-log-removal.md` | 구분자 |
| `15.schedule-rules.md` | `15-schedule-rules.md` | 구분자 (번호 유지 — 선 채번) |
| `15-backup-before-modify.md` | **`18-backup-before-modify.md`** | 번호 중복 해소 (NUM-7) |
| `16-report-writing.md` | `16-report-writing.md` | 변경 없음 |

### 4.2 신규 문서 채번 (G1·G2·G4 산출물)

| NN | 파일 | 출처 계획서 |
|----|------|-------------|
| 19 | `19-project-identity.md` | G1 (`28_02`) |
| 20 | `20-repo-layout.md` | G2 (`28_03`) |
| 21 | `21-project-isolation.md` | G2 (`28_03`) |
| 22 | `22-doc-numbering.md` | **본 계획서** (NUM 규칙 정본) |
| 23 | `23-compass-rule.md` | G4 (`28_05`) |

> 19~23은 `10`–`29` 대역(절차·산업물 규칙). 17·18은 중복 해소로 동일 대역에 흡수된다.

### 4.3 하위 폴더

| as-is | to-be |
|-------|-------|
| `core/00-core/01.global-rules.md` | `common/core/00-core/01-global-rules.md` |
| `core/00-core/02.triggers.md` | `common/core/00-core/02-triggers.md` |
| `core/00-core/03.plan-mode.md` | `common/core/00-core/03-plan-mode.md` |
| `core/00-core/03-plan-mode/` | `common/core/00-core/03-plan-mode/` (변경 없음 — 이제 파일명과 일치) |
| `core/10-project-compass/01_scan.md` | `common/core/10-project-compass/01-scan.md` |
| `core/10-project-compass/02_design.md` | `common/core/10-project-compass/02-design.md` |
| `core/10-project-compass/03_templates.md` | `common/core/10-project-compass/03-templates.md` |
| `core/10-project-compass/04_split_rule.md` | `common/core/10-project-compass/04-split-rule.md` |
| `core/03-workflow/README.md` | 유지 (NUM-3 허용) |
| `core/03-workflow/{precheck,request-analysis,execution-steps,common-module-impact,debugging-lessons,post-guideline-change}.md` | `01-`~`06-` 채번 — **README.md의 기재 순서**를 따른다 (임의 순서 금지, 실행 전 README 확인) |
| `core/04-design-change/{principles,scale,standard,light,scenarios,checklist}.md` | 동일 방식으로 `01-`~`06-` 채번 |
| `core/08-guideline-modification/01.plan-mode.md` 외 5개 | `01-`~`06-` 구분자만 변경 |

> `03-workflow/`·`04-design-change/` 채번 순서는 **각 폴더 `README.md`를 읽어 실제 나열 순서대로** 부여한다. 본 계획서에서 순서를 단정하지 않는다(추측 금지).

---

## 5. 변경 파일 목록

| # | 파일 | 유형 |
|---|------|------|
| 1 | `.clinerules/NUMBERS.md` | 신규 (채번 대장) |
| 2 | `.clinerules/common/core/22-doc-numbering.md` | 신규 (NUM 규칙 정본) |
| 3 | §4.1 19개 + §4.3 하위 폴더 다수 | rename |
| 4 | `.clinerules/common/core/00-core.md` | 수정 (분류표·문서위치표 링크 전량 갱신 + "지침 문서 채번" 행 추가) |
| 5 | `.clinerules/common/core/08-guideline-modification/02-modification-procedure.md` | 수정 (채번 절차 NUM-5 참조 추가) |
| 6 | 링크를 보유한 전 md | 수정 (rename에 따른 링크 갱신) |

---

## 6. rename 실행 절차 (링크 파손 방지)

1. **기준선 확보**: rename 전에 린터(G4) `L5`(링크 실존 검사)를 실행해 **현재 깨진 링크 목록**을 저장한다. 파일: `wordcloud_project/plans/2026/07/28_04_doc-numbering-std/result/links_before.txt`
2. `git mv`로 rename (이력 보존).
3. 링크 일괄 치환: 구 파일명 → 신 파일명. 치환 대상은 `.clinerules/**/*.md` + `CLAUDE.md` + `.claude/agents/*.md`.
4. 린터 `L5` 재실행 → `links_after.txt`.
5. **`after`가 `before`의 부분집합**이어야 한다(새로 깨진 링크 0건). 아니면 롤백.

> `.claude/agents/*.md`를 치환 대상에 포함하는 근거: wordcloud `.claude/agents/`에 11개 에이전트 정의가 있고 그중 `guideline-curator.md`는 `.clinerules/` 경로를 직접 지시한다(에이전트 설명문에 `.clinerules/` 명시).

---

## 7. 검증 계획

| # | 항목 | 방법 | 기대 |
|---|------|------|------|
| 1 | 구분자 단일화 | `ls common/core/*.md \| grep -c "[0-9]\."` | 0 |
| 2 | 언더스코어 잔존 | `find common -name "*_*.md" \| grep -v "^.*README"` | 0건 |
| 3 | 번호 중복 | 린터 `N1` (폴더별 `NN` 중복 검사) | 0쌍 |
| 4 | 무번호 파일 | 린터 `N2` (NUM-3 예외 외 무번호) | 0건 |
| 5 | 대장 정합 | 린터 `N3` (파일 시스템 ↔ `NUMBERS.md` 대사) | 불일치 0건 |
| 6 | 링크 | §6-5 | 새 파손 0건 |
| 7 | slug 길이 | 린터 `N4` (30자 초과) | 0건 |

---

## 8. 리스크

| 리스크 | 대응 |
|--------|------|
| 19개+하위 rename으로 링크 대량 파손 | §6 절차. before/after 차분으로만 판정 |
| 사용자·AI의 기억 속 경로(`02.hallucination-prevention.md`)가 깨짐 | `NUMBERS.md`에 `이동(→17)` 이력을 남겨 검색 가능하게 함 |
| 하위 폴더 무번호 파일 채번 시 순서 오판 | README 나열 순서를 근거로만 부여. README가 없거나 순서가 불명확하면 **채번을 보류하고 사용자에게 질문** |
| 대장과 파일이 다시 어긋남 | 린터 `N3`을 `post-guideline-change` 절차에 필수 단계로 등록 (G4 A9) |

---

## 9. 완료 기준

- [ ] `.clinerules/NUMBERS.md` 존재, 전 폴더 섹션 채워짐
- [ ] `common/core/22-doc-numbering.md` 존재 (NUM-1~NUM-8 수록)
- [ ] 검증 #1~#7 전부 PASS
- [ ] `00-core.md`의 모든 링크가 신규 파일명을 가리킴
- [ ] `08-guideline-modification` 절차에 NUM-5 채번 단계가 연결됨

---

## 실행 로그 (2026-07-28)

| 산출물 | 경로 |
|--------|------|
| 규칙 정본 | `.clinerules/common/core/22-doc-numbering.md` |
| 채번 대장 | `.clinerules/NUMBERS.md` (105개 파일 등재) |
| 대장 동기화 도구 | `.clinerules/tools/gen_numbers.py` |

### 실제 적용

- 구분자 통일(점·언더스코어 → 하이픈): `common/core/` 전 파일.
- 번호 중복 해소(NUM-7, git 최초추가일 기준 후행분 이동):
  `02.hallucination-prevention.md` → **17**, `15-backup-before-modify.md` → **18**.
- slug 정리: `11-performance-optimization-plan` → `11-performance-optimization`.
- 무번호 파일 채번: `03-workflow/`·`04-design-change/` 각 6개, `03-plan-mode/` 유형 템플릿 6개 — **각 폴더 README.md 의 나열 순서**를 근거로 부여(추측 아님).

### 계획과 달라진 점 — NUM-3 범위 축소

계획서는 "무번호 = 위반"이었으나 `common/development`(15)·`ui`(10)·`verification`(3) 까지 강제 채번하면 링크 파손 위험만 크고 실익이 없었다. **번호 필수 구역을 `common/core/` 로 한정**하고 사전형 폴더는 번호를 선택으로 바꿨다. "순서가 의미를 갖는 곳에만 번호를 강제한다"는 원칙은 유지된다.

검증: 린터 `N1`~`N5` 전부 0건.
