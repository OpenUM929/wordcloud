# 0701_03 — 판정 패킷 ↔ 그룹검토 게시판 통합 (status 기반 단일 캐리어)

> 상태: Pre-Done | 작성일: 2026-07-01 | 작업 유형: type-B 신규 기능
>
> 구현·단위테스트 통과. DN은 사용자 수동 왕복 실동작 검증 후.

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-01 | 전면 | v1(needs_human을 별도 eval/*.jsonl로 내보내고 reflect) 구현·단위테스트 완료 |
| 2026-07-02 | 전면 재설계 | v2 — 별도 파일 폐기. 패킷 item을 게시판 행 스키마로 통일 + `status`(1/2/3)로 파이프라인 구동. 게시판이 패킷을 직접 로드/저장. v1 코드(export/reflect/UI 반영섹션) 되돌림 |
| 2026-07-02 | §요구사항 원자화 | 지침 항목 14 첫 적용 — 사용자 질문(패킷 구조·게시판·DB 반영)을 원자 질문 표로 기록·재확인. 1.1~3.1 확인 완료, 3.2(사람 판정분 DB 반영)는 **현행 유지**(judgment_apply 일원화, 옵션 B)로 확정 → 코드 변경 없음 |

## 요구사항 원자화

> 지침 `03.plan-mode.md` §14. 각 원자 질문에 실측 답+근거. **기대=결정 대기** 행은 사용자 확정 필요.

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | 패킷 item은 여전히 문장 단위인가? | Y | Y — `select_hard_sentences`가 문장별 `key{db_id,sent_idx}` 생성 (judgment_packet_service.py:180) |
| 1.2 | 기존 item에 `status` **하나만** 추가됐는가? | N | N — status 외 `rec_id`·`field`·`ai_reference`·`human_decision` 추가, `cur_label`→`cur_rule_label` 개명(게시판 행 스키마 통일). (:180) |
| 2.1 | 그룹검토 파일 목록에서 이 패킷을 선택할 수 있는가? | Y | Y — `/group-review/files`가 `eval/judgment/**` 패킷 노출 (perspective_routes.py:1680) |
| 2.2 | 그 파일을 기존 게시판 형태로 열어 수정 가능한가? | Y | Y — `/load`가 status==2 행만 게시판 행으로 매핑, 게시판 JS 무변경 (:1708) |
| 2.3 | 게시판에서 저장하면 DB가 아니라 **패킷 파일**에 써지는가? | Y | Y — `/save`→`update_packet_decisions`가 파일에 `human_decision`·status=3 기록, DB 미접촉 (:1760) |
| 3.1 | AI 판정분(status=3)은 judgment_apply 업로드 시 DB에 써지는가? | Y | Y — `apply_judgment_packet`이 `evaluations.sentiment_corrections` UPDATE (:334) |
| 3.2 | 사람 판정분(status=2→3)은 게시판 저장 **즉시 DB**에 써지는가? | **N (현행 유지·2026-07-02 확정)** | N — 게시판 저장은 파일에만 기록(`update_packet_decisions` :1760), 사람 판정분도 judgment_apply "재적용"으로 DB 반영(`apply_judgment_packet` :334). **DB 쓰기는 judgment_apply로 일원화**(사용자 확정, 옵션 B). |

## 배경 및 목적

판정 반영(`/judgment_apply`)에서 AI가 확신 못한 문장의 사람 판정 경로가 끊겨 있었다.
v1은 별도 파일 브리지로 풀었으나 사용자 피드백으로 재설계: **패킷 item 스키마를 그룹검토
게시판 행과 통일**하고 각 item에 **`status` 상태값**을 두어, 같은 게시판이 패킷을 직접 판정하고
포맷이 하나로 일관되게 한다. 변환·별도 파일 불요.

## 상태값·흐름

- `status`: **1**=AI 판정 대기 · **2**=사람 판정 대기 · **3**=확정(DB 반영 대상).
- 추출 → status=1 → AI 판정(ai_reference 채움; 확신 3, 애매 2) → 게시판(status==2만, human_decision·status=3)
  → 반영(status==3만, 라벨=human_decision 우선 없으면 ai_reference.polarity).

## 통합 item 스키마

`rec_id`(=db_id_sent_idx), `key{db_id,sent_idx}`, `text`, `field`, `cur_rule_label`,
`kote/gap/hard/margin_band`, `ai_reference{polarity,confidence,reason}`, `status`, `human_decision`.
(구 `cur_label`·`result` 제거.)

## 구현 (코드 검증 완료)

### 백엔드 — `src/services/judgment_packet_service.py`
- `select_hard_sentences`(`:151`): 통합 item 생성(status=1, ai_reference=null, human_decision=null).
- `_packet_skeleton`(`:97`): `_stages.judge` 지침을 status 흐름으로 재작성 + `_status_codes` 추가.
- `resolve_item(it)` 신규: (status, final_label) 반환. 레거시(result) 파생 호환.
- `apply_judgment_packet`(`:256`): **status==3만** in-place 반영. 반환
  `{inserted_sentences, updated_evaluations, pending_ai, pending_human, skipped}`.
- `load_packet` / `update_packet_decisions` 신규: 게시판 저장 위임(human_decision·status=3, 봉투/key 보존).
- v1 함수(`_eval_root`/`export_needs_human_to_review`/`reflect_review_file`) 제거.

### 라우트 — `src/routes/perspective_routes.py`
- `api_judgment_apply`(`:652`) 개정: 업로드/본문 패킷 반영 + **서버 저장**(`save_packet_file`,
  게시판 접근용) + body `{file}`로 **서버 패킷 재적용**. 응답 = status 분포 + `packet_file`.
- 신규 `GET /judgment/packets`: 서버 패킷 목록(+status 분포) — 재적용 드롭다운용.
- `_safe_packet_path`·`_packet_item_to_row` 신규 + 게시판 3종 확장:
  `/group-review/files`(패킷도 나열, rows=status2), `/load`(패킷이면 status==2만 행 매핑),
  `/save`(패킷이면 `update_packet_decisions` 위임). **게시판 JS 무변경.**
- v1 라우트(`/judgment/review-files`, `/judgment/reflect-from-review`) 제거.

### UI — `web/templates/judgment_apply.html` + `web/static/js/judgment_apply.js`
- 결과를 status 분포로 표시(반영3/사람대기2/AI대기1/건너뜀). status2 있으면 그룹검토 안내.
- "서버 저장 패킷 재적용" 섹션(`/judgment/packets` 드롭다운 → `{file}` 재적용).
- apply POST URL 교정(`/judgment/apply`→`/api/perspective/judgment/apply`, 기존 0624_03 버그).

## 재사용
- `save_packet_file`(`:86`), `_safe_segment`(`:64`), apply의 by_db in-place UPDATE, 게시판 UI/JS.
- `batch_processor.py:1084-1086`(build/save 호출)은 스키마 변경 자동 반영(수정 불요).

## 테스트
- **`0623_01/test/test_judgment_extract.py`**: 통합 item 스키마 단언 추가(`test_item_unified_schema`).
- **`test/test_packet_status_flow.py`**(신규): resolve_item(우선순위·레거시 파생),
  apply_judgment_packet(status==3만 반영), update_packet_decisions(전이·봉투/key 보존). **전건 통과.**
- **수동 왕복**(사용자): 배치→패킷 저장 → AI 판정 → 판정반영 업로드(status 분포) →
  `/group-review`에서 패킷 선택·status2 판정 → 판정반영 재적용 → corrections 반영·status 전이 확인.

## 상태
- 단위테스트 통과 → **Pre-Done**. 수동 왕복 실동작 검증 후 **Done**.
