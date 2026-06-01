# 애니메이션 워드클라우드 전환 및 외부 연계 계획서

> 작성일: 2026-05-29  
> 상태: 구현 대기  
> 목표: 이미지 기반 워드클라우드 → 데이터 기반 SVG 애니메이션 워드클라우드 + 외부 연계

---

## 목차

1. [현황 분석](#1-현황-분석)
2. [목표 아키텍처](#2-목표-아키텍처)
3. [Phase 1 — Data API](#3-phase-1--data-api)
4. [Phase 2 — JS 애니메이션 렌더러](#4-phase-2--js-애니메이션-렌더러)
5. [Phase 3 — 테스트 페이지](#5-phase-3--테스트-페이지)
6. [Phase 4 — 외부 연계](#6-phase-4--외부-연계)
7. [구현 순서 및 일정](#7-구현-순서-및-일정)
8. [신규 파일 목록](#8-신규-파일-목록)

---

## 1. 현황 분석

### 현재 아키텍처
```
CSV 업로드 → batch_processor → WordCloudGenerator (PIL + python-wordcloud)
           → wordcloud_{id}.png 저장 → <img src=""> 로 화면 출력
```

### 활용 가능한 기존 데이터 구조
`tmeta/employee_{id}.json`에 이미 다음 데이터가 존재 — 추가 처리 없이 렌더링에 바로 활용 가능:

| 필드 | 내용 | 활용처 |
|------|------|--------|
| `consolidated_analysis.word_frequency` | `{단어: 빈도수}` | 단어 크기 결정 |
| `evaluations[].emotion_analysis_results` | 평가별 감정 점수 | 단어별 감정 색상 |
| `consolidated_analysis.emotion_distribution` | 통합 감정 분포 | 전체 색상 톤 |
| `target_employee_department/position` | 부서·직책 | 메타 표시 |
| `total_evaluations` | 평가 건수 | 데이터 규모 표시 |

**결론**: 이미지 재생성 없이 기존 JSON에서 바로 애니메이션 렌더링 가능

---

## 2. 목표 아키텍처

```
[기존 배치 처리] — 변경 없음
       ↓
[Phase 1] Data API
  GET /api/wordcloud/data/{batch_id}/{employee_id}
  → {words: [{text, weight, emotion_score, color, ...}]} JSON 반환

[Phase 2] JS 애니메이션 렌더러 (WordCloudRenderer.js)
  d3-cloud 레이아웃 + GSAP 애니메이션
  → 브라우저에서 직접 SVG 렌더링

[Phase 3] 테스트 페이지 (/wordcloud-preview)
  기존 배치 선택 → 직원 선택 → 파라미터 조정 → 실시간 미리보기

[Phase 4] 외부 연계
  iFrame embed / REST API (CORS) / Webhook
```

---

## 3. Phase 1 — Data API

### 신규 엔드포인트

```
GET  /api/wordcloud/data/{batch_id}/{employee_id}   단일 직원 데이터
GET  /api/wordcloud/data/batch/{batch_id}            배치 전체 집계
POST /api/wordcloud/data/custom                      임시 텍스트 → 데이터
```

### 응답 데이터 구조

```json
{
  "meta": {
    "employee_id": "EMP001",
    "batch_id": "batch_20260520_1",
    "department": "개발팀",
    "position": "팀장",
    "total_evaluations": 12,
    "generated_at": "2026-05-29T10:00:00"
  },
  "words": [
    {
      "text": "리더십",
      "weight": 45,
      "normalized_weight": 1.0,
      "emotion_score": 0.82,
      "emotion_label": "강한_긍정",
      "color": "#64BF91",
      "frequency": 45
    }
  ],
  "emotion_summary": {
    "positive_ratio": 0.72,
    "neutral_ratio": 0.18,
    "negative_ratio": 0.10,
    "dominant_emotion": "positive"
  },
  "render_hints": {
    "suggested_max_words": 60,
    "color_theme": "emotion_based",
    "total_word_count": 180
  }
}
```

### 색상 매핑 (기존 PIL 생성기와 동일 기준 유지)

```python
# src/services/wordcloud_data_service.py
EMOTION_COLORS = {
    "강한_긍정":  "#64BF91",   # mint green   (score > 0.5)
    "약한_긍정":  "#91D2A5",   # light green  (0 < score ≤ 0.5)
    "중립":       "#ACB2C8",   # lavender     (-0.5 < score ≤ 0)
    "약한_부정":  "#E69696",   # salmon       (-1 < score ≤ -0.5)
    "강한_부정":  "#D77882",   # rose         (score ≤ -1)
}
```

### 신규 파일

```
src/services/wordcloud_data_service.py    데이터 추출 로직
src/routes/wordcloud_data_routes.py       API 엔드포인트 등록
```

---

## 4. Phase 2 — JS 애니메이션 렌더러

### 라이브러리

| 라이브러리 | 역할 | 비고 |
|-----------|------|------|
| **d3-cloud** v1.2.7 | 워드 레이아웃 계산 (위치/각도/크기) | 오픈소스, 한글 지원 |
| **D3.js** v7 | SVG 렌더링 및 데이터 바인딩 | d3-cloud 기반 |
| **GSAP** v3 | 애니메이션 타임라인 | CDN, 선택적 적용 |

### 렌더러 구조

```
web/static/js/wordcloud/
├── WordCloudRenderer.js      핵심 렌더러 클래스
├── WordCloudAnimator.js      애니메이션 제어
├── WordCloudTheme.js         색상/스타일 테마
└── WordCloudEmbed.js         iframe embed용 경량 버전
```

### WordCloudRenderer.js 인터페이스

```javascript
class WordCloudRenderer {
  constructor(containerId, options = {})
  // options: { width, height, maxWords, animationMode, theme }

  async loadFromAPI(batchId, employeeId) { ... }
  loadFromData(wordData) { ... }     // 외부 데이터 직접 주입
  render() { ... }                    // 레이아웃 계산 + SVG 생성
  animate(mode) { ... }               // 'fadeIn' | 'spiral' | 'pop'
  onWordClick(callback) { ... }       // 단어 클릭 이벤트
  onWordHover(callback) { ... }       // 단어 호버 툴팁
  exportSVG() { ... }                 // SVG 문자열 반환
  exportPNG() { ... }                 // Canvas → PNG blob
  resize(width, height) { ... }
}
```

### 애니메이션 모드

| 모드 | 설명 |
|------|------|
| `fadeIn` | 중앙→외곽 순차 등장. 가중치 높은 단어부터 fade in |
| `spiral` | 나선형 배치 + d3-cloud 기본 레이아웃 트랜지션 |
| `pop` | transform scale 0 → 정상 크기로 팝 |

### 호버 툴팁 내용

```
[단어: 리더십]
빈도: 45회
감정: 강한 긍정 (0.82)
████████░░ 82%
```

---

## 5. Phase 3 — 테스트 페이지

### URL

```
GET /wordcloud-preview                            테스트 페이지 진입
GET /api/wordcloud/preview/employees/{batch_id}   배치 내 직원 목록
```

(배치 목록은 기존 `GET /api/batch/list` 재활용)

### 레이아웃

```
┌────────────────────────────────────────────────────────────┐
│  [← 메인으로]     애니메이션 워드클라우드 테스트             │
├─────────────────┬──────────────────────────────────────────┤
│  [데이터 선택]   │         워드클라우드 미리보기             │
│  ─────────────  │                                          │
│  배치: [▼]      │  ┌──────────────────────────────────┐   │
│                 │  │                                  │   │
│  직원: [▼]      │  │    SVG 애니메이션 렌더링 영역     │   │
│                 │  │                                  │   │
│  [렌더링 옵션]  │  └──────────────────────────────────┘   │
│  ─────────────  │                                          │
│  최대 단어수:   │  ┌──── 단어 상세 데이터 ──────────────┐  │
│  [슬라이더]     │  │ 단어   빈도  감정점수  감정레이블   │  │
│                 │  │ 리더십  45   0.82    강한 긍정 ██ │  │
│  애니메이션:    │  │ 소통    38   0.41    약한 긍정 █  │  │
│  ○ fadeIn       │  └───────────────────────────────────┘  │
│  ○ spiral       │                                          │
│  ○ pop          │  [SVG 내보내기] [PNG 내보내기] [JSON복사] │
│                 │                                          │
│  배경색: [🎨]   │                                          │
│                 │                                          │
│  [렌더링 시작]  │                                          │
└─────────────────┴──────────────────────────────────────────┘
```

### 동작 흐름

```
1. 페이지 진입
   → GET /api/batch/list
   → 배치 드롭다운 채우기

2. 배치 선택
   → GET /api/wordcloud/preview/employees/{batch_id}
   → batch_summary.json의 employee_ids 반환
   → 직원 드롭다운 채우기

3. 직원 선택 + [렌더링 시작] 클릭
   → GET /api/wordcloud/data/{batch_id}/{employee_id}
   → WordCloudRenderer.loadFromData(response.words)
   → renderer.render() + renderer.animate(selectedMode)

4. 단어 클릭 (옵션)
   → 해당 단어가 포함된 평가 문장 발췌 팝업
```

### 비교 보기 (옵션)

같은 직원의 시점별 변화를 나란히 비교:
```
[배치 A ▼]  vs  [배치 B ▼]
[직원 ▼  ]      [직원 ▼  ]
      ↓                ↓
[워드클라우드]   [워드클라우드]
```

### 신규 파일

```
web/templates/wordcloud_preview.html
web/static/js/wordcloud/WordCloudRenderer.js
web/static/js/wordcloud/WordCloudAnimator.js
web/static/js/wordcloud/WordCloudTheme.js
src/routes/wordcloud_preview_routes.py
```

---

## 6. Phase 4 — 외부 연계

### 4-1. iFrame Embed

```html
<!-- 외부 시스템에서 삽입하는 코드 -->
<iframe
  src="https://wordcloud.internal/embed/{token}/{employee_id}?theme=dark&anim=fadeIn&max_words=50"
  width="800" height="600"
  frameborder="0">
</iframe>
```

embed 전용 엔드포인트:
```
GET /embed/{token}/{employee_id}
```

embed 전용 경량 페이지 (`wordcloud_embed.html`):
- 헤더/사이드바 없음
- `WordCloudEmbed.js` (경량 버전) 사용
- URL 파라미터로 테마·애니메이션 설정

### 4-2. REST API (CORS 지원)

```
GET /api/v1/wordcloud/data/{employee_id}
    ?batch_id=latest              최신 배치 자동 선택
    &format=json                  json | svg | png
    &max_words=60
    &token={api_token}

응답 헤더:
  Access-Control-Allow-Origin: {허용 도메인}
  Content-Type: application/json
  Cache-Control: max-age=3600
```

### 4-3. 접근 제어 (토큰)

```
GET /api/admin/embed-token        관리자 토큰 발급
→ { token: "wc_...", expires_at: "...", scope: ["ALL" | ["EMP001"]] }
```

### 4-4. Webhook (배치 완료 알림)

```json
POST {webhook_url}
{
  "event": "batch_completed",
  "batch_id": "batch_20260529_1",
  "employee_ids": ["EMP001", "EMP002"],
  "data_url": "/api/v1/wordcloud/data/{id}?batch_id=batch_20260529_1"
}
```

### 신규 파일

```
web/templates/wordcloud_embed.html
web/static/js/wordcloud/WordCloudEmbed.js
src/routes/wordcloud_embed_routes.py     /embed + /api/v1 엔드포인트
src/services/embed_token_service.py      토큰 발급/검증
```

---

## 7. 구현 순서 및 일정

| 순서 | Phase | 내용 | 예상 공수 | 의존성 |
|-----|-------|------|---------|-------|
| 1 | **Phase 1** | Data API 구현 | 1일 | 없음 |
| 2 | **Phase 3 기초** | 테스트 페이지 골격 + 배치·직원 선택 UI | 0.5일 | Phase 1 |
| 3 | **Phase 2** | JS 렌더러 (`WordCloudRenderer.js`) | 2일 | Phase 1 |
| 4 | **Phase 3 완성** | 옵션 패널 + 단어 상세 테이블 + 비교 보기 | 1일 | Phase 2 |
| 5 | **Phase 4-embed** | iFrame embed 페이지 + 토큰 발급 | 1일 | Phase 2 |
| 6 | **Phase 4-API** | CORS 설정 + v1 API + Webhook | 1일 | Phase 1 |

---

## 8. 신규 파일 목록 (전체)

### 백엔드

| 파일 | 역할 |
|------|------|
| `src/services/wordcloud_data_service.py` | JSON에서 렌더링 데이터 추출 |
| `src/routes/wordcloud_data_routes.py` | `/api/wordcloud/data/*` 엔드포인트 |
| `src/routes/wordcloud_preview_routes.py` | `/wordcloud-preview` 페이지 라우트 |
| `src/routes/wordcloud_embed_routes.py` | `/embed/*`, `/api/v1/*` 엔드포인트 |
| `src/services/embed_token_service.py` | 토큰 발급/검증 |

### 프론트엔드

| 파일 | 역할 |
|------|------|
| `web/templates/wordcloud_preview.html` | 테스트 페이지 |
| `web/templates/wordcloud_embed.html` | iFrame embed 경량 페이지 |
| `web/static/js/wordcloud/WordCloudRenderer.js` | 핵심 렌더러 |
| `web/static/js/wordcloud/WordCloudAnimator.js` | 애니메이션 제어 |
| `web/static/js/wordcloud/WordCloudTheme.js` | 색상/스타일 테마 |
| `web/static/js/wordcloud/WordCloudEmbed.js` | embed용 경량 버전 |

### 변경되는 기존 파일

| 파일 | 변경 내용 |
|------|----------|
| `web/app.py` | 신규 Blueprint 등록 |
| `web/templates/base.html` | 사이드바에 "워드클라우드 미리보기" 메뉴 추가 |

### 변경 없는 기존 파일 (의도적 유지)

| 파일 | 이유 |
|------|------|
| `src/services/batch_processor.py` | 이미지 생성 파이프라인 유지 |
| `src/modules/wordcloud_generator.py` | PIL 기반 이미지 생성 계속 동작 |
| `src/services/perspective_service.py` | 기존 분석 로직 무변경 |

---

## 설계 원칙

1. **기존 배치 처리 파이프라인 무변경** — 이미지 생성은 계속 동작, 데이터 API는 추가만
2. **점진적 전환** — 이미지 출력과 애니메이션 출력을 병행 제공하다 검증 후 이미지 제거
3. **단어별 감정 색상 일관성** — PIL 생성기와 동일한 5단계 감정 색상 체계 유지
4. **기존 데이터 완전 활용** — `tmeta/employee_{id}.json`의 `consolidated_analysis`에서 추가 처리 없이 추출

---

> 시작점: **Phase 1 (Data API)** — `src/services/wordcloud_data_service.py` 신규 작성
