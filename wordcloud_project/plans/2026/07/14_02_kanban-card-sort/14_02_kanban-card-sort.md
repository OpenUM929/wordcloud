# 계획서 — Plans Kanban 카드 정렬 (오름차순/내림차순)

> 상태: Done | 작성일: 2026-07-14
> 작업 유형: B (기능 개선/신규 기능)
> 선행: 14_01_kanban-card-chips (칩+Done 그룹카드)

## 요구사항 원자화

| # | 원자 질문 | 기대 | 작업 후 답 (근거) |
|---|-----------|------|------------------|
| 1.1 | 각 컬럼 헤더 우측에 `↑↓` 정렬 버튼이 표시되는가? | Y | |
| 1.2 | 클릭 시 정렬 방향이 오름차순↔내림차순 전환되는가? | Y | |
| 1.3 | 모든 컬럼이 같은 정렬 방향을 공유하는가? | Y | |
| 1.4 | 비-Done 카드가 선택한 방향으로 `date` 기준 재정렬되는가? | Y | |
| 1.5 | Done 컬럼의 월 그룹 순서가 정렬 방향을 따르는가? | Y | |
| 1.6 | Done 현재월 개별카드 내 순서도 정렬 방향을 따르는가? | Y | |

## 1. 배경 및 목적

### 1.1 문제
- 현재 칸반 카드는 `date` 오름차순(오래된 순) 고정 정렬
- 사용자가 최신순/오래된순을 선택할 수 없음
- 특히 Todo/Doing 등 작업 우선순위 판단에 정렬 전환이 필요

### 1.2 목적
1. 각 컬럼 헤더 우측에 `↓`(내림차순)/`↑`(오름차순) 버튼 배치
2. 클릭 시 모든 컬럼의 정렬 방향 전환
3. `date` 필드 기준 정렬 (빈 날짜는 항상 마지막)

## 2. 구현 상세

### 2.1 대상 파일
- `D:\dev\wordcloud\wordcloud_project\web\templates\plans_kanban.html` — 프론트만 변경 (백엔드 불변)

### 2.2 CSS 추가
```css
.col-header-right { display: flex; align-items: center; gap: 6px; }
.sort-btn { cursor: pointer; font-size: 14px; color: #999; user-select: none; padding: 0 4px; border-radius: 4px; transition: all 0.12s; }
.sort-btn:hover { background: rgba(0,0,0,0.06); }
```

### 2.3 HTML 변경 (컬럼 헤더)
현재: `<span class="count" id="count_...">N</span>`
변경:
```html
<div class="col-header-right">
  <span class="count" id="count_{{ col_key }}">N</span>
  <span class="sort-btn" onclick="toggleSort()">↓</span>
</div>
```

### 2.4 JS 추가/변경

**전역 변수**: `_sortAsc = false` (기본 내림차순)

**`sortPlans(plans)`** — plans를 `_sortAsc` 방향으로 date 정렬, 빈 날짜는 항상 마지막

**`toggleSort()`** — `_sortAsc` 전환, 버튼 텍스트 `↓`↔`↑` 갱신, `loadPlans()` 재호출

**`renderCards(data)`** — 각 컬럼 렌더 전 `sortPlans()` 호출

**`renderDoneColumn()`** — 월 정렬 시 `_sortAsc` 방향 반영 (내림차순=최신월 우선, 오름차순=오래된월 우선), 그룹 내 개별카드도 date 정렬

### 2.5 정렬 상세 동작
- **기본값**: 내림차순(`↓`, 최신순) — 가장 최근 계획서가 상단
- **내림차순**: `07`월 Done 개별카드 → `06`월 그룹카드 → `04`월 그룹카드
- **오름차순**: `04`월 그룹카드 → `06`월 그룹카드 → `07`월 Done 개별카드
- **빈 date 처리**: 날짜가 없는 plan은 항상 리스트 마지막에 배치
- **전환 시**: `loadPlans()` 재호출로 전체 데이터 재렌더

## 3. 구현 순서

| 순서 | 작업 내용 | 담당 |
|------|-----------|------|
| 1 | CSS `.col-header-right` / `.sort-btn` 추가 | [저] |
| 2 | HTML 컬럼 헤더에 정렬 버튼 추가 (Jinja) | [저] |
| 3 | JS `_sortAsc`, `sortPlans()`, `toggleSort()` 추가 | [저] |
| 4 | JS `renderCards()` / `renderDoneColumn()` 정렬 연동 | [저] |
| 5 | 시각 확인 (브라우저) | [고] |

## 4. 영향도 분석

| 대상 | 영향 |
|------|------|
| `plans_kanban.html` | CSS+HTML+JS 추가, 기존 함수 시그니처 불변 |
| `plans_routes.py` | 변경 없음 (정렬은 전적으로 프론트) |
| DB/스키마 | 변경 없음 |
