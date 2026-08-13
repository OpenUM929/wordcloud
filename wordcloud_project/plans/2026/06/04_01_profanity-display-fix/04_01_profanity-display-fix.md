# 수정 계획서: 욕설 표시 누락 & 영어 욕설 미감지 — 근본 원인 재분석

**작성일시**: 2026-06-04
**작업 유형**: bug fix
**상태**: DN (코드 적용 확인 — generate_perspective_matrix가 profanity_summary 반환, 2026-06-18)
**대상**: `perspective_service.py`, `perspective_test.html`

---

## 1. 문제 정의

이전 계획(`profanity-eng-fix_260602_01`)에서 다음을 수정했다고 판단했으나, 여전히 증상이 재현됨:

- ❌ 욕설 감지 문장 섹션이 화면에 표시되지 않음
- ❌ 영어 욕설("fuck" 등)이 탐지되지 않음

### 1-1. 이전 계획의 실패 원인

**표면적 수정에 그침.** 프론트엔드 렌더링 로직(`profanity_sentences` 직접 출력)과 백엔드 탐지 로직(`advanced_filter_text` 내 영어 직접 탐지)을 수정했지만, **데이터 흐름의 연결 지점**을 확인하지 않음.

특히:
- 프론트: `res.profanity_summary?.profanity_sentences` 조건 → 이 값이 API 응답에 없으면 아무것도 표시 안 됨
- 백엔드: 탐지 로직은 존재하나, **기존 배치 데이터**는 수정 전에 생성되어 영어 욕설 기록이 없음

---

## 2. 실제 근본 원인 (이번 분석 결과)

### 2-1. 욕설 섹션 미표시 — API 응답 누락

**핵심 원인**: `generate_perspective_matrix` 함수가 **`profanity_summary` 필드를 반환하지 않음.**

```python
# src/services/perspective_service.py:1323-1337
def generate_perspective_matrix(...):
    ...
    return {
        'employee_id': employee_id,
        'employee_name': employee_name or None,
        'employee_department': employee_department or None,
        'row_field': row_field,
        'row_label': ...,
        'col_mode': col_mode,
        'col_label': ...,
        'analysis_type': ...,
        'analysis_types': ...,
        'rows': row_keys_sorted,
        'columns': col_keys_sorted,
        'matrix': matrix,
        # ❌ profanity_summary 누락!
    }
```

`profanity_summary`는 **배포 저장 스트리밍 API** (`/api/perspective/matrix/save-deploy-stream`)의 done 이벤트에서만 추가됨:

```python
# src/routes/perspective_routes.py:303
result['profanity_summary'] = build_profanity_summary(unified, eid)
```

반면 일반 조회 API (`/api/perspective/matrix`, `/api/perspective/matrix/save-deploy` non-stream)에는 포함되지 않음.

**결과**: 프론트엔드 `res.profanity_summary`가 `undefined` → `if (ps && ps.profanity_sentences...)` 조건 실패 → 욕설 섹션 렌더링 자체가 실행되지 않음.

### 2-2. 영어 욕설 미감지 — 데이터 시점 문제

**코드상 탐지 로직은 존재함** (`profanity_filter.py:353-369`):

```python
for word in self.english_profanity_words:
    for m in re.finditer(re.escape(word), text, re.IGNORECASE):
        ...
        detected_profanity.append(w_lower)
```

**하지만**: 배치 처리 시 `metadata_manager.py:73`에서 `advanced_filter_profanity()`를 호출하여 결과를 저장. 이 시점이 코드 수정 **이전**이라면, 저장된 JSON 내 `profanity_analysis_results.detected_profanity`에는 영어 단어가 기록되어 있지 않음.

**결과**: `build_profanity_summary`는 저장된 데이터를 읽기만 함 → 이미 저장된 배치에서는 영어 욕설이 없음.

---

## 3. 수정 계획

### Step 1 — `generate_perspective_matrix`에 `profanity_summary` 추가

**파일**: `src/services/perspective_service.py`

`generate_perspective_matrix` 함수의 반환값 마지막에 `profanity_summary`를 포함:

```python
from src.services.perspective_service import build_profanity_summary  # 이미 import 됨

def generate_perspective_matrix(unified_data, employee_id, ...):
    ...
    return {
        ...
        'matrix': matrix,
        'profanity_summary': build_profanity_summary(unified_data, employee_id),  # 추가
    }
```

**영향도**: `perspective_test.html`의 `renderComplete()`에서 `res.profanity_summary`에 값이 채워짐 → 욕설 섹션 조건부 렌더링이 정상 작동.

### Step 2 — `generate_all_employee_matrix`에도 `profanity_summary` 추가

**파일**: `src/services/perspective_service.py`

동일한 누락이 `generate_all_employee_matrix`에도 있을 수 있음. 확인 후 필요하면 추가.

### Step 3 — 프론트엔드 욕설 섹션 렌더링 검증

**파일**: `web/templates/perspective_test.html`

`renderComplete()` 내 `profanity_summary` 사용 부분이 이미 구현되어 있음 (`line 1036-1047`). Step 1, 2 적용 후 자동으로 동작할 것으로 예상.

추가 확인:
- `highlightProfanity()`가 `<mark>` 태그로 bold 처리 → 시각적으로 표시됨 (이미 구현됨, `line 553-554`)
- `profanity_sentences`가 배열 형태로 내려오는지 확인

### Step 4 — 영어 욕설 탐지 검증 (신규 배치)

**방법**: 신규 배치 생성 테스트

1. 테스트 문서에 "fuck", "shit" 등 영어 욕설 포함
2. 메타데이터 생성 (배치 처리) 실행
3. 생성된 JSON의 `profanity_analysis_results.detected_profanity` 확인
4. 그룹분석 페이지에서 해당 배치 로드 → 욕설 섹션 노출 확인

**주의**: 기존 배치는 수정 전 데이터이므로 영어 욕설이 없는 것이 정상. 기존 배치 재처리는 별도 기능 개발 필요.

---

## 4. 변경 파일 요약

| 파일 | 변경 내용 | 영향도 |
|------|----------|--------|
| `src/services/perspective_service.py` | `generate_perspective_matrix` 반환값에 `profanity_summary` 추가 | 모든 직원 개별 조회 시 욕설 요약 포함 |
| `src/services/perspective_service.py` | `generate_all_employee_matrix` 반환값에도 동일하게 추가 (필요 시) | 전체 직원 일괄 조회 시 포함 |

---

## 5. 검증 시나리오

| 케이스 | 조건 | 확인 항목 | 예상 결과 |
|--------|------|----------|----------|
| A | 한국어 욕설("시발") 포함 배치, 개별 직원 조회 | 부정 컬럼 하단 "⚠ 욕설 감지 문장" 표시 | 섹션 노출 + 빨간 하이라이팅 |
| B | 영어 욕설("fuck") 포함 **신규 배치**, 조회 | `detected_profanity`에 영어 단어 포함 | 섹션 노출 + 영어 단어 표시 |
| C | 욕설 없는 배치 | 욕설 섹션 미표시 | 깔끔한 화면 |
| D | 전체 직원 일괄 조회 (`all_employees=True`) | 각 직원 결과에 `profanity_summary` 포함 | 개별과 동일하게 동작 |

---

## 6. 리스크 & 주의사항

1. **성능**: `build_profanity_summary`는 직원 전체 평가를 순회함. `generate_perspective_matrix`는 이미 무거운 작업이므로 추가 부하는 미미할 것으로 예상 (단순 순회).
2. **기존 배치 호환성**: 기존 배치의 `profanity_analysis_results`에 영어 욕설이 없으면 여전히 표시되지 않음. 이는 **데이터 한계**이며 코드 버그는 아님.
3. **불필요한 중복 호출**: `save-deploy-stream`에서도 `build_profanity_summary`를 호출하고, 이제 `generate_perspective_matrix`에서도 호출 → 중복 가능성. 하지만 두 함수는 서로 다른 API 엔드포인트에서 사용되므로 실제 중복은 없음.

---

## 7. 이전 계획과의 차이점

| 구분 | 이전 계획 (`profanity-eng-fix_260602_01`) | 이번 계획 |
|------|------------------------------------------|----------|
| **접근 방식** | 프론트엔드 렌더링 + 백엔드 탐지 로직 수정 | **데이터 흐름(API 응답)의 연결 지점** 수정 |
| **근본 원인** | 표면: 볼드 안 됨, 탐지 안 됨 | 실제: API가 `profanity_summary`를 반환 안 함 |
| **수정 대상** | `perspective_test.html`, `profanity_filter.py` | `perspective_service.py` (matrix 생성 함수) |
| **검증 초점** | 코드 로직 존재 여부 | **실제 API 응답 데이터** 확인 |

---

*본 계획은 이전 계획의 실패를 교훈 삼아, 수정 후 반드시 실제 API 응답을 확인하는 절차를 포함함.*
