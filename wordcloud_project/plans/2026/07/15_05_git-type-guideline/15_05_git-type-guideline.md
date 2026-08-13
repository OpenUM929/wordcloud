# 계획서 — git 커밋 타입 지침 보강

> 상태: In Progress | 작성일: 2026-07-15 (수정 적용 완료 · 커밋/푸시 대기)
> 작업 유형: D
> 선행: -

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-15 | 최초 작성 | 260625.txt(Conventional Commits) 기준 git 지침 타입 용어·분류 보강 |
| 2026-07-15 | 검증 반영 | REQ 선두 프리픽스 유지(덧붙이기), 72자 완화는 사전 확인 필요 명시, §2.1 표현 정정(타입 필드 추가) |
| 2026-07-15 | 수행 완료 | .clinerules 실제 수정 — 06.git-rules.md(타입 프리픽스 섹션 신설+예시 블록 emoji/type prefix+CR템플릿 `요청 유형`→`요청 타입`), kanban-board-guide.md(§4.9 `유형`→`타입`, §4.11 `CR요청유형`→`CR 요청타입`). ⚠️ kanban은 submodule 미추적(untracked) 신규 파일, submodule 선행 미커밋 변경 15+건 coexist |

## 요구사항 원자화

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | git 커밋 메시지 분류의 호칭은? | Conventional Commits 스펙대로 `타입` | 작업 후 기입 |
| 1.2 | 적용 범위는? | 커밋/CR 분류(기존 `요청 유형`)만 `타입`, 그 밖의 `유형`은 유지 | 작업 후 기입 |
| 1.3 | 표준 타입 값은? | feat/fix/docs/style/refactor/perf/test/chore + inquiry/analysis(병합) | 작업 후 기입 |
| 1.4 | 이모지는? | 260625.txt 이모지 맵 그대로 적용 | 작업 후 기입 |
| 1.5 | 저장 위치는? | `wordcloud_project/plans/2026/07/15_05_git-type-guideline/` | 작업 후 기입 |

## 1. 배경 및 목적
- `260625.txt`는 Conventional Commits 국제 스펙 기반 이모지+`타입` 커밋 규칙.
- 현재 `D:\dev\wordcloud\.clinerules\core\06.git-rules.md`는 커밋 메시지에 `REQ-yymm-nnn:` + FP/공수 + CR 보고서 방식을 쓰며, 분류를 `유형`(요청 유형)으로 지칭.
- 월별 CR 현황(칸반 `git` 탭)도 동일 분류를 `요청 유형`으로 표시.
- 목적: 커밋/CR 분류만 한정적으로 `타입`(Conventional Commits)으로 통일하고, 260625.txt 기준 표준 타입 집합·이모지 맵을 지침에 반영.

## 2. 구현/수정 상세
### 2.1 범위 (IN)
  - `06.git-rules.md` 커밋 메시지 형식에 **타입** 필드(이모지+타입 프리픽스) 추가 + 이모지 맵 테이블 추가.
- CR 템플릿(기본/상세) 헤더 `요청 유형` → **`요청 타입`**, 값을 §2.3 집합으로 명시.
- 릴리즈노트·예시 커밋 블록에 이모지+타입 프리픽스 적용.
  - 추가 규칙: 명령형 어조, 첫 줄 72자(기존 50자 규칙 완화·확인 필요), 원자적 커밋, 분할 기준, "Claude 서명 미추가" 가드레일.
- `D:\dev\wordcloud\.clinerules\docs\development\kanban-board-guide.md` §4.9 CR 행 `유형`→`타입`, §4.11 `CR요청유형`→`CR 요청타입`(함수명 `_cr_by_type`은 그대로).

### 2.2 범위 (OUT — 변경 안 함)
- `작업 유형`(기능/비기능), `변경 유형`(생성/수정/삭제), 칸반 계획 `작업 유형`(A~E), DB `타입`/데이터 타입.

### 2.3 표준 타입 정의 (260625.txt 기준, 병합)
| 타입 | 이모지 | 의미 | 실사용 여부 |
|------|--------|------|------------|
| feat | ✨ | 새로운 기능 | O |
| fix | 🐛 | 버그 수정 | O |
| docs | 📝 | 문서화 | O |
| style | 💄 | 포맷팅 | 미사용 |
| refactor | ♻️ | 리팩토링 | O |
| perf | ⚡ | 성능 개선 | 미사용 |
| test | ✅ | 테스트 | 미사용 |
| chore | 🔧 | 빌드/도구 | 미사용 |
| inquiry | ❓ | 질문/문의 | 템플릿만 |
| analysis | 🔍 | 분석/디버깅 | 템플릿만 |

> **출처 주석(정확성)**: 상단 8개(feat~chore)와 그 이모지는 `260625.txt`의 "**타입:**" 목록 그대로다. 하단 `inquiry`/`analysis`는 260625.txt에 **없고**, 기존 `.clinerules/core/06.git-rules.md`(`:243`·`:379` 요청유형·`:119~120` 정의)에서 병합한 것이다. 두 타입의 이모지 `❓`/`🔍`는 260625.txt·06.git-rules.md 어디에도 정의되지 않은 **본 계획의 신규 배정**이므로 수행 시 사용자 확인 필요. (`260625.txt`는 국제 스펙 원문이 아니라 Conventional Commits+이모지 기반 Claude Code `/commit` 커맨드 정의 파일임.)

> 커밋 첫 줄: `<이모지> <타입> REQ-yymm-nnn: <요약 72자 이내>` (기존 REQ 선두 프리픽스·FP/공수 푸터 유지; 72자 한도는 기존 50자 규칙 완화로 사전 확인 필요)

## 3. 영향도 분석
- 수정 파일: `.clinerules/core/06.git-rules.md`, `.clinerules/docs/development/kanban-board-guide.md` (둘 다 `.clinerules` 서브모듈).
- 기존 `작업 유형`/`변경 유형`/`A~E` 호칭은 변경 없음 → 타입/유형 혼동 차단.
- `.clinerules`는 `.gitmodules` 등록 서브모듈 → 교체 금지(기존 내용 유지·추가 방식), `git diff --cached -- .clinerules/` 검토 필수.

## 4. 테스트/검증 계획
- `git -C .clinerules diff --cached -- 06.git-rules.md`로 기존 규칙 삭제/누락 없음 확인.
- 메인 `git status`에서 `.clinerules` 포인터만 변경됐는지 확인.
- `06.git-rules.md` 내 `작업 유형`/`변경 유형`에 `타입` 유입 없음 확인.

## 5. 리스크 및 제약
- 실제 `.clinerules` 수정은 사용자 "수행" 승인 후 진행(Plan 모드 규칙 및 `08-guideline-modification` 절차 준수).
- 규칙 수정 시 Before/After를 사용자에게 제시하고 승인 후 반영.
- 서브모듈 커밋 후 메인 저장소에서 포인터 갱신 커밋 필수.

## 6. 수행 이력

### 6.1 적용 변경(diff 요약)
- **.clinerules/core/06.git-rules.md** (tracked, 수정):
  - 신설: `### 타입 프리픽스 (Conventional Commits 기반)` — 첫 줄 형식 `<이모지> <타입> REQ-yymm-nnn: <요약 72자 이내>`, 명령형/원자적 커밋/Claude 서명 금지 가드레일, 표준 타입 10종 이모지 맵 테이블(inquiry/analysis 이모지 ❓/🔍 신규 배정·사용자 승인)
  - 예시 커밋 블록(feat/fix 기본·적용) 첫 줄에 `✨ feat`/`🐛 fix` prefix + 50자→72자
  - 상세 템플릿 첫 줄 50자→72자
  - CR 템플릿(기본/상세) 헤더 `요청 유형` → `요청 타입`, 값 10종으로 확장(feat/fix/docs/style/refactor/perf/test/chore/inquiry/analysis)
- **.clinerules/docs/development/kanban-board-guide.md** (untracked 신규 파일):
  - §4.9 CR 행 `유형` → `타입`
  - §4.11 `CR요청유형별` → `CR 요청타입별`

### 6.2 검증
- `git -C .clinerules diff -- core/06.git-rules.md`로 기존 규칙 삭제/누락 없음 확인(REQ 선두 프리픽스·FP/공수 푸터·작업유형/변경유형 모두 유지)
- `작업 유형`/`변경 유형`에 `타입` 유입 없음 확인

### 6.3 미해결 / 후속
- **kanban-board-guide.md는 submodule 미추적(untracked)** — 최초 커밋 시 신규 파일로 추가됨
- **submodule 작업트리에 선행 미커밋 변경 15+건 coexist**(operator-manual 다수, 00-core, docs/cr 등) — 이 계획과 무관. 커밋 시 일괄 묶임 방지 차원에서 별도 커밋 필요
- 커밋/푸시는 사용자 별도 승인 후 진행(푸시는 명시적 요청 필요)
