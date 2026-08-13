# 계획서 G6 — 타 프로젝트 적용(롤아웃) 가이드

> 상태: Todo | 작성일: 2026-07-28
> 작업 유형: C (설계) + E (마이그레이션)
> 선행: 07/28_06_common-promotion
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
| 1.1 | wordcloud와 msys의 `.clinerules`는 같은 git 저장소인가? | **N** (origin 상이) | (미수행) |
| 1.2 | 두 저장소의 레이아웃이 동일한가? | N | (미수행) |
| 1.3 | msys 쪽 `common/`에 wordcloud 정보가 들어가 있는가? | Y (14파일) | (미수행) |
| 2.1 | 새 프로젝트에 이식할 때 프로젝트별로 바꿔야 하는 파일이 `project.json` 하나인가? | Y | (미수행) |
| 2.2 | 이식 후 린터가 그 프로젝트에서 그대로 동작하는가? | Y | (미수행) |

---

## 1. 배경 — 두 저장소는 이미 갈라졌다 (실측)

| 프로젝트 | `.clinerules` origin | 레이아웃 | HEAD 커밋(2026-07-28 시점) |
|----------|----------------------|----------|---------------------------|
| wordcloud | `https://github.com/OpenUM929/clinerules` | `core/` + `docs/` | `6abcce2 docs: 지침 체계 정비 — 환각방지·백업·보고 규칙 추가 + A 개선분 흡수 + 운영자 메뉴얼 재편` |
| msys | `https://github.com/feelmydream80-sys/clinerules` | `CLAUDE.md` + `common/` + `docs/` + `projects/` | `b20787a REQ-2605-012: CR 보고서 - 오늘 날짜 강조 기능` |

측정: 각 `.clinerules`에서 `git remote -v`, `git log --oneline -3`.

**함의 3가지**:

1. **"서브모듈을 공유하다 섞였다"는 가설은 틀렸다.** 두 저장소가 각자 진화하며 **서로의 정보를 복사해 들여왔다**. 오염 경로는 공유가 아니라 **수기 복사**다.
2. **msys 쪽이 구조는 더 앞서 있다**(`common/`+`projects/` 3분할). 그러나 `common/` 14개 파일에 wordcloud가 박혀 있어 **분리만으로는 오염을 막지 못한다는 증거**이기도 하다.
3. **wordcloud 쪽이 규칙은 더 앞서 있다**(환각방지·백업·보고 규칙 등 2026-07-22 추가분, msys HEAD는 2026-05 계열 CR). 사용자 지시대로 **wordcloud를 정본**으로 삼는 것이 내용 손실이 적다.

---

## 2. 정본(canonical) 저장소 결정

### 2.1 선택지

| 안 | 내용 | 장점 | 단점 |
|----|------|------|------|
| **A. wordcloud 정본** (기본값, PRD D1) | `OpenUM929/clinerules`를 표준으로 확정. msys가 이 저장소를 서브모듈로 재접속 | 사용자 지시 부합. 최신 규칙 보존 | msys 저장소의 고유 변경분 이관 필요 |
| B. msys 정본 | `feelmydream80-sys/clinerules`를 표준으로 | 구조(3분할)가 이미 근접 | 규칙 최신분이 뒤처짐. 사용자 우선순위와 반대 |
| C. 신규 저장소 | 제3의 저장소를 만들어 양쪽 병합 | 이력 정리 | 작업량 최대. 두 이력 모두 단절 |

**기본값 = A.** 다만 **실행 전에 §2.2 차분을 산출**해 msys 고유분의 규모를 확인한 뒤 확정한다.

### 2.2 차분 산출 (실행 첫 단계)

두 저장소를 같은 작업 트리에 올려 비교한다.

```bash
# msys 저장소를 wordcloud 쪽 .clinerules에 원격으로 추가해 비교
git -C D:/dev/wordcloud/.clinerules remote add msys https://github.com/feelmydream80-sys/clinerules.git
git -C D:/dev/wordcloud/.clinerules fetch msys
git -C D:/dev/wordcloud/.clinerules log --oneline HEAD..msys/main   # msys에만 있는 커밋
git -C D:/dev/wordcloud/.clinerules diff --stat HEAD msys/main
```

> 브랜치명(`main`/`master`)은 실행 시 `git -C ... branch -r`로 확인한다. **추측 금지.**

산출물: `wordcloud_project/plans/2026/07/28_07_multi-prj-rollout/result/repo_diff_260728.md`

이 차분에서 **msys에만 있는 규칙**(공통 자격 COM 충족분)은 wordcloud 정본으로 흡수한 뒤 A안을 실행한다.

---

## 3. 롤아웃 절차 (신규/기존 프로젝트 공통)

이 절이 사용자 요구 **2.1 "다른 프로젝트에 활용하기 위한 가이드"**의 본문이다. 완성 후 `common/core/25-project-onboarding.md`로 지침화한다(번호는 `NUMBERS.md` 채번).

### Step 0. 사전 조건 확인

| 확인 | 방법 |
|------|------|
| 대상이 git 저장소인가 | `git -C <repo> rev-parse --show-toplevel` |
| 기존 `.clinerules`가 있는가 | 있으면 Step 5(기존 프로젝트 경로), 없으면 Step 1 |

### Step 1. 지침 저장소 연결

```bash
git -C <repo> submodule add https://github.com/OpenUM929/clinerules.git .clinerules
```

### Step 2. `project.json` 작성 — **프로젝트별로 바꾸는 유일한 파일**

`<repo>/project.json`. 스키마는 G1 §2.2. 필수 4개(`schema_version`, `project_id`, `project_name`, `guideline`)를 채운다.

`project_id` 결정 규칙: 소문자 케밥, 3~20자, 저장소를 대표하는 최단 이름. 이미 사용 중인 id는 `common/PROJECTS-REGISTRY.md`에서 확인해 **중복 금지**.

### Step 3. 프로젝트 지침 폴더 생성

```
.clinerules/projects/prj-<project_id>/README.md
```

`README.md`는 프로젝트 나침반이므로 CMP-2(60줄) 이하, CMP-3 콘텐츠 규칙 준수.

### Step 4. 레지스트리 등록

`.clinerules/common/PROJECTS-REGISTRY.md`에 한 행 추가:

| project_id | project_name | 저장소 | 등록일 |
|------------|--------------|--------|--------|
| `msys` | MSYS | `D:\dev\msys` | 2026-MM-DD |

> 이 등록이 곧 린터 `L2`의 **금칙어 사전**이 된다. 등록하지 않으면 그 프로젝트명이 `common/`에 새어 들어가도 검출되지 않는다.

### Step 5. 기존 프로젝트 마이그레이션 (msys 해당)

| # | 작업 | 검증 |
|---|------|------|
| 5-1 | 기존 `.clinerules` 백업 (`git bundle` 또는 폴더 복사) | 백업 경로 기록 |
| 5-2 | §2.2 차분에서 **이 프로젝트 고유분**을 추출 | 파일 목록 |
| 5-3 | 서브모듈 origin을 정본으로 교체 | `git remote set-url` |
| 5-4 | 고유분을 `projects/prj-<id>/`로 재배치 | G2 N-PRJ 준수 |
| 5-5 | `common/`에 남은 타 프로젝트 문자열 제거 | 린터 `L2` 0건 |
| 5-6 | 링크 수리 | 린터 `K1` 0건 |

**msys 구체 작업 (실측 기반)**:

| 대상 | 조치 |
|------|------|
| `D:\dev\msys\.clinerules\common\` 중 `wordcloud` 포함 14파일 | 정본(wordcloud 이관본)으로 **대체**. msys 고유 변경이 있으면 §2.2 차분으로 먼저 흡수 |
| `D:\dev\msys\.clinerules\projects\msys\` (246파일) | → `projects/prj-msys/` (폴더명에 `prj-` 접두사 부여) |
| `D:\dev\msys\.clinerules\docs\cr\` | → `outputs/cr/` |
| `D:\dev\msys\CLAUDE.md` | 현재 `@` import 3줄뿐 — G1 §2.5의 0단계(project.json 확인) 추가 |
| `D:\dev\msys\.env` | **손대지 않는다.** 비밀값 전용. `project.json`과 역할 분리 |
| `D:\dev\msys\.claude\agents\` (11파일) | wordcloud와 파일명 10개 동일 — 경로·프로젝트명 참조 전수 대사 |

### Step 6. 검증

```bash
python .clinerules/tools/lint_guidelines.py
```

error 0건이어야 온보딩 완료.

### Step 7. 커밋

`.clinerules`(서브모듈) 먼저 커밋·푸시 → 상위 저장소에서 포인터 갱신 커밋. **두 커밋을 분리**한다.

---

## 4. 이식 시 프로젝트별로 바뀌는 것 / 안 바뀌는 것

이 표가 표준화의 성과 지표다.

| 항목 | 프로젝트마다 다른가 | 위치 |
|------|--------------------|------|
| `project_id`, 경로, 산출물명 | ✅ 다름 | `project.json` **단 1개 파일** |
| 프로젝트 구조·도메인 규칙 | ✅ 다름 | `projects/prj-<id>/` |
| 작업 규율·절차·표준 | ❌ 동일 | `common/` (서브모듈 공유) |
| 린터 | ❌ 동일 | `tools/` |
| 채번 대장 | ⚠️ 공통부는 공유, 프로젝트 섹션만 다름 | `NUMBERS.md` |

> `NUMBERS.md`가 유일한 회색 지대다. 공통 저장소를 공유하므로 프로젝트 섹션이 서로 보인다. **허용**한다 — 번호 충돌을 막으려면 오히려 한곳에 있어야 하고, 폴더 목록일 뿐 규칙 내용이 아니므로 ISO 위반이 아니다. 이 판단 근거를 `24-common-criteria.md`에 명시한다.

---

## 5. 신규 프로젝트 체크리스트 (배포용)

`common/core/25-project-onboarding.md`에 수록할 최종 체크리스트.

- [ ] `project.json` 작성 (필수 4키)
- [ ] `project_id`가 `PROJECTS-REGISTRY.md`에 미등록 상태였다 → 등록 완료
- [ ] `.clinerules` 서브모듈 연결
- [ ] `projects/prj-<id>/README.md` 작성 (60줄 이하)
- [ ] 루트 `CLAUDE.md`에 0단계(project.json 확인) 포함
- [ ] `common/`에 손대지 않았다 (프로젝트 고유 규칙은 전부 `projects/` 아래)
- [ ] 린터 error 0건
- [ ] 서브모듈·상위 저장소 커밋 분리

---

## 6. 변경 파일 목록

| # | 파일 | 유형 |
|---|------|------|
| 1 | `.clinerules/common/core/25-project-onboarding.md` | 신규 (§3 절차 + §5 체크리스트) |
| 2 | `.clinerules/common/PROJECTS-REGISTRY.md` | 수정 (msys 등록) |
| 3 | `result/repo_diff_260728.md` | 신규 (산출물) |
| 4 | msys 측 다수 | 이동/수정 (Step 5, **msys 저장소에서 별도 세션으로 실행**) |

> #4는 `D:\dev\msys` 저장소를 건드린다. **본 계획서의 승인 범위와 별개로, msys 작업 착수 시 사용자에게 재확인**한다.

---

## 7. 검증 계획

| # | 항목 | 방법 | 기대 |
|---|------|------|------|
| 1 | 차분 산출 완료 | `result/repo_diff_260728.md` 존재 | Y |
| 2 | msys 고유 규칙 유실 없음 | 차분 목록 대비 흡수/보류 판정 전건 표기 | 미판정 0 |
| 3 | msys `common/`에 wordcloud 문자열 | `grep -rin wordcloud D:/dev/msys/.clinerules/common` | **0건** (현재 14파일) |
| 4 | msys `projects/` 폴더명 | `ls D:/dev/msys/.clinerules/projects` | `prj-msys` 1개 |
| 5 | msys에서 린터 실행 | `python .clinerules/tools/lint_guidelines.py` | error 0 |
| 6 | 두 저장소 origin 일치 | 양쪽 `git remote -v` | 동일 URL |

---

## 8. 리스크

| 리스크 | 대응 |
|--------|------|
| origin 교체로 msys 고유 커밋 이력 단절 | Step 5-1 백업(`git bundle`) 필수. 백업 경로를 실행 로그에 기록 |
| msys 저장소에 최근 변경이 있어 차분이 큼 | §2.2를 **첫 단계**로 두어 규모를 먼저 확인. 차분이 크면 A안 재검토(사용자 결정) |
| msys 쪽 작업을 승인 없이 진행 | §6 #4 주석대로 재확인 게이트 |
| 정본 교체 후 wordcloud 쪽 규칙이 msys 사정으로 흔들림 | 공통 규칙 변경은 COM 기준 통과 + 린터 통과 시에만. 프로젝트 사정은 `projects/`에서 해결 |
| 두 프로젝트가 동시에 `common/`을 고쳐 충돌 | 서브모듈 브랜치 운영 규칙을 `25-project-onboarding.md`에 1절로 추가 (변경 전 pull, 변경은 소규모 커밋) |

---

## 9. 완료 기준

- [ ] `common/core/25-project-onboarding.md` 존재 (절차 + 체크리스트)
- [ ] `PROJECTS-REGISTRY.md`에 wordcloud·msys 등록
- [ ] `result/repo_diff_260728.md` 작성 + 정본 결정 확정
- [ ] (사용자 승인 시) msys 마이그레이션 완료 + 검증 #3~#6 PASS
- [ ] 신규 프로젝트가 `project.json` 1개 작성만으로 온보딩 가능함이 절차서로 입증됨

---

## 실행 로그 (2026-07-28) — 절차서만 작성, 마이그레이션 미실행

| 산출물 | 경로 | 상태 |
|--------|------|------|
| 온보딩 절차서 | `.clinerules/common/core/25-project-onboarding.md` | 완료 |
| 레지스트리 | `.clinerules/common/PROJECTS-REGISTRY.md` | wordcloud·msys 등록 완료 |
| msys 마이그레이션 | — | **미실행 (사용자 승인 대기)** |

### 사전 조사에서 확정된 사실

| 항목 | 실측 |
|------|------|
| wordcloud `.clinerules` origin | `https://github.com/OpenUM929/clinerules` |
| msys `.clinerules` origin | `https://github.com/feelmydream80-sys/clinerules` |
| msys 의 `common/`+`projects/` 재편 | **커밋되지 않은 워킹트리 변경** (`git ls-files projects` → 0건) |
| msys `common/` 의 wordcloud 하드코딩 | 14파일 |
| wordcloud 에만 있는 msys 문서 | 30파일 |
| 양쪽 공통 169파일 중 내용 상이 | 49파일 |

→ "msys 구조가 더 앞서 있다"는 PRD §1 의 관찰은 **미커밋 로컬 작업**이었다. A안(wordcloud 정본)의 근거는 오히려 강해졌으나, msys 저장소를 건드리므로 착수 전 사용자 재확인이 필요하다.

### 다음 단계

1. `git remote add msys ...` + `fetch` 로 차분 산출 → `result/repo_diff_260728.md`
2. msys 고유 규칙 중 COM 충족분 흡수
3. `outputs/_transfer-msys/` 199파일을 msys 저장소 `projects/msys/` 로 이관
4. msys `common/` 을 정본으로 교체 + `project.json` 작성
5. msys 에서 린터 error 0 확인
