# 계획서 — 신규 그룹 gold 검토 웹 UI (재사용 라벨링 도구)

> 상태: Pre-Done | 작성일: 2026-06-24
> 작업 유형: B (신규 기능)
> 선행: 0624_04_emotion-clustering(D4 needs_human·baseline 산출) · 0623_01/0624_03(판정 패킷·반영 UI)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-24 | 전체 | 최초 작성. needs_human/baseline JSONL을 웹에서 빠르게 사람 판정하는 재사용 검토 UI |
| 2026-06-24 | 3.2 UI | 사용자 요청으로 카드 1건씩 → **게시판(표) 형태**로 변경. 행마다 긍/부/중/그룹아님 인라인 버튼·미판정만 필터·페이징(100). 백엔드 API(files/load/save) 불변 |
| 2026-06-24 | 3.2 UI | "저장 기능이 안 보임" 피드백 → **명시적 저장 모델**로 변경: 행 선택=미저장(점선/노랑 표시), **💾 저장(N) 버튼으로 일괄 저장**, 저장 토스트·미저장 이탈 경고·파일전환 확인 |
| 2026-06-24 | 🔴버그수정+UX | **데이터 손실 버그**: 저장이 행별 병렬 POST(각각 파일 전체 재기록)→lost-update로 판정 소실. **배치 원자 저장**으로 수정(`save`가 `decisions[]` 1회 read-modify-write). UX: 저장 후 행 유지(사라짐 방지), 페이징 시 상단 스크롤, **키보드 ↑↓ 행이동·1~4 판정+자동advance**, 컬럼 재배치(문장·현규칙·판정·내판정·필드), 문장폭 42%→30% |
| 2026-06-24 | 자동저장 | "선택 즉시 저장?" → **자동저장 전환**: 선택 시 0.4초 디바운스 + 단일처리(saving 플래그)로 배치 flush(빠른 키입력에도 병렬충돌 0). 💾는 즉시 flush. 페이징/파일전환에도 저장분 보존 |

## 1. 배경 및 목적

- 0624_04 D4가 `eval/group_needs_human_260624.jsonl`(679, **내 판정 `ai_reference` 동봉**)·`eval/baseline_eval_260624.jsonl`(1,500, `gold` 비움)을 만들었다. 이들은 **사람이 긍/부/중을 빠르게 선택해 confirmed gold로 승격**해야 한다.
- 사용자 요구: "데이터가 추가될 때마다 계속 데이터 보강이 일어나니, 확인할 때 **웹 화면으로 유사 JSON을 호출해 빠르게 선택**하게 구성하라." → 1회용 아닌 **재사용 라벨링 도구**.
- 목적: `eval/*.jsonl`(human_decision/gold 칸이 있는 검토 파일)을 드롭다운으로 골라 한 건씩 빠르게 판정(키보드/버튼) → 파일에 결정 저장. `ai_reference`를 힌트로 표시해 사람 판단과 대조.

## 2. 현재 시스템 분석 (실측)

- 라우트: `perspective_bp`(`src/routes/perspective_routes.py:36`, url_prefix `/api/perspective`), 가드 `_is_admin()`(:39, `session['admin_logged_in']`). 쓰기 POST는 전부 `_is_admin` 체크(다수 실측).
- 페이지: `ui_bp`(`src/routes/ui_routes.py`) GET 페이지 라우트(가드 없음, 기존 패턴). nav `주기능` = `base.html:167`.
- 검토 파일 위치: `plans/_datasets/kote_finetune/eval/*.jsonl`(프로젝트 루트 기준). plans/는 **배포 제외**(dev 전용 도구로 적합). 행 스키마: `{rec_id, text, field, group, cur_rule_label, ai_reference?, human_decision|gold}`.
- 신규 함수 필요: 파일 목록·로드·저장 API 3종 + 페이지 라우트 1 + 템플릿/JS(현재 없음 → 신규).

## 3. 구현 상세

### 3.1 백엔드 (perspective_routes.py, additive)
- 안전 경로: `_EVAL_DIR = os.path.join(dirname(__file__), '..','..','plans','_datasets','kote_finetune','eval')`. **basename 화이트리스트 + `.jsonl`만**(경로 traversal 차단).
- `GET /api/perspective/group-review/files` → eval 디렉터리의 `*.jsonl` 목록(+행수). `_is_admin` 가드.
- `GET /api/perspective/group-review/load?file=<name>&offset&limit` → 행 배열(text·field·ai_reference·현재 결정). 가드.
- `POST /api/perspective/group-review/save` `{file, rec_id, decision}` → 해당 행 `human_decision`(gold셋이면 `gold`) 갱신·재기록(O(n), 검토파일 한정). 가드. `decision ∈ {positive,negative,neutral,not_group,skip}`.

### 3.2 프론트엔드
- `templates/group_review.html`: 파일 드롭다운 + 진행카운터 + 카드(문장·필드·현규칙·**ai_reference 힌트**) + 빠른 선택 버튼[긍정/부정/중립/그룹아님/건너뜀] + 키보드(1/2/3/0/스페이스).
- `static/js/group_review.js`: files→load→큐 순회, 선택 즉시 save·다음 행. 남은 수·완료 수 표시.
- `base.html` nav `주기능`에 `<a href="/group-review">🏷️ 그룹 검토</a>`.

## 4. 구현 순서
| 순서 | 작업 | 의존 |
|------|------|------|
| 1 | perspective_routes 3 API(files/load/save) | — |
| 2 | ui_routes `/group-review` + 템플릿 | 1 |
| 3 | group_review.js | 2 |
| 4 | base.html nav | 2 |

## 5. 영향도 분석
| 파일 | 변경 | 영향 |
|------|------|------|
| `src/routes/perspective_routes.py` | API 3 additive | 기존 라우트 불변, 가드 일관 |
| `src/routes/ui_routes.py` | GET 라우트 1 | additive |
| `templates/group_review.html`·`static/js/group_review.js` | 신규 | 신규 화면 |
| `templates/base.html` | nav 1줄 | 메뉴 1개 |
- 데이터 트랙 전용(production 분류 로직 무변경). eval 파일만 읽기/검토 갱신.

## 6. 테스트/검증 계획
- 정적: `python -m py_compile`(routes), `node --check`(js). (서버 무단 실행 금지 → 실동작 미수행, 상태 Pre-Done 유지)
- 실동작(사용자 서버 기동 후): 파일 선택→로드→버튼/키 판정→파일 저장 확인, 비관리자 401, 경로 traversal 차단(`../` 거부).

## 7. 리스크 및 제약
- 경로 traversal: basename 화이트리스트 + eval 디렉터리 고정 + `.jsonl`만. 절대경로/`..` 거부.
- 쓰기 동시성: 단일 사용자 dev 도구 → 행 단위 갱신 후 전체 재기록(작은 파일). 대용량 시 후속 최적화.
- 배포: plans/ 배포 제외 → 내부망 패키지에 미포함. dev 전용.
- DN: 실서버 검증 전 Pre-Done(서버 무단 실행 금지).
