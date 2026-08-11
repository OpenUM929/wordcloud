# 서브에이전트 카탈로그

> 🧭 **나침반 문서** — 정의 목록·짝 구조·라우팅만 담는다. 규칙 본문은 담지 않는다.
> 규약 정본 [`26-agent-definitions.md`](../../.clinerules/common/core/26-agent-definitions.md) · 실행 0단계 [`28-agent-bootstrap.md`](../../.clinerules/common/core/28-agent-bootstrap.md) · 이식 [`25-project-onboarding.md`](../../.clinerules/common/core/25-project-onboarding.md) Step 6

## 작성자 ↔ 검증자 짝

| 영역 | 작성 | 검증 (읽기 전용) |
|------|------|------------------|
| 지침·규칙 | `guideline-curator` | `guideline-reviewer` |
| 계획서·설계 | `plan-writer` | `plan-reviewer` |
| 코드 구현 | `ui-builder` · `api-builder` | `code-reviewer` |
| 산출물 문서 | `report-writer` | `report-auditor` |
| 특허 문서 | `patent-writer` | `patent-auditor` |

## 정의 목록 (22종)

| 구분 | 에이전트 | 역할 | 도구 |
|------|----------|------|------|
| 지침 | `guideline-curator` | 지침 작성·개정 | 읽기 + 쓰기 |
| 지침 | `guideline-reviewer` | 지침 검토·린터 감사 | 읽기 |
| 지침 | `guideline-rollout` | 온보딩·개정분 전파 | 읽기 + 쓰기 |
| 계획 | `plan-writer` | 계획서 작성 | 읽기 + 쓰기 |
| 계획 | `plan-reviewer` | 계획서 검증·5단계 판정 | 읽기 |
| 문서 | `report-writer` | 산출물 문서 작성·개정 | 읽기 + 쓰기 |
| 문서 | `one-paper-writer` | A4 1장 원페이퍼 | 읽기 + 쓰기 |
| 문서 | `report-auditor` | 산출물 문서 감사·5단계 판정 | 읽기 |
| 문서 | `fp-estimator` | 기능점수·개발비 산정 | 읽기 + 쓰기 |
| 특허 | `patent-writer` | 발명신고서·청구범위·대사표 작성·개정 | 읽기 + 쓰기 |
| 특허 | `patent-auditor` | 발명신고서·청구범위 검수 | 읽기 (체크포인트 예외) |
| 측정 | `metrics-measurer` | 전수 측정·센서스 | 읽기 + 쓰기 |
| 방법론 | `paper-specialist` | 수식·통계·기법 문헌 대조 | 읽기 + 웹 |
| 구현 | `bug-diagnostician` | 버그 진단 (증상→로그→재현) | 읽기 |
| 구현 | `code-reviewer` | 코드 리뷰 | 읽기 |
| 구현 | `ui-builder` | 화면 구현·수정 | 읽기 + 쓰기 |
| 구현 | `api-builder` | 백엔드 API·데이터 계층 | 읽기 + 쓰기 |
| 절차 | `cr-scribe` | 커밋·CR 절차 | 읽기 + 쓰기 |
| 절차 | `deploy-verifier` | 배포 패키지 검증 | 읽기 |
| 도메인* | `sentiment-judge` | 감정 판정·라벨링 | 읽기 + 쓰기 |
| 도메인* | `dataset-curator` | 학습 데이터셋 누적·승격 | 읽기 + 쓰기 |
| 도메인* | `client-acceptance-reviewer` | 발주기관 관점 인수검수 | 읽기 |

`도메인*` = AGT-10 도메인 전용. 그 도메인이 없는 프로젝트에서는 이식 대상에서 제외한다.

## 라우팅

| 요청 | 흐름 |
|------|------|
| 지침 확인·개정 | `guideline-curator` → `guideline-reviewer` → 사용자 승인 |
| 지침 이식·전파 | `guideline-rollout` → `guideline-reviewer` |
| 버그 신고 | `bug-diagnostician` → 승인 → `ui-builder`·`api-builder` → `code-reviewer` |
| 신규 기능 | `plan-writer` → `plan-reviewer` → 사용자 "수행" → `ui-builder`·`api-builder` → `code-reviewer` |
| 감정 라벨링 | `sentiment-judge` → `dataset-curator` |
| 수치 요청·재측정 | `metrics-measurer` → `report-writer` → `report-auditor` |
| 방법론 점검 | `paper-specialist` → `metrics-measurer` 또는 `report-writer` |
| 문서 요청 | `report-writer` → `report-auditor` / `fp-estimator` |
| "한 장으로" | `one-paper-writer` (감사는 요청 시에만) |
| 구축완료 검수 | `client-acceptance-reviewer` → `report-writer` |
| 발명신고서 작성·개정·검수 | `patent-writer` → `patent-auditor` → `patent-writer` 반영 → 사용자 승인 |
| "커밋해줘" | `cr-scribe` → 배포 시 `deploy-verifier` |
