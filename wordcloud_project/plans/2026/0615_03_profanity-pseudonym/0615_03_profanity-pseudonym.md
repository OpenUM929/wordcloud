# 비속어 기능 가명 복원 누락 수정 — 0615_03

> 상태: Done | 작성일: 2026-06-15 | 완료일: 2026-06-15 | 작업 유형: 기능 문제 분석/디버깅

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-15 | 최초 작성 | |
| 2026-06-15 | §2.1.1 | **검토 반영: ①`pseudo_mgr = _get_pseudo_mgr()` 호출을 함수 선두로 이동해야 한다는 구현 주의사항 추가(`NameError` 방지). ②출력 복원(items의 employee_id/name/department)은 현재 코드에서 이미 구현됨을 명시 — 수정 범위는 WHERE 절 필터링만임을 명확화** |

---

## 1. 문제 분석

현재 비속어(profanity) 관련 기능에서 **가명 복원(restore)**이 여러 곳에서 누락되어, UI에 가명이 그대로 표시됨.

전체 데이터 흐름:
```
batch_processor.check_profanity_in_metadata
  → profanity_employees 리스트 (employee_id=가명)
    → save_batch_profanity → profanity_employees 테이블 (가명 저장)
      → get_all_profanity_employees → employees JOIN 조회
        (search/department 필터 시 가명으로 쿼리해야 함)
      → get_profanity_sentences → evaluator_id 복원 누락
      → get_distinct_departments → 부서명 복원 누락

perspective_service.build_profanity_summary → evaluator_id 복원 누락
perspective_routes.api_profanity_list_csv → profanity_sentences 미포함
```

## 2. 수정 대상 파일 및 함수

### 2.1 `profanity_db_service.py`

#### 2.1.1 `get_all_profanity_employees` — search/department WHERE 절 가명 변환

> **범위 명확화**: 현재 코드 L152–172에서 `items` 출력의 `employee_id` / `name` / `department`는 이미 `get_real_id()`로 복원되고 있다. 수정 대상은 출력이 아닌 **WHERE 절 필터링**뿐이다.

**now** (L67-86): WHERE 절에 실명 변환 없음
```python
if search:
    conditions.append("(e.name LIKE ? OR e.employee_id LIKE ?)")
    like = f"%{search}%"
    params.extend([like, like])
```

**문제**: 사용자가 실명으로 검색하면 DB에는 가명이 저장되어 있어 `LIKE` 검색이 0건.

> **⚠️ 구현 주의**: 현재 `pseudo_mgr = _get_pseudo_mgr()`는 L129(rows 조회 후)에 위치한다. search/department 블록에서 사용하려면 **함수 선두(conditions 블록 전)로 이동**해야 한다. 이동하지 않으면 `NameError` 발생.
>
> ```python
> # 함수 진입 직후 — conditions = [] 전에 배치
> pseudo_mgr = _get_pseudo_mgr()
> conditions = []
> params = []
> ```

**수정 (search)**:
- `get_all_mappings()` 순회 → `search`가 포함된 실명의 가명을 찾아 `IN` 절 추가
- `search`가 가명이면 `LIKE` 검색만으로 충분

```python
if search:
    matched_pseudonyms = []
    for real_id, pseudo in pseudo_mgr.get_all_mappings():
        if search in real_id:
            matched_pseudonyms.append(pseudo)
    if matched_pseudonyms:
        placeholders = ','.join('?' for _ in matched_pseudonyms)
        conditions.append(f"(e.name LIKE ? OR e.employee_id LIKE ? OR e.employee_id IN ({placeholders}))")
        like = f"%{search}%"
        params.extend([like, like])
        params.extend(matched_pseudonyms)
    else:
        conditions.append("(e.name LIKE ? OR e.employee_id LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])
```

**now** (L84-86): department 필터도 동일하게 가명 미변환
```python
if department:
    conditions.append("e.department = ?")
    params.append(department)
```

**수정 (department)**:
- `get_all_mappings()` 순회 → 정확히 일치하는 실명의 가명을 찾아 `OR` 조건 추가
- (배치 처리 시 department는 `forced_pseudo`에 포함되어 항상 매핑이 존재함)

```python
if department:
    matched_dept_pseudo = None
    for real_id, pseudo in pseudo_mgr.get_all_mappings():
        if real_id == department:
            matched_dept_pseudo = pseudo
            break
    if matched_dept_pseudo:
        conditions.append("(e.department = ? OR e.department = ?)")
        params.extend([department, matched_dept_pseudo])
    else:
        conditions.append("e.department = ?")
        params.append(department)
```

#### 2.1.2 `get_all_profanity_employees` — include_sentences 파라미터 추가

**now**: `profanity_sentences` 조회하지 않음. CSV 다운로드에서 문장 목록이 항상 비어있음.

**수정**: `include_sentences=False` 파라미터 추가. `True`일 때 각 `item`에 대해 `get_profanity_sentences()` 호출하여 `profanity_sentences` 추가.

```python
def get_all_profanity_employees(search=None, department=None, min_count=1,
                                  sort='count', order='desc', page=1, limit=50,
                                  include_sentences=False):
    # ... (기존 코드) ...
    if include_sentences:
        for item in items:
            item['profanity_sentences'] = get_profanity_sentences(item['employee_id'])
    return { ... }
```

#### 2.1.3 `get_profanity_sentences` — evaluator_id 복원

**now** (L210-223): `evaluator_id`를 그대로 반환 (가명 상태)

**수정**: 반환 시 `get_real_id()` 복원 추가

```python
raw_eval_id = row['evaluator_id'] or ''
real_eval_id = pseudo_mgr.get_real_id(raw_eval_id) if raw_eval_id else ''
display_eval_id = real_eval_id if real_eval_id and real_eval_id != raw_eval_id else raw_eval_id
sentences.append({
    ... (기존) ...
    'evaluator_id': display_eval_id,
    ... (기존) ...
})
```

#### 2.1.4 `get_distinct_departments` — 부서명 복원

**now** (L239): `r[0]` 반환 (가명 상태)

**수정**: 반환 시 `get_real_id()` 복원 추가

```python
depts = []
for r in rows:
    raw = r[0]
    if raw:
        real = pseudo_mgr.get_real_id(raw)
        depts.append(real if real and real != raw else raw)
return depts
```

### 2.2 `perspective_service.py`

#### 2.2.1 `build_profanity_summary` — evaluator_id 복원

**now** (L1222-1228): `evaluator_id`를 `ev.get('evaluator_id', '')`로 그대로 사용

- `ev`는 `evaluations` 테이블의 JSON 데이터이며, `evaluator_id`는 `forced_pseudo`에 포함되어 가명화됨.
- `build_profanity_summary`는 `save_to_deploy`의 결과에 추가되며, `perspective_routes.py`의 스트리밍 done 이벤트에서 사용됨.

**수정**: `pseudo_mgr = _get_pseudo_mgr()` 사용하여 `evaluator_id` 복원

```python
pseudo_mgr = _get_pseudo_mgr()
# ...
raw_eval_id = ev.get('evaluator_id', '')
real_eval_id = pseudo_mgr.get_real_id(raw_eval_id) if raw_eval_id else ''
display_eval_id = real_eval_id if real_eval_id and real_eval_id != raw_eval_id else raw_eval_id
profanity_sentences.append({
    'evaluator_id': display_eval_id,
    # ... (기존) ...
})
```

#### 2.2.2 `build_all_profanity_summary` — include_sentences 파라미터 전달

**now** (L1233-1240): `get_all_profanity_employees(...)`만 호출

**수정**: `include_sentences=False` 파라미터 추가 및 전달

```python
def build_all_profanity_summary(search=None, department=None, min_count=1,
                                sort='count', order='desc', page=1, limit=50,
                                include_sentences=False):
    from src.services.profanity_db_service import get_all_profanity_employees
    return get_all_profanity_employees(
        search=search, department=department, min_count=min_count,
        sort=sort, order=order, page=page, limit=limit,
        include_sentences=include_sentences,
    )
```

### 2.3 `perspective_routes.py`

#### 2.3.1 `api_profanity_list_csv` — include_sentences=True 전달

**now** (L1286-1293): `build_all_profanity_summary(...)` 호출

**수정**: `include_sentences=True` 추가

```python
result = build_all_profanity_summary(
    search=search or None,
    department=department or None,
    min_count=min_count,
    sort=sort,
    order=order,
    page=1,
    limit=10000,
    include_sentences=True,
)
```

---

## 3. 변경 영향도

| 함수 | 호출자 | 영향 |
|------|--------|------|
| `profanity_db_service.get_all_profanity_employees` | `perspective_service.build_all_profanity_summary` | search/department 필터 개선 (호환성 유지) |
| `profanity_db_service.get_profanity_sentences` | `perspective_routes.api_profanity_list_sentences` | `evaluator_id`가 실명으로 반환됨 |
| `profanity_db_service.get_distinct_departments` | `perspective_routes.api_profanity_list_departments` | 부서명이 실명으로 반환됨 |
| `perspective_service.build_profanity_summary` | `perspective_routes` (스트리밍 done) | `evaluator_id`가 실명으로 반환됨 |
| `perspective_routes.api_profanity_list_csv` | 사용자 (CSV 다운로드) | 문장 목록 컬럼이 채워짐 |

**리스크**: 없음. 모든 변경은 기존 동작을 보존하며 가명 복원만 추가.

---

## 4. 검증 계획

1. Python import 테스트: 수정된 모든 파일의 import 성공 확인
2. `get_distinct_departments` 반환값 실명 확인
3. 배치 처리 후 profanity_list 페이지에서 가명/실명 표시 확인
