# WordCloud 프로젝트 소스 코드 수정 계획서

> 작성일: 2026-05-29
> 작성자: AI Agent
> 상태: Build Mode 대기
> 범위: `.clinerules/*` 지침 수정 제외, `wordcloud_project/*` 소스 코드 수정만

---

## 1. 계획서 개요

### 1.1 배경

`.clinerules` 지침 문서 정리는 완료되었습니다. 이 계획서는 **순수 소스 코드 수정**만을 다룹니다.

발견된 소스 코드 수준의 문제:
1. **배치 삭제 API 이중화**: `metadata_batch.js`가 `POST /api/batch/delete`를 호출하나 이 API는 `users/*.json` 데이터를 정리하지 않음
2. **백엔드 삭제 함수 문서화 부족**: `batch_manager.delete_batch_directory()`가 users 데이터 정리를 하지 않는다는 사실이 주석/문서에 명시되지 않음

### 1.2 목표

- 배치 삭제 시 `users/*.json` 데이터 일관성 확보
- 삭제 API를 `DELETE /api/perspective/batch/<id>`로 통일
- 삭제 함수의 제한사항을 코드 주석으로 명확화

---

## 2. 문제 상세 및 타당성 분석

### 🔴 문제 1: `metadata_batch.js`가 잘못된 삭제 API 호출 (심각)

**발견 내용**:

| 호출 파일 | API | users/*.json 정리 | 문제 |
|-----------|-----|------------------|------|
| `metadata_batch.js:995` | `POST /api/batch/delete` | ❌ **안 함** | **유령 데이터 발생** |
| `admin_batch_management.html:74` | `DELETE /api/perspective/batch/<id>` | ✅ **함** | 정상 |
| `perspective_test.html:1086` | `DELETE /api/perspective/batch/<id>` | ✅ **함** | 정상 |

**근거 코드** (`metadata_batch.js:969-1008`):
```javascript
function deleteBatch() {
    var batchPath = sessionStorage.getItem('batchDir');
    // ...
    fetch('/api/batch/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ batch_path: batchPath })
    })
    // batch_routes.py → batch_manager.delete_batch_directory() 
    // → shutil.rmtree(batchPath)만 실행, users/*.json untouched
}
```

**근거 코드** (`perspective_routes.py:382-409`):
```python
@perspective_bp.route('/batch/<batch_id>', methods=['DELETE'])
def api_batch_delete(batch_id):
    summary = load_batch_summary(batch_dir)
    employee_ids = summary.get('employee_ids', [])
    remove_batch_from_all(batch_id, employee_ids)  # users/*.json 정리
    shutil.rmtree(batch_dir)
```

**타당성**:
- `POST /api/batch/delete`를 통해 삭제하면 `users/*.json`에 해당 배치의 평가 데이터가 그대로 잔존
- 이후 `load_all_batches()` 호출 시 삭제된 배치의 평가가 여전히 조회됨 → **데이터 무결성 침해**
- 프론트엔드 일관성: `admin_batch_management.html`, `perspective_test.html`은 이미 올바른 API 사용 중. `metadata_batch.js`만 예외
- 수정 방식: `metadata_batch.js`의 호출 대상을 `DELETE /api/perspective/batch/<id>`로 교체

**A 방식(권장) 근거**:
1. `perspective_routes.py`에 이미 완전한 삭제 로직 존재 → 중복 구현 방지
2. 프론트엔드 전체에서 동일한 삭제 API 사용 → 일관성 확보
3. `POST /api/batch/delete`는 RESTful하지 않음 (POST로 삭제, 리소스 식별자 없음)

**수정 난이도**: **낮음** (fetch URL 및 파라미터 변경)
**리스크**: **매우 낮음** (더 안전한 API로 교체)

---

### 🟠 문제 2: `batch_manager.py` 삭제 함수 제한사항 미기술 (주요)

**발견 내용**:

```python
# batch_manager.py:70-89
def delete_batch_directory(batch_path):
    """Delete a batch directory."""
    import shutil
    shutil.rmtree(batch_path)
    return {'success': True, 'message': '...'}, 200
```

**타당성**:
- 이 함수는 순수 디렉토리 삭제만 수행. `users/*.json`에서 해당 배치 데이터를 제거하지 않음
- `batch_routes.py`가 이 함수를 직접 호출하여 "배치 삭제"를 완료한다고 오인할 수 있음
- 주석에 "이 함수는 users/*.json을 정리하지 않음"을 명시해야 함
- 수정 난이도: **매우 낮음** (주석 추가)
- 리스크: **없음**

---

### 🟡 문제 3: `batch_routes.py`의 `POST /api/batch/delete` 미사용 처리 (보통)

**발견 내용**:
- `metadata_batch.js`가 이 엔드포인트를 사용하나, 수정 후 사용하지 않게 됨
- 그러나 백업 파일(`metadata_batch_backup.html`)에서 동일한 호출이 존재할 수 있음
- 안전을 위해 deprecated 표시 후 유지, 또는 프론트엔드 마이그레이션 완료 후 제거

**타당성**:
- 예상치 못한 다른 프론트엔드 코드에서 이 엔드포인트를 호출할 가능성
- `batch_routes.py`에 주석으로 "Deprecated: users/*.json 미정리" 표시 필요
- 수정 난이도: **매우 낮음** (주석 추가)
- 리스크: **없음**

---

## 3. 실행 계획 (소스 코드 수정만)

### Phase 1: 안전 장치 (백업)

| 순서 | 작업 | 명령어 |
|-----|------|--------|
| 1.1 | `wordcloud_project/` 전체 백업 | `xcopy /E /I wordcloud_project wordcloud_project_backup_$(date)` |
| 1.2 | 백업 무결성 확인 | `dir /s /b wordcloud_project_backup_* | find /c "\"` |

---

### Phase 2: `metadata_batch.js` 삭제 API 교체

| 순서 | 작업 | 대상 위치 |
|-----|------|----------|
| 2.1 | `batchPath` → `batchId` 추출 로직 추가 | `metadata_batch.js:974-994` |
| 2.2 | `fetch('/api/batch/delete', POST...)` → `fetch('/api/perspective/batch/' + batchId, DELETE)` | `metadata_batch.js:995-999` |
| 2.3 | `Content-Type` 헤더 및 `body` 제거 (DELETE는 body 불필요) | `metadata_batch.js` |
| 2.4 | 에러 핸들링 로직 확인 (응답 형식 동일함) | `metadata_batch.js:1000-1008` |

**변경 상세**:

```javascript
// BEFORE (metadata_batch.js:995-998)
fetch('/api/batch/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ batch_path: batchPath })
})

// AFTER
// sessionStorage.getItem('batchDir') 예시: "/abs/path/to/processed_data/batch/batch_20260512_0"
// → .split('/').pop() → "batch_20260512_0"
var batchId = batchPath.split('/').pop();
fetch('/api/perspective/batch/' + batchId, {
    method: 'DELETE'
})
```

**주의사항**:
- `batchPath`가 `sessionStorage.getItem('batchDir')`에서 오는 경우 절대경로일 수 있음
- `.split('/').pop()` 또는 `.split('\\').pop()`으로 Windows/Unix 모두 대응
- `batchId`가 `batch_YYYYMMDD_N` 형식이어야 함. 아니면 정규식 `/batch_[^_]+/`로 추출

---

### Phase 3: `batch_routes.py` deprecated 표시

| 순서 | 작업 | 대상 위치 |
|-----|------|----------|
| 3.1 | `delete()` 함수 상단에 deprecated 주석 추가 | `batch_routes.py:61` |

**추가할 주석**:
```python
@batch_bp.route('/delete', methods=['POST'])
def delete():
    """Delete a batch directory.
    
    ⚠️ DEPRECATED: This endpoint does NOT clean up users/*.json data.
    Use DELETE /api/perspective/batch/<batch_id> instead for full cleanup.
    """
```

---

### Phase 4: `batch_manager.py` 주석 강화

| 순서 | 작업 | 대상 위치 |
|-----|------|----------|
| 4.1 | `delete_batch_directory()` docstring에 제한사항 명시 | `batch_manager.py:70` |

**변경 상세**:
```python
def delete_batch_directory(batch_path):
    """Delete a batch directory.
    
    ⚠️ WARNING: This function only removes the batch directory on disk.
    It does NOT remove the batch's evaluation data from users/*.json files.
    For complete cleanup including user data, use remove_batch_from_all()
    from user_data_manager before calling this function.
    
    Args:
        batch_path: Path to batch directory
        
    Returns:
        tuple: (dict result, status_code)
    """
```

---

### Phase 5: 테스트 및 검증

| 순서 | 테스트 항목 | 통과 기준 | 검증 방법 |
|-----|-----------|----------|----------|
| 5.1 | `metadata_batch.js` 구문 오류 없음 | JS console 에러 없음 | 브라우저 개발자도구 |
| 5.2 | 삭제 API 호출 경로 확인 | Network 탭에서 `DELETE /api/perspective/batch/{id}` 확인 | 브라우저 개발자도구 |
| 5.3 | users/*.json 데이터 정리 확인 | 삭제 후 `users/{emp_id}.json`에서 해당 batch_id 평가 제거 | 파일 시스템 직접 확인 |
| 5.4 | 기존 삭제 엔드포인트 여전히 동작 | `POST /api/batch/delete`가 200 반환 (backward compat) | curl/Postman |
| 5.5 | 백업 파일에서 동일한 호출 부분 검색 | `metadata_batch_backup.html` 등에 `/api/batch/delete` 호출 여부 | grep 검색 |

---

### Phase 6: git 커밋 (사용자 승인 시)

| 커밋 | 메시지 | 대상 파일 | 범위 |
|-----|--------|----------|------|
| 1 | `fix: unify batch delete to DELETE /api/perspective/batch/<id>` | `metadata_batch.js` | 소스 |
| 2 | `docs: mark POST /api/batch/delete as deprecated` | `batch_routes.py` | 소스 |
| 3 | `docs: clarify delete_batch_directory only removes disk files` | `batch_manager.py` | 소스 |

---

## 4. 리스크 및 대응

| 리스크 | 확률 | 영향도 | 대응책 |
|--------|-----|--------|--------|
| `metadata_batch.js`에서 `batchPath` 형식 예외 | 중간 | 중간 | `split(/[\\/]/).pop()`로 Windows/Unix 모두 대응. 예외 시 정규식 `batch_\d+_\d+` 추출 |
| `sessionStorage.getItem('batchDir')`이 null | 낮음 | 높음 | 기존 null 체크 로직(990-992라인) 그대로 유지 |
| `DELETE /api/perspective/batch/<id>` 권한 오류 | 낮음 | 중간 | 관리자 세션 필요. `metadata_batch.js`는 배치 처리 직후 세션이 유효한 상태 |
| 백업 파일의 동일한 호출 누락 | 낮음 | 중간 | Phase 5.5에서 전체 프로젝트 grep으로 `/api/batch/delete` 재확인 |
| 기존 삭제 엔드포인트 완전 제거 시 호환성 파괴 | 낮음 | 낮음 | deprecated 표시만 하고 엔드포인트는 유지 (향후 제거 결정은 별도) |

---

## 5. 수정 파일 목록 (총 3개)

| # | 파일 경로 | 수정 유형 | 수정 내용 |
|---|----------|----------|----------|
| 1 | `wordcloud_project/web/static/js/metadata_batch.js` | 코드 변경 | fetch URL: `/api/batch/delete` → `/api/perspective/batch/{batchId}` |
| 2 | `wordcloud_project/src/routes/batch_routes.py` | 주석 추가 | `delete()` 함수 deprecated 표시 |
| 3 | `wordcloud_project/src/services/batch_manager.py` | 주석 추가 | `delete_batch_directory()` 제한사항 명시 |

---

## 6. 제외된 항목 (지침/문서 수정)

다음 항목은 본 계획서에서 제외되었습니다 (`.clinerules/*` 범위):

- `00-core.md` 경로 오류 수정
- `docs/project_wordcloud/` 신규 문서 생성
- `data-pipeline.md` 보강
- `08-guideline-modification/` 동기화 규칙 추가

---

## 7. 결론

본 계획은 **소스 코드 3개 파일의 최소 수정**으로 데이터 무결성 침해를 해결합니다. 특히:

1. **`metadata_batch.js` API 교체**: 핵심 수정. `users/*.json` 유령 데이터 방지
2. **주석 강화**: 미래 개발자의 실수 방지 (batch_manager.py의 제한사항, batch_routes.py의 deprecated)

수정 범위가 좁고 리스크가 낮으므로 즉시 실행 가능합니다.
