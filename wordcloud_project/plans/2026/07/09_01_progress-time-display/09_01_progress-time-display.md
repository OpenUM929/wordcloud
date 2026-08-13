# 계획서 — 진행 시간 및 예상 종료 시간 표시 기능 추가

> 상태: Doing | 작성일: 2026-07-09 | 업데이트: 2026-07-09 — 구현 완료(8/10), 수동 테스트 대기
> 작업 유형: B (기능 개선/신규 기능)
> 선행: 없음

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-07-09 | 전체 작성 | 신규 계획서 작성 (0708 → 0709 폴더번호 변경, 위치 수정) |

---

## 1. 배경 및 목적

사용자 요청:
1. **메타데이터 배치 처리** (`/metadata_batch`) — "배치 처리시작" 시 **예상 종료 시간**과 **현재 진행 시간** 표시
2. **그룹 분석 테스트** (`/perspective_test`) — "제출용 저장"(`saveDeploy`), "메트릭스 저장"(`generateMatrix`) 시 **예상 종료 시간**과 **현재 진행 시간** 표시
3. **감정 재판정 기능 검증** — 워드클라우드 분석 결과에 따라 긍정/부정/중립을 사용자가 재판정 가능한데, 모델 업그레이드와 알고리즘 변경에 따라 이 기능 검증 필요

---

## 2. 현재 시스템 분석

### 2.1 메타데이터 배치 처리 (`/metadata_batch`)

**관련 파일:**
- `web/templates/metadata_batch.html` — 4단계 화면, `processingStatus` 영역(진행바·단계 원형·텍스트)
- `web/static/js/metadata_batch.js` — `startBatchProcessing()` → `openSseAndListen()` SSE 수신
- `src/services/batch_processor.py` — `process_batch()` 메인 루프, `batch_processing_state` 전역 상태 갱신
- `src/services/batch_events.py` — `stream_batch_events()` 0.5초 폴링 SSE 스트림
- `src/routes/batch_routes.py` — `/api/batch/process`, `/api/batch/events`

**현재 진행 표시:**
- `batch_processing_state` 딕셔너리에 `current_step`, `progress`, `status_message`, `processed_employees`, `total_employees` 등 갱신
- 프론트엔드 `metadata_batch.js:820-860` SSE `onmessage`에서 `data.step`, `data.progress`, `data.status` 받아 진행바·단계 원형·텍스트 갱신

### 2.2 그룹 분석 테스트 (`/perspective_test`)

**관련 파일:**
- `web/templates/perspective_test.html` — `generateMatrix()`(매트릭스 저장), `saveDeploy()`(제출용 저장)
- `src/routes/perspective_routes.py` — `/api/perspective/matrix`, `/api/perspective/matrix/save-deploy`, `/api/perspective/deploy-session/*`
- `src/services/deploy_session_service.py` — 청크 기반 세션 관리, SQLite(`deploy_sessions`, `deploy_tasks`)로 진행 추적
- `src/services/perspective_service.py` — `save_to_deploy()`, `generate_perspective_matrix()`

**현재 진행 표시:**
- `generateMatrix()`: `renderProgress()`로 로컬 프로그레스 바·상태 라인 렌더링(워커 4개 병렬, `yieldToRenderer`로 UI 양보)
- `saveDeploy()`: `renderProgress()` 유사 패턴 + `deploy_session_service` 세션으로 청크 단위 진행·완료·실패 집계
- 두 함수 모두 `showBusyOverlay('…완료까지 페이지를 벗어나지 마세요')`로 전면 차단 + `updateBusyOverlay(statusText)`로 상태 텍스트 갱신

### 2.3 감정 재판정 기능 (기존 구현 — 소스 분석 기반)

**데이터 플로우:**
```
사용자 UI 변경 (라디오 버튼)
       ↓
onSentenceModified() → ZIP 버튼 비활성화·"수정 중" 표시
       ↓
collectSentenceCorrections() → {db_id: {sent_idx: "positive|negative|neutral"}}
       ↓
POST /api/perspective/sentence-corrections/save
       ↓
api_save_sentence_corrections() → evaluations.sentiment_corrections (JSON TEXT) UPDATE
       ↓
재제출(resubmitEmployee) → /api/perspective/matrix/save-deploy
       ↓
save_to_deploy() → _get_sentence_level_scores(corrections=corrections_map)
       ↓
sentence_sentiment_override() → 사용자 교정값으로 점수 강제 치환 (L1896-1907)
       ↓
워드클라우드/감정 점수 재계산 반영
```

**핵심 구현 상세 (실제 코드 위치):**

| 기능 | 파일/라인 | 동작 |
|------|-----------|------|
| 문장 렌더링 (라디오 초기값) | `perspective_test.html:1971-1991` | `data-orig-sentiment="` + `s.sentiment`로 초기값 설정, `checked` 속성으로 현재 라벨 표시 |
| 사용자 변경 감지 | `perspective_test.html:2682-2688` | `change` 이벤트 위임 → `onSentenceModified()` + 행 배경색 변경 |
| 교정 수집 | `perspective_test.html:2666-2680` | `.sentence-row` 순회 → `dataset.dbId`, `dataset.sentIdx`, 선택된 라디오 값 수집 |
| 교정 저장 API | `perspective_routes.py:560-614` | `POST /sentence-corrections/save` → `evaluations` 테이블 `sentiment_corrections` 컬럼 UPDATE (JSON 병합) |
| 교정 로드 | `perspective_service.py:1803-1826` | `_load_corrections_map(employee_id)` → `{db_id: {sent_idx: label}}` 반환 |
| 교정 적용 (점수 치환) | `perspective_service.py:1896-1907` | `_get_sentence_level_scores()` 내부에서 `corrections` 인자로 전달 → `sentence_sentiment_override` 결과 대신 사용자 교정값으로 강제 치환 |
| 재제출 플로우 | `perspective_test.html:2555-2653` | `resubmitEmployee()` → 변경 전 상태 캡처 → 교정 저장 → `/matrix/save-deploy` 호출 → 결과 재렌더링 + 변경 로그 표시 |

**데이터베이스 스키마:**
- `deploy_session_service.py:182` — `ALTER TABLE evaluations ADD COLUMN sentiment_corrections TEXT DEFAULT '{}'` (Schema v4)
- 컬럼 내용: `{ "sent_idx": "positive|negative|neutral", ... }` 형태의 JSON 문자열

**알고리즘 변경 영향 범위 (모델 업그레이드·규칙 변경 시 검증 필요):**
1. **KoTE 파인튜닝/HR 감정 모델** (`perspective_service.py:1866-1880`) — `USE_HR_SENTIMENT_MODEL` 플래그 시 `predict_sentiments()` 배치 추론으로 극성 결정, 실패 시 규칙 폴백
2. **반전 표지어 규칙** (`perspective_service.py:1230-1380` `_sentence_sentiment_override_explain`) — `positive_rescue`, `negation_praise`, `no_response_neutral`, `rule3_last_low`, `neutral_dominant`, `neutral_keyword`, `euphemistic_negative` 등 rule_id 분기
3. **마진 밴드/판정 패킷** (`judgment_packet_service.py:26-29, 161-202`) — `|pos-neg| < margin` 저마진, `cur_rule_label ≠ kote` 긍↔부 불일치 탐지
4. **문서 단위 극성 필드** (`perspective_service.py:1837-1838`, `batch_processor.py:216-219`) — `evaluation_document_field`("장점"/"단점") 프리픽스로 HR 모델 추론 시 학습/서빙 정합성 보장

**현재 검증 가능한 진입점:**
- `perspective_test.html` → 그룹 분석 테스트 화면에서 문장별 라디오 직접 조작
- `judgment_apply.html` → 판정 패킷 업로드 후 "DB에 반영" 버튼으로 `sentiment_corrections` in-place 병합
- `api_regenerate_matrix` (`perspective_routes.py:789-838`) → 저장된 교정 맵 로드 후 단일 직원 매트릭스 재생성

---

## 3. 구현 상세

### 3.1 백엔드

#### 3.1.1 공통 유틸리티: 진행 시간 계산 헬퍼

**신규 파일:** `src/utils/progress_time.py`

```python
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

def now_kst() -> datetime:
    return datetime.now(KST)

def format_elapsed(start: datetime) -> str:
    """경과 시간을 'H시간 M분 S초' 또는 'M분 S초' 형식 문자열로 반환"""
    delta = now_kst() - start
    total_sec = int(delta.total_seconds())
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}시간 {m}분 {s}초"
    return f"{m}분 {s}초"

def estimate_remaining(start: datetime, current: int, total: int) -> str | None:
    """현재 진행률로 예상 남은 시간 계산. total=0 이면 None."""
    if total <= 0 or current <= 0:
        return None
    elapsed = (now_kst() - start).total_seconds()
    rate = current / elapsed  # 건/초
    remaining = total - current
    if rate <= 0:
        return None
    eta_sec = remaining / rate
    eta_dt = now_kst() + timedelta(seconds=eta_sec)
    return eta_dt.strftime("%H:%M:%S")  # KST 기준 예상 종료 시각
```

#### 3.1.2 메타데이터 배치 처리 — 상태에 시작 시각 추가

**파일:** `src/services/batch_processor.py`

- `process_batch()` 진입 시 `batch_processing_state['started_at'] = now_kst().isoformat()` 기록
- 기존 `status_message` 갱신 지점(예: `_ingested_rows` 루프, `completed` 루프) 유지
- SSE 이벤트(`batch_events.py:stream_batch_events`)에 `started_at`, `elapsed`, `eta` 필드 추가 전달

#### 3.1.3 그룹 분석 테스트 — 세션에 시작 시각 추가

**파일:** `src/services/deploy_session_service.py`

- `create_session()` 시 `session.started_at = now_kst().isoformat()` 저장 (`deploy_sessions` 테이블에 `started_at` 컬럼 추가 필요 — 마이그레이션 별도)
- `get_session_progress()` 응답에 `started_at`, `elapsed`, `eta` 포함
- 프론트엔드 폴링(`/api/perspective/deploy-session/progress`) 또는 기존 렌더 로직에서 계산 가능

### 3.2 프론트엔드

#### 3.2.1 공통 JS 유틸리티

**신규 파일:** `web/static/js/progress-time.js`

```javascript
// 경과 시간 포맷터
function formatElapsed(startIso) {
    const start = new Date(startIso);
    const diff = Date.now() - start.getTime();
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    return h ? `${h}시간 ${m}분 ${s}초` : `${m}분 ${s}초`;
}

// 예상 종료 시각 포맷터
function formatEta(etaStr) {
    return etaStr || '계산 중...';
}

// 주기적 업데이트용 타이머 헬퍼
function startProgressTimer(getStartIso, getCurrent, getTotal, onUpdate) {
    // 1초마다 onUpdate(elapsedStr, etaStr) 호출
    const timer = setInterval(() => {
        const start = getStartIso();
        if (!start) return;
        const elapsed = formatElapsed(start);
        const current = getCurrent();
        const total = getTotal();
        let eta = '계산 중...';
        if (total > 0 && current > 0) {
            const startTime = new Date(start).getTime();
            const rate = current / ((Date.now() - startTime) / 1000);
            if (rate > 0) {
                const remainSec = (total - current) / rate;
                const etaDate = new Date(Date.now() + remainSec * 1000);
                eta = etaDate.toLocaleTimeString('ko-KR', { hour12: false });
            }
        }
        onUpdate(elapsed, eta);
    }, 1000);
    return () => clearInterval(timer);
}
```

#### 3.2.2 메타데이터 배치 화면 (`metadata_batch.html` + `metadata_batch.js`)

**HTML 변경 (`web/templates/metadata_batch.html`):**
- `processingStatus` 영역에 경과 시간·예상 종료 시간 표시 줄 추가
```html
<div id="progressTimeInfo" style="margin: 8px 0; font-size: 13px; color: var(--text-muted); display: flex; gap: 16px; flex-wrap: wrap;">
    <span>경과: <strong id="elapsedTime">0초</strong></span>
    <span>예상 종료: <strong id="etaTime">계산 중...</strong></span>
</div>
```

**JS 변경 (`web/static/js/metadata_batch.js`):**
- `openSseAndListen()` 내부에서 `data.started_at` 수신 시 `startProgressTimer()` 시작
- SSE `onmessage`에서 `data.elapsed`, `data.eta` 수신 시 `#elapsedTime`, `#etaTime` 갱신

#### 3.2.3 그룹 분석 테스트 화면 (`perspective_test.html`)

**HTML 변경:**
- `generateMatrix()` 진행 영역(`renderProgress` 내부)에 경과/예상 종료 줄 추가
- `saveDeploy()` 진행 영역에도 동일 추가

**JS 변경:**
- `generateMatrix()`: `renderProgress()` 호출 전 `startTime = nowKst()` 기록, `startProgressTimer()`로 1초마다 경과/예상 갱신
- `saveDeploy()`: 세션 생성 시 `sessionId` 저장, `getSessionProgress()` 폴링 응답의 `started_at`로 타이머 시작 (또는 로컬 `startTime` 사용)

### 3.3 감정 재판정 기능 검증 (요청 3번 — 소스 분석 기반 구체화)

**검증 항목 체크리스트 (실제 구현 코드 위치 명시):**

| # | 검증 항목 | 실제 구현 위치 | 예상 결과 | 검증 방법 |
|---|-----------|----------------|-----------|-----------|
| 1 | 문장별 라디오(긍/부/중) 초기값이 KoTE 분석 결과(`s.sentiment`)와 일치하는가? | `perspective_test.html:1982-1984` `data-orig-sentiment` + `checked` | 예 — `s.sentiment`가 `positive/negative/neutral` 중 하나로 라디오에 반영 | 렌더링된 HTML에서 `data-orig-sentiment` 값과 선택된 라디오 `value` 비교 |
| 2 | 사용자 라디오 변경 시 `onSentenceModified()` → ZIP 다운로드 버튼 비활성화·"수정 중 (재제출 필요)" 표시 | `perspective_test.html:2656-2664`, `2682-2688` | 동작 — 버튼 `disabled=true`, 텍스트 변경, `opacity=0.5` | 라디오 클릭 후 `#zipDownloadBtn` 상태 확인 |
| 3 | `collectSentenceCorrections()` → `/api/perspective/sentence-corrections/save` 저장 후 `evaluations.sentiment_corrections` JSON 컬럼 반영 | `perspective_test.html:2666-2680`, `perspective_routes.py:587-601` | 저장됨 — `{db_id: {sent_idx: label}}` 형태 JSON으로 UPDATE | DB에서 해당 `evaluations.id` 행의 `sentiment_corrections` 컬럼 조회 |
| 4 | 재제출(`resubmitEmployee`) 시 저장된 교정 맵 로드 → `_get_sentence_level_scores(corrections=...)` → `sentence_sentiment_override` 대신 교정값으로 점수 강제 치환 | `perspective_test.html:2555-2653`, `perspective_service.py:1896-1907`, `1912-1946` | 반영됨 — `corrections` 인자 존재 시 `original_score` 대신 사용자 교정값(`+abs()`, `-abs()`, `0.0`) 사용 | 재제출 전후 매트릭스 감정 점수·워드클라우드 색상 변화 비교 |
| 5 | 모델 업그레이드(KoTE 파인튜닝/HR 모델) 시 `USE_HR_SENTIMENT_MODEL` 플래그 하에서 `predict_sentiments()` 배치 추론이 교정값과 충돌 없이 동작하는가? | `perspective_service.py:1866-1880` | 충돌 없음 — 모델 극성 결정 후 교정값이 최종 점수 치환하므로 우선순위 보장 | HR 모델 ON/OFF 각각에서 교정 적용된 문장 점수 확인 |
| 6 | 알고리즘 변경(반전 표지어 규칙 `positive_rescue`, `negation_praise`, `rule3_last_low` 등) 후에도 교정값이 규칙 결과보다 우선 적용되는가? | `perspective_service.py:1230-1380` (`_sentence_sentiment_override_explain`), `1896-1907` | 우선 적용됨 — `if corrections and str(i) in corrections:` 분기가 `original_score` 계산 이후 실행 | 규칙 변경 전후로 동일 문장에 교정 걸었을 때 결과 불변 확인 |
| 7 | 판정 패킷(`judgment_packet_service.py`) → "DB에 반영" 버튼(`apply_judgment_packet`) → `sentiment_corrections` in-place 병합 후 재제출 시 교정값 유지되는가? | `judgment_packet_service.py:336-380`, `perspective_routes.py:742-786` | 유지됨 — `human_decision` → `status=4` → DB 반영 시 `sentiment_corrections` UPDATE 병합 | 패킷 적용 후 `resubmitEmployee`로 재생성 시 교정 라벨 유지 확인 |

---

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `src/utils/progress_time.py` 헬퍼 모듈 생성 | — |
| 2 | `batch_processor.py` `process_batch()` 진입 시 `started_at` 기록, SSE 이벤트에 `elapsed`/`eta` 포함 | 1 |
| 3 | `deploy_session_service.py` `create_session()`에 `started_at` 저장, `get_session_progress()`에 `elapsed`/`eta` 포함 (DB 마이그레이션 별도) | 1 |
| 4 | `web/static/js/progress-time.js` 공통 유틸 생성 | — |
| 5 | `metadata_batch.html` 진행 영역에 경과/예상 종료 표시 요소 추가 | 4 |
| 6 | `metadata_batch.js` `openSseAndListen()`에 타이머 연동 (SSE `started_at` 기준) | 2, 5 |
| 7 | `perspective_test.html` `generateMatrix`/`saveDeploy` 진행 영역에 경과/예상 종료 표시 요소 추가 | 4 |
| 8 | `perspective_test.html` `generateMatrix`/`saveDeploy` 내부 타이머 연동 | 3, 7 |
| 9 | 수동 테스트: 배치 처리·매트릭스 저장·제출용 저장 각각 진행 시 경과/예상 종료 정상 표시 확인 | 6, 8 |
| 10 | 감정 재판정 기능 회귀 테스트 시나리오 문서화 (별도 이슈로 인계) | — |

---

## 5. 영향도 분석

| 파일 | 변경 유형 | 영향 범위 |
|------|-----------|-----------|
| `src/utils/progress_time.py` (신규) | 추가 | 공통 유틸, 타 모듈 import만 |
| `src/services/batch_processor.py` | 수정 | 배치 처리 진행 상태, SSE 이벤트 |
| `src/services/batch_events.py` | 수정 | SSE 페이로드 확장 (`started_at`, `elapsed`, `eta`) |
| `src/services/deploy_session_service.py` | 수정 | 세션 생성/진행 조회, DB 스키마 변경 필요 |
| `src/services/perspective_service.py` | 수정 (가능성) | `save_to_deploy` 진행 콜백 연동 시 |
| `web/templates/metadata_batch.html` | 수정 | 진행 UI에 2줄 텍스트 추가 |
| `web/static/js/metadata_batch.js` | 수정 | SSE 수신 핸들러에 타이머 추가 |
| `web/templates/perspective_test.html` | 수정 | 두 진행 영역에 2줄 텍스트 추가 |
| `web/static/js/progress-time.js` (신규) | 추가 | 공통 포맷터·타이머 헬퍼 |

**DB 마이그레이션 필요:** `deploy_sessions.started_at` 컬럼 추가 (SQLite `ALTER TABLE`)

---

## 6. 테스트/검증 계획

| 시나리오 | 검증 항목 | 통과 기준 |
|----------|-----------|-----------|
| 메타데이터 배치 시작 → 진행 중 | 경과 시간이 1초 단위 증가, 예상 종료 시각이 총 직원 수 대비 합리적 범위 | ±30초 오차 내 |
| 배치 완료 | 완료 시점 경과 시간 = 실제 소요 시간, 예상 종료 시각 ≈ 실제 완료 시각 | 일치 |
| 매트릭스 저장(`generateMatrix`) | 워커 4개 병렬 처리 중 경과/예상 표시 정상 갱신 | 1초 간격 갱신, UI 블로킹 없음 |
| 제출용 저장(`saveDeploy`) | 청크 단위 진행 중 경과/예상 표시 정상 갱신 | 1초 간격 갱신, 세션 재시작 시에도 연속 |
| 감정 재판정 회귀 | 라디오 초기값·변경·저장·재제출 전 과정 정상 | 체크리스트 1~5 모두 통과 |

---

## 7. 리스크 및 제약

1. **DB 마이그레이션**: `deploy_sessions.started_at` 컬럼 추가는 기존 세션과 호환되어야 함 (NULL 허용 → `COALESCE`로 처리)
2. **시간대 일관성**: 백엔드(KST), 프론트엔드(브라우저 로컬) 차이 → `progress_time.py`에서 KST 고정, 프론트는 `Date.now()` 기준 상대 계산으로 통일
3. **SSE 빈도**: 0.5초 폴링 + 1초 타이머 → 브라우저 탭 비활성 시 타이머 지연 가능 → `visibilitychange` 이벤트로 보정 고려
4. **감정 재판정 검증 범위**: 모델·알고리즘 변경 사항이 광범위할 경우 별도 회귀 테스트 계획 필요 (본 계획서 범위 외)
5. **교정 우선순위 보장**: HR 감정 모델(`predict_sentiments`)·반전 표지어 규칙(`_sentence_sentiment_override_explain`) 변경 시에도 사용자 교정(`sentiment_corrections`)이 최종 점수에 우선 적용되는 로직(`_get_sentence_level_scores` L1896-1907) 불변성 유지 필수
6. **데이터 정합성**: `evaluations.sentiment_corrections` JSON 컬럼이 `db_id`(정수 PK) 키로 저장되므로, `resubmitEmployee` 시 `corrections_map` 키 타입(`str(db_id)`) 일치 확인 필요 (`perspective_service.py:1816`, `1931`)

---

## 8. 산출물 체크리스트

- [x] `src/services/progress_time.py` 생성 (`src/utils/` 대신 `services/` — 프로젝트 구조에 맞춤)
- [x] `batch_processor.py` `started_at` 기록
- [x] `batch_events.py` SSE 페이로드에 `started_at` 추가
- [x] `deploy_session_service.py` `started_at` 저장/조회 + Schema v8 마이그레이션
- [x] `web/static/js/progress-time.js` 생성
- [x] `metadata_batch.html` 진행 영역 UI (경과/예상 종료 표시)
- [x] `metadata_batch.js` SSE `onmessage`에서 `started_at` 기반 elapsed/ETA 갱신
- [x] `perspective_test.html` `generateMatrix`/`saveDeploy` — progress 영역에 elapsed/ETA 표시
- [x] `perspective_test.html` `_matrixStartTime`/`_deployStartTime` 기록 + `formatElapsed` 호출
- [ ] 수동 테스트 시나리오 실행 및 기록 (백엔드 실행 필요)
- [ ] 감정 재판정 회귀 테스트 체크리스트 별도 이슈로 등록
