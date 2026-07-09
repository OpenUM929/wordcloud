# 계획서 — 메타데이터 배치 저장 화면 개선 + 배치 재시작 잠금 버그

> 상태: Partial (게이트 대기) | 작성일: 2026-07-01
> 작업 유형: B (기능/UI 개선) + 내부에 A (버그) 1건 포함 — §3.A
> 대상 화면: `메타데이터 생성 (배치 처리)` — `web/templates/metadata_batch.html` §step4
> 요구 원문: `260625.txt` (6개 항목)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-01 | 신규 작성 | 260625.txt 6개 항목(폴더이동·재시작잠금버그·step4 레이아웃·불필요 멘트) 계획화 |
| 2026-07-01 | §2.2·§2.3·§3.1·§3.2·§3.A.3·§3.A.4·§4·§6·§7·§8 | [코드대조 검토] 7개 보완: ① `judgment_count` SSE 미도달 원인·자동해소 명시(§2.3→§3.1), ② 핸드오프 경로 계산(`resolve_handoff_path` 재호출) 보완(§3.1), ③ 폴더 이동 엔드포인트 화이트리스트 구체 명세(§3.1·§7), ④ Resume 테스트 강화(§6 #7), ⑤ Stage6 성능 로그 영구 포인트 권장(§3.A.4), ⑥ 후처리 단계 `proc-step` 변경·`batch-name-card` margin 제거 명시(§3.2·§3.4·§3.A.3), ⑦ 게이트 미통과 상태 상단 주석 추가 |
| 2026-07-01 | §3.A.3·§5·§6·§7 | [재검토·코드대조] Option A 정정: `batch_service._run_batch_process:280`이 반환 직후 이미 `completed=True` 설정함을 실측 → "L1081 앞 신규 set"은 **L280과 중복**이므로 폐기, **L1026 삭제만**으로 정렬(§3.A.3·§5). 후처리 중 예외 시 잠금 해제 경로 검증 추가(§6 #9). Stage6 재스캔이 임계구역 내 O(n) 유지 확인 리스크 추가(§7). |
| 2026-07-01 | §3.A.4·§3.1·§3.2·§3.3·§3.4·§5 | [구현] ① Stage6 영구 로깅 추가(§3.A.4), ② SSE에 handoff_path·judgment_path·건수 필드 추가(§3.1·`batch_events.py`), ③ 핸드오프 경로 state 저장(§3.1·`batch_processor.py`), ④ 세 카드 flex row 33.3%·동일높이(§3.2·`metadata_batch.html`), ⑤ 처리설정 체크박스 한 행(§3.3), ⑥ `.step-status` 제거(§3.4), ⑦ 결과영역 경로표기+📂열기+📋복사(§3.1·`metadata_batch.js`), ⑧ `POST /api/batch/open-folder` 엔드포인트(화이트리스트+관리자가드)(§3.1·§5). **§3.A.3은 게이트 대기 중.** |

---

> ⛔ **§3.A(항목2)는 런타임 게이트 미통과 상태** — 정적 근거는 매우 강력하나(§2.3 실행 순서 결정적), 본 계획서만으로 원인 확정·수정 불가. 진단(§3.A.4) → 게이트 통과 후에만 §3.A.3 구현에 진입한다.
> 
> **동기**: 0625_01 오진(정적 분석만으로 수정했다가 실제 원인과 달랐던 사례) 교훈. 항목 2는 정적 근거가 명확하지만 절차를 건너뛰지 않는다.

---

## 1. 배경 및 목적

`260625.txt` 6개 항목. 원문 그대로 번호 보존:

1. **[기능]** 「핸드오프 코퍼스 적립」·「판정 패킷 추출」에 **생성된 폴더로 이동하는 기능** 추가.
2. **[버그]** 배치 완료 후 다른 신규 입력 파일로 신규 배치를 만들면 **"다른 배치 처리가 이미 실행 중입니다."** 가 뜨며 배치가 동작 안 함. **서버가 멈추는 것 같음.**
3. **[UI]** 배치명칭·핸드오프·패킷 위치 설정을 **한 행에 각 33.3%** 로 배치 → 한 행에서 셋 다 표현.
4. **[UI]** 3항의 세 카드 **높이를 가장 높은 것에 맞춤**.
5. **[UI]** 「처리 설정」 옆에 「데이터 정제 적용」·「감정 분석 적용」 체크박스를 **한 행**에 표기.
6. **[UI]** `1단계: 데이터 업로드 대기 중 … 4단계: 배치 저장 대기 중` — **내용을 업데이트하지 않을 거면 불필요한 멘트** → 정리.

목적: 배치 저장 화면(step4)의 레이아웃 밀도·정보 노출을 개선하고, 데이터셋 산출물(핸드오프/판정 패킷) 접근 동선을 추가하며, **연속 배치 실행을 막는 재시작 잠금 버그**를 해소한다.

---

## 2. 현재 시스템 분석 (코드 실측)

### 2.1 step4 저장 화면 구조 — `web/templates/metadata_batch.html`

- L371~399 `#step4` 내부:
  - L374~376 「처리 설정」 + 체크박스 2개(`#enablePreprocessing`, `#enableEmotionAnalysis`)가 각각 `<label>…</label><br>` 로 **세로 나열**.
  - L381~385 `.batch-name-card` — 배치 명칭(`#batchDisplayName`).
  - L386~392 `.batch-name-card` — 핸드오프(`#acqHandoffEnabled` + `#acqHandoffLabel`).
  - L393~399 `.batch-name-card` — 판정 패킷(`#judgmentExtractEnabled` + `#judgmentExtractLabel`).
  - → 세 카드가 **세로로 쌓임**(각각 `margin:15px 0`, `.batch-name-card` 정의 L151).
- L238~243 `.step-status` — `#step1-status`~`#step4-status` **4줄 정적 텍스트**.
  - JS 검색 결과 `step1-status`~`step4-status` 를 **갱신하는 코드 없음**(`metadata_batch.js` 내 `getElementById('stepN-status')` 미존재). → 항목 6의 "업데이트 안 함" 사실 확인.
  - 별개로 L229~230 `#current-step-info` 는 `updateStepButtons()`(js L312)에서 **실제 갱신됨** — 유지 대상.

### 2.2 산출물 경로 — 실측

- 핸드오프: `src/services/acquired_handoff.py:35 resolve_handoff_path(dest_label, batch_id)` → `plans/_datasets/kote_finetune/emotion/handoff/<label>/<batch_id>.jsonl` (L39). `append_handoff_records`(L70)는 건수만 반환.
- 판정 패킷: `batch_processor.py:1063` `save_packet_file(...)` 반환 경로를 `batch_processing_state['judgment_path']`(L1066)에 저장.
- **현재 SSE는 두 경로를 클라이언트로 전달하지 않음** — `batch_events.py:50~65` `data` 딕셔너리에 `judgment_path`·핸드오프 경로·`judgment_count`·`acq_handoff_count` **미포함**(전달 필드는 `batch_dir` 뿐).
- 서버 측 폴더 열기 기능(`os.startfile` 등) **부재**(grep 0건).

### 2.3 배치 재시작 잠금 — 실측 (항목 2 관련)

- 전역 잠금: `batch_service.py` `_batch_busy` / `_batch_lock`.
  - `process_batch_metadata`(L305): L313~316 `if _batch_busy: return {'error':'다른 배치 처리가 이미 실행 중입니다.'}, 429` → 아니면 `_batch_busy=True` 후 백그라운드 스레드(`_run_batch_process`) 시작.
  - `_run_batch_process`(L266): `try` 안에서 `process_batch(...)` 호출, **`finally`(L300~302)에서만** `_batch_busy=False`. 즉 **잠금은 `process_batch` 가 반환해야 풀린다.**
- `process_batch`(`batch_processor.py:521`) 후반부 실행 순서(실측):
  - **L1026 `batch_processing_state['completed']=True`** (progress=100).
  - L1029~1038 Stage5 욕설 저장 → L1042~1045 batch_summary → L1047~1053 작업서 완료 →
  - **L1058~1071 Stage6 판정 패킷 추출**(`build_judgment_packet(batch_id=...)` — 영속 평가를 batch_id로 재로드·재스캔. **대량 배치에서 무거움**) →
  - L1073~1076 staging 정리 → L1079 VRAM 모니터 종료 → **L1081 `return`**.
- SSE 스트림: `batch_events.py:49~75` 루프 → **L69 `if completed: break`**. 즉 `completed=True`(L1026) 직후 첫 tick에서 스트림 종료 → 클라(`metadata_batch.js:832`)가 EventSource close + "처리 완료!" 표시.

> **관찰되는 구조적 모순**: UI는 L1026 시점에 "완료"로 끊기지만, 백그라운드 스레드는 그 이후 **Stage6(판정 패킷) 등 후처리를 계속 수행**하며 그동안 `_batch_busy==True` 가 유지된다. 사용자가 "완료" 화면을 보고 신규 배치를 시작하면 L314 가드에 걸려 **429** 를 받는다. (부수 확인: `judgment_count`/`judgment_bands` 는 L1064~1065 에서 `completed` 이후 설정되므로, 스트림이 이미 끊겨 `metadata_batch.js:838` 의 "판정 패킷 N건" 표기도 대개 도달하지 못한다.)

---

## 3. 구현 상세

### 3.A [항목 2] 배치 재시작 잠금 버그 — **Type-A (증거 우선 · 게이트 적용)**

#### 3.A.1 문제 정의

- **관찰된 실패 산출물**: 신규 배치 시작 시 응답 `{'error':'다른 배치 처리가 이미 실행 중입니다.'} , HTTP 429` (`batch_service.py:315`). 사용자 체감 "서버가 멈추는 것 같음".
- **증상**: (a) 직전 배치가 UI상 "완료"로 보인 뒤, (b) 다른 CSV로 신규 배치 시작 → 429, 배치 미동작. (c) 그 사이 서버 응답 지연.
- **재현 조건(가설)**: 판정 패킷 추출(Stage6)이 켜진(`judgment_extract_enabled=true`, 기본값) 대량 배치 완료 직후, UI "완료" 표시를 보고 **곧바로** 다른 파일로 신규 배치 시작.

#### 3.A.2 원인 분석 — ⛔ 게이트 미통과 (런타임 확증 필요)

> 서버 무단 실행 금지 지침에 따라 **본 계획서 작성 단계에서 서버를 실행해 재현하지 않았다.** 아래는 **정적 증거로 매우 강하게 지지되는 유력 가설**이며, §3.A.4 진단 절차로 런타임 3요건을 채운 뒤에만 "원인 확정" 후 수정 구현에 진입한다.

- **유력 가설 (정적 근거 확정적)**: `completed=True`(L1026)와 `_batch_busy=False`(반환 후 `finally`, L300~302) **사이에 Stage6 판정 패킷 추출 등 무거운 후처리가 존재**한다(§2.3). UI "완료"와 잠금 해제가 **시간적으로 어긋나** 사용자가 그 창(window)에서 신규 배치를 시작하면 429. "멈춤" 체감은 Stage6가 단일 스레드(GIL)로 CPU/IO를 점유하기 때문.
- **정적 근거**: 실행 순서가 코드상 결정적 — L1026(completed) → L1058(judgment) → L1081(return) → `finally` busy 해제. 순서 자체가 증거.
- **반증 실험(가설이 틀렸다면)**: 판정 패킷을 **끈**(`judgment_extract_enabled=false`) 배치에서는 후처리 꼬리가 짧아 429 재현이 **안 되거나 확률이 급감**해야 한다. 또한 신규 배치 시작을 완료 표시 후 충분히(후처리 완료까지) 지연시키면 429가 사라져야 한다. → 이 두 조건에서 여전히 429가 재현되면 본 가설은 기각(다른 원인: 예외로 `finally` 미도달 여부·좀비 스레드 등 재조사).

#### 3.A.3 수정 방안 (게이트 통과 후 구현) — 권장 Option A

- **Option A (권장) — "완료" 단일 진실원을 후처리 끝으로 이동 + 후처리 단계 가시화**:
  - `batch_processor.py`: **L1026 의 `completed=True` 를 삭제**한다. **신규 설정 추가 불요** — 호출부 `batch_service._run_batch_process:277~280`이 `process_batch` 반환(status==200) 직후, 즉 Stage6·staging 정리·VRAM 종료·`return`이 모두 끝난 시점에 **이미 `completed=True` 를 설정**하고 그 다음 `finally`(L300~302)에서 `_batch_busy=False` 로 해제한다. 따라서 **L1026 한 줄 삭제만으로** "완료"·잠금 해제가 자동 정렬된다(L1081 앞에 새 `completed=True` 를 넣으면 L280 과 **중복 설정**이 되므로 넣지 않는다).
  - 그 사이 후처리 구간에 사용자 대기 신호 제공 — `status_message`/`progress` 를 유지한 채 예: `'후처리(판정 패킷 추출) 중…'` 로 갱신(진행 표시는 계속 보이게, 전면 오버레이 금지 — 메모리 원칙).
  - **`processingStepsIndicator`(metadata_batch.html:435~464) 단계 호환**: 현재 6단계(데이터 수집~완료). 후처리 구간이 별도 단계로 보이도록 7단계로 확장하거나, 기존 "완료" 원형(step6)을 `후처리 중` 으로 변경하고 마지막에 진짜 완료 원형(✓) 추가. 후자가 단계 수 변화 최소화. 후처리 step 추가 시 `data-step`/`data-group` 일관성 유지.
  - 효과: SSE 종료(`batch_events.py:69`)와 `_batch_busy` 해제가 **정렬** → "완료" 표시 시점엔 잠금이 이미 풀려 있어 429 소멸. 부수적으로 `judgment_count`/`judgment_bands`(L1064)도 완료 tick 전에 채워져 §2.3 표기 누락도 해소.
- **Option B (대안, 후처리가 과도히 길 때)**: Stage6를 잠금 임계구역 밖으로 분리(후처리 전용 후속 스레드). 배치 간 Stage6 중첩 위험 → 별도 잠금 필요. 복잡도↑ → 우선순위 낮음.
- **Option C (보강, 단독 불가)**: 429 응답 문구를 상태 기반으로 정교화("이전 배치 후처리 중 — 잠시 후 재시도"). Option A와 병행 가능한 UX 보강.

#### 3.A.4 진단 절차 (게이트 3요건 충족용 — 사용자 승인 하 실행)

1. `_run_batch_process`/`process_batch` 후처리 구간에 진입·이탈 타임스탬프 로그 추가(임시) → completed=True 이후 Stage6 소요시간 계측.
   - **권장 (향후 재활용)**: 영구 로깅 포인트로 남길 것 — `logging.info(f'[batch] stage6 start batch_id={bid}')` / `logging.info(f'[batch] stage6 end batch_id={bid} dur={dt}s')`. 대시보드·성능 모니터링에 재사용 가능.
2. 실제 대량 CSV로 배치 완료 직후 신규 배치 시도 → 429 재현 및 그 순간 `_batch_busy` 값·현재 실행 라인 관측.
3. 반증(§3.A.2): 판정 OFF·지연 시작 두 조건에서 429 소멸 확인.
- 3요건 충족 시 §3.A.3 Option A 구현.

### 3.1 [항목 1] 산출물 폴더 이동 기능

- **경로 확보**:
  - 판정 패킷 경로(`judgment_path`): `batch_processing_state`에 이미 존재(L1066) — `save_packet_file` 반환값.
  - 핸드오프 경로(`handoff_path`): `acquired_handoff.append_handoff_records`(L70)는 **건수만 반환**. 경로를 state에 기록하려면 `batch_processor.py` 후처리 구간에서 `resolve_handoff_path(label, batch_id)`를 **재호출**하여 경로를 구한 뒤 `handoff_path`·`acq_handoff_count` 함께 저장.
- **SSE 전달**: 두 경로·건수를 `batch_events.py:50~65` `data` 딕셔너리에 추가 (`handoff_path`, `judgment_path`, `acq_handoff_count`, `judgment_count`).
  - `judgment_count`/`judgment_bands`는 현재 `completed=True`(L1026) **이후에 설정**(L1064~1065)되어 SSE 스트림이 이미 종료된 상태 → 클라에 미도달(§2.3). **§3.A Option A로 `completed` 이동 시 자동 해소**되며, 이는 SSE 필드 추가의 근거이기도 함.
- **프론트(step4 결과 영역)**: 핸드오프/판정 각 카드의 결과 표기에 **경로 텍스트 + 이동 버튼** 추가(`processingResults` 렌더 `metadata_batch.js:860~886`).
- **이동 방식 — 미결(§8 Q1)**: 내부망·데스크톱 단일기 특성상 후보 (a) 서버 `os.startfile(dir)` 로 탐색기 열기(신규 가드형 엔드포인트) / (b) 경로 클립보드 복사 버튼 / (c) 앱 내 파일 나열. 권장 (a)+(b) 병행. (a) 채택 시 **경로 화이트리스트** 필수:
  - 허용 루트: `plans/_datasets/kote_finetune` (절대경로: `os.path.realpath`로 정규화)
  - 검증: `os.path.commonprefix([허용루트, 요청경로]) == 허용루트` + `..` 트래버설 차단
  - 구현: `batch_routes.py` 신규 엔드포인트 `POST /api/batch/open-folder` + `_is_admin()` 가드 (경로는 화이트리스트 검증 후 `os.startfile`)

### 3.2 [항목 3·4] 세 설정 카드 한 행 33.3% + 높이 정렬

- `#step4` 의 세 `.batch-name-card`(배치명칭 L381 / 핸드오프 L386 / 판정 L393)를 **flex row 컨테이너**로 감싼다.
  - 컨테이너: `display:flex; gap:var(--space-3); align-items:stretch;` → `align-items:stretch` 로 **세 카드 높이 = 가장 높은 카드**(항목 4 충족).
  - 각 카드: `flex:1 1 0; min-width:0;` → 균등 33.3%.
- 반응형/모바일 고려 없음(내부망 데스크톱 전용 — 메모리 원칙). 고정 3열.
- 기존 `.batch-name-card` 의 `margin:15px 0`(L151)은 flex row 컨테이너 안에서 `margin:0`으로 오버라이드(컨테이너 `gap`으로 간격 대체). 외부 `.batch-name-card` 정의는 유지(다른 곳에서 사용 중이면 영향 방지).

### 3.3 [항목 5] 처리 설정 체크박스 한 행

- L374~376 「처리 설정」 헤더 + `#enablePreprocessing`·`#enableEmotionAnalysis` 를 **한 행(flex row)** 으로: 헤더 옆에 두 체크박스를 inline 배치.
- 마크업: `<div class="proc-settings-row" style="display:flex; align-items:center; gap:var(--space-4);">` 안에 `<h3>처리 설정</h3>` + 두 `<label>`. `<br>` 제거.

### 3.4 [항목 6] 불필요한 단계 멘트 정리

- L238~243 `.step-status`(`#step1-status`~`#step4-status`) — **JS 미갱신 정적 4줄**. 제거.
- 상단 `.step-indicator`(L206~226, 1~4 원형 진행표시)와 `#current-step-info`(L229~230, 실제 갱신됨)는 **유지**.
- 제거 대상이 JS에서 참조되지 않음을 재확인(§2.1) 후 삭제 → 회귀 없음.

---

## 4. 구현 순서

| 순서 | 작업 내용 | 유형 | 의존 |
|------|-----------|------|------|
| 1 | §3.A.4 진단 → 게이트 통과(429 원인 확정) | A진단 | — |
| 2 | §3.A.3 Option A: **L1026 `completed=True` 삭제**(신규 set 없음 — `batch_service:280`에 위임) + 후처리 status | A수정 | 1 |
| 3 | §3.1 상태/ SSE 에 handoff_path·judgment_path·건수 추가 | B | 2 |
| 4 | §3.2/§3.3/§3.4 step4 템플릿 레이아웃(33.3%·높이·체크박스행·멘트제거) | B/UI | — |
| 5 | §3.1 프론트: 결과영역 경로 표기 + 이동 버튼(+엔드포인트/가드, §8 Q1 확정 후) | B | 3,4 |
| 6 | 검증(§6) | — | 2~5 |

> 4번(순수 UI)은 1~3과 독립 → 병행 가능. 5번은 §8 Q1(이동 방식) 결정 필요.

---

## 5. 영향도 분석

| 파일 | 변경 | 비고 |
|------|------|------|
| `src/services/batch_processor.py` | **L1026 `completed=True` 삭제**(신규 set 추가 없음 — 반환 후 `batch_service:280`이 이미 설정), 후처리 status, handoff_path/건수 state 기록 | 핵심 로직 — 회귀 주의(완료 판정 타이밍) |
| `src/services/batch_events.py` | SSE `data` 에 `handoff_path`·`judgment_path`·`acq_handoff_count`·`judgment_count` 추가 | 필드 추가만(기존 필드 불변) |
| `src/services/batch_service.py` | (Option C 채택 시) 429 문구 정교화 | 선택 |
| `web/templates/metadata_batch.html` | §step4 레이아웃(카드 3열·체크박스행), `.step-status` 제거, 결과영역 경로/이동 버튼 | UI |
| `web/static/js/metadata_batch.js` | 결과 렌더에 경로/이동 버튼, 신규 SSE 필드 사용 | `resultsSummary` 렌더 확장 |
| `src/routes/batch_routes.py` (+가드 모듈) | (§8 Q1=(a) 채택 시) 폴더 열기 엔드포인트 신규 | 경로 화이트리스트 필수 |

- **미변경**: 배치 처리 파이프라인 로직(Stage1~4), 감정 분석, 가명화 경로. 재시작/Resume 경로(`resume_batch_metadata`)는 동일 진입점 재사용 — completed 타이밍 변경 영향 확인 필요(§6).

## 6. 테스트/검증 계획

| # | 시나리오 | 기대 |
|---|----------|------|
| 1 | 판정 ON 대량 배치 완료 → 즉시 신규 배치 시작 | 429 미발생, 신규 배치 정상 시작 (항목2) |
| 2 | 완료 tick 시 `judgment_count`/`bands` 표기 도달 | "판정 패킷 N건 …" 정상 표시 |
| 3 | 배치 완료 후 결과영역에 핸드오프/판정 경로 표기 + 이동 동작 | 경로 정확, 이동/열기 정상 (항목1) |
| 4 | step4 세 카드 한 행 33.3%·동일 높이 | 3열, 높이 = 최대 카드 (항목3·4) |
| 5 | 「처리 설정」 + 체크박스 2개 한 행 | 정렬 정상 (항목5) |
| 6 | `.step-status` 제거 후 `#current-step-info`·진행표시 정상 | 회귀 없음 (항목6) |
| 7 | Resume(이어서 배치) 경로 | completed 타이밍 변경 후에도 정상 완료. `resume_batch_metadata`는 `process_batch`(공통 경로)를 재사용하므로 `completed` 이동이 자동 정렬됨. 단, Resume 시작 시 작업서가 'running' 상태인지 확인 |
| 8 | 판정 OFF 배치 | completed 표시 정상, 후처리 멘트 미노출/즉시완료 |
| 9 | 후처리(Stage6/ staging 정리) 중 예외 발생 | `process_batch` raise → `_run_batch_process` except(L281)로 `error` 설정·`finally` 잠금 해제 → SSE `error` break, UI 멈춤 없음. 신규 배치 시작 가능 |

## 7. 리스크 및 제약

- **completed 타이밍 변경 = L1026 삭제(§3.A.3)**: 사용자가 100% 진행 후 후처리(판정 추출) 동안 대기하게 됨 → 반드시 후처리 status 문구로 "멈춘 것 아님"을 알린다. 전면 블러 오버레이 금지, 진행 가시화 유지(메모리 `busy_disable_not_block`). **부수 검증**: 클라(`metadata_batch.js:832`)의 완료 UI·EventSource close·`isProcessing=false`가 전부 `data.completed` 기준(≠`progress==100`)이므로 삭제 시 클라도 후처리 동안 완료로 전환되지 않음(전제 확인됨). 단 신규 배치 시작 시 `batch_processing_state['completed']`가 False로 **리셋**되는지 확인(기존 L1026 방식에서도 필요했던 초기화 — 회귀 아님).
- **대량(약 1.9만명) Stage6 소요**: 후처리가 길면 Option A 대기 체감↑ → 필요 시 Option B(분리 스레드) 재검토. 추적 로직 O(n) 이하 유지. **Stage6 진입/이탈 영구 로깅**(§3.A.4)으로 실측 데이터 확보 권장 — Option A vs B 결정 근거. 단, `build_judgment_packet(batch_id=)`가 영속 평가를 batch_id로 **재로드·재스캔**하므로 Option A에서는 이 재스캔이 임계구역(잠금 유지) 안에 남는다 — 19k 규모에서 재스캔 자체가 O(n) 이하인지 확인(O(n²) 금지, 메모리 `batch_scale_19k`).
- **폴더 이동 엔드포인트(§8 Q1=(a))**: 서버 FS 접근 → `plans/_datasets/kote_finetune` 화이트리스트·`os.path.realpath` 정규화·`commonprefix` 검증·`..` 트래버설 차단 필수. 엔드포인트는 `batch_routes.py` 신규 `POST /api/batch/open-folder` + `_is_admin()` 가드. `plans/`는 배포 제외이므로 내부망 dev 환경 전제.
- **후처리 단계 표시 불일치 리스크**: `processingStepsIndicator`(6단계)와 실제 `status_message` 단계 수가 안 맞으면 사용자 혼란 → §3.A.3 Option A 구현 시 indicator 동기화 필수.
- **버그 게이트**: §3.A는 런타임 재현 전 수정 금지(0625_01 오진 교훈). 정적 근거가 강하더라도 3요건 충족 후 구현.

## 8. 미결 결정사항 (구현 전 확정)

- **Q1 (항목1 이동 방식)**: (a) 서버 탐색기 열기(`os.startfile`+가드) / (b) 경로 복사 버튼 / (c) 앱 내 나열 — 권장 (a)+(b). 사용자 확정 필요.
- **Q2 (항목2 수정안)**: Option A(권장) vs B(분리 스레드). 진단서 Stage6 실측 소요로 결정.
