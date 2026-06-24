# 계획서 — 판정 결과 반영 UI (판정 패킷 적용)

> 상태: Pre-Done | 작성일: 2026-06-24
> 작업 유형: B (신규 기능)
> 선행: plans/2026/0623_01_judgment-extract-ui/0623_01_judgment-extract-ui.md (추출 UI — 본 건은 그 짝인 "반영")

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-24 | 전체 | 최초 작성. 구현 선행 후 사후 문서화(절차상 계획서 누락을 사용자 지적으로 보정) |

## 1. 배경 및 목적

- 판정 패킷(`build_judgment_packet`)을 메타데이터 생성 시 **추출**하는 경로(`/judgment/extract`)는 웹 UI에 연결돼 있으나, AI/사람이 판정한 패킷을 DB에 **반영**하는 경로(`/judgment/apply`)는 **백엔드만 존재하고 웹 UI 호출부가 없었다**(curl/수동 POST만 가능 → end-to-end 단절).
- 목적: nav `주기능`에 "판정 결과 반영" 페이지를 추가해, 판정 완료 패킷 JSON 업로드 → `/judgment/apply` 호출 → 반영 요약·사람검토 큐 표시까지 UI로 잇는다.
- 이름은 추출(`판정 패킷 추출`)과 대칭되도록 "판정 결과 반영"으로 정한다. ("메타데이터 업데이트"는 '메타데이터 필드 수정'으로 오해 소지.)
- **범위(사용자 확정)**: 적용만(1차). 영향받은 직원의 매트릭스/워드클라우드 재생성은 기존 `/matrix/regenerate` 경로로 분리 유지(본 페이지 미포함).

## 2. 현재 시스템 분석 (코드 실측)

- **DB 반영 함수**: `src/services/judgment_packet_service.py:256` `apply_judgment_packet(packet, conn=None)`
  - `evaluations.sentiment_corrections`(JSON 컬럼)에 **in-place 병합**. 별도 테이블 없음.
  - 키잉: `item.key.db_id`(= `evaluations.id`, DB row id) + `sent_idx`. evaluation_id 비고유 제약 준수.
  - 병합: `merged = {**existing, **sent_corr}` — 기존 인덱스 보존, 신규 판정 우선(`:297`). UPDATE만.
  - 필터: `result.label ∈ {positive,negative,neutral}` 만 반영(`:276`); `result.needs_human is True`는 DB 미반영, `needs_human` 목록으로 분리(`:273`); label/키 없음 → `skipped`.
  - 반환: `{inserted_sentences, updated_evaluations, needs_human, needs_human_items, skipped}`.
- **라우트**: `src/routes/perspective_routes.py:631` `POST /judgment/apply` (`api_judgment_apply`)
  - 관리자 전용(`_is_admin()` → 401). 파일 업로드 `request.files['packet']` 또는 JSON body 허용(`:642`).
  - 반환: `{success, summary, needs_human_queue:[{text,key,result}]}` (needs_human 본문 노출 최소화).
- **재사용 UI 자산**: `web/static/css/base.css:365` `.upload-area`(+`.dragover`) — 메타데이터 생성 1단계 드롭존과 동일 클래스.
- **nav**: `web/templates/base.html:167` `주기능` 섹션(메타데이터 생성/그룹분석/설정/불용어 관리).

## 3. 구현 상세

### 3.1 백엔드

- **서비스/라우트 변경 없음** — 기존 `apply_judgment_packet` + `POST /judgment/apply` 그대로 사용(시그니처 불변).
- **신규 GET 페이지 라우트**: `src/routes/ui_routes.py` `@ui_bp.route('/judgment_apply')` → `render_template('judgment_apply.html')`. (메타데이터 생성 등 기존 페이지와 동일 패턴, GET 가드 없음 — 실제 반영 POST가 서버측 관리자 가드.)

### 3.2 프론트엔드

- **신규 템플릿** `web/templates/judgment_apply.html`: `base.html` 확장. 설명 카드 + `.upload-area` 드롭존(`.json` accept) + 로딩 스피너 + 결과 영역(통계 4카드 `반영된 문장/갱신된 평가/사람 검토 필요/건너뜀` + 사람검토 큐).
- **신규 JS** `web/static/js/judgment_apply.js`: 파일선택·드래그드롭 → `FormData('packet', file)` → `POST /judgment/apply` → `summary` 통계 + `needs_human_queue`(가명 텍스트 + db_id·sent_idx만) 렌더. 실패 시 에러 카드. (필드명 `packet`은 라우트 `request.files['packet']`와 일치 확인.)
- **nav 추가**: `base.html` `주기능`에 `<a href="/judgment_apply">📥 판정 결과 반영</a>` (메타데이터 생성 바로 아래).

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `judgment_apply.html` 템플릿(드롭존/결과 영역) | — |
| 2 | `judgment_apply.js`(업로드→apply→렌더) | 1 |
| 3 | `ui_routes.py` GET `/judgment_apply` | 1 |
| 4 | `base.html` nav `주기능` 링크 | 3 |

## 5. 영향도 분석

| 파일 | 변경 | 영향 |
|------|------|------|
| `web/templates/judgment_apply.html` | 신규 | 신규 페이지. 기존 화면 영향 없음 |
| `web/static/js/judgment_apply.js` | 신규 | 신규 JS. 전역 오염 없음(IIFE) |
| `src/routes/ui_routes.py` | GET 라우트 1개 추가 | additive. 기존 라우트 불변 |
| `web/templates/base.html` | nav `주기능` 1줄 추가 | 모든 페이지 nav에 메뉴 1개 노출 |
- 백엔드 서비스/`/judgment/apply` 로직 **무변경** → 기존 동작 회귀 위험 없음.

## 6. 테스트/검증 계획

- 정적: `ui_routes.py` AST 컴파일 OK, `judgment_apply.js` `node --check` OK (완료).
- 실동작(서버 기동 후 — **미수행**, 서버 무단 실행 금지):
  1. `/judgment_apply` 접속 → 페이지·드롭존 렌더.
  2. 관리자 로그인 상태에서 판정 완료 패킷(JSON) 업로드 → 통계 4카드 + needs_human 큐 표시.
  3. 비관리자/비로그인 → 401 에러 카드 표시.
  4. 반영 후 해당 `evaluations.sentiment_corrections`에 신규 판정 병합·기존 보존 확인(in-place).
  5. `result.label` 없는 항목 `skipped`, `needs_human:true` 항목 DB 미반영·큐 노출 확인.
- → 위 1~5 실서버 검증 통과 시에만 상태 `Done`으로 전환(현재 Pre-Done).

## 7. 리스크 및 제약

- **DN 규약**: 실서버 동작 검증 전이므로 `Done` 아님(`Pre-Done`). 단위/정적 검증만 완료.
- 권한: 페이지 GET은 가드 없음 — 실제 쓰기(POST)는 서버측 관리자 가드에 의존(메타데이터 생성 페이지와 동일 정책).
- 프라이버시: needs_human 큐는 가명 텍스트 + db_id/sent_idx만 표시(백엔드 반환 그대로). plans/ 패킷은 배포 제외 폴더 규약 유지.
- 매트릭스/워드클라우드 재생성은 본 범위 밖 — 반영 후 별도 `/matrix/regenerate` 필요.
