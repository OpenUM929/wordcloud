# 계획서 — CSS 표준화 및 최대 너비 확장

> 상태: Done | 작성일: 2026-06-24
> 작업 유형: D (리팩토링)
> 선행: 없음

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-24 | 최초 작성 | CSS 표준안 위반 분석 및 수정 계획 |

## 1. 배경 및 목적

### 1.1 발견된 문제

**문제 1: CSS 표준안 위반** — `stopwords.css`가 base.css의 디자인 토큰을 사용하지 않음
- 하드코딩된 색상, 간격, 폰트, border-radius 사용
- base.css에 이미 정의된 컴포넌트(버튼, 카드, 폼 등)를 중복 정의
- **영향**: 스타일 불일치, 유지보수 어려움, 디자인 시스템 표준에서 이탈

**문제 2: 최대 콘텐츠 너비 1300px 제한** — 사용자 요청 1600~1900px
- `stopwords.css:19` — `.container { max-width: 1200px; }` 제한
- `bootstrap.min.css`에서 `.container`의 max-width 고정 (1140px)
- **영향**: 넓은 모니터(1920px+)에서 좌우 여백 과다, 콘텐츠 영역 비효율적 사용

### 1.2 목표
1. `stopwords.css`를 디자인 토큰 기반으로 전환 (base.css와 일관성 유지)
2. 콘텐츠 영역 최대 너비 1600px~1900px로 확장
3. Bootstrap의 `.container` max-width 제약 해제

## 2. 현재 코드 분석

### 2.1 `stopwords.css` 문제 목록

| # | 문제 | 위치(라인) | 현재 방식 | 수정 방향 |
|---|------|-----------|-----------|-----------|
| 1 | `.container { max-width: 1200px; }` | 18-20 | 하드코딩 1200px | 제거 또는 1600px로 변경 |
| 2 | 하드코딩 색상 `#6366f1`, `#28a745`, `#dc3545` 등 | 다수 | raw hex 값 | `var(--color-*)` 토큰으로 대체 |
| 3 | 하드코딩 border-radius `8px`, `4px` | 다수 | raw px | `var(--radius-*)` 토큰으로 대체 |
| 4 | 하드코딩 그림자 `0 2px 4px rgba(...)` | 다수 | raw shadow | `var(--shadow-*)` 토큰으로 대체 |
| 5 | 자체 `.table` 스타일 정의 | 374-377 | base.css와 충돌 | 제거 (base.css `.table` 사용) |
| 6 | 자체 scrollbar 정의 (중복) | 222-238 | base.css와 동일 | 제거 |
| 7 | Bootstrap-like 클래스명 사용 | 4-15, 23-35 | `.navbar`, `.navbar-brand` 등 | 제거 (base.css nav 사용) |
| 8 | 하드코딩 폰트 크기 | 다수 | `0.875rem`, `0.9rem` 등 | `var(--font-size-*)` 토큰 사용 |

### 2.2 최대 너비 제약 분석

**현재 너비 체인** (실제 렌더링 너비 계산):
1. `base.css .container` → flex: 1 (no max-width)
2. `stopwords.css .container` → max-width: 1200px
3. `bootstrap.min.css .container` → max-width: 1140px (lg), 960px (md), etc.
4. `perspective_test.html` → max-width: none !important (예외적 처리)

**결론**: `stopwords.css`의 `.container { max-width: 1200px; }` + Bootstrap의 container max-width가 결합되어 약 1140~1200px로 제한됨.

### 2.3 base.css 키워드 함수 없음 확인

base.css에는 `min()`/`max()`/`clamp()` 등의 CSS 함수가 사용되지 않음.

## 3. 변경 설계

### 3.1 `stopwords.css` 디자인 토큰 전환

```css
/* Before */
.container { max-width: 1200px; }
.card { box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); border-radius: 8px; }

/* After */
.container { max-width: 1600px; } /* 1600~1900px 중 1600px 채택 */
.card { box-shadow: var(--shadow-sm); border-radius: var(--radius-lg); }
```

**전환 원칙**:
- `#6366f1` → `var(--color-primary)`
- `#28a745` → `var(--color-success)`
- `#dc3545` → `var(--color-danger)`
- `#f59e0b` → `var(--color-warning)`
- `#17a2b8` → `var(--color-info)`
- `#dee2e6` → `var(--border-color)`
- `#e5e7eb` → `var(--border-color-light)`
- `#e0e0e0` → `var(--border-color-muted)`
- Hardcoded px 간격 → `var(--space-*)`
- Hardcoded border-radius → `var(--radius-*)`
- Hardcoded shadow → `var(--shadow-*)`
- Hardcoded font-size → `var(--font-size-*)`

### 3.2 제거할 중복 스타일

`stopwords.css`에서 아래는 base.css와 중복되어 제거:
- `::-webkit-scrollbar` 관련 (base.css 407-410행)
- `.card`, `.card-header`, `.card-title` (base.css 198-209행)
- `.table` 관련 (base.css 374-377행)

### 3.3 최대 너비 확장

**적용 대상**: `base.css` + `stopwords.css`
- `stopwords.css .container { max-width: 1200px; }` → `max-width: 1600px;`
- Bootstrap 컨테이너 max-width는 `base.html`에서 별도 처리 방안 검토
- `base.css .container`에 min/max 너비 설계토큰 추가 검토

**너비 결정**: 1600px (1600~1900px 범위 중 안정적인 1600px 선택)

## 4. 변경 파일 목록

| 파일 | 변경 유형 | 현재 방식 | 변경 방식 |
|------|-----------|-----------|-----------|
| `web/static/css/stopwords.css` | 수정 | 하드코딩 값 | 디자인 토큰 기반 + max-width: 1600px |
| `web/static/css/base.css` | 수정 | max-width 없음 | `.container`에 max-width 제안 토큰 추가? 필요성 검토 |
| `web/templates/base.html` | 수정 (검토) | Bootstrap CDN CSS | Bootstrap container override 추가 검토 |

## 5. 영향도 분석

| 영향 범위 | 상세 | 위험도 |
|-----------|------|--------|
| stopwords.html | 디자인 토큰 적용 시 시각적 변화 최소 (색상 동일) | 낮음 |
| 다른 페이지 | base.css .container 변경 시 모든 페이지 영향 | 중간 (기존 max-width none 유지) |
| perspective_test | 이미 `!important`로 재정의, 영향 없음 | 없음 |
| metadata_batch, metadata 등 | `.container` 직접 제어 없음, 영향 없음 | 없음 |

**핵심**: `stopwords.css`의 `.container` max-width만 1200→1600px 변경. 다른 페이지는 base.css container의 flex:1 기반이므로 자동 확장.

## 6. 테스트/검증 계획

1. **시각 검증**: stopwords 페이지에서 모든 요소가 정상 표시되는지 확인
   - 카테고리 패널, 불용어 테이블, 검색/추가 폼, 데모 영역
2. **너비 검증**: 1920px 모니터에서 콘텐츠 영역이 1600px까지 확장되는지 확인
3. **회귀 검증**: 다른 페이지(index, metadata, results 등)에 영향 없는지 확인
4. **콘솔 검증**: 브라우저 개발자 도구에서 CSS 오류 없음 확인

## 7. 리스크 및 제약

| 리스크 | 완화 방안 |
|--------|-----------|
| Bootstrap container max-width가 여전히 제한 | base.html에서 `style` 블록으로 override |
| 디자인 토큰 변경 시 stopwords.html의 JS 바인딩 영향 | JS는 클래스명/ID 기반, CSS 변경만으로 영향 없음 |
| stopwords.css의 하드코딩이 많아 누락 가능성 | 변경 후 base.css 토큰만 사용하는지 grep 검증 |

## 8. 구현 순서

1. **step 1**: `stopwords.css` max-width 수정 (1200px → 1600px)
2. **step 2**: `stopwords.css` 하드코딩 색상 → 디자인 토큰
3. **step 3**: `stopwords.css` 하드코딩 간격/폰트/radius/shadow → 디자인 토큰
4. **step 4**: `stopwords.css` 중복 스타일(::-webkit-scrollbar, .card, .table) 제거
5. **step 5**: `base.html` Bootstrap container override 검토
6. **step 6**: 최종 검증
