# 0610_04_perspective-test-corpus

> 상태: Done(코드 적용 확인, 2026-06-18) | 작성일: 2026-06-10
> 작업 유형: 기능 개발 | 담당: 요청자

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| — | — | 초안 작성 |
| 2026-06-10 | §3.4, §3.1, §3.3 A, §4 | 검토 반영: 모듈 함수명 수정, DDL 위치 변경, confidence/batch_id 처리 명시, 영향도 표 보완 |
| 2026-06-10 | §3.2.5, §3.3 A, §3.3 C, §4, §6 | 2차 검토 반영: backend augmentation, saveToCorpus 응답 체크+Toast, data-full-text escape, 페이지네이션 |
| 2026-06-10 | §3.2.5, §3.3 A, §5 | 3차 검토 반영: emotion_cell 변수명 수정(pos_score/neg_score), HTML에 data-confidence/batch-id 추가, §5 단계1 산출물 수정+중복헤더 제거 |
| 2026-06-11 | §3.2.5, §3.3 A, §4, §6 | 4차 검토 반영: confidence 계산 설계 확정(_get_sentence_level_scores 4-tuple 확장 / _generate_wc_for_items 기본값 0.0), data-employee-id wrapper 누락 수정, 영향도·리스크 보완 |
| 2026-06-11 | §3.2.5, §3.3 A, §4, §6 | 5차 검토 반영: data-full-text escape 방식 `escapeHtml`→`encodeURIComponent`+`decodeURIComponent` 수정, `context` 필드 backend/frontend 추가, 리스크·영향도 보완 |
| 2026-06-11 | §3.1, §3.2.5, §3.3 A, §6 | 6차 검토 반영: source_evaluation_id DDL TEXT로 변경, _get_sentence_level_scores early return 4-tuple 수정 명시, 중립 문장 코퍼스 저장 설계 결정 명시, 리스크 보완 |
| 2026-06-11 | §3.1, §3.2.5, §6 | 7차 검토 반영: _generate_wc_for_items가 _get_sentence_level_scores를 실제로 호출(line 1701)함을 확인, confidence 실시간 계산(abs(pos-neg))으로 설계 변경, JSON 예시 source_evaluation_id 문자열 수정, 호출부 리스트에 _generate_wc_for_items 추가 |
| 2026-06-11 | §3.3 A ① ② | 8차 검토 반영: data-employee-id wrapper가 line 1559에 이미 존재함 확인 → §3.3 A ① 불필요 변경 제거; data-confidence 설명의 경로별 0.0/실제값 오류 수정(양 경로 모두 abs(pos-neg)); _generate_wc_for_items 호출 line 1696→1697 수정 |
| 2026-06-11 | §3.2.5, §6 | 9차 검토 반영: _generate_wc_for_items line 번호 1697/1698→1701/1702로 정정(line 1689-1690 neutral_details/neu_seen 추가로 인한 행 번호 변동), 중립 문장 설명 `pos_details`→`neutral_details`로 정정, 리스크 line 번호 1696→1701 정정 |
| 2026-06-11 | §2.1, §3.2.5, §3.3, §6, §8 | 10차 검토 반영: perspective_service.py 전반적으로 +4행 오프셋 정정(_get_sentence_level_scores 754→758, early return 761→765, _generate_wc_for_items 1667→1671, _generate_emotion_cell 1040→1044, 영향 범위 1074/825/1003→1077/829/1007); perspective_test.html _renderDeploymentSentences 1415→1407, sentence-row 1419→1420, wrapper 1559→1561, 재제출 1668→1670; §8 line 범위 수정 |

---

## 1. 요약

`perspective_test.html`에서 "제출용 저장" 결과의 문장별 라디오버튼 영역에 **"📋 코퍼스 저장" 버튼**을 추가한다.
사용자가 해당 문장을 버튼 클릭으로 저장하면, **Nav > 테스트 > 습득한 데이터** (`/acquired-data`) 페이지에서 모아보고 **감정/욕설/비꼼 분석**을 재실행하여 **모델 판단과 사용자 판단의 차이**를 분석한다.

---

## 2. 배경 및 현황

### 2.1 현재 구조

- **Nav 메뉴 (base.html:378-384)**
  ```
  테스트 (dropdown)
  ├── 감정테스트  → /sentiment-test
  └── 욕설필터   → /profanity-test
  ```

- **`perspective_test.html`** `_renderDeploymentSentences` 함수 (line 1407)
  - 각 sentence row = `div.sentence-row`
  - 3개 라디오버튼 (긍정/부정/중립) + 문장 텍스트
  - `data-db-id`, `data-eval-id`, `data-sent-idx`, `data-orig-sentiment` 속성 보유

- **라우트 패턴 (ui_routes.py:127-136)**
  ```python
  @ui_bp.route('/sentiment-test')
  def sentiment_test():
      return render_template('sentiment_test.html')
  ```

- **API 패턴 (perspective_routes.py)**
  - `/api/perspective/sentence-corrections/save` — 문장 감정 수정 저장
  - `/api/perspective/test/sentence-sentiment` — 문장 감정 분석 테스트

### 2.2 문제점
- 사용자가 "모델이 긍정이라 했는데 우리는 부정이라고 판단한 문장"을 발견해도 이를 **별도로 축적하고 체계적으로 분석할 수단이 없음**
- `TEST_SENTENCES_100`은 하드코딩되어 실제 운영 데이터 케이스를 반영하지 못함
- 감정테스트(`/sentiment-test`)와 욕설필터(`/profanity-test`)는 각각 독립 테스트 페이지로 존재하지만, **실제 평가 데이터에서 수집한 문장을 분석하는 파이프라인은 없음**

---

## 3. 구현 상세

### 3.1 데이터 모델

**DDL 추가 위치**: `deploy_session_service.py`의 `_init_db()` 내 `conn.executescript()` 블록
(기존 패턴: `deploy_session_service._init_db()`에서 DDL 관리 → `perspective_service.py`에서 CRUD 사용)

**스키마 마이그레이션**: `_apply_schema_migrations()`에 v5 마이그레이션으로 추가 (현재 v4까지 사용 중)

```sql
-- v5 migration: acquired_sentences 테이블 추가
CREATE TABLE IF NOT EXISTS acquired_sentences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sentence_text   TEXT NOT NULL,
    user_label      TEXT CHECK(user_label IN ('positive','negative','neutral')),
    model_label     TEXT CHECK(model_label IN ('positive','negative','neutral')),
    confidence      REAL DEFAULT 0.0,
    source_employee_id   TEXT DEFAULT '',
    source_evaluation_id TEXT DEFAULT '',
    source_batch_id      TEXT DEFAULT '',
    sentence_index        INTEGER DEFAULT 0,
    db_id                 INTEGER DEFAULT 0,
    context         TEXT DEFAULT '',
    memo            TEXT DEFAULT '',
    analysis_results TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    updated_at      TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(sentence_text, source_evaluation_id, sentence_index)
);
```

### 3.2 API 설계 (`perspective_routes.py`에 추가)

| 메서드 | 엔드포인트 | 설명 | 인증 |
|--------|-----------|------|------|
| `POST` | `/api/perspective/acquired-sentences/save` | 문장 저장 | 관리자 |
| `GET`  | `/api/perspective/acquired-sentences/list` | 목록 조회 (페이지네이션 + 필터) | 관리자 |
| `DELETE` | `/api/perspective/acquired-sentences/<id>` | 단건 삭제 | 관리자 |
| `POST` | `/api/perspective/acquired-sentences/analyze` | 선택 문장 분석 실행 | 관리자 |
| `GET`  | `/api/perspective/acquired-sentences/export` | CSV보내기 | 관리자 |

**저장 요청 예시:**
```json
POST /api/perspective/acquired-sentences/save
{
  "sentence_text": "업무 능력은 뛰어나나 커뮤니케이션이 부족합니다.",
  "user_label": "negative",
  "model_label": "positive",
  "confidence": 0.09,
  "source_employee_id": "EMP001",
  "source_evaluation_id": "A2025_001",
  "source_batch_id": "batch_2026_06",
  "sentence_index": 2,
  "db_id": 456,
  "context": "전반적으로 ... 업무 능력은 뛰어나나 커뮤니케이션이 부족합니다. ..."
}
```

**분석 요청/응답:**
```json
POST /api/perspective/acquired-sentences/analyze
{ "ids": [1, 2, 3], "analysis_types": ["emotion", "profanity", "sarcasm"] }

→ {
  "results": [
    {
      "id": 1,
      "sentence_text": "...",
      "user_label": "negative",
      "model_label": "positive",
      "emotion": { "positive": 0.35, "negative": 0.58, "neutral": 0.07, "result": "negative" },
      "profanity": { "detected": false },
      "sarcasm": { "detected": false }
    }
  ]
}
```

### 3.2.5 Backend augmentation — `confidence`/`batch_id`/`context` 추가

현재 `_generate_wc_for_items` (perspective_service.py line 1671)와 `_generate_emotion_cell` (line 1044)에서 생성하는 `positive_details`/`negative_details` 객체에 **`confidence`**와 **`batch_id`** 필드가 없다.
📋 저장 시 이 값들이 필요하므로, backend 객체를 확장한다.

#### 전제: `_get_sentence_level_scores` 반환 형식 변경 (line 758)

현재 반환값 `(sent, score)` 2-tuple에 raw pos/neg를 추가하여 4-tuple로 확장한다.
`_get_sentence_level_scores`를 호출하는 모든 사용처도 함께 수정한다.

현재:
```python
if not sentences:
    return [(None, 0.0)]   # line 765 — early return도 함께 수정 필요

result.append((sent, score))
return result
```

변경:
```python
if not sentences:
    return [(None, 0.0, 0.0, 0.0)]   # early return: 4-tuple 일관성 유지

result.append((sent, score, pos, neg))
return result
```

> 이 변경의 영향 범위: `_generate_emotion_cell` (line 1077), `calculate_word_scores` 내부 (line 829), `_aggregate_emotion` (line 1007), `_generate_wc_for_items` (line 1702) — 모두 `for sent, score in sent_scores`(또는 `(_, sc)`) 패턴으로 사용 중이므로, 각각 4-tuple에 맞게 수정한다.

---

**`_generate_wc_for_items` 수정 (line 1700 부근):**

`_generate_wc_for_items`의 sentence 루프는 line 1701에서 `_get_sentence_level_scores`를 호출하고, line 1702에서 `sent_score_map`으로 2-tuple을 언패킹한다. 4-tuple 확장 시 이 언패킹도 수정해야 하며, `pos`/`neg`를 활용하여 **문장 수준 confidence를 실시간 계산(abs(pos - neg))**한다.

현재:
```python
sent_scores_list = _get_sentence_level_scores(doc, corrections=eval_corr)
sent_score_map = {idx: sc for idx, (_, sc) in enumerate(sent_scores_list)}  # line 1702 2-tuple
...
base = {
    'text': sent,
    'evaluation_id': eval_id,
    'db_id': db_id,
    'item_index': item_idx,
    'sentence_index': i,
}
```

변경:
```python
sent_scores_list = _get_sentence_level_scores(doc, corrections=eval_corr)
sent_score_map = {}
confidence_map = {}
for idx, (_, sc, pos, neg) in enumerate(sent_scores_list):   # 4-tuple 언패킹
    sent_score_map[idx] = sc
    confidence_map[idx] = abs(pos - neg)
...
sent_score = sent_score_map.get(i, 0.0)
confidence = confidence_map.get(i, 0.0)
base = {
    'text': sent,
    'evaluation_id': eval_id,
    'db_id': db_id,
    'item_index': item_idx,
    'sentence_index': i,
    'confidence': confidence,               # abs(pos - neg) 실시간 계산 (analyze 재실행 불필요)
    'batch_id': ev.get('batch_id', ''),
    'context': doc,                         # save 시 context 필드로 사용; UI에서 data-context로 전달
}
```

변경 후 `sent_score` 기준 분기(positive/negative/neutral)는 기존 로직과 동일하게 유지한다.

---

**`_generate_emotion_cell` 수정 (line 1074 부근):**

`_get_sentence_level_scores` 4-tuple 확장 후, 문장 수준 `pos`/`neg`를 직접 사용한다.
(`pos_score`/`neg_score` — line 1067-1068 — 는 문서 전체 점수이므로 사용하지 않는다.)

> **[설계 결정] 중립 문장(score == 0) 처리**: `_generate_emotion_cell` 경로에서 중립 판단 문장(`score == 0`)은 현재 `positive_details`/`negative_details` 어디에도 추가되지 않아 sentence-row 자체가 렌더링되지 않는다. 따라서 해당 경로에서 온 중립 문장은 📋 버튼이 노출되지 않아 코퍼스 저장이 불가능하다.
> 반면 `_generate_wc_for_items` 경로는 중립 문장을 `neutral_details`에 `sentiment: 'neutral'`로 추가하므로 버튼이 생긴다.
> **이 차이는 의도된 동작으로 유지한다.** `_generate_emotion_cell`에서 중립 문장을 추가하면 sentence-row 수가 대폭 늘어나 UI가 과부하 될 수 있고, 코퍼스 수집 목적(긍정↔부정 불일치 파악)과도 맞지 않는다. 중립 문장이 필요하면 `_generate_wc_for_items` 경로(통합 탭)를 통해 저장한다.

현재:
```python
for i, (sent, score) in enumerate(sent_scores):
    ...
    positive_details.append({
        'text': sent,
        'evaluation_id': eval_id,
        'db_id': db_id,
        'sentence_index': i,
        'sentiment': 'positive',
    })
```

변경:
```python
for i, (sent, score, pos, neg) in enumerate(sent_scores):
    ...
    positive_details.append({
        'text': sent,
        'evaluation_id': eval_id,
        'db_id': db_id,
        'sentence_index': i,
        'sentiment': 'positive',
        'confidence': abs(pos - neg),              # 신규 (문장 수준 raw score)
        'batch_id': ev.get('batch_id', ''),        # 신규
        'context': doc,                            # 신규 (전체 문서 텍스트)
    })
```

(negative_details도 동일 패턴 적용)

### 3.3 프론트엔드 변경

#### A. `perspective_test.html` — `_renderDeploymentSentences` 수정 + 직원 wrapper `data-employee-id` 추가

**① 직원 섹션 wrapper `data-employee-id` — 변경 불필요 (이미 존재)**

`saveToCorpus`에서 `row.closest('[data-employee-id]')?.dataset.employeeId`로 사원 ID를 탐색한다.
이 속성은 `renderDeployComplete` 함수(line 1559)에서 `_buildEmployeeResultHtml` 호출 전에 외부 wrapper에 **이미 추가**되어 있다:

```javascript
// line 1561 (변경 불필요 — 이미 존재)
h += '<div' + (sectionId ? ' id="' + sectionId + '"' : '') + ' data-employee-id="' + empId + '" style="...">';
h += _buildEmployeeResultHtml(res);  // sentence-row들이 이 div 내부에 위치
h += '</div>';
```

재제출 경로(line 1670)도 `section = document.getElementById(sectionId)`로 이 div를 참조하므로,
`section.innerHTML = _buildEmployeeResultHtml(...)` 후에도 `section` 자체에 `data-employee-id`가 유지된다.
`_buildEmployeeResultHtml` 내부 수정은 불필요하다.

---

**② `_renderDeploymentSentences` 내 sentence-row 수정**

현재 문장 row 구조 (line 1420):
```html
<div class="sentence-row" data-db-id="..." data-eval-id="..." data-sent-idx="..." data-orig-sentiment="...">
  <label><input type="radio" name="..." value="positive"></label>
  <label><input type="radio" name="..." value="negative"></label>
  <label><input type="radio" name="..." value="neutral"></label>
  <span style="flex:1;...">• text...</span>
</div>
```

변경 후:
```html
<div class="sentence-row" data-db-id="..." data-eval-id="..." data-sent-idx="..." data-orig-sentiment="..."
     data-full-text="..." data-confidence="..." data-batch-id="..." data-context="...">
  <label><input type="radio" name="..." value="positive"></label>
  <label><input type="radio" name="..." value="negative"></label>
  <label><input type="radio" name="..." value="neutral"></label>
  <span style="flex:1;...">• text...</span>
  <button class="copy-btn" onclick="saveToCorpus(this)" title="코퍼스에 저장">📋</button>
</div>
```

sentence-row에 추가할 `data-*` 속성 (기존 4개 + 신규 4개):
- `data-full-text="..."` — `encodeURIComponent(s.text)`로 인코딩, `decodeURIComponent(row.dataset.fullText)`로 읽어 원문 복원
- `data-confidence="..."` — 모델 confidence 값 (`abs(pos - neg)`; 양 경로 `_generate_wc_for_items`/`_generate_emotion_cell` 모두 실시간 계산)
- `data-batch-id="..."` — 소속 배치 ID (상위 컨테이너 또는 row에서 전달)
- `data-context="..."` — `encodeURIComponent(전체 문서 텍스트)`로 인코딩, save 시 context 필드로 사용

추가될 JS 함수 `saveToCorpus` (응답 체크 + Toast 포함):
```javascript
async function saveToCorpus(btn) {
  const row = btn.closest('.sentence-row');
  const rawText = row.dataset.fullText;
  const text = rawText ? decodeURIComponent(rawText) : row.querySelector('span').textContent.replace(/^[•\s]+/, '').trim();
  const userLabel = row.querySelector('input[type="radio"]:checked')?.value || 'neutral';
  const modelLabel = row.dataset.origSentiment || 'neutral';
  const dbId = row.dataset.dbId;
  const evalId = row.dataset.evalId;
  const sentIdx = row.dataset.sentIdx;
  const empId = row.closest('[data-employee-id]')?.dataset.employeeId || '';
  const confidence = parseFloat(row.dataset.confidence || '0');
  const batchId = row.dataset.batchId || row.closest('[data-batch-id]')?.dataset.batchId || '';
  const rawContext = row.dataset.context;
  const context = rawContext ? decodeURIComponent(rawContext) : '';

  try {
    const res = await fetch('/api/perspective/acquired-sentences/save', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        sentence_text: text,
        user_label: userLabel,
        model_label: modelLabel,
        confidence: confidence,
        source_employee_id: empId,
        source_evaluation_id: evalId,
        source_batch_id: batchId,
        sentence_index: sentIdx,
        db_id: dbId,
        context: context,
      })
    });
    if (!res.ok) throw new Error(res.statusText);
    const d = await res.json();
    if (!d.success) throw new Error(d.error || '저장 실패');
    btn.textContent = '✅';
    showDeployToast('✅ 코퍼스에 저장됨', '/acquired-data');
    setTimeout(() => { btn.textContent = '📋'; }, 2000);
  } catch(e) {
    btn.textContent = '❌';
    console.error('Corpus save failed:', e);
  }
}
```

#### B. `base.html` — Nav 메뉴에 링크 추가 (line 382와 383 사이)

```html
<div class="dropdown">
    <span class="dropbtn">테스트</span>
    <div class="dropdown-content">
        <a href="/sentiment-test">감정테스트</a>
        <a href="/profanity-test">욕설필터</a>
        <a href="/acquired-data">습득한 데이터</a>   <!-- ← 추가 -->
    </div>
</div>
```

#### C. 새 템플릿 `acquired_data.html` 생성

`sentiment_test.html` 패턴을 따라 새 페이지 생성:
- `{% extends "base.html" %}`
- 상단: 요약 통계 (총 저장 문장 수, 불일치 건수 등)
- 중간: 필터 영역 (불일치만 보기, 라벨별, 날짜별)
- 하단: 결과 테이블
  - 컬럼: 문장 | 사용자라벨 | 모델라벨 | 일치여부 | 감정분석 | 욕설 | 비꼼 | 저장일 | 삭제
  - 체크박스 + "분석 실행" 버튼
  - **페이지네이션**: `page`/`per_page` 파라미터 기반, 이전/다음 버튼
  - CSV보내기 버튼

#### D. `ui_routes.py`에 신규 라우트 추가

```python
@ui_bp.route('/acquired-data')
def acquired_data():
    """습득한 데이터 게시판"""
    return render_template('acquired_data.html')
```

### 3.4 분석 파이프라인

- **재사용 모듈** (실제 함수 시그니처):
  ```python
  from src.modules.emotion_analysis import analyze_emotion
  from src.modules.profanity_filter import advanced_filter_profanity
  from src.modules.sarcasm_analysis import analyze_sarcasm

  emotion_result   = analyze_emotion(sentence_text)          # → dict {positive, negative, neutral, result}
  profanity_result = advanced_filter_profanity(sentence_text) # → dict {detected, filtered, ...}
  sarcasm_result   = analyze_sarcasm(sentence_text)          # → dict {detected, score, ...}
  ```
- 분석 결과는 `acquired_sentences.analysis_results` 컬럼에 JSON 캐시
- 재분석 버튼 클릭 시 캐시 갱신

---

## 4. 영향도

| 파일 | 변경 유형 | 변경 내용 |
|------|-----------|-----------|
| `perspective_test.html` | 수정 | `_renderDeploymentSentences`에 📋 버튼 + data-full-text/confidence/batch-id/context 속성 추가 + `saveToCorpus` 함수 추가 (직원 wrapper `data-employee-id`는 line 1559에 이미 존재 — 변경 불필요) |
| `base.html` | 수정 | Nav 테스트 드롭다운에 "습득한 데이터" 링크 추가 |
| `acquired_data.html` | **신규** | 새 페이지 템플릿 |
| `perspective_routes.py` | 수정 | `acquired-sentences` API 5종 추가 |
| `perspective_service.py` | 수정 | `_get_sentence_level_scores` 반환 형식 4-tuple 확장 + 모든 호출부 수정 + `acquired_sentences` CRUD + 분석 로직 + `_generate_wc_for_items`/`_generate_emotion_cell`에 `confidence`/`batch_id`/`context` 필드 추가 |
| `deploy_session_service.py` | 수정 | `_init_db()`에 `acquired_sentences` DDL 추가 + v5 마이그레이션 추가 |
| `ui_routes.py` | 수정 | `/acquired-data` 라우트 추가 |

---

## 5. 작업 단계

| 단계 | 작업 내용 | 산출물 | 예상 |
|------|-----------|--------|------|
| 1 | DB: `acquired_sentences` 테이블 DDL + v5 마이그레이션 | `deploy_session_service.py` | 0.5h |
| 2 | API: save/list/delete/analyze 4종 | `perspective_routes.py` | 2h |
| 3 | Backend: `_generate_wc_for_items`/`_generate_emotion_cell`에 `confidence`/`batch_id`/`context` 필드 추가 | `perspective_service.py` | 1h |
| 4 | 프론트: `_renderDeploymentSentences`에 📋 버튼 + `saveToCorpus` + Toast | `perspective_test.html` | 1.5h |
| 5 | 프론트: `acquired_data.html` 신규 작성 (페이지네이션 포함) | 새 템플릿 | 2.5h |
| 6 | Nav 링크 + `/acquired-data` 라우트 | `base.html`, `ui_routes.py` | 0.5h |
| 7 | 분석 파이프라인 통합 + 캐싱 | `perspective_service.py` | 1.5h |
| 8 | CSV보내기 + 테스트 | 전체 | 1h |
| **합계** | | | **~10.5h** |

---

## 6. 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| 📋 버튼이 문장 row 영역을 넘어감 | `flex-shrink:0` + 크기 축소 (18px) |
| `data-full-text`가 HTML 이스케이프로 인해 깨짐 | `encodeURIComponent(s.text)`로 인코딩, `decodeURIComponent(dataset.fullText)`로 디코딩하여 원문 복원. `escapeHtml` 사용 시 `dataset`이 HTML 엔티티를 자동 디코딩하지 않으므로 `encodeURIComponent`를 사용 |
| 분석 중 서버 부하 | 한 번에 최대 50문장 제한 + 결과 캐싱 |
| 같은 문장 중복 저장 | `sentence_text + source_evaluation_id + sentence_index` UNIQUE 또는 중복 체크 후 UPDATE |
| `_generate_wc_for_items` 경유 저장 시 confidence 계산 누락 | `_generate_wc_for_items`는 line 1701에서 `_get_sentence_level_scores`를 호출하므로 `pos`/`neg`를 추출 가능. `sent_score_map` 생성 시 confidence(abs(pos-neg))를 함께 저장하지 않으면 confidence=0이 됨. §3.2.5에서 dict 분리 방식으로 명시 |
| `_get_sentence_level_scores` 4-tuple 확장 시 호출부 누락 | 영향 범위: `_generate_emotion_cell`, `calculate_word_scores`, `_aggregate_emotion`, `_generate_wc_for_items` — 모두 `for sent, score`(또는 `(_, sc)`) 패턴으로 수정 필요. 구현 단계 3에서 일괄 처리 |
| `_get_sentence_level_scores` early return 미수정 | line 761 `return [(None, 0.0)]`을 `[(None, 0.0, 0.0, 0.0)]`으로 함께 수정. 누락 시 빈 문서 처리 시 ValueError 발생. §3.2.5에 명시 |
| `source_evaluation_id` 타입 불일치 | `evaluation_id`가 문자열(`"A2025_001"` 등)일 수 있으므로 DDL을 `TEXT DEFAULT ''`로 정의. JS에서 문자열로 전달되므로 일관성 유지 |
| `data-employee-id` DOM 부재로 `saveToCorpus`에서 empId 취득 불가 | 해당 속성은 line 1561 외부 wrapper에 이미 존재. `_buildEmployeeResultHtml` 내부 수정 불필요. 재제출 경로(line 1670)도 동일 div 참조로 안전 |
| `data-context` DOM 부재로 save 시 context 누락 | `_generate_wc_for_items`/`_generate_emotion_cell` 상세 객체에 `context: doc` 추가. §3.2.5에서 명시 |
| `data-full-text`와 `data-context`의 URI 인코딩으로 HTML 소스 가독성 저하 | data-* 속성은 프로그램 전용이므로 가독성 불필요. 문제 없음 |

---

## 7. 테스트 시나리오

| # | 시나리오 | 방법 | 성공 기준 |
|---|----------|------|-----------|
| 1 | 문장 📋 저장 | perspective_test에서 문장 row의 📋 클릭 | Toast ✅, DB에 row 생성 |
| 2 | 습득한 데이터 목록 | /acquired-data 접속 | 저장된 문장 목록 표시 |
| 3 | 분석 실행 | 체크박스 선택 → 분석 실행 | emotion/profanity/sarcasm 결과 표시 |
| 4 | 불일치 필터 | "불일치만 보기" | user_label ≠ model_label만 표시 |
| 5 | 삭제 | 개별 ❌ 버튼 | DB row 삭제, 목록 갱신 |
| 6 | CSV보내기 | CSV 버튼 | CSV 파일 다운로드 |

---

## 8. 관련 파일

- `D:\dev\wordcloud\wordcloud_project\web\templates\base.html` — Nav 수정 대상 (line 378-384)
- `D:\dev\wordcloud\wordcloud_project\web\templates\perspective_test.html` — 📋 버튼 추가 대상 (line 1407-1437)
- `D:\dev\wordcloud\wordcloud_project\web\templates\sentiment_test.html` — 신규 템플릿 참조 패턴
- `D:\dev\wordcloud\wordcloud_project\src\routes\perspective_routes.py` — API 추가 대상
- `D:\dev\wordcloud\wordcloud_project\src\routes\ui_routes.py` — 라우트 추가 대상 (line 127-142)
- `D:\dev\wordcloud\wordcloud_project\src\services\perspective_service.py` — CRUD + 분석 로직 추가 대상
