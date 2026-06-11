# 중립 문장 배포 카드 표시

> 상태: DN | 작성일: 2026-06-10 | 완료일: 2026-06-10

## 배경 및 목적

현재 배포 카드(deploy card)에는 **긍정 문장**과 **부정 문장**만 표시된다.
문장별 감정 보정 기능(`0610_03_sentiment-correction`) 도입 이후, 사용자가 어떤 문장을 **중립**으로 보정했는지 확인할 수 없다.
또한 원래부터 중립인 문장들도 배포 카드에서 전혀 노출되지 않아 데이터 누락 우려가 있다.

이 계획서는 배포 카드에 **중립 컬럼을 추가**하여, 보정으로 중립이 된 문장과 원래 중립인 문장을 모두 표시하는 방안을 정의한다.

---

## §1 현재 구조 분석

### 1-1. 배포 카드 데이터 흐름

```
_generate_wc_for_items()           ← perspective_service.py
  └─ pos_details / neg_details     ← 긍/부 문장 목록 반환
       └─ save_to_deploy()         ← DB에 저장
            └─ /api/deploy         ← JSON 응답
                 └─ _renderDeploymentSentences()  ← perspective_test.html JS
                      └─ 긍정 탭 / 부정 탭
```

### 1-2. 중립 문장이 사라지는 지점

`_generate_wc_for_items` 내부 분류 로직:
```python
# 현재: 긍/부 버킷만 존재
if final_label == 'positive':
    pos_details.append(...)
elif final_label == 'negative':
    neg_details.append(...)
# neutral → 아무것도 하지 않음 (누락)
```

---

## §2 변경 범위

| 파일 | 변경 내용 |
|------|-----------|
| `src/services/perspective_service.py` | `neutral_details` 버킷 추가, `_generate_wc_for_items` 반환값 변경, `save_to_deploy` 결과 포함 |
| `web/templates/perspective_test.html` | 배포 카드에 중립 탭/컬럼 추가, `_renderDeploymentSentences` JS 수정 |

---

## §3 Python 변경 — `perspective_service.py`

### 3-1. `_generate_wc_for_items` — 중립 버킷 추가

**위치**: `_generate_wc_for_items` 클로저 내부 문장 분류 루프

**Before:**
```python
if final_label == 'positive':
    pos_details.append({
        'sentence': sent,
        'score': score,
        'sentence_index': i,
        'db_id': db_id,
    })
elif final_label == 'negative':
    neg_details.append({
        'sentence': sent,
        'score': score,
        'sentence_index': i,
        'db_id': db_id,
    })
```

**After:**
```python
detail_item = {
    'sentence': sent,
    'score': score,
    'sentence_index': i,
    'db_id': db_id,
}
if final_label == 'positive':
    pos_details.append(detail_item)
elif final_label == 'negative':
    neg_details.append(detail_item)
else:  # neutral
    neutral_details.append(detail_item)
```

**`neutral_details` 초기화 추가**: 클로저 상단에서
```python
neutral_details = []
```

### 3-2. 반환값 변경

**① `_generate_wc_for_items` 반환 튜플 8→9개**

현재 (line 1721):
```python
return combined_url, positive_url, negative_url, combined_sent, positive_sent, negative_sent, pos_details, neg_details
```

변경:
```python
return combined_url, positive_url, negative_url, combined_sent, positive_sent, negative_sent, pos_details, neg_details, neutral_details
```

**② `save_to_deploy` unpacking (line 1726)도 함께 수정**

현재:
```python
combined_url, positive_url, negative_url, combined_sent, positive_sent, negative_sent, pos_det, neg_det = _generate_wc_for_items(filtered_items, '통합')
```

변경:
```python
combined_url, positive_url, negative_url, combined_sent, positive_sent, negative_sent, pos_det, neg_det, neu_det = _generate_wc_for_items(filtered_items, '통합')
```

**③ 반환 dict에 `neutral_details` 포함**

`save_to_deploy` result dict 추가:
```python
result_data = {
    ...
    'pos_details': wc_result.get('pos_details', []),
    'neg_details': wc_result.get('neg_details', []),
    'neutral_details': wc_result.get('neutral_details', []),   # 신규
    ...
}
```

### 3-3. `save_to_deploy` — neutral_details 포함

`save_to_deploy`가 배포 결과를 JSON으로 저장하는 부분에서, `neutral_details`도 함께 포함:
```python
result_data = {
    ...
    'pos_details': wc_result.get('pos_details', []),
    'neg_details': wc_result.get('neg_details', []),
    'neutral_details': wc_result.get('neutral_details', []),   # 신규
    ...
}
```

> **참고**: `neutral` 문장은 `_get_sentence_level_scores`에서 `score = 0.0`이 반환된다. 워드클라우드 가중치 기여도는 0이지만, 문장 목록으로서 배포 카드에 표시할 수 있다.

---

## §4 JavaScript 변경 — `perspective_test.html`

### 4-1. `_renderDeploymentSentences` — 중립 탭 추가

현재 렌더링 구조:
```
[통합] [긍정] [부정]
```

변경 후:
```
[통합] [긍정] [부정] [중립]
```

**탭 버튼 추가**:
```javascript
// 기존 탭 버튼 생성 코드 옆에
'<button class="tab-btn" data-tab="neutral">중립 (' + (data.neutral_details || []).length + ')</button>'
```

**중립 탭 콘텐츠 영역 추가**:
```javascript
var neutralHtml = '<div class="tab-content" data-tab-content="neutral" style="display:none;">';
var neutralItems = data.neutral_details || [];
if (neutralItems.length === 0) {
    neutralHtml += '<p class="empty-msg">중립 문장 없음</p>';
} else {
    neutralItems.forEach(function(s) {
        neutralHtml += '<div class="sentence-row neutral-row" data-db-id="' + s.db_id + '" data-sentence-index="' + s.sentence_index + '">'
            + '<span class="sent-text">' + escapeHtml(s.sentence) + '</span>'
            + '<span class="sent-score">' + (s.score !== undefined ? s.score.toFixed(3) : '-') + '</span>'
            + buildRadioGroup('neutral', s.db_id, s.sentence_index)
            + '</div>';
    });
}
neutralHtml += '</div>';
```

> **비고**: 실제 코드(`_renderDeploymentSentences` line 1428)에서 라디오 버튼은 inline으로 하드코딩되어 있다. 중립 탭에도 동일한 패턴(`input[type="radio"]` 3개 + `flex` 레이아웃)으로 추가한다.

### 4-2. `collectSentenceCorrections` — 변경 없음

현재 `querySelectorAll('.sentence-row[data-db-id]')`로 **모든 탭**의 `.sentence-row`를 수집하므로, 중립 탭에 `.sentence-row.neutral-row` 클래스를 그대로 적용하면 자동으로 포함된다.

### 4-3. `afterState` — 중립 문장 추적

`resubmitEmployee`의 `afterState` 구성 시, 중립 탭의 `sentence-row`도 `querySelectorAll`에 이미 포함되므로 **변경 없음**.

---

## §5 UI 레이아웃

### 탭 구성 (최종)

```
┌──────────────────────────────────────────────────────┐
│  [통합]  [긍정 (N)]  [부정 (N)]  [중립 (N)]           │
├──────────────────────────────────────────────────────┤
│  (선택된 탭 내용)                                       │
│  ┌─────────────────────────────────────────┬──────┐  │
│  │ 문장 텍스트                             │ 점수 │  │
│  │                  ○긍정  ○부정  ●중립    │      │  │
│  └─────────────────────────────────────────┴──────┘  │
└──────────────────────────────────────────────────────┘
```

- **중립 탭**: 중립 문장 목록 + 각 문장에 긍/부/중립 라디오 버튼(재보정 가능)
- **중립 문장 기본 선택**: 라디오 버튼 기본값 = `neutral` (현재 상태 반영)
- **긍/부 탭의 중립 라디오**: 이미 있는 `buildRadioGroup` 방식 유지

---

## §6 구현 결과

### 실제 변경 내역 (2026-06-10)

**`perspective_service.py`**
- `_generate_wc_for_items` 조기 반환 튜플 8→9개 확장
- `neutral_details = []` 버킷 추가 (line 1686)
- `correction == 'neutral'` 분기: `pass` → `neutral_details.append({**base, 'sentiment': 'neutral'})`
- 분류 루프 말미 `else` 추가: top_pos/top_neg 모두 미포함 시 자동으로 `neutral_details`에 수집
- logger에 `neutral_details` 카운트 추가
- 반환 튜플 마지막에 `neutral_details` 추가
- 언패킹 변수 `neu_det` 추가
- result dict에 `'neutral_sentence_details': neu_det` 추가

**`perspective_test.html`**
- `_renderDeploymentSentences` — 중립 radio 버튼에 `checked` 속성 추가 (`s.sentiment === 'neutral'` 시)
- `row_results` 경로 컬럼 배열에 `['중립', '', [], '#6c757d', rowData.neutral_sentence_details || null]` 추가
- 직접 결과 경로 컬럼 배열에 `['중립', '', [], '#6c757d', res.neutral_sentence_details || null]` 추가
- `afterState` 추적 — `rv.neutral_sentence_details` 및 `d.neutral_sentence_details` 항목 추가

### 계획서 vs 실제 구현 차이점

| 항목 | 계획서 | 실제 구현 |
|------|--------|-----------|
| 결과 키명 | `neutral_details` | `neutral_sentence_details` (기존 패턴 일치) |
| detail_item 키 | `'sentence'` | `'text'` (실제 코드 패턴) |
| 중립 URL | 미언급 | `''` 빈 문자열 (이미지 없음) |
| 암묵적 중립 수집 | `else: neutral_details.append` | 동일 적용 |

### 테스트 체크리스트
- [ ] 서버 재시작 후 배포 실행 → 중립 탭에 문장 표시 확인
- [ ] 중립 탭 문장 → 긍정/부정 재보정 후 재제출 → 해당 탭으로 이동 확인
- [ ] 긍정 탭 문장 → 중립 보정 후 재제출 → 중립 탭으로 이동 확인

---

## §7 범위 외 (이번 작업 미포함)

- 워드클라우드 이미지 자체에 중립 단어 반영 (score=0이므로 가중치 0, 변경 없음)
- 중립 문장 개수의 직원 통계 집계
- 중립 탭 CSS 디자인 세부 커스터마이징 (기존 긍/부 스타일 재사용)
