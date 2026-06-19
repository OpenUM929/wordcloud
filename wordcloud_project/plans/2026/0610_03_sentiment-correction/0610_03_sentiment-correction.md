# 문장별 감정 수정 및 워드클라우드 재생성

> 상태: DN(코드 적용 확인, 2026-06-18) | 작성일: 2026-06-10

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-10 | - | 최초 작성 |
| 2026-06-10 | 2.1, 3, 4.2, 4.3.1, 4.4.3, 5, 6 | 검토 반영: DB 저장 구조 단순화, `_generate_cell_content`·`generate_perspective_matrix` 수정 대상 추가, API 경로 충돌 수정, corrections 실패 시 비중단 처리, regenerate·save_to_deploy 플로우 분리 명시, neutral 비율 집계 정의 |
| 2026-06-10 | 4.4.5, 6 | 사용자 플로우 명확화: 문장 수정 시 다운로드 버튼 비활성화, 재제출 시 활성화 |
| 2026-06-10 | 1.1, 2.3, 4.4.5, 6 | 최종 사용자 플로우 텍스트 그림 추가, 다운로드 버튼 상태 관리 구현 계획 추가, "수정 중 다운로드 비활성화" 예외 처리 추가 |
| 2026-06-10 | 2.2, 2.3, 4.4.2, 4.4.3, 4.4.5, 7 | 2차 검토 반영: 2.2 matrix/regenerate→save-deploy 수정, 2.3 ② 제출용 저장 단계(3~4단계) 추가 및 전체 단계 재번호, collectSentenceCorrections 파라미터 통일, beforeunload 플래그 구현 추가, showWarning 출처 명시, 섹션 7 "4개→7개 함수" 수정 |

---

## 1. 작업 개요

### 문제
워드클라우드 생성 시 사용된 평가 문장들의 감정(긍정/부정)이 모델에 의해 자동 분석되나, 사용자가 이를 확인하고 직접 수정할 수 있는 기능이 없음.

### 목표
`/perspective_test` 페이지에서 매트릭스 저장(미리보기) 후 각 셀의 문장별 감정을 사용자가 긍정/부정/중립으로 직접 수정하고, "제출용 저장" 시 수정 내역을 DB에 영구 저장한 뒤 해당 직원의 워드클라우드를 재생성하여 화면에 다시 출력함.

### 결정 사항 (사용자 확인 완료)
| 항목 | 결정 |
|------|------|
| 수정 단위 | 개별 문장 |
| 저장 방식 | 영구 DB 저장 |
| 문장 식별 키 | `evaluation_id + sentence_index` |
| 재생성 트리거 | "제출용 저장" 버튼 클릭 시 |
| 재생성 범위 | 해당 직원의 워드클라우드만 재생성 → 화면 업데이트 |

---

## 2. 데이터 저장 구조

### 2.1 DB 스키마 변경

**대상:** `deploy_sessions.db` — `evaluations` 테이블

```sql
ALTER TABLE evaluations ADD COLUMN sentiment_corrections TEXT DEFAULT '{}';
```

**저장 데이터 형식 (JSON 문자열):**

각 evaluation row의 `sentiment_corrections` 컬럼에는 해당 evaluation에 속한 문장 인덱스 → 감정만 저장한다. evaluation_id는 row 자체에 있으므로 중복 키로 쓰지 않는다.

```json
{
  "<sentence_index>": "positive",
  "<sentence_index>": "negative",
  "<sentence_index>": "neutral"
}
```

`corrections_map`은 DB 로드 시 코드에서 조립:

```python
corrections_map = {
    row["evaluation_id"]: json.loads(row["sentiment_corrections"] or "{}")
    for row in evaluations
}
# 결과: {evaluation_id: {sentence_index: sentiment}}
```

### 2.2 데이터 흐름

```
[매트릭스 저장] → _generate_emotion_cell() → 문장 목록 + 현재 감정 반환
                                                      ↓
[화면 렌더링] → 각 문장에 라디오 버튼 (긍정/부정/중립)
                                                      ↓
[사용자 수정] → 문장별 감정 변경 (프론트엔드 객체에 임시 저장)
                                                      ↓
[제출용 저장 클릭]
    ├─ 1. POST /api/perspective/sentence-corrections/save → DB 저장
    └─ 2. POST /api/perspective/save-deploy (기존 엔드포인트)
         ├─ corrections_map 로드 (DB에서 조회)
         ├─ word_scores 재계산 (사용자 지정 감정 반영)
         ├─ 워드클라우드 이미지 재생성
         └─ 3. 화면에 새 결과 렌더링
```

### 2.3 사용자 플로우 (텍스트 그림)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    [1단계] 매트릭스 저장 클릭                            │
│                         (미리보기 생성)                                   │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  [2단계] 결과 화면 출력                                                  │
│  ┌──────────────────────────────────┐  ┌──────────────────────────┐   │
│  │  워드클라우드 이미지               │  │  ▼ 긍정 사유 3건          │   │
│  │  ┌────────────────────────┐      │  │  ○긍정 ●부정 ○중립      │   │
│  │  │  [워드클라우드 PNG]   │      │  │    성실합니다            │   │
│  │  │  긍 73%  부 27%     │      │  │  ○긍정 ●부정 ○중립      │   │
│  │  └────────────────────────┘      │  │    보고가 미흡          │   │
│  │                                  │  │  ○긍정 ○부정 ●중립      │   │
│  │                                  │  │    전반적으로 보통      │   │
│  │                                  │  └──────────────────────────┘   │
│  │                                  │  ┌──────────────────────────┐   │
│  │                                  │  │  ▼ 부정 사유 2건          │   │
│  │                                  │  │  ○긍정 ●부정 ○중립      │   │
│  │                                  │  │    업무 속도가 느림      │   │
│  │                                  │  │  ●긍정 ○부정 ○중립      │   │
│  │                                  │  │    (수정 예정 문장)      │   │
│  │                                  │  └──────────────────────────┘   │
│  └──────────────────────────────────┘                                  │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │ [제출용 저장]            ⬇️ 결과물 ZIP (숨김)                │      │
│  └────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              [3단계] 사용자가 "제출용 저장" 클릭                          │
│                    (최초 워드클라우드 생성 + DB 저장)                    │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  [4단계] 제출 완료 — 다운로드 버튼 활성화                                │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │ [제출용 저장]            ⬇️ 결과물 ZIP ✅                   │      │
│  └────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    [5단계] 사용자가 문장 수정 시작                        │
│  ⚠️ 사용자가 "부정"으로 변경 → 시스템 감지                             │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  [6단계] 다운로드 버튼 자동 비활성화                                     │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │ [제출용 저장]            ⬇️ 수정 중 (재제출 필요) 🔒        │      │
│  └────────────────────────────────────────────────────────────┘      │
│  - 다운로드 버튼: disabled, opacity 50%                                │
│  - 클릭 불가 (이전 데이터가 아닌 최신 데이터가 필요함)                   │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              [7단계] 사용자가 다시 "제출용 저장" 클릭                     │
│                         (재생성 트리거)                                 │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  1. DB 저장      │ │  2. 재계산       │ │  3. 재생성       │
│  corrections    │ │  word_scores    │ │  워드클라우드    │
│  저장 완료      │ │  (감정 반영)    │ │  이미지 생성    │
│  (영구 보관)    │ │                 │ │  (새 파일)      │
└─────────────────┘ └─────────────────┘ └─────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  [8단계] 결과 화면 업데이트 (재생성된 이미지)                          │
│  ┌──────────────────────────────────┐  ┌──────────────────────────┐   │
│  │  워드클라우드 이미지 (변경됨)    │  │  ▼ 긍정 사유 2건          │   │
│  │  ┌────────────────────────┐      │  │  ○긍정 ●부정 ○중립      │   │
│  │  │  [새 워드클라우드 PNG]│      │  │    성실합니다          │   │
│  │  │  긍 67%  부 33%     │      │  │  ○긍정 ●부정 ○중립      │   │
│  │  │  (색상 분포 변경)   │      │  │    보고가 미흡          │   │
│  │  └────────────────────────┘      │  │                          │   │
│  │  ← 수정된 감정이 반영되어        │  │  ▼ 부정 사유 3건          │   │
│  │    긍정 단어 ↓, 부정 단어 ↑     │  │  ●긍정 ○부정 ○중립      │   │
│  │                                  │  │    업무 속도가 느림      │   │
│  │                                  │  │  ○긍정 ●부정 ○중립      │   │
│  │                                  │  │    (새로 추가된 문장)    │   │
│  │                                  │  └──────────────────────────┘   │
│  └──────────────────────────────────┘                                  │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │ [제출용 저장]            ⬇️ 결과물 ZIP ✅                   │      │
│  └────────────────────────────────────────────────────────────┘      │
│  - 다운로드 버튼: 활성화, 클릭 가능                                    │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              [9단계] 사용자가 ZIP 다운로드 클릭                          │
│                         (수정된 데이터 기반)                            │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  📦 ZIP 파일 생성                                                       │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  deploy_abc123.zip                                         │      │
│  │  ├─ 통합/직원A_통합.png  ← 수정된 데이터로 생성된 이미지    │      │
│  │  ├─ 긍정/직원A_긍정.png                                    │      │
│  │  └─ 부정/직원A_부정.png                                    │      │
│  └────────────────────────────────────────────────────────────┘      │
│  ✅ 사용자가 수정한 감정이 반영된 워드클라우드 포함                      │
└─────────────────────────────────────────────────────────────────────────┘
```

**핵심 상태 전이표:**

| 단계 | 사용자 행동 | 화면 상태 | 다운로드 버튼 |
|------|-------------|-----------|---------------|
| ① | 매트릭스 저장 | 결과 렌더링 | ❌ 숨김 |
| ② | 제출용 저장 | 결과 확정 + 워드클라우드 생성 | ✅ `⬇️ 결과물 ZIP` |
| ③ | 문장 감정 수정 | 수정 중 | 🔒 `⬇️ 수정 중 (재제출 필요)` |
| ④ | 재제출용 저장 | 재생성 완료 | ✅ `⬇️ 결과물 ZIP` |
| ⑤ | ZIP 다운로드 | ZIP 저장 | ✅ 그대로 |

---

## 3. 수정할 파일 목록

| # | 파일 | 변경 유형 | 설명 |
|---|------|-----------|------|
| 1 | `src/services/deploy_session_service.py` | 수정 | `create_evaluations_table()`에 `sentiment_corrections` 컬럼 추가 |
| 2 | `src/services/perspective_service.py` | 수정 | `_get_sentence_level_scores`, `calculate_word_scores`, `_aggregate_emotion`, `_generate_cell_content`, `_generate_emotion_cell`, `_generate_nlp_cell`, `generate_perspective_matrix`에 `corrections_map` 파라미터 추가 |
| 3 | `src/routes/perspective_routes.py` | 추가 | 새 API 3개 엔드포인트 + 기존 `api_save_deploy` 수정 |
| 4 | `web/templates/perspective_test.html` | 수정 | 문장별 수정 UI + 재생성 플로우 |

---

## 4. 상세 구현

### 4.1 DB: `deploy_session_service.py` — 컬럼 추가

`create_evaluations_table()` 함수에서 `sentiment_corrections TEXT DEFAULT '{}'` 컬럼을 `data` 컬럼 다음에 추가.

또한 기존 데이터에 대해 마이그레이션 SQL 추가:
```sql
ALTER TABLE evaluations ADD COLUMN sentiment_corrections TEXT DEFAULT '{}';
```

### 4.2 서비스: `perspective_service.py` — corrections 로직

#### 4.2.1 `_get_sentence_level_scores()` — `corrections` 파라미터 추가

```python
def _get_sentence_level_scores(doc, threshold=0.20, weight=2.0, corrections=None):
    """
    corrections: {sentence_index: "positive"|"negative"|"neutral"}
    corrections가 있으면 해당 문장 점수를 강제 설정.
      positive → +1.0, negative → -1.0, neutral → 0.0
    """
    sentences = split_sentences(doc)
    ...
    for i, (pos, neg, neutral) in enumerate(sent_scores_raw):
        if corrections and str(i) in corrections:
            # 사용자 지정 감정으로 강제 오버라이드
            if corrections[str(i)] == 'positive':
                score = 1.0
            elif corrections[str(i)] == 'negative':
                score = -1.0
            else:  # neutral
                score = 0.0
        else:
            # 기존 교정 로직 적용
            score = sentence_sentiment_override(...)
        result.append((sent, score))
    return result
```

#### 4.2.2 `calculate_word_scores()` — `corrections_map` 파라미터 추가

```python
def calculate_word_scores(filtered_evaluations, word_frequency, corrections_map=None):
    """
    corrections_map: {evaluation_id: {sentence_index: sentiment}}
    evaluation_id + sentence_index로 문장을 찾아 해당 문장의 점수를 강제 설정.
    """
```

#### 4.2.3 `_aggregate_emotion()` — `corrections_map` 파라미터 추가

```python
def _aggregate_emotion(filtered_items, threshold=0.20, weight=2.0, corrections_map=None):
    """문장 집계 시 corrections_map 반영"""
```

#### 4.2.4 `_generate_emotion_cell()` — `corrections_map` 파라미터 추가

emotion 셀의 `positive_sentences` / `negative_sentences` 분류를 corrections_map 기반으로 재분류.

neutral로 수정된 문장은 긍/부정 목록에서 제외하여 비율 집계에서도 제외한다 (긍+부 합산 기준으로 비율 재계산).

#### 4.2.5 `_generate_nlp_cell()` — `corrections_map` 파라미터 추가

`calculate_word_scores()` 호출 시 `corrections_map` 전달하여 워드클라우드 이미지 재생성.

#### 4.2.6 `_generate_cell_content()` — `corrections_map` 파라미터 추가

내부의 `_generate_emotion_cell()` 및 `_generate_nlp_cell()` 호출 시 `corrections_map` 전달.

#### 4.2.7 `generate_perspective_matrix()` — `corrections_map` 파라미터 추가

`_generate_cell_content()` 호출 시 `corrections_map` 전달. `api_regenerate_matrix`에서 직접 호출하는 진입점.

### 4.3 라우트: `perspective_routes.py` — API 3개 추가

#### 4.3.1 `GET /api/perspective/sentence-corrections/by-employee/<employee_id>`

해당 직원의 모든 `evaluation_id`에 대한 문장 수정 내역 조회.

경로 충돌 방지: `/sentence-corrections/save` (POST)와 `/sentence-corrections/<employee_id>` (GET)가 동일 prefix를 공유하면 "save"가 employee_id로 해석될 수 있으므로 `/by-employee/<employee_id>`로 분리한다.

```python
@perspective_bp.route('/sentence-corrections/by-employee/<employee_id>', methods=['GET'])
def api_get_sentence_corrections(employee_id):
    # DB에서 해당 직원의 evaluations 데이터 로드
    # 각 evaluation의 sentiment_corrections 값을 수집하여 반환
```

**응답 형식:**
```json
{
  "success": true,
  "corrections": {
    "eval-uuid-1": {"0": "positive", "1": "negative"},
    "eval-uuid-2": {"0": "neutral"}
  }
}
```

#### 4.3.2 `POST /api/perspective/sentence-corrections/save`

문장 수정 내역을 DB에 저장.

```python
@perspective_bp.route('/sentence-corrections/save', methods=['POST'])
def api_save_sentence_corrections():
    data = request.json
    employee_id = data['employee_id']
    corrections = data['corrections']  # {evaluation_id: {sentence_index: sentiment}}
    
    # 각 evaluation_id별로 DB UPDATE
    # UPDATE evaluations SET sentiment_corrections = ? WHERE evaluation_id = ?
```

**요청 형식:**
```json
{
  "employee_id": "emp_123",
  "corrections": {
    "eval-uuid-1": {"0": "positive", "1": "negative", "2": "neutral"}
  }
}
```

#### 4.3.3 `POST /api/perspective/matrix/regenerate`

수정된 감정으로 해당 직원의 매트릭스 + 워드클라우드 재생성.

```python
@perspective_bp.route('/matrix/regenerate', methods=['POST'])
def api_regenerate_matrix():
    data = request.json
    employee_id = data['employee_id']
    options = data['options']  # 기존 matrix/save-deploy와 동일한 옵션
    
    # 1. DB에서 corrections_map 로드
    # 2. generate_perspective_matrix() 호출 시 corrections_map 파라미터 전달
    # 3. 결과 반환 (워드클라우드 URL 포함)
    result = generate_perspective_matrix(unified, employee_id, row_field, col_mode, analysis_type, options, corrections_map=corrections_map)
```

### 4.4 프론트엔드: `perspective_test.html`

#### 4.4.1 문장별 감정 수정 UI

`_generate_emotion_cell`의 결과 데이터에 긍정/부정 문장 목록이 포함되어 있음.  
이를 `renderCellSection`에서 아래와 같이 렌더링:

```html
<!-- 각 문장 행: 라디오 버튼 + 문장 텍스트 -->
<div class="sentence-row" data-eval-id="eval-uuid-1" data-sent-idx="0">
  <input type="radio" name="sent_eval-uuid-1_0" value="positive" checked>
  <input type="radio" name="sent_eval-uuid-1_0" value="negative">
  <input type="radio" name="sent_eval-uuid-1_0" value="neutral">
  <span>문장 내용</span>
</div>
```

- 긍정 문장 → `positive`가 기본 선택
- 부정 문장 → `negative`가 기본 선택
- 기존 neutral 문장은 없으나 (현재 시스템은 긍/부정만 분류), 수정 UI에서는 중립도 선택 가능

**셀 내부 UI 배치:**

```
┌─────────────────────────────────┐
│  12건                           │
│  [워드클라우드 이미지]          │
│  긍 73%  부 27%                 │
│                                 │
│  ▼ 긍정 사유 3건                │
│  ○긍정 ●부정 ○중립  • 성실합니다     │
│  ○긍정 ○부정 ●중립  • 업무가 보통   │
│  ○긍정 ●부정 ○중립  • 개선 필요     │
│                                 │
│  ▼ 부정 사유 2건                │
│  ○긍정 ●부정 ○중립  • 느립니다      │
│  ○긍정 ●부정 ○중립  • 부족합니다    │
└─────────────────────────────────┘
```

#### 4.4.2 수정 상태 수집 함수

```javascript
function collectSentenceCorrections() {
    // 전체 매트릭스 내 모든 .sentence-row 데이터 수집
    // {evaluation_id: {sentence_index: sentiment}} 형태 반환
}
```

#### 4.4.3 "제출용 저장" 기능 확장

두 플로우를 명확히 구분한다:

- **제출용 저장 버튼**: corrections 저장 → `save_to_deploy` (기존 엔드포인트, 내부에서 corrections_map 로드하여 재계산)
- **`api_regenerate_matrix` 엔드포인트**: corrections 이미 저장된 상태에서 워드클라우드만 단독 재생성하는 독립 API (미리보기 새로고침 등 별도 버튼 용도)

기존 `saveDeploy()` 함수 수정:

```javascript
async function saveDeploy(resumeSessionId = null) {
    // 1. 수정된 문장 감정 수집
    const corrections = collectSentenceCorrections();
    
    // 2. corrections 저장 (실패해도 기존 저장은 계속 진행)
    if (Object.keys(corrections).length > 0) {
        try {
            await fetch('/api/perspective/sentence-corrections/save', {
                method: 'POST',
                body: JSON.stringify({employee_id: empId, corrections})
            });
        } catch (e) {
            // 경고만 표시하고 중단하지 않음 (기본 평가 저장이 더 중요)
            console.warn('감정 수정 내역 저장 실패 (기본 저장은 계속 진행):', e);
            showWarning('감정 수정 내역 저장에 실패했습니다. 기본 저장은 계속 진행됩니다.');
            // showWarning: 기존 코드에 있는 토스트/모달 헬퍼 함수
        }
    }
    
    // 3. 기존 제출용 저장 실행
    // save_to_deploy 내부에서 corrections_map을 로드하여 word_scores 재계산 → 워드클라우드 재생성
    // ... 기존 saveDeploy 로직 ...
}
```

#### 4.4.4 결과 리렌더링

`renderDeployComplete`에서 제출 완료 후,  
해당 직원의 통합 결과에 재생성된 워드클라우드 이미지 URL을 반영하여 화면 업데이트.

#### 4.4.5 다운로드 버튼 상태 관리

문장 수정과 다운로드 버튼 간의 상태 동기화:

```javascript
// 미저장 수정 여부 추적 플래그
let _hasUnsavedCorrections = false;

// 1) 제출용 저장 완료 후: 다운로드 버튼 활성화 + 플래그 초기화
function renderDeployComplete(summary) {
    // ... 기존 코드 ...
    const zipBtn = document.getElementById('zipDownloadBtn');
    if (successCount > 0 && window._lastDeploySessionId) {
        zipBtn.style.display = 'inline-block';
        zipBtn.disabled = false;
        zipBtn.textContent = '⬇️ 결과물 ZIP';
        zipBtn.style.opacity = '1';
        zipBtn.style.cursor = 'pointer';
    }
    _hasUnsavedCorrections = false;  // 저장 완료 → 플래그 초기화
}

// 2) 사용자가 문장 수정 시작 시: 다운로드 버튼 비활성화 + 플래그 설정
function onSentenceModified() {
    _hasUnsavedCorrections = true;
    const zipBtn = document.getElementById('zipDownloadBtn');
    if (zipBtn.style.display !== 'none') {
        zipBtn.disabled = true;
        zipBtn.textContent = '⬇️ 수정 중 (재제출 필요)';
        zipBtn.style.opacity = '0.5';
        zipBtn.style.cursor = 'not-allowed';
    }
}

// 3) 문장 라디오 버튼 클릭 시 onSentenceModified 호출
document.addEventListener('change', function(e) {
    if (e.target.matches('.sentence-row input[type="radio"]')) {
        onSentenceModified();
    }
});

// 4) 페이지 이탈 시: 미저장 수정 있으면 경고
window.addEventListener('beforeunload', function(e) {
    if (_hasUnsavedCorrections) {
        e.preventDefault();
        e.returnValue = '수정된 감정 내용이 저장되지 않았습니다. 페이지를 떠나시겠습니까?';
    }
});

// 5) 재제출용 저장 시작 시: 기존 상태 유지 (비활성화 상태 그대로)
// 6) 재제출용 저장 성공 후: renderDeployComplete에서 다시 활성화 + 플래그 초기화
```

**상태 전이 규칙:**

| 상태 | 다운로드 버튼 | 발생 조건 |
|------|--------------|-----------|
| `INITIAL` | 숨김 (`display:none`) | 매트릭스 저장 후, 제출 전 |
| `READY` | 활성화 | 제출용 저장 성공 완료 |
| `MODIFIED` | 비활성화 (텍스트: "⬇️ 수정 중") | 사용자가 아무 문장 라디오 버튼 클릭 |
| `RE_SUBMITTING` | 비활성화 (그대로) | 재제출용 저장 API 호출 중 |
| `RE_READY` | 활성화 | 재제출용 저장 성공 완료 → `READY`와 동일 |

---

## 5. 변경 영향도 분석

| 기존 코드 | 영향 | 대응 |
|-----------|------|------|
| `_get_sentence_level_scores()` | 새로운 파라미터 추가 | 기본값 `None`으로 하위 호환 유지 |
| `calculate_word_scores()` | 새로운 파라미터 추가 | 기본값 `None`으로 하위 호환 유지 |
| `_aggregate_emotion()` | 새로운 파라미터 추가 | 기본값 `None`으로 하위 호환 유지 |
| `_generate_emotion_cell()` | 새로운 파라미터 추가 | 기본값 `None`으로 하위 호환 유지 |
| `_generate_nlp_cell()` | 새로운 파라미터 추가 | 기본값 `None`으로 하위 호환 유지 |
| `_generate_cell_content()` | 새로운 파라미터 추가 (내부 함수로 전달) | 기본값 `None`으로 하위 호환 유지 |
| `generate_perspective_matrix()` | 새로운 파라미터 추가 (`api_regenerate_matrix` 진입점) | 기본값 `None`으로 하위 호환 유지 |
| `save_to_deploy()` | 내부에서 corrections_map 로드 후 재계산 | DB에서 corrections_map 조회 후 전달 |
| `api_generate_matrix()` | **변경 없음** | — |
| `api_save_deploy()` | 내부 `save_to_deploy` 호출 시 corrections_map 반영됨 | 직접 수정 불필요 |

> 모든 기존 함수는 `corrections_map=None` 기본값을 사용하므로, 기존 기능에 **전혀 영향 없음**.

---

## 6. 예외 처리

| 상황 | 처리 |
|------|------|
| corrections_map에 없는 evaluation_id | 기존 교정 로직 그대로 사용 |
| evaluation_id는 있지만 해당 sentence_index 없음 | 무시 (기존 교정 로직 사용) |
| 문장 분할 결과(index 수)가 변경됨 | DB에 저장된 index가 범위를 벗어나면 무시 |
| corrections 저장 API 실패 | 경고 메시지 표시 후 기존 제출용 저장은 계속 진행 (감정 수정보다 기본 평가 저장이 우선) |
| 재생성 실패 | 기존 결과는 유지, 사용자에게 오류 메시지 |
| neutral로 수정된 문장 | 점수 0.0 적용, 긍/부정 분류 목록에서 제외, 비율 집계 시 분모에서도 제외 |
| **문장 수정 중 다운로드 클릭** | 버튼이 `disabled` 상태이므로 클릭 불가 (프론트엔드에서 차단) |
| **수정 후 재제출 전 페이지 이탈** | `beforeunload` 이벤트로 "수정된 내용이 저장되지 않았습니다" 확인 |
| **변경 사항 없는 상태에서 재제출** | corrections 저장 API는 변경 없는 경우 빈 객체 전송, DB UPDATE 생략 |

---

## 7. 구현 순서

```
1단계: deploy_session_service.py — sentiment_corrections 컬럼 추가
2단계: perspective_service.py — corrections_map 로직 구현 (7개 함수 수정: 4.2.1~4.2.7)
3단계: perspective_routes.py — API 3개 엔드포인트 추가
4단계: perspective_test.html — UI + 재생성 플로우 구현
5단계: 통합 테스트
```

---

## 8. 예상 소요 시간

| 단계 | 예상 시간 |
|------|-----------|
| DB 컬럼 추가 | 0.3시간 |
| 서비스 로직 (corrections_map) | 1.5시간 |
| API 엔드포인트 | 1시간 |
| 프론트엔드 UI + 재생성 플로우 | 2시간 |
| 통합 테스트 및 디버깅 | 1시간 |
| **합계** | **약 5.8시간** |
