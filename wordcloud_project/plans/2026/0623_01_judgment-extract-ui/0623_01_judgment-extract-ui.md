# 0623_01 판정 패킷 추출 — 배치 체크박스 연동 (핸드오프 코퍼스와 동형)

> 상태: Pre-Done | 작성일: 2026-06-23 | 구현·단위검증 완료, 내부망 실배치 검증 대기
> 작업 유형: 기능 개선/신규 기능 (type-b) · 핵심가치: 긍↔부 오분류 0 · plans 배포 제외(가명 텍스트만)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-23 | 신규 | 최초 작성 |
| 2026-06-23 | §1·§2·§3·§4 | 초기 업로드 로딩 표시 + 마진 다중(0.05/0.10/0.15) 검색형 추출 추가 |
| 2026-06-23 | 구현 | 전 기능 구현 + 단위/회귀 통과(긍↔부 0). Pre-Done(내부망 실배치 검증 대기). |

## 배경 및 목적

판정 패킷(어려운 문장 → AI 판정 → 삽입) 기능은 **백엔드 라우트만** 존재하고 **UI·저장 진입점이 없다**. 그래서 메타데이터를 생성해도 "추출된 데이터"가 **어디에도 남지 않는다**(현 `/judgment/extract`는 호출 시 파일을 다운로드만 하고 서버에 저장 안 함). 사용자 요구: **핸드오프 코퍼스와 똑같이** 배치 화면에서 체크박스로 켜고, 배치 저장 흐름에서 자동으로 **고정 위치에 저장**되게 한다.

## 1. 요구사항

1. 메타데이터 배치 화면에서 **핸드오프 코퍼스 체크박스가 있는 동일 위치**에, 판정 패킷 추출 체크박스를 **나란히** 추가한다.
2. **두 체크박스(핸드오프 + 판정 패킷) 모두 기본 체크(checked)** 상태로 한다. (현재 핸드오프는 기본 미체크 → 함께 변경)
3. 배치 처리 중/후 판정 패킷이 **고정된 데이터셋 경로에 저장**되게 한다(핸드오프와 동형 규약: plans 하위, 가명 텍스트만).
4. KoTE 재실행 0 (저장된 `sentence_emotion_cache` 재사용). O(n). 긍↔부 0 게이트 불변.
5. **초기 입력 업로드 로딩 표시**: 파일/폴더 업로드(`/api/batch/upload`) 응답 전까지 "업로드·분석 중" 인디케이터를 띄워 멈춘 것처럼 보이지 않게 한다.
6. **마진 다중 추출(검색형)**: 단일 0.05 대신 **3개 마진(0.05/0.10/0.15)을 동시 산출**해 사용자가 적정 마진을 비교·선택할 수 있게 한다. **기본 추출/판정 초점은 0.05** 유지.

## 2. 현재 시스템 분석 (코드 실측)

### 핸드오프 코퍼스(레퍼런스 패턴, 0622_01)
- **UI**: `web/templates/metadata_batch.html:361-367` — `batch-name-card` 안 `<input type="checkbox" id="acqHandoffEnabled">` (기본 미체크) + 라벨 입력 `acqHandoffLabel` + 저장 위치 안내 문구.
- **JS**: `web/static/js/metadata_batch.js:762-763` — payload에 `acq_handoff_enabled`, `acq_handoff_label` 포함.
- **배치**: `src/services/batch_processor.py:834-836` 플래그 읽기 → `:902-913` 영속 직후 루프에서 `build_records_from_metadata(_meta)` + `append_handoff_records(label, batch_id, recs)` 호출.
- **서비스**: `src/services/acquired_handoff.py` — `resolve_handoff_path`/`build_records_from_metadata`/`append_handoff_records`. 저장 루트 고정 `plans/_datasets/kote_finetune/emotion/handoff/<label>/<batch_id>.jsonl` (경로 탈출 차단).

### 판정 패킷(기존 자산)
- **서비스**: `src/services/judgment_packet_service.py` — `build_judgment_packet(batch_id=None, margin=0.05, limit=None)` → `(packet, quarantined)`. 내부 `_load_pseudonymized_evals(batch_id)`가 DB(`evaluations`)에서 **db_id 포함** 재로드 후 `select_hard_sentences(ev, db_id, existing_corr, margin)`로 하드케이스 추출. 패킷은 자기설명(`_stages`/judge.rules/output_schema), 키=`{db_id, sent_idx}`, 실명/원본 ID 없음 + PII 게이트.
- **라우트**: `src/routes/perspective_routes.py:596` `POST /judgment/extract`(다운로드만, **저장 안 함**), `:628` `/judgment/apply`(업로드→`evaluations.sentiment_corrections` in-place). 둘 다 `_is_admin()` 게이트.
- **UI**: 템플릿/JS 전체 검색 결과 **0건**(진입점 없음 — 본 계획서가 채움).

### 초기 입력 업로드 (로딩 표시 부재 — 실측)
- `metadata_batch.js:1466` 파일 업로드 `change` 핸들러, `:35 selectFolder()` 폴더 업로드 — **둘 다 `fetch('/api/batch/upload')` 호출과 응답 사이 로딩 표시가 전혀 없다.** 대용량(수십~수백 MB) 파싱 동안 화면 무반응 → "멈춘 줄" 오인. 응답 `.then`에서 비로소 `fileInfo`/`folderInfo` 노출.

### 마진 의미 (실측)
- `select_hard_sentences(ev, db_id, existing_corr, margin)` (`judgment_packet_service.py:101`): 하드 = `pol_flip`(보정후 극 ≠ KoTE 극) **또는** `low_margin`(`abs(pos-neg) < margin`). 마진이 클수록 경계 문장을 더 넓게 포획. 각 item은 이미 `kote=[pos,neg,neu]` 보유 → `gap=|pos-neg|` 산출 가능.

### 핵심 설계 제약 (실측)
- 배치 영속은 `batch_processor.py:885` `upsert(_eid, _meta, evaluations, batch_id)` → 반환 `(_inserted, _skip)`. **db_id 미반환.** 판정 패킷은 삽입 시 db_id가 필수 → **영속 직후 루프(핸드오프 위치)에서 패킷을 만들기엔 db_id가 없다.**
  - → **해결**: 패킷 생성은 **배치 루프 종료 후 1회**, 기존 `build_judgment_packet(batch_id)`를 그대로 호출(DB에서 db_id 포함 재로드). 이미 영속 완료된 상태라 전수 포함. KoTE 재실행 없음(cache 재사용). 이로써 db_id 문제·중복코드 없이 기존 로직 100% 재사용.

## 3. 구현 상세

### 3.1 프론트엔드
- **`metadata_batch.html`**:
  - 기존 핸드오프 체크박스에 `checked` 추가(요구사항 2).
  - 핸드오프 `batch-name-card` **바로 아래** 새 `batch-name-card` 추가:
    - `<input type="checkbox" id="judgmentExtractEnabled" checked> 판정 패킷 추출 (어려운 문장 AI 판정용)`
    - 안내: 저장 위치 `plans/_datasets/kote_finetune/eval/judgment/<라벨>/<batch_id>.json`
    - 라벨 입력 `judgmentExtractLabel`(미입력 시 default).
    - 안내 문구에 **마진 3단 동시 추출(0.05/0.10/0.15) + 기본 0.05** 명시. 별도 마진 입력칸 없음(밴드 고정) — 배치 완료 후 결과에 밴드별 건수가 표시되어 검색·선택.
- **`metadata_batch.js`** (`:762` payload): `judgment_extract_enabled`, `judgment_label` 추가.
- **초기 업로드 로딩 표시** — `metadata_batch.js`:
  - 파일 업로드(`:1466`)·폴더 업로드(`:35 selectFolder`) 두 핸들러에서 `fetch('/api/batch/upload')` **직전 로딩 인디케이터 ON**, `.then`/`.catch` 양쪽에서 **OFF**(누락 방지). 멈춘 것처럼 보이지 않게.
  - 표시 형태: 업로드 영역에 "업로드·분석 중…" 텍스트 + 스피너(전면 블러 오버레이 금지 — Nav/버튼만 비활성 규약 준수). `metadata_batch.html`에 해당 인디케이터 요소 추가.
- **배치 완료 결과(밴드 표시)**: SSE 완료 이벤트에서 `judgment_count`·`judgment_bands` 수신 시, 결과 영역에 "판정 패킷 N건(0.05: a · 0.10: b · 0.15: c · flip: d) → 저장 경로" 표기.

### 3.2 백엔드
- **마진 밴드 태깅(추가만)** — `judgment_packet_service.py`:
  - `_MARGIN_BANDS = (0.05, 0.10, 0.15)` 상수. `select_hard_sentences`를 **가장 넓은 마진(0.15)으로 1회** 호출하되, 각 item에 `gap = round(abs(pos-neg), 4)`와 `margin_band`(gap이 속하는 최소 임계값; pol_flip은 `'flip'`)를 기록. 시그니처·기존 키 불변, 필드 추가만 → **O(n) 1회로 3개 마진 동시 표현**.
  - `build_judgment_packet(batch_id, margin=max(_MARGIN_BANDS), ...)` 후 패킷에 `_margin` 요약 추가: `{default: 0.05, bands: {"0.05": n1, "0.10": n2, "0.15": n3, "flip": nf}}`. 재추출 없이 사용자가 밴드로 검색·선택.
- **저장 함수 `save_packet_file(packet, label, batch_id) -> path`(신규, 추가만)** — `judgment_packet_service.py`:
  - 저장 루트 **고정** `plans/_datasets/kote_finetune/eval/judgment/<label>/<batch_id>.json`. `acquired_handoff._safe_segment` 동형 경로 탈출 차단. 디렉토리 자동 생성, 패킷 dict를 UTF-8 JSON 기록(멱등 덮어쓰기 — 배치 1회 종단 산출이라 append 불요).
- **배치 `batch_processor.py`**:
  - `:834` 부근 플래그 읽기 추가: `_judgment_enabled = data.get('judgment_extract_enabled', True)`(기본 True), `_judgment_label = (data.get('judgment_label') or 'default')`.
  - **배치 루프 종료 후**(전 직원 영속 완료, 작업서 마감 직전):
    ```
    if _judgment_enabled:
        packet, quarantined = build_judgment_packet(batch_id, margin=max(_MARGIN_BANDS))
        path = save_packet_file(packet, _judgment_label, batch_id)
        batch_processing_state['judgment_count'] = len(packet['items'])
        batch_processing_state['judgment_bands'] = packet['_margin']['bands']
    ```
  - try/except로 감싸 실패해도 배치 본류 불방해(핸드오프와 동일 보호).
- **라우트**: 변경 없음(`/judgment/extract`·`/apply` 그대로). 배치 자동 저장이 기본 경로, 다운로드는 기존 라우트로도 가능.

## 4. 저장 위치 (요구사항 3 — 핸드오프와 동형)

| 산출물 | 고정 경로 |
|--------|-----------|
| 핸드오프 코퍼스(기존) | `plans/_datasets/kote_finetune/emotion/handoff/<label>/<batch_id>.jsonl` |
| **판정 패킷(신규)** | `plans/_datasets/kote_finetune/eval/judgment/<label>/<batch_id>.json` |

- `eval/` 선택 이유: 검증·하드케이스 산출물 폴더(이미 `validation_candidates_*.jsonl` 거주). 판정 패킷은 사람/AI 검토용 = eval 성격.
- plans 폴더는 `build_deploy.ps1` 제외 대상(0623 수정 반영) → **내부망 배포 패키지에 미포함**(유출 방지). 가명 텍스트만 기록.

## 5. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `_MARGIN_BANDS` + `select_hard_sentences` 밴드 태깅(gap·margin_band) + `_margin` 요약 | — |
| 2 | `save_packet_file` 추가(경로 고정·탈출 차단) + 단위 테스트 | — |
| 3 | `batch_processor` 플래그 읽기 + 루프 종료 후 패킷 생성·저장(try/except, bands 상태) | 1,2 |
| 4 | `metadata_batch.html` 체크박스 2종(둘 다 checked) + 안내 + 로딩 인디케이터 요소 | — |
| 5 | `metadata_batch.js` payload 2필드 + 업로드 로딩 ON/OFF(파일·폴더) + 완료 밴드 표기 | 4 |
| 6 | 배치 1건(소규모) 실동작 검증 → 저장 경로 패킷 생성·밴드 카운트·업로드 로딩, 긍↔부 0 회귀 | 1-5 |

## 6. 테스트 계획

- 단위: `save_packet_file` 경로 고정/탈출 차단(`../` 거부), 패킷 직렬화 왕복. 밴드 태깅(gap별 margin_band 분류·pol_flip='flip')·`_margin.bands` 카운트 정확성. (`test/` 하위)
- 통합: 인메모리/소규모 배치 → `judgment_extract_enabled=True`면 지정 경로에 패킷 파일 생성, `items` 키가 `{db_id, sent_idx}`·실명 없음, PII 격리 반영, 밴드 카운트 노출.
- UI 수동: 대용량 업로드 시 로딩 표시 ON→응답 후 OFF(파일·폴더), 오류 시에도 OFF.
- 회귀: 기존 `0617_01/test/run_*_regression.py` 긍↔부 0 불변(서비스 분류 로직 무변경 — 밴드는 메타 필드 추가만).

## 7. 리스크 / 가드

- **db_id 의존**: 배치 종료 후 호출이므로 전 직원 영속 완료 전제 — 루프 완전 종료 지점에 배치(중간 호출 금지).
- **대량(1.9만)**: `build_judgment_packet`은 batch_id로 1회 전수 스캔 O(n)·KoTE 0. 메모리: items만 적재(하드케이스 한정이라 부분집합).
- **배포 유출**: 저장 루트는 plans 하위 고정·경로 탈출 차단. 그 외 위치 금지.
- **핵심가치**: 서비스 분류 로직 무변경 → 긍↔부 0 불변. 패킷 judge 규칙에 "긍↔부 0·중립↔긍정 허용" 이미 명시됨.

## 8. 범위 밖

- needs_human 모달 UI(삽입 후 사람 확정 큐) — 별도. 본 계획은 **추출 저장 + 체크박스**까지.
- `extract_pending` 상태 훅(메타데이터 저장 시 마킹) — 배치 종단 일괄 추출로 대체하므로 불요.
