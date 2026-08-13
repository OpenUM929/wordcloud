# 계획서 G1 — 프로젝트 식별 체계 (`project.json`)

> 상태: Done | 작성일: 2026-07-28 | 완료일: 2026-07-28
> 작업 유형: B (기능 개선 — 신규 규약·파일)
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
| 1.1 | `D:\dev\wordcloud\project.json` 이 현재 존재하는가? | N | (미수행) |
| 1.2 | `D:\dev\wordcloud\.env` 가 현재 존재하는가? | N | (미수행) |
| 1.3 | 공통 나침반 `.clinerules/core/00-core.md`가 프로젝트명을 하드코딩하고 있는가? | Y | (미수행) |
| 1.4 | 계획서 저장 경로 규칙이 공통 문서에 하드코딩되어 있는가? | Y | (미수행) |
| 2.1 | `project.json` 도입 후, 공통 지침 파일에서 `wordcloud` 문자열이 0건이 되는가? | Y | (미수행) |
| 2.2 | `project.json`이 없을 때 AI가 폴더명으로 폴백하고, 그것도 실패하면 **질문**하는가? | Y | (미수행) |

---

## 1. 배경 및 목적

### 문제 (실측)

| 파일 | 내용 | 문제 |
|------|------|------|
| `.clinerules/core/00-core.md:9-11` | `## 현재 프로젝트` → `docs/project_wordcloud/README.md` | 공통 나침반에 프로젝트가 **글자로** 박혀 있다 |
| `.clinerules/core/00-core.md:20` | `wordcloud 관련 작업` 행 | 동일 |
| `.clinerules/core/00-core.md:43-45` | `build_deploy.ps1` → `wordcloud-project.zip` | 동일 |
| `.clinerules/core/00-core/03.plan-mode.md:12` | 계획서 저장 위치 `wordcloud_project/plans/YYYY/MM/` | 공통 절차 문서에 프로젝트 경로 하드코딩 |
| `D:\dev\msys\.clinerules\common\core\00-core.md:11,20,43-45` | **msys의 공통 지침이 wordcloud를 가리킴** | 치환 누락이 그대로 굳은 상태 |

측정: `grep -rln "wordcloud" D:/dev/msys/.clinerules/common` → 14파일.

### 원인

공통 지침을 새 프로젝트로 복사할 때, **프로젝트 고유값이 문서 본문에 흩어져 있어 사람/AI가 전수 치환해야 한다.** 한 곳이라도 빠지면 그 문서는 남의 프로젝트를 가리킨 채 "정상 문서"로 남는다. 23_01 계획서 `:37`이 지목한 바로 그 실패다.

### 목적

프로젝트 고유값을 **문서에서 뽑아 단일 데이터 파일로 옮긴다.** 공통 지침은 값을 담지 않고 **키를 참조**한다. 치환 대상이 1개 파일로 줄면 누락이 구조적으로 불가능해진다.

---

## 2. 설계

### 2.1 파일 위치와 이름

**`<저장소 루트>/project.json`** (사용자 지정)

- wordcloud: `D:\dev\wordcloud\project.json`
- 저장소 루트에만 둔다. 하위 폴더(`wordcloud_project/`)에 두지 않는다 — git 루트 = 식별 단위.
- git **추적 대상**이다(`.gitignore` 금지). 비밀값을 넣지 않기 때문에 가능하다.

### 2.2 스키마 (v1.0)

```json
{
  "schema_version": "1.0",
  "project_id": "wordcloud",
  "project_name": "워드클라우드 인사평가 분석 시스템",
  "aliases": ["wc", "워드클라우드"],
  "guideline": {
    "root": ".clinerules",
    "common_dir": "common",
    "project_dir": "projects/prj-wordcloud"
  },
  "paths": {
    "app_root": "wordcloud_project",
    "plans_root": "wordcloud_project/plans",
    "scripts_root": "wordcloud_project/scripts",
    "deploy_script": "wordcloud_project/deploy/build_deploy.ps1",
    "deploy_artifact": "wordcloud-project.zip",
    "venv": "wordcloud_project/venv"
  },
  "entrypoint": "wordcloud_project/web/app.py"
}
```

#### 필드 정의

| 키 | 필수 | 형식 | 의미 |
|----|------|------|------|
| `schema_version` | ✅ | `"1.0"` | 스키마 버전. 파서 호환 판단용 |
| `project_id` | ✅ | `^[a-z][a-z0-9-]{2,19}$` (3~20자) | **식별자 정본**. 폴더명·검사·로그 전부 이 값을 씀 |
| `project_name` | ✅ | 문자열 | 사람이 읽는 이름. 한글 허용. 식별에 쓰지 않음 |
| `aliases` | ⬜ | 문자열 배열 | 사용자가 부르는 다른 이름. 요청 해석 보조용 |
| `guideline.root` | ✅ | 상대경로 | 지침 저장소 위치. 통상 `.clinerules` |
| `guideline.common_dir` | ✅ | 상대경로 | `root` 기준 공통 지침 폴더 |
| `guideline.project_dir` | ✅ | 상대경로 | `root` 기준 이 프로젝트 지침 폴더. **`projects/prj-<project_id>` 여야 한다**(G2 규칙, 린터 검사) |
| `paths.*` | ⬜ | 상대경로 | 공통 지침이 하드코딩하던 값들. 저장소 루트 기준 |
| `entrypoint` | ⬜ | 상대경로 | 앱 진입점 |

> **모든 경로는 저장소 루트 기준 상대경로**로 적는다. 절대경로(`D:\...`) 금지 — 다른 머신·워크트리에서 깨진다.

### 2.3 해석 순서 (Resolution Order) — 규칙

AI/도구가 "지금 어느 프로젝트인가"를 결정하는 절차. **이 순서를 벗어난 추측 금지.**

| 순위 | 방법 | 조건 |
|------|------|------|
| 1 | `<git 루트>/project.json`의 `project_id` | 파일이 있고 스키마 검증 통과 |
| 2 | **폴백** — git 저장소 루트 폴더명을 정규화(소문자화, 공백·언더스코어→하이픈) | `project.json` 부재 또는 파싱 실패 |
| 3 | **중단 후 질문** — "이 저장소의 `project_id`가 무엇입니까? `project.json`을 만들까요?" | 1·2 모두 실패(git 저장소가 아닌 경우 등) |

폴백(2순위)을 쓸 때는 **응답에 "폴백으로 판별했음"을 반드시 표시**한다. 조용히 넘어가면 오판을 못 잡는다.

#### 폴백을 1순위로 삼지 않는 이유 (실측 근거)

`D:\dev\wordcloud\` 루트에 다음이 공존한다: `wordcloud_project/`, `wordcloud-internal/`, `wordcloud-source/`, `wordcloud-project.zip`. 폴더명 `wordcloud` 하나로는 **어느 것이 앱 루트인지, plans가 어디인지** 결정할 수 없다. `project.json`은 그 매핑까지 담는다.

### 2.4 공통 지침의 참조 문법

공통 지침 문서는 프로젝트 값을 **플레이스홀더**로 쓴다.

| 표기 | 해소 결과(wordcloud) |
|------|---------------------|
| `{{project_id}}` | `wordcloud` |
| `{{project_name}}` | `워드클라우드 인사평가 분석 시스템` |
| `{{guideline.project_dir}}` | `projects/prj-wordcloud` |
| `{{paths.plans_root}}` | `wordcloud_project/plans` |
| `{{paths.deploy_artifact}}` | `wordcloud-project.zip` |

**적용 예 — `core/00-core/03.plan-mode.md:12`**

```
현행: 프로젝트 루트 기준 `wordcloud_project/plans/YYYY/MM/` 연도·월별 폴더 아래 …
개정: 프로젝트 루트 기준 `{{paths.plans_root}}/YYYY/MM/` 연도·월별 폴더 아래 …
      (현 프로젝트에서는 `wordcloud_project/plans/` — project.json에서 해소)
```

> 플레이스홀더만 남기면 사람이 읽을 때 불편하므로, **괄호로 "현 프로젝트에서의 해소값"을 병기**한다. 병기값은 참고용이며 **정본은 `project.json`**임을 문서 상단에 1회 명시한다.

### 2.5 프로젝트 나침반 규칙 (CLAUDE.md)

`D:\dev\wordcloud\CLAUDE.md` 최상단 필수 체크에 **0단계**를 추가한다.

```markdown
## ⛔ 작업 시작 전 필수 체크

0. `project.json` 을 Read 하여 `project_id` 와 `guideline.project_dir` 를 확인한다.
   - 파일이 없으면 git 루트 폴더명으로 폴백하고, **폴백했음을 응답에 표시**한다.
   - 둘 다 실패하면 작업을 멈추고 사용자에게 묻는다.
1. `{{guideline.root}}/{{guideline.common_dir}}/core/00-core.md` 를 Read 한다
2. 분류표에서 현재 작업 유형을 찾는다
3. 해당 문서를 Read 한 뒤 작업을 시작한다
```

---

## 3. 변경 파일 목록

| # | 파일 (저장소 루트 기준) | 유형 | 내용 |
|---|------------------------|------|------|
| 1 | `project.json` | 신규 | §2.2 스키마로 작성 |
| 2 | `CLAUDE.md` | 수정 | 필수 체크 0단계 추가 (§2.5) |
| 3 | `.clinerules/common/core/00-core.md` | 수정 | "현재 프로젝트" 섹션을 `{{guideline.project_dir}}` 참조로 교체, wordcloud 하드코딩 행 3곳 제거 (G2 이관 후 최종 경로 반영) |
| 4 | `.clinerules/common/core/00-core/03.plan-mode.md` | 수정 | `plans_root` 플레이스홀더화 (`:12`, `:17`, `:32`, `:112~121` 예시 포함) |
| 5 | `.clinerules/common/core/01-project-identity.md` | 신규 | 본 설계를 **규칙 문서**로 고정 (해석 순서·스키마·플레이스홀더 문법). 번호는 G3 채번 규칙에 따름 |
| 6 | `.clinerules/CLAUDE.md` | 신규 | 저장소 안내 나침반. `project.json`을 읽는 진입 절차 명시 (PRD A1) |

> #3·#4의 최종 경로(`common/core/...`)는 G2 이관 완료 후 확정된다. G1 단독 실행 시에는 현행 경로(`core/...`)에 적용하고, G2에서 그대로 이동한다.

---

## 4. 다른 프로젝트에서의 값 (참고)

msys에 이식할 때 채워야 할 값. 실측 기반이며 G6에서 사용한다.

```json
{
  "schema_version": "1.0",
  "project_id": "msys",
  "project_name": "MSYS",
  "guideline": {
    "root": ".clinerules",
    "common_dir": "common",
    "project_dir": "projects/prj-msys"
  },
  "paths": {
    "app_root": ".",
    "deploy_artifact": "msys.zip",
    "venv": "msys_venv"
  },
  "entrypoint": "msys_app.py"
}
```

근거: `D:\dev\msys\` 루트 실측 — `msys_app.py`, `msys_venv/`, `msys.zip` 존재. `plans_root`는 msys에 `plans/` 폴더가 확인되지 않아 비워둔다(이식 시 확인 필요).

---

## 5. 검증 계획

| # | 검증 항목 | 방법 | 기대 |
|---|-----------|------|------|
| 1 | `project.json` 스키마 유효 | `python -c "import json;json.load(open('project.json'))"` | 예외 없음 |
| 2 | `project_id` 정규식 통과 | 린터(G4) 항목 `P1` | PASS |
| 3 | `guideline.project_dir` == `projects/prj-<project_id>` | 린터 항목 `P2` | PASS |
| 4 | `paths.*` 경로 실존 | 린터 항목 `P3` — 각 값에 대해 존재 확인 | 전부 존재 |
| 5 | 공통 지침에 프로젝트명 하드코딩 없음 | `grep -rin "wordcloud" .clinerules/common` | **0건** |
| 6 | 플레이스홀더가 스키마에 정의된 키만 사용 | 린터 항목 `P4` — `{{...}}` 추출 후 스키마 대조 | 미정의 키 0건 |
| 7 | 폴백 동작 | `project.json`을 임시 이동 후 AI에 프로젝트 질의 → 폴더명 폴백 + 폴백 표시 | 표시됨 |

---

## 6. 리스크

| 리스크 | 대응 |
|--------|------|
| 플레이스홀더 때문에 사람이 문서를 읽기 어려워짐 | §2.4대로 해소값 병기. 병기값과 `project.json` 불일치는 린터가 검출(항목 `P5`) |
| `project.json`을 AI가 다시 수기 편집해 오염 | `project.json` 수정은 **사용자 요청 시에만** 허용하는 조항을 `01-project-identity.md`에 명시 |
| 기존 문서 다수가 하드코딩 상태 → 일괄 치환 시 오치환 | 치환은 G5에서 파일 단위로 수행하고, 각 치환에 대해 diff를 남긴다 |
| `paths.deploy_artifact` 등이 실제와 어긋남 | 검증 #4로 실존 확인. 없으면 값을 빼고 문서에 "해당 없음" 명시 |

---

## 7. 완료 기준

- [ ] `D:\dev\wordcloud\project.json` 존재 + 검증 #1~#4 PASS
- [ ] `CLAUDE.md`에 0단계 존재
- [ ] `.clinerules/CLAUDE.md`(저장소 안내) 존재
- [ ] 공통 지침 내 프로젝트명 하드코딩 0건 (검증 #5)
- [ ] `01-project-identity.md` 규칙 문서 존재

---

## 실행 로그 (2026-07-28)

| 산출물 | 경로 |
|--------|------|
| 식별 파일 | `D:\dev\wordcloud\project.json` |
| 규칙 문서 | `.clinerules/common/core/19-project-identity.md` |
| 저장소 나침반 | `.clinerules/CLAUDE.md` |
| 루트 나침반 0단계 | `D:\dev\wordcloud\CLAUDE.md` |

`guideline.project_dir` 값은 사용자 지시에 따라 `projects/wordcloud`(접두사 없음).

검증: 린터 `P1`~`P4` 전부 PASS. `common/` 내 프로젝트 고유어 67행 → **0행**.
