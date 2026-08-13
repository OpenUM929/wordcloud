> 상태: Done | 완료일: 2026-06-15

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-15 | 전체 | 초안 — 그룹분석/제출용저장 회귀 원인 분석 및 수정 방안 |
| 2026-06-15 | §4.1, §9 | **검토(260615.txt) 반영 + 핵심 수정 구현. ①`target_employee_name` 소비처 전수 확인 — 모두 'real'/enrich에서 자체 복원 또는 의도적 가명 표시(이중 복원 확정). ②`real_employee_id` 동적 키 접근 없음 확인(제거 안전). ③`created_at` 수정은 별도 결함이라 분리(이번 미적용). ④PATCH 검증 문구 유지. `load_all_batches()` 02534c8 변경 되돌림 적용** |

---

# 그룹 분석·제출용 저장 회귀 수정 (target_employee_id 매칭 키 복원)

## 1. 개요

배치 명칭 기능 및 비속어 가명 복원 작업(커밋 `02534c8`) 이후 발생한 두 가지 회귀를 수정한다.

- **작업 유형:** 기존 기능 회귀 수정 (백엔드)
- **핵심 결론:** 커밋 `02534c8`이 `load_all_batches()`의 `target_employee_id`를 **가명 ID(`emp_id`)** → **실명(`display_name`)**으로 바꾸면서, 직원 매칭 키 계약이 깨졌다. 이로 인해 **제출용 저장(워드클라우드 생성)** 과 **그룹 분석 매트릭스 생성**이 모두 실패한다.

---

## 2. 증상 (사용자 보고)

| # | 메뉴 | 증상 |
|---|------|------|
| 1 | 그룹 분석 | 배치 이력/분석 데이터를 제대로 가져오지 못함, 명칭 변경 동작 이상 |
| 2 | 그룹 분석 | 제출용 저장 등 워드클라우드 생성이 정상 처리되지 않음 |

---

## 3. 원인 분석 (코드·git 근거)

### 3.1 회귀 도입 지점 — 커밋 `02534c8` (REQ-2606-030 "비속어 기능 가명 복원 누락 수정")

`git show 02534c8 -- src/services/perspective_service.py` 결과, `load_all_batches()`에 아래 변경이 포함됨:

```diff
+    pseudo_mgr = _get_pseudo_mgr()
     for emp_id, name, dept, pos, data, ev_db_id in rows:
         if emp_id not in emp_meta:
+            real_id = pseudo_mgr.get_real_id(emp_id) if emp_id else emp_id
+            real_name = pseudo_mgr.get_real_id(name) if name else name
+            real_dept = pseudo_mgr.get_real_id(dept) if dept else dept
+            real_pos = pseudo_mgr.get_real_id(pos) if pos else pos
             emp_meta[emp_id] = {
-                'target_employee_name': name or '',
-                'target_employee_department': dept or '',
-                'target_employee_position': pos or '',
+                'target_employee_name': real_name or real_id or '',
+                'target_employee_department': real_dept or '',
+                'target_employee_position': real_pos or '',
+                'real_employee_id': real_id or emp_id,
             }
     ...
+        display_name = meta['target_employee_name'] or meta['real_employee_id'] or emp_id
         employee_results.append({
             'metadata': {
-                'target_employee_id': emp_id,
+                'target_employee_id': display_name,
```

> 직전 커밋(`b90727c`)까지 `'target_employee_id': emp_id` 였음을 git으로 확인 (`git show b90727c:...` → line 635 `emp_id`).

### 3.2 깨진 계약: `target_employee_id`는 "가명 ID(매칭 키)"여야 한다

현재 코드 위치(`src/services/perspective_service.py`):

- `load_all_batches()` line 649~652: `target_employee_id = display_name`(실명)으로 저장.
- `_get_employee_metadata(unified, employee_id)` line 959~964:
  ```python
  if meta.get('target_employee_id') == employee_id:
  ```
- `_get_evaluations_for_employee(unified, employee_id)` line 1402~1415:
  ```python
  if meta.get('target_employee_id') != employee_id:  continue
  ```
- `_get_row_value_counts(...)` line 1337, `get_matrix_meta(...)` line 1365 도 `target_employee_id`를 키로 사용.

매칭에 넘어오는 `employee_id`는 **가명 ID로 변환된 값**이다:

- `save_to_deploy()` line 1682~1685:
  ```python
  pseudo_mgr = _get_pseudo_mgr()
  resolved_id = _resolve_to_pseudo(employee_id, pseudo_mgr)   # 원본→가명
  target_meta = _get_employee_metadata(unified_data, resolved_id)
  ```
- `generate_perspective_matrix()` line 1444~1448:
  ```python
  resolved_id = _resolve_to_pseudo(employee_id, _get_pseudo_mgr())
  target_meta = _get_employee_metadata(unified_data, resolved_id)
  all_items = _get_evaluations_for_employee(unified_data, resolved_id)
  if not all_items:
      return None
  ```
- `_resolve_to_pseudo()` line 411~417: `real_to_pseudo` 맵으로 원본→**가명** 변환.

**결과:** `resolved_id`(가명) ≠ `target_employee_id`(실명) → 매칭 실패 → `all_items` 비어 있음 → `save_to_deploy`/`generate_perspective_matrix`가 `None` 반환.

- 제출용 저장 경로(`api_save_deploy`, `src/routes/perspective_routes.py` line 497~502)에서 모든 직원이 `None` → `'매칭되는 직원의 평가 데이터가 없습니다.'` → **워드클라우드 생성 실패 (증상 2).**
- 그룹 분석 매트릭스/메타 조회도 동일하게 매칭 실패 → **분석 데이터 못 가져옴 (증상 1).**

### 3.3 `load_all_batches`의 실명 복원은 중복이며 유해

가명→실명 복원은 이미 **상위 enrich 계층**에서 수행된다. `get_matrix_meta(unified, employee_id, enrich=True)` line 1360, 1375~1387:

```python
pseudo_mgr = _get_pseudo_mgr() if enrich else None
...
if enrich and pseudo_mgr:
    real_id = _dr(emp_id)
    entry['employee_id'] = real_id
    entry['employee_name'] = _dr(raw_name) if raw_name else None
    entry['department'] = _dr(entry.get('department')) ...
```

즉 회귀 이전에도 `target_employee_id=가명`, `target_employee_name=가명`을 두고, enrich 시점에 실명으로 변환했다. 커밋 `02534c8`이 `load_all_batches`에서 미리 실명화한 것은 **이중 복원**이며, 추가로 `save_to_deploy`의 `output_mode == 'real'` 파일명 로직(line 1690~1705)을 깨뜨린다:

```python
raw_name = target_meta.get('target_employee_name')   # 이미 실명
real_name = pseudo_mgr.get_real_id(raw_name)          # 실명→실명 (변화 없음)
if not real_name or real_name == resolved_id or real_name == raw_name:
    real_name = ''                                    # raw_name과 동일 → 이름이 공란 처리됨
```

→ 실명 모드 배포 파일명에서 이름이 누락된다(부차적 결함).

### 3.4 비속어 가명 복원(REQ-2606-030의 실제 의도)은 별도 위치

실제 비속어 가명 복원은 아래에 있으며 **유지해야 한다**:
- `_generate_profanity_cell()` line 1183~1184, 1198~1205 (`evaluator_id` 복원)
- `build_profanity_summary()` line 1222~1244 (`evaluator_id` 복원)
- `src/services/profanity_db_service.py` 변경

→ `load_all_batches` 회귀와 무관하므로 손대지 않는다.

---

## 4. 수정 방안

### 4.1 (핵심) `load_all_batches()`의 `02534c8` 변경 되돌리기

`src/services/perspective_service.py` line 623~656 구간을 회귀 이전 동작으로 복원한다.

**제거:** line 623 `pseudo_mgr = _get_pseudo_mgr()`, line 628~631 `real_id/real_name/real_dept/real_pos` 계산, line 636 `'real_employee_id'`, line 649 `display_name` 계산.

**복원:**
```python
    emp_evals = defaultdict(list)
    emp_meta = {}
    for emp_id, name, dept, pos, data, ev_db_id in rows:
        if emp_id not in emp_meta:
            emp_meta[emp_id] = {
                'target_employee_name': name or '',
                'target_employee_department': dept or '',
                'target_employee_position': pos or '',
            }
        if data:
            ev_obj = json.loads(data)
            ev_obj['_db_id'] = ev_db_id
            emp_evals[emp_id].append(ev_obj)

    employee_results = []
    total_evals = 0
    for emp_id, meta in emp_meta.items():
        evals = emp_evals[emp_id]
        total_evals += len(evals)
        employee_results.append({
            'metadata': {
                'target_employee_id': emp_id,
                'target_employee_name': meta['target_employee_name'],
                'target_employee_department': meta['target_employee_department'],
                'target_employee_position': meta['target_employee_position'],
                'evaluations': evals,
            }
        })
```

> `real_employee_id`는 `load_all_batches` 내부(line 636, 649)에서만 참조되므로 제거해도 외부 영향 없음(`grep` 확인 완료. `wordcloud_data_service.py:131`의 동명 키는 별도 컨텍스트로 무관).

이 한 가지 수정으로 증상 1·2의 매칭 실패가 모두 해소된다.

### 4.2 (부차) `_ensure_batch_summary`의 `created_at` 공란 수정

`src/services/batch_processor.py` line 380:
```python
'created_at': batch_processing_state.get('created_at', ''),
```
`batch_processing_state`에는 `created_at` 키가 설정된 적이 없어(전 구간 `grep` 확인) 신규 `batch_summary.json`의 `created_at`이 항상 `""`로 기록된다(디스크의 `batch_20260615_12/tmeta/batch_summary.json`에서 `"created_at": ""` 확인). 메타데이터 페이지 `get_batch_list()`(`metadata_service.py` line 132)에서 생성일이 공란으로 표시된다.

**수정안:** 처리 시각으로 대체.
```python
'created_at': batch_processing_state.get('created_at') or (datetime.now().isoformat() + 'Z'),
```
> 그룹 분석 페이지의 생성일은 DB `MIN(created_at)`(`_load_batch_list`)에서 가져오므로 영향 없음. 본 수정은 메타데이터 페이지 표시 정확도용이며 우선순위 낮음.
> **[검토 반영]** 본 회귀와 직접 인과관계가 없는 별도 결함이므로, 리뷰/롤백 관리를 위해 **이번 구현에서 분리(미적용)** 한다. 별도 작업으로 처리한다.

### 4.3 명칭 변경(PATCH) — 코드 검증 결과 정상

`PATCH /api/perspective/batch/<id>/display-name`(`perspective_routes.py` line 835~869)와 프론트엔드 `editDisplayName()`(`perspective_test.html` line 2666~2686), 읽기 경로 `_load_batch_list()`(line 573~589)를 모두 점검한 결과 **로직상 결함 없음**:
- 쓰기/읽기 경로 동일: `PROCESSED_DATA_DIR_PATH/batch/<id>/tmeta/batch_summary.json`.
- import 정상: `os`, `json as json_lib`, `log_action` 모두 존재(line 2~4, 28).
- summary 미존재 시 최소 summary 생성 후 진행하도록 이미 보정됨(미커밋 작업 트리 변경).

→ 사용자가 체감한 "명칭 변경 안됨"은 **그룹 분석 페이지 전체가 매칭 실패로 깨진 상태**(4.1)에서 파생된 것으로 추정된다. **4.1 적용 후에도 재현되면 정확한 에러 메시지/응답 코드를 확보**하여 재분석한다(추측 금지 원칙).

---

## 5. 수정 파일 목록

| # | 파일 | 변경 | 우선순위 |
|---|------|------|----------|
| 1 | `src/services/perspective_service.py` | `load_all_batches()` `02534c8` 변경 되돌리기 (target_employee_id=emp_id, 실명복원 제거) | 🔴 필수 |
| 2 | `src/services/batch_processor.py` | `_ensure_batch_summary` `created_at` 공란 수정 | 🟢 선택 |

**예상 변경: 약 15줄 (대부분 삭제/복원)**

---

## 6. 영향도 분석

| 항목 | 영향 | 설명 |
|------|------|------|
| 제출용 저장 / 워드클라우드 | ✅ 복구 | `save_to_deploy` 매칭 정상화 |
| 그룹 분석 매트릭스 | ✅ 복구 | `generate_perspective_matrix` 매칭 정상화 |
| 직원 목록/메타(enrich) | ❌ 영향 없음 | `get_matrix_meta`가 enrich로 실명 복원 — 기존 동작 유지 |
| 실명 출력 모드 파일명 | ✅ 개선 | 이중 복원 제거로 이름 누락 결함 동반 해소 |
| 비속어 가명 복원(REQ-2606-030) | ❌ 영향 없음 | `_generate_profanity_cell`/`build_profanity_summary`/`profanity_db_service`는 변경하지 않음 |
| 배치 이력 목록(`_load_batch_list`) | ❌ 영향 없음 | DB 기반 + summary display_name, target_employee_id 미사용 |
| 명칭 변경 PATCH | ❌ 영향 없음 | 독립 경로 |
| 배치 규모 1.9만명 | ✅ 개선 | 실명복원 루프 제거로 `load_all_batches` 부하 소폭 감소 |

---

## 7. 테스트 항목

1. 그룹 분석에서 특정 직원 선택 → 매트릭스 생성 → 워드클라우드 정상 출력 확인
2. 제출용 저장(단건/CSV/전체) → 성공 건수 > 0, `매칭되는 직원의 평가 데이터가 없습니다` 미발생
3. 실명 출력 모드 → 파일명에 실명 포함 확인
4. 비속어 리스트/문장 → evaluator_id 실명 복원 정상(회귀 없음) 확인
5. 배치 이력 목록 로드 + 명칭 변경(✏️) → 변경 즉시 반영 확인
6. (선택) 신규 배치 생성 → `batch_summary.json`의 `created_at`이 공란 아님 확인

> 테스트 코드/결과는 본 폴더 내 `test/`, `result/` 하위에 저장한다.

---

## 8. 롤백

- 단일 파일 중심 수정이므로 `git checkout -- src/services/perspective_service.py`(및 batch_processor.py)로 즉시 롤백 가능.
- DB/스키마/파일 포맷 변경 없음.

---

## 9. 구현 결과 (2026-06-15)

### 9.1 적용된 변경

- **`src/services/perspective_service.py` `load_all_batches()` (line 623~654)** — 커밋 `02534c8` 변경 되돌림:
  - `target_employee_id`: `display_name`(실명) → `emp_id`(가명 ID) 복원
  - `pseudo_mgr = _get_pseudo_mgr()` 및 `real_id/real_name/real_dept/real_pos` 사전 계산 제거
  - `target_employee_name/department/position`: 가명 원본(`name/dept/pos`)으로 복원
  - `real_employee_id` 키 및 `display_name` 지역변수 제거
  - 의도 주석 추가
- `python -m ast` 구문 검사 통과.

### 9.2 검토 의견(260615.txt) 처리

| 검토 항목 | 처리 결과 |
|-----------|-----------|
| ① `get_real_id(name)` 의도 / 이중 복원 재확인 | `target_employee_name` 전 소비처 확인: `get_matrix_meta`(line 1384, enrich `_dr`), `generate_perspective_matrix`(line 1505~1508, 'real' `_deref`), `save_to_deploy`(line 1695, `get_real_id`)는 자체 복원, 라우트 line 150/766·비-enrich는 02534c8 이전부터 의도적 가명 표시. → **이중 복원 확정, 되돌림 정당** |
| ② `real_employee_id` 동적 키 접근 | `grep` 재확인: 제거 대상 라인 외 `wordcloud_data_service.py:131`(별도 함수 컨텍스트)만 존재, 문자열 동적 접근 없음. → **제거 안전** |
| ③ `created_at` 수정 분리 | 본 회귀와 무관한 별도 결함 → **이번 구현에서 분리(미적용)**, §4.2에 명시 |
| ④ PATCH 검증 문구 | 그대로 유지(추측 금지 원칙) |

### 9.3 추가 확인 — 회귀 동반 복구 지점

되돌림으로 함께 정상화되는 매칭 의존 코드:
- `_get_employee_metadata`(959), `_get_evaluations_for_employee`(1402), `_get_row_value_counts`(1337), `get_matrix_meta`(1365)
- 라우트 CSV 매칭(`perspective_routes.py` line 156~158: 가명·실명 양쪽 키 구성), `/users` 그룹핑(line 755~772)

### 9.4 남은 검증 (사용자 환경)

> 서버 무단 실행 금지 원칙에 따라 런타임 테스트는 미수행. 아래는 사용자 확인 권장.

- §7 테스트 항목 1~5 수동 확인
- 특히 §4.3대로 "명칭 변경"이 본 수정 후에도 재현되면 정확한 에러/응답 코드 확보 요청
