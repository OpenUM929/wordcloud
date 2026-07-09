# 04. 워드클라우드 생성

> 코드 위치: `wordcloud_project/src/modules/wordcloud_generator.py`

## 개요 — 무엇을 만드는가

워드클라우드는 **자주 나온 단어일수록 크게, 그림처럼 배치한 단어 구름**이다. 이 시스템은 단순히 빈도만 크기로 반영하는 것을 넘어, **각 단어의 감정 점수에 따라 색을 입힌다** — 긍정 단어는 초록 계열, 부정 단어는 붉은 계열로.

따라서 한 장의 워드클라우드만 봐도 "어떤 단어가 많이 쓰였는지(크기)"와 "그 단어가 긍정적이었는지 부정적이었는지(색)"를 동시에 읽을 수 있다.

---

## 적용 분야

- 직원/부서/조직 단위 평가 키워드 요약 이미지
- 감정이 반영된 시각적 리포트
- 다양한 크기/배경색 프리셋으로 보고서·화면용 출력

---

## 기술 상세

### 1. 두 가지 생성 경로

| 메서드 | 엔진 | 특징 | 코드 위치 |
|--------|------|------|-----------|
| `generate()` / `generate_wordcloud_with_options()` | `wordcloud` 라이브러리 | 표준 워드클라우드 | `wordcloud_generator.py:149`, `:204` |
| `generate_with_colors_and_options()` | **커스텀 PIL 비트맵** | 감정 색상 + 충돌 감지 나선 배치 | `wordcloud_generator.py:275` |

핵심은 두 번째, **자체 구현한 감정 색상 워드클라우드**다.

### 2. 크기·배경색 프리셋

코드 위치: `wordcloud_generator.py:18` `WordCloudConfig`

```python
SIZE_PRESETS = {
    "thumbnail": {400x300}, "small": {600x400}, "standard": {800x600},
    "large": {1000x750}, "xlarge": {1200x900}, "hd": {1600x1200}
}
SUPPORTED_COLORS = ["white","black","lightblue","lightgray",
                    "lightgreen","lightyellow","lightpink"]
```

### 3. 빈도 → 글자 크기 (비선형 스케일)

빈도를 그대로 크기에 비례시키면 1등 단어만 거대하고 나머지는 안 보인다. 그래서 **제곱근에 가까운 곡선(`ratio ** 0.6`)** 으로 완만하게 키운다.

코드 위치: `wordcloud_generator.py:324`

```python
def get_font_size(freq):
    ratio = freq / max_freq
    return max(min_font, int(min_font + (ratio ** 0.6) * (max_font - min_font)))
```

폰트 범위도 캔버스 면적과 단어 수로 동적 계산한다(`wordcloud_generator.py:314`):

```python
canvas_area = width * height
max_font = min(min(width, height)//5,
               int(math.sqrt(canvas_area / max(n_words,10)) * 1.0))
max_font = max(max_font, 14)
min_font = max(8, max_font // 5)
```

### 4. 감정 색상 매핑 (핵심 차별점)

각 단어의 감정 점수(-1.0 ~ +1.0)를 5단계 파스텔 색으로 변환한다.

코드 위치: `wordcloud_generator.py:332`

```python
def get_emotion_color(word):
    score = max(-1.0, min(1.0, word_scores.get(word, 0.0)))
    if   score >  0.5: return (100,190,145)   # 강한 긍정 — 파스텔 민트그린
    elif score >  0.0: return (145,210,165)   # 약한 긍정 — 파스텔 그린
    elif score > -0.5: return (172,178,200)   # 중립 — 파스텔 라벤더그레이
    elif score > -1.0: return (230,150,150)   # 약한 부정 — 파스텔 살몬
    else:              return (215,120,130)   # 강한 부정 — 파스텔 로즈
```

| 점수 구간 | 의미 | 색 |
|-----------|------|----|
| > 0.5 | 강한 긍정 | 민트그린 |
| 0 ~ 0.5 | 약한 긍정 | 그린 |
| -0.5 ~ 0 | 중립 | 라벤더그레이 |
| -1.0 ~ -0.5 | 약한 부정 | 살몬 |
| ≤ -1.0 | 강한 부정 | 로즈 |

> 감정 점수는 감정 분석 모듈([05장](05-emotion-analysis.md))이 산출한 단어별 점수(`word_scores`)에서 온다. 즉 워드클라우드는 NLP·감정 분석 결과를 **시각적으로 합성**한 최종 산출물이다.

### 5. 충돌 감지 나선형 배치

단어들이 겹치지 않게 **중앙에서 바깥으로 나선(spiral)을 그리며** 빈자리를 찾아 배치한다. PIL 비트맵에 이미 그려진 픽셀과 겹치는지 검사한다.

코드 위치: `wordcloud_generator.py:341` `spiral_positions()`

```python
def spiral_positions(cx, cy, start_angle):
    diagonal = math.sqrt(width**2 + height**2)
    b = diagonal / (2 * math.pi * 10)
    theta = 0.0
    ...
```

- `random.seed(42)` 로 **재현 가능한** 배치를 보장(`wordcloud_generator.py:304`) — 같은 입력이면 같은 그림.
- 빈도 내림차순으로 큰 단어부터 중앙에 배치(`wordcloud_generator.py:306`).

### 6. 불용어 2차 제거

워드클라우드 생성 시점에도 한 번 더 불용어를 제거한다(`wordcloud_generator.py:294`) — NLP 단계에서 놓친 단어를 차단하는 안전망.

### 7. 렌더링 백엔드

- `matplotlib.use('Agg')` — GUI 없는 서버 환경에서 이미지 파일로 렌더링.
- 폰트: `malgun.ttf`(맑은 고딕) — 한글 표시용(`wordcloud_generator.py:290`).
- 출력: PNG (PIL `Image`/`ImageDraw`/`ImageFont`).

---

## 핵심 포인트 정리

| 항목 | 내용 |
|------|------|
| 엔진 | `wordcloud` 라이브러리 + 커스텀 PIL 비트맵 배치 |
| 크기 스케일 | `ratio ** 0.6` 비선형 (1등 독점 방지) |
| 색상 | 감정 점수 5단계 파스텔 매핑 (긍정 초록 ↔ 부정 빨강) |
| 배치 | 충돌 감지 나선형, `seed=42` 재현 보장 |
| 폰트/렌더 | 맑은 고딕, matplotlib Agg, PNG 출력 |

---

*다음: [05. 감정 분석 (KoTE 딥러닝)](05-emotion-analysis.md)*
