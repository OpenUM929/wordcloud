> 상태: Done(코드 적용 확인, 2026-06-18) | 작성일: 2026-06-10

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-10 | - | 최초 작성 |
| 2026-06-10 | 3.1③⑤④, 3.2, 3.6, 3.7, 5, 6 | 검토 반영: wordcloud.html JS 누락 추가, api_routes/wordcloud_service 누락 파일 추가, combined 모드 주석 명확화, 감정 색상 제거 경고 추가, 라인 번호 수정, 구현 순서 재정렬 |

# 배포 모드 통합 추가 + 색상 선택 + 프리셋 확장

---

## 1. 요구사항

| # | 요구사항 | 설명 |
|---|----------|------|
| 1 | 배포 모드에 `통합` 추가 | 현재 `통합+개별`, `개별` → `통합`, `통합+개별`, `개별` |
| 2 | 기타 옵션에 색상 선택 추가 | 감정 색상 체크박스 → 색상 픽커 |
| 3 | 프리셋 확장 | `WordCloudPreset`이 배포 모드·색상도 저장/불러오기 |

**효과:** 사용자가 `통합` + 색상 선택만으로 긍정/부정 데이터 각각 원하는 단색 워드클라우드 생성 가능.

---

## 2. 현재 시스템 분석

### 2.1 배포 모드 (프론트엔드)
- `perspective_test.html:315-317`: `통합+개별`(기본), `개별` 2개 라디오
- `perspective_test.html:661`: `getDeployMode()`로 라디오 값 읽음
- `perspective_test.html:962`: `saveDeploy()`에서 `deploy_mode`로 전송

### 2.2 배포 모드 (백엔드)
- `perspective_service.py`: `save_to_deploy()`에서 `deploy_mode` 옵션을 전혀 사용하지 않음
- `row_combine_all=True`면 통합, `False`면 개별 row로 동작
- 긍정/부정/통합 3종 워드클라우드를 항상 생성 (분리 로직 내장)

### 2.3 색상 처리
- `apply_emotion_colors` 옵션: True면 감정 점수 기반 색상, False면 회색 단색
- `_save_wordcloud_to_path` → `generate_with_colors_and_options`로 전달
- `wordcloud_generator.py:327-334`: `get_emotion_color(word)` 함수로 점수별 색상 반환

### 2.4 프리셋
- `WordCloudPreset.js`: localStorage 기반, `options` 객체 통째로 저장
- `wcPresetSave()`: `getWcOptions()` → `WordCloudPreset.save(name, options)`
- `wcPresetLoad()`: `WordCloudPreset.load(id)` → `applyWcOptions(options)`
- 단순 구조라 옵션만 추가하면 자동 확장됨

---

## 3. 변경 대상 및 상세

### 3.1 `perspective_test.html` (프론트엔드 · +20줄)

**① 배포 모드 라디오 (line 315-317)**
```html
<label><input type="radio" name="deployMode" value="combined" checked> 통합</label>
<label><input type="radio" name="deployMode" value="combined+individual"> 통합+개별</label>
<label><input type="radio" name="deployMode" value="individual"> 개별</label>
```

**② 기타 옵션: 감정 색상 체크박스 → 색상 픽커 (line 416)**
```html
<div style="display:flex;align-items:center;gap:6px;">
    <label style="font-size:12px;color:#555;white-space:nowrap;">단어 색상:</label>
    <input type="color" id="wco-word-color" value="#333333" onchange="updateWcOptionsSummary()">
</div>
```

**③ `getWcOptions()`에 `word_color` 추가 (line 1931)**
```javascript
function getWcOptions() {
    const sizeVal = (document.querySelector('input[name="wcoSize"]:checked') || {value: '800x600'}).value;
    const [w, h] = sizeVal.split('x').map(Number);
    const posCbs = document.querySelectorAll('.wco-pos-cb:checked');
    return {
        background_color: document.getElementById('wco-bg-color').value || 'white',
        width: w, height: h,
        max_words: parseInt(document.getElementById('wco-max-words').value),
        apply_emotion_colors: false,  // 색상 픽커로 대체 → 감정 색상 항상 비활성화
        word_color: document.getElementById('wco-word-color').value,
        remove_profanity: document.getElementById('wco-remove-profanity').checked,
        wordcloud_pos: Array.from(posCbs).map(cb => cb.value),
    };
}
```

> ⚠️ `wco-emotion-colors` 체크박스를 제거하고 `apply_emotion_colors`를 `false`로 고정하면 감정 점수 기반 색상 모드가 `perspective_test.html`에서도 영구 비활성화됨. 기존 프리셋의 `apply_emotion_colors: true` 항목은 불러와도 UI 반영 불가. 의도적 변경임을 확인 후 적용.

**④ `applyWcOptions()`에 `word_color` 복원 추가 (line 1946)**
```javascript
if (options.word_color) {
    document.getElementById('wco-word-color').value = options.word_color;
}
```

**⑤ `updateWcOptionsSummary()`에 `word_color` 표시 (line 1916)**
```javascript
if (opts.word_color) parts.push('색상:' + opts.word_color);
```

**⑥ `saveDeploy()`에서 word_color 전달 (line 960-970)**
```javascript
word_color: _wco.word_color,
```

### 3.2 `wordcloud.html` (프론트엔드 · +15줄)

**① 감정 색상 체크박스 → 색상 픽커 (line 379-380)**
```html
<!-- 제거 -->
<!-- <label><input type="checkbox" id="applyEmotionColors" checked> <span>감정 기반 색상 적용</span></label> -->

<!-- 추가 -->
<div class="emotion-colors-group" style="display:flex;align-items:center;gap:6px;">
    <label style="font-size:12px;white-space:nowrap;">단어 색상:</label>
    <input type="color" id="wordcloudWordColor" value="#333333" oninput="updatePreviewSummary && updatePreviewSummary()">
</div>
```

> ⚠️ `applyEmotionColors` 체크박스를 제거하면 감정 점수 기반 색상 모드가 `wordcloud.html`에서 영구 비활성화됨. 의도적 변경임을 확인 후 적용.

**② `getPreviewOptions()`에 `word_color` 추가, `apply_emotion_colors: false` 고정 (line ~1100-1112)**
```javascript
function getPreviewOptions() {
    ...
    return {
        ...,
        apply_emotion_colors: false,
        word_color: document.getElementById('wordcloudWordColor').value,
        ...
    };
}
```

**③ `applyWcPreviewOptions()`에 `word_color` 복원 추가 (line ~1130)**
```javascript
if (options.word_color) {
    document.getElementById('wordcloudWordColor').value = options.word_color;
}
```

### 3.3 `perspective_service.py` — `save_to_deploy()` (백엔드 · +15줄)

**① `deploy_mode` 옵션 처리 (line 1559 직후)**
```python
deploy_mode = options.get('deploy_mode', 'combined+individual')
```

**② 통합(combined) 모드: row 분리 없이 전체를 하나의 그룹으로 처리**
```python
if deploy_mode == 'combined':
    # row_values 분리 없이 모든 아이템을 하나의 그룹으로 합쳐 처리.
    # 3종 PNG(통합/긍정/부정)는 그대로 생성됨 — "combined"는 row 묶음 방식, PNG 종류가 아님.
    combined_url, positive_url, negative_url, combined_sent, positive_sent, negative_sent = _generate_wc_for_items(filtered_items, '통합')
    result = {
        'name': deploy_name, 'timestamp': ts,
        'combined': combined_url,
        'positive': positive_url, 'negative': negative_url,
        'combined_sentences': combined_sent,
        'positive_sentences': positive_sent, 'negative_sentences': negative_sent,
    }
    ...
```

**③ `wc_options`에 `word_color` 추가 (line 1564)**
```python
'word_color': options.get('word_color'),
```

### 3.4 `perspective_service.py` — `_save_wordcloud_to_path()` (+1줄)

```
word_color=options.get('word_color'),
```

### 3.5 `perspective_service.py` — 기타 옵션 저장 (+2줄)

`_append_to_deploy_manifest()` (line 1437-1445) 및 `_index_matrix_to_manifest()` (line 1493-1501): `word_color` 옵션 저장.

### 3.6 `api_routes.py` — `/api/analyze` 엔드포인트 (+2줄)

현재 `generate_with_colors_and_options()` 호출(line 162)에 `apply_emotion_colors`·`word_color` 미전달.

```python
success = generator.generate_with_colors_and_options(
    word_freq, word_scores, output_path,
    background_color=background_color,
    width=width, height=height, max_words=max_words,
    remove_stopwords=not remove_profanity,
    apply_emotion_colors=apply_emotion_colors,   # 추가 (line 94에서 이미 읽음)
    word_color=data.get('word_color'),            # 추가
)
```

### 3.7 `wordcloud_service.py` — `_generate_one()` (+2줄)

현재 `generate_with_colors_and_options()` 호출(line 169)에 `apply_emotion_colors`·`word_color` 미전달.

```python
ok = generator.generate_with_colors_and_options(
    freq, scores, out_path,
    background_color=background_color,
    max_words=max_words,
    width=width,
    height=height,
    apply_emotion_colors=apply_emotion_colors,   # 추가 (line 39에서 이미 읽음)
    word_color=data.get('word_color'),            # 추가
)
```

### 3.8 `wordcloud_generator.py` — `generate_with_colors_and_options()` (+5줄)

```python
def generate_with_colors_and_options(self, word_freq, word_scores,
    output_path=None, background_color='white', max_words=100,
    width=800, height=600, remove_stopwords=True,
    apply_emotion_colors=True, word_color=None):
```

색상 로직 변경 (line 384):
```python
if word_color:
    fill_color = hex_to_rgb(word_color)
elif apply_emotion_colors:
    fill_color = get_emotion_color(word)
else:
    fill_color = (50, 50, 50)
```

**필요한 유틸리티 함수 추가:**
```python
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
```

---

## 4. 프리셋 동작 방식

`WordCloudPreset`은 `perspective_test.html`의 `getWcOptions()` 결과 전체를 `options`로 저장.

- `getWcOptions()`에 `word_color` 추가 → 프리셋에 자동 포함
- `applyWcOptions()`에 `word_color` 복원 추가 → 불러오기 시 자동 적용

**저장 예:**
```json
{
  "id": "1234567890",
  "name": "긍정_데이터용",
  "savedAt": "2026-06-10T...",
  "options": {
    "background_color": "white",
    "width": 800, "height": 600, "max_words": 80,
    "apply_emotion_colors": false, "remove_profanity": false,
    "wordcloud_pos": ["Noun"],
    "word_color": "#28a745"
  }
}
```

---

## 5. 영향도

| 파일 | 변경 | 영향 범위 |
|------|------|-----------|
| `perspective_test.html` | 라디오 1줄, 색상 픽커 3줄, JS 10줄 | 프론트엔드 |
| `wordcloud.html` | 색상 픽커 HTML + JS(getPreviewOptions, applyWcPreviewOptions) | 프론트엔드 |
| `perspective_service.py` | `deploy_mode` 분기, `word_color` 전달 | 백엔드 |
| `api_routes.py` | `apply_emotion_colors`, `word_color` 제너레이터 전달 추가 | 백엔드 |
| `wordcloud_service.py` | `apply_emotion_colors`, `word_color` 제너레이터 전달 추가 | 백엔드 |
| `wordcloud_generator.py` | `word_color` 파라미터 + hex_to_rgb | 백엔드 |
| `deploy_gallery.html` | 변경 없음 | - |
| `WordCloudPreset.js` | 변경 없음 | 자동 확장 |
| 기존 데이터 | 영향 없음 | 하위 호환 |

---

## 6. 구현 순서

1. `wordcloud_generator.py` — `word_color` 파라미터, `hex_to_rgb()` 추가 (하위 의존)
2. `perspective_service.py` — `deploy_mode` 분기, `word_color` 전달
3. `api_routes.py` — `apply_emotion_colors`, `word_color` 제너레이터 전달
4. `wordcloud_service.py` — `apply_emotion_colors`, `word_color` 제너레이터 전달
5. `perspective_test.html` — 배포 모드 라디오, 색상 픽커, JS 확장
6. `wordcloud.html` — 색상 픽커 HTML + JS 확장
7. 통합 테스트
