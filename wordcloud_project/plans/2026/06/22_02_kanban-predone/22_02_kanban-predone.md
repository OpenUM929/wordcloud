# 계획서 — Kanban Pre-Done 상태 추가

> 상태: Done | 작성일: 2026-06-22
> 작업 유형: B (기능 개선/신규 기능)

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-22 | 전체 | 최초 작성 — Pre-Done(PDN) 상태를 Kanban에 추가 |

## 1. 요구사항

- Kanban 보드에 **Pre-Done(PDN)** 상태를 추가하여, 작업 완료 전 최종 점검이 필요한 계획서를 별도 컬럼에서 관리
- `_index.md`에 `PDN` 약어로 표기 가능해야 함
- 기존 `PND`(Todo) → `분석`(Doing) → `DN`(Done) 흐름 중간에 위치

## 2. 현재 시스템 분석

### 2.1 현재 상태 체계

`plans_routes.py:139-151`:
- `STATUS_MAP`: `DN`→done, `PND`→todo, `분석`→doing, `보류`→hold, `폐기`→drop
- `STATUS_LABEL`: 5개 상태 레이블
- `TABLE_RE` 정규식: `PND|DN|분석|보류|폐기` — 5개 토큰만 매칭
- `_group_by_status`: 5개 컬럼 고정

`plans_kanban.html:197,305`:
- 컬럼 순서 하드코딩: `todo → doing → done → hold → drop`
- CSS 변수 5세트 (색상, 배경, 테두리)
- 헤더 클래스 5개, 배지 클래스 5개

### 2.2 변경 흐름

```
변경 전: PND → 분석 → DN
변경 후: PND → 분석 → PDN → DN
```

## 3. 구현 상세

### 3.1 백엔드 — `src/routes/plans_routes.py`

| 항목 | 위치 | 변경 내용 |
|------|------|-----------|
| `STATUS_MAP` | line 139-145 | `'PDN': 'predone'` 추가 |
| `STATUS_LABEL` | line 146 | `'predone': '🔶 Pre-Done'` 추가 |
| `TABLE_RE` | line 148-151 | `(PND\|DN\|...)` → `(PND\|PDN\|DN\|...)` |
| `_group_by_status` | line 227 | `'predone': []` 추가 |

### 3.2 프론트엔드 — `web/templates/plans_kanban.html`

| 항목 | 위치 | 변경 내용 |
|------|------|-----------|
| CSS 변수 | line 5-21 | `--predone-color`, `--predone-bg`, `--predone-border` 추가 |
| 헤더 클래스 | line 41-45 | `.col-header.header-predone` 추가 |
| 배지 클래스 | line 58-62 | `.badge-predone` 추가 |
| 컬럼 루프 | line 197 | `doing`과 `done` 사이에 `('predone', '🔶 Pre-Done', 'header-predone')` 추가 |
| JS renderCards | line 305 | `['todo','doing','predone','done','hold','drop']` |
| JS stats | line 337-343 | `predone` 카운트 표시 추가 |

## 4. 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | `plans_routes.py` — STATUS_MAP, STATUS_LABEL, TABLE_RE, _group_by_status 수정 | 없음 |
| 2 | `plans_kanban.html` — CSS 변수, 헤더/배지 클래스 추가 | 없음 |
| 3 | `plans_kanban.html` — 컬럼 루프, JS renderCards, stats 수정 | 1 |
| 4 | `plans/2026/_index.md` — 본 계획서 행을 `PDN` 상태로 추가 | 없음 |

## 5. 영향도 분석

| 파일 | 변경 방식 | 영향 |
|------|-----------|------|
| `src/routes/plans_routes.py` | 4개소 추가 (기존 코드 수정 아님) | 신규 상태만 추가, 기존 5개 상태 영향 없음 |
| `web/templates/plans_kanban.html` | 6개소 추가 | 컬럼 1개 증가, 기존 레이아웃 flex로 자동 조정 |

## 6. 테스트/검증 계획

1. `_index.md`에 `PDN` 상태 행 추가 후 Kanban 보드에서 Pre-Done 컬럼에 표시되는지 확인
2. 기존 `PND`/`분석`/`DN`/`보류`/`폐기` 상태가 영향을 받지 않는지 확인
3. 컬럼 순서가 `Todo → Doing → Pre-Done → Done → Hold → Drop` 순서인지 확인

## 7. 리스크 및 제약

- 없음. 기존 상태값 변경 없이 새 상태만 추가
