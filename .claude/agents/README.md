# 서브에이전트 카탈로그

> 🧭 **나침반 문서** — 정의 목록·짝 구조·라우팅만 담는다. 규칙 본문은 담지 않는다.
> 정의 파일 규약 정본 → [`.clinerules/common/core/26-agent-definitions.md`](../../.clinerules/common/core/26-agent-definitions.md)

각 파일은 Claude Code 서브에이전트 정의(`.claude/agents/*.md`)다. **프로젝트 고유값을 본문에 담지 않는다** — 값은 저장소 루트 `project.json` 과 `{{guideline.project_dir}}/` 에 있다.

## 작성자 ↔ 검증자 짝 (핵심 구조)

| 영역 | 작성 | 검증 (읽기 전용) |
|------|------|------------------|
| 지침·규칙 | `guideline-curator` | `guideline-reviewer` |
| 계획서·설계 | `plan-writer` | `plan-reviewer` |
| 코드 구현 | `ui-builder` · `api-builder` | `code-reviewer` |
| 산출물 문서 | `report-writer` | `report-auditor` |
| 특허 문서 | (사용자) | `patent-auditor` |

검증자는 `Write`·`Edit` 를 갖지 않는다. 지적이 조용한 수정으로 사라지지 않고 **반드시 보고로 남게** 하기 위해서다. 작성자는 스스로 통과 판정하지 않는다 (AGT-6).

> **데이터 활용 히스토리 3종** — `_FACTS.md`(확인 사실 대장, FL-1) · `_분석데이터_출처대장_*.md` · `IMPROVEMENT_HISTORY.md`·`status_YYMMDD.md`. **원자료보다 먼저 읽고, 나가기 전에 적립한다.** 생산 역할(`report-writer`·`one-paper-writer`·`metrics-measurer`)은 **없으면 만들고**, 검증 역할(`report-auditor`·`patent-auditor`)은 **없으면 없다고 보고**한다(직접 만들지 않는다). 어느 쪽이든 **대장 값을 그대로 인용하지 말고 원본까지 표본 검증**한다 — 대장도 문서다.

> 예외 1건 — `patent-auditor` 는 세션 한도로 중단돼도 진행 상황이 남도록 **자기 체크포인트 파일 1개에만** 추가 기록한다(정의 §1-2). 검수 대상 문서·소스는 여전히 열어 보기만 한다.

## 구성 (21종)

### 지침·규칙 (3종)

| 에이전트 | 역할 | 도구 |
|----------|------|------|
| `guideline-curator` | 지침 **작성·개정**. 공통/프로젝트 판정, 채번, 나침반 유지 | 읽기 + 쓰기 |
| `guideline-reviewer` | 지침 **검토**. 린터 실행, 격리·정본 단일성·참조 무결성 감사 | **읽기 전용** |
| `guideline-rollout` | 지침 **적용·전파**. 신규 온보딩 / 개정분 전파 / 마이그레이션 | 읽기 + 쓰기 |

### 계획·문서 (7종)

| 에이전트 | 역할 |
|----------|------|
| `plan-writer` | 계획서 작성 (검증된 사실만, 저장 규약 준수) |
| `plan-reviewer` | 계획서 **검증**. 주장 대조·`[FACT]/[INFERENCE]/[UNCERTAIN]` 태깅·5단계 판정. **읽기 전용** |
| `report-writer` | 산출물 문서 (A4 규격, 캡처 규칙, 수치 재계산). **개정 규율**(표시로 때우지 않고 구값 교체·파급 자리 동시 수정·서수 상호참조 금지). 1장 요약본은 제외 |
| `one-paper-writer` | **A4 1장 원페이퍼** (기관장·임원 보고용). 6블록 고정 + 분량 한도로 관리, **지면 계산 금지**. 수치는 상세본을 베끼지 않고 `_FACTS.md`·원자료에서 가져온다 |
| `report-auditor` | 산출물 문서 **감사**. **증거 등급**(문서의 자기서술=배너·취소선은 원자료가 아님), 수치 원자료 추적·분모 일관성·폐기값 잔존·추정/전수 구분·**개정 파급**·5단계 판정. 지적은 3분류(감사자 확정/작성자 판단/사용자 결정)로 낸다. **읽기 전용** |
| `fp-estimator` | 기능점수(FP) 산정·검증·개발비 |
| `patent-auditor` | 발명신고서·청구범위 **검수**. **증거 규율**(문서의 자기서술은 증거 아님·개수는 재현 명령과 단위 병기·파일 유형 전수 스윕), 기재↔구현·산출물 대조, 청구항 뒷받침·명확성, 선출원 저촉, **용어 대장**(청구항 명사구 전건 추적), **양식 준수**, **why-first 서사 매핑표**, **개정 파급**, 데이터 출처 대장. 지적은 3분류로 내고 권리범위가 바뀌는 것만 되던진다. 유닛 분할 + 체크포인트로 중단 대비. 진보성은 판정하지 않는다. **읽기 전용**(체크포인트 파일 예외) |

### 측정 (1종)

| 에이전트 | 역할 |
|----------|------|
| `metrics-measurer` | 전수 측정·센서스. 입력 정합성 선행 검증 → 조건 동일성 역검정 → 검산 → 재현 스크립트·JSON 산출. **측정 1건 = 대장 2행**(`_FACTS.md` + 출처대장). **추정보다 전수** |

### 방법론 (1종)

| 에이전트 | 역할 |
|----------|------|
| `paper-specialist` | 수식·통계 절차·모델 기법의 **문헌 대조**. 문헌상 지위(유지/개선판/대체/비권장) × 현 자료 적합성 2축 판정, 문서 서술↔구현 대조, 인용 규율(열어본 자료만·URL 필수). **읽기 전용 + 웹 조회** |

### 구현 (4종)

| 에이전트 | 역할 |
|----------|------|
| `bug-diagnostician` | 버그 진단 (증상→로그→재현). **읽기 전용** |
| `code-reviewer` | 코드 리뷰. 심각도 3단계 + 도메인 잠금 대조. **읽기 전용** |
| `ui-builder` | 화면 구현·수정 |
| `api-builder` | 백엔드 API·데이터 계층 |

### 절차 (2종)

| 에이전트 | 역할 |
|----------|------|
| `cr-scribe` | 커밋·CR 절차 (CR ID 채번, 보고서, 서브모듈 분리 커밋). "커밋해줘" 요청 시에만 |
| `deploy-verifier` | 배포 패키지 검증. **읽기 전용** |

### 도메인 (3종 — 해당 도메인이 없는 프로젝트에서는 제외 / AGT-10 도메인 전용)

| 에이전트 | 역할 |
|----------|------|
| `sentiment-judge` | 감정 판정·라벨링 |
| `dataset-curator` | 학습 데이터셋 누적·승격·감사 |
| `client-acceptance-reviewer` | 발주기관 관점 **인수검수**. 증적 기반 7분류 체크리스트·완료/조건부/미완료 판정·원페이퍼/상세 이원 산출. **읽기 전용** |

## 설계 원칙

1. **프로젝트 고유값 외재화** — 정의 본문에 경로·수치·도메인 규칙을 박지 않는다. 값은 실행 시점에 얻는다: 0단계 절차 정본 [`28-agent-bootstrap.md`](../../.clinerules/common/core/28-agent-bootstrap.md) BOOT-1~6. 본문에 박으면 이식할 때 통째로 따라가고, 지침 저장소의 정본과 두 벌이 되어 갈라진다 (AGT-1·AGT-5).
2. **읽기/쓰기 권한 분리** — 진단·검증 역할은 읽기 전용 도구만 부여해 "분석 중 임의 수정"을 구조적으로 차단.
3. **작성자와 검증자 분리** — 같은 에이전트가 만들고 스스로 통과 판정하면 검증이 형식화된다.
4. **실패 이력의 체크리스트화** — 실제 사고를 `domain-locks.md` 의 행으로 변환해 누적한다. **정의 파일이 아니라 지침 저장소에 쌓는다.**
5. **담당하지 않는 업무를 명시** — 역할 경계를 정의 안에 적어 에이전트끼리 일을 넘겨받게 한다.
6. **확신도 태깅** — 검증 역할은 `[FACT]/[INFERENCE]/[UNCERTAIN]` 로 근거 수준을 표시한다. "추측 금지"를 원칙이 아니라 **출력 형식으로 강제**하는 장치다.

## 다른 프로젝트로 이식

`guideline-rollout` 이 수행한다. 수기 절차가 필요하면:

1. 이 폴더의 `*.md` 를 대상 저장소 `.claude/agents/` 에 **본문 수정 없이** 복사
2. 대상 저장소 루트에 `project.json` 작성 ([`19-project-identity.md`](../../.clinerules/common/core/19-project-identity.md) §2)
3. `{{guideline.project_dir}}/domain-locks.md` 를 대상 프로젝트 사고 이력으로 작성 (없으면 만들지 않는다 — 빈 표를 두지 않는다)
4. 도메인 특화 정의는 해당 도메인이 없으면 제외
5. 린터로 검증 — `python .clinerules/tools/lint_guidelines.py` 의 `A1`~`A7` 이 0건이어야 한다

**정의 파일 본문을 손대야 한다면 그것은 이식 실패다** — 공통/프로젝트 분리가 잘못된 것이므로 고쳐 넣지 말고 분리 오류로 보고한다 (AGT-7).

## 권장 협업 흐름

```
요청 접수
 ├─ 지침 확인/개정   → guideline-curator → guideline-reviewer (검증) → 사용자 승인
 ├─ 지침 이식/전파   → guideline-rollout → guideline-reviewer (검증)
 ├─ 버그 신고        → bug-diagnostician (진단만) → 승인 후 ui-builder/api-builder → code-reviewer
 ├─ 신규 기능        → plan-writer → plan-reviewer (검증) → 사용자 "수행"
 │                     → ui-builder + api-builder → code-reviewer
 ├─ 감정 라벨링      → sentiment-judge → dataset-curator (승격)
 ├─ 수치 요청/재측정 → metrics-measurer → report-writer (서술) → report-auditor (검증)
 ├─ 방법론 점검      → paper-specialist (문헌 대조) → metrics-measurer(재측정) / report-writer(반영)
 ├─ 문서 요청        → report-writer → report-auditor (검증) / fp-estimator
 ├─ "한 장으로"      → one-paper-writer (초안 1개로 끝. 감사는 요청 시에만)
 ├─ 구축완료 검수    → client-acceptance-reviewer (발주자 관점) → report-writer (반영)
 ├─ 발명신고서 검수  → patent-auditor (기재↔구현·용어·양식·서사) → 사용자 반영
 │                     ※ 문서가 크면 유닛 묶음으로 나눠 디스패치 (정의 §1-1)

 └─ "커밋해줘"       → cr-scribe → 배포 시 deploy-verifier
```

> **수치 흐름의 방향은 되돌리지 않는다** — 문서에서 수치를 만들지 말고 `metrics-measurer` 의 산출물에서 가져온다. 감사에서 수치 오류가 나오면 문서를 고치는 것이 아니라 **측정으로 되돌아간다**.
