# WordCloud 시스템 — 기능 구현/수정 계획서

## 목차
1. [완료된 수정](#1-완료된-수정)
2. [가명처리 강제화](#2-가명처리-강제화)
3. [통합데이터 배치이력 + 삭제](#3-통합데이터-배치이력--삭제)
4. [원데이터/가명 모드 표시 로직 정리](#4-원데이터가명-모드-표시-로직-정리)

---

## 1. 완료된 수정

### 1.1 matplotlib.use('Agg')
- **파일**: `src/services/perspective_service.py:2-3`
- **내용**: 모듈 최상단에 `matplotlib.use('Agg')` 추가
- **효과**: ThreadPoolExecutor와 tkinter 백엔드 충돌 방지 (`Tcl_AsyncDelete` 크래시 해결)

### 1.2 pageLog 재귀 버그 수정
- **파일**: `web/templates/perspective_test.html:293-298`
- **내용**: `_origLog`/`_origError`에 원본 함수 바인딩 저장 후 `pageLog`에서 사용
- **효과**: `console.log` 오버라이드 내부에서 `console.log` 호출 시 무한루프 방지

### 1.3 NDJSON Streaming Save-Deploy
- **파일**: `src/routes/perspective_routes.py:221-296`
- **엔드포인트**: `POST /api/perspective/matrix/save-deploy-stream`
- **내용**: NDJSON 스트리밍으로 직원별 진행률 실시간 전송
- **프론트**: `saveDeploy()`에서 `ReadableStream` 파싱, 진행 게이지 + 상태 라인 + 재시도 버튼
- **추가**: deploy-path 보존 (`result` 필드에 전체 결과 포함)

### 1.4 allEmployeesCheck 반영
- **파일**: `src/routes/perspective_routes.py` — save-deploy + save-deploy-stream
- **파일**: `web/templates/perspective_test.html` — `saveDeploy()`
- **내용**: "전체 직원 대상" 체크박스가 save-deploy에서도 동작하도록 수정
- **효과**: save-deploy 시 `all_employees=true` → 서버에서 전체 직원 ID 수집 → 일괄 처리

### 1.5 Progress Bar Infinity% 수정
- **파일**: `web/templates/perspective_test.html:628`
- **내용**: `const total` → `let total`
- **효과**: `allEmp` 모드에서 `total = data.total` 재할당 시 TypeError 방지

---

## 2. 가명처리 강제화

### 2.1 배경
- 기존: 가명 체크박스로 사용자가 선택해야만 가명처리됨
- 문제: 미선택 시 원본 데이터 그대로 저장 → `pseudonym_mappings.enc`에 매핑 누락 → 원데이터 모드에서 `get_real_id()` 실패 → 코드값(U002 등) 노출

### 2.2 수정 내용

#### 2.2.1 batch_processor.py — 모든 PII 필드 강제 가명처리 ✅
- **파일**: `src/services/batch_processor.py:502-504`
- **변경**:
  ```
  pseudonym_fields = data.get('pseudonym_fields', [])
  forced_pseudo = [
      'target_employee_id', 'evaluator_id',
      'target_employee_department', 'target_employee_position',
      'evaluator_department', 'evaluator_position',
  ]
  for f in forced_pseudo:
      if f not in pseudonym_fields: pseudonym_fields.append(f)
  ```
- **효과**:
  - 모든 배치에서 강제로 PII 필드 가명처리
  - `get_pseudonym(원본ID)` 호출 → `pseudonym_mappings.enc`에 자동 저장
  - 동일 `target_employee_id`면 항상 동일 가명 반환 (통합데이터 기준 자동 매칭)

#### 2.2.2 metadata UI — 가명 체크박스 제거 ✅
- **파일**: `web/static/js/metadata_batch.js`
- **변경**:
  - `renderMetadataTree()`에서 `🔒 <input type="checkbox"> 가명` → `🔒 가명` (표시용 텍스트로)
  - `togglePseudonym()` 함수 제거
  - `startBatchProcessing()`에서 `pseudoFields` / `pseudonym_fields` 제거
  - `restorePseudonymFieldsFromLocal()` 호출 제거
  - `pseudonymFieldsDisplay` → "모든 PII 필드가 항상 가명처리됩니다"
- **파일**: `web/templates/metadata_batch.html`
  - pseudonymInfo 텍스트 동기화

### 2.3 잔여 작업
- [ ] 기존 배치(batch_20260512_0, batch_20260518_0)는 삭제 후 새로 처리 필요 (기존 데이터는 U001~U015 원본값)
- [ ] 새 배치 처리 시 forced_pseudo에 의해 모든 PII 필드가 가명처리됨

---

## 3. 통합데이터 배치이력 + 삭제

### 3.1 요구사항
1. 통합데이터(`load_all_batches()`)에 각 데이터(employee_result)별 배치 출처 정보 포함
2. 특정 배치 이력의 정보를 삭제하는 기능 (배치 단위 삭제)

### 3.2 현재 상태 분석

#### 3.2.1 load_all_batches() 구조
```python
merged = {
    'batch_info': {'total_evaluations': int, 'unique_employees': int, 'batch_count': int},
    'employee_results': [  # 모든 배치의 employee_result를 flat하게 병합
        {'employee_id': str, 'metadata': {'target_employee_id': str, ...}}
    ],
    'batches': [  # 배치 메타정보 (batch_id, path, created_at, employee_count, total_evaluations)
        {'batch_id': 'batch_20260518_0', 'path': '...', 'created_at': '...', ...}
    ]
}
```
- 각 `employee_result`에 **batch_id가 포함되어 있지 않음**
- 각 `evaluation`에는 `ev['batch_id']`가 injection됨 (line 215)
- `merged['batches']`에 배치 목록은 존재하나, employee_result와의 연결고리 없음

#### 3.2.2 현재 삭제 기능
- **엔드포인트**: `POST /api/batch/delete` → `delete_batch()` → `shutil.rmtree(batch_path)`
- **문제점**: 
  - 배치 디렉토리만 삭제하고, `pseudonym_mappings.enc`나 deploy 출력물은 정리 안 함
  - 통합데이터 재조회 시 단순히 해당 배치가 없어짐 (clean)

### 3.3 구현 계획

#### 3.3.1 employee_result에 batch_id 추가
- **파일**: `src/services/perspective_service.py` — `load_all_batches()`
- **변경**: `employee_results` append 시 각 `er`에 `batch_id` 필드 추가
  ```python
  for er in summary.get('employee_results', []):
      er['batch_id'] = item  # batch directory name
      merged['employee_results'].append(er)
  ```
- **효과**: 통합데이터 사용처에서 employee_result의 출처 배치 식별 가능

#### 3.3.2 배치 삭제 시 연관 데이터 정리
- **파일**: `src/services/batch_manager.py` — `delete_batch_directory()`
- **추가**: 
  1. 배치 디렉토리 삭제
  2. 해당 배치 ID로 저장된 deploy 출력물 정리 (선택적)
  3. `pseudonym_mappings.enc`에서 해당 배치 전용 매핑 정리 (선택적)
- **프론트**: `metadata_batch.html` 하단 배치 목록에 삭제 버튼 유지

#### 3.3.3 프론트 — 배치 이력 조회 UI
- **파일**: `web/templates/perspective_test.html` 또는 별도 페이지
- **추가 예정**:
  - 통합데이터 로드 시 배치 목록 표시
  - 각 배치별 직원 수, 평가 수, 생성일 표시
  - 개별 배치 삭제 버튼
  - 삭제 전 확인 모달

### 3.4 API 설계 (초안)

#### GET /api/perspective/batch-history
- 통합데이터에 포함된 모든 배치 이력 조회
- Response:
  ```json
  {
    "success": true,
    "batches": [
      {"batch_id": "batch_20260518_0", "employee_count": 15, "evaluation_count": 50, "created_at": "..."}
    ]
  }
  ```

#### DELETE /api/perspective/batch/{batch_id}
- 특정 배치 삭제 (관리자 인증 필요)
- 배치 디렉토리 + 연관 deploy 출력물 정리
- Response: `{"success": true, "message": "..."}`

### 3.5 일정
| 작업 | 우선순위 | 예상 시간 |
|------|---------|----------|
| `load_all_batches()`에 batch_id 포함 | 상 | 30분 |
| 배치 삭제 API + 연관 데이터 정리 | 상 | 1시간 |
| 프론트 배치 이력 UI | 중 | 2시간 |
| 통합 테스트 | 중 | 1시간 |

---

## 4. 원데이터/가명 모드 표시 로직 정리

### 4.1 요구사항
- **저장**: 데이터는 항상 가명처리된 상태로 저장 (`target_employee_id = 평가자_XXXXXX`)
- **원데이터 모드**: `get_real_id(가명)` → 원본 ID/이름 표시
- **가명 모드**: 저장된 가명 그대로 표시

### 4.2 현재 문제
`save_to_deploy()`에서 항상 `get_real_id()`를 호출하여 원본으로 해소:
```python
pseudo_mgr = _get_pseudo_mgr()
real_id = pseudo_mgr.get_real_id(employee_id)
deploy_name = real_id if real_id and real_id != employee_id else employee_id
```
→ 가명 모드에서도 해소되어 원본이 표시됨

### 4.3 수정 계획
- `save_to_deploy()`에 `output_mode` 파라미터 추가
- 원데이터 모드: `get_real_id()` 호출 (현행 유지)
- 가명 모드: `employee_id`를 그대로 `deploy_name`으로 사용

#### 변경 대상 함수:
- `perspective_service.py:save_to_deploy()` — `output_mode` 파라미터 추가
- `perspective_routes.py:api_save_deploy()` — `output_mode` 전달
- `perspective_routes.py:api_save_deploy_stream()` — `output_mode` 전달
- `web/templates/perspective_test.html:saveDeploy()` — `output_mode`를 body에 포함

### 4.4 일정
| 작업 | 우선순위 | 예상 시간 |
|------|---------|----------|
| `save_to_deploy()` output_mode 추가 | 상 | 30분 |
| 라우트에서 output_mode 전달 | 상 | 15분 |
| 프론트에서 output_mode 전송 | 상 | 15분 |
| 테스트 | 중 | 30분 |

---

## 5. 파일 변경 이력 요약

| 파일 | 변경사항 | 상태 |
|------|---------|------|
| `src/services/perspective_service.py` | `matplotlib.use('Agg')` 추가 | ✅ 완료 |
| `src/services/batch_processor.py` | forced_pseudo로 모든 PII 강제 가명처리 | ✅ 완료 |
| `src/routes/perspective_routes.py` | save-deploy-stream + all_employees + deploy-path 보존 | ✅ 완료 |
| `web/templates/perspective_test.html` | streaming saveDeploy + allEmployeesCheck + `const→let` | ✅ 완료 |
| `web/static/js/metadata_batch.js` | 가명 체크박스 제거, 관련 함수/호출 정리 | ✅ 완료 |
| `web/templates/metadata_batch.html` | pseudonymInfo 텍스트 변경 | ✅ 완료 |
| `src/services/perspective_service.py` | `load_all_batches()` batch_id 포함 | 🔲 예정 |
| `src/services/batch_manager.py` | 삭제 시 연관 데이터 정리 | 🔲 예정 |
| `src/services/perspective_service.py` | `save_to_deploy()` output_mode 파라미터 | 🔲 예정 |
| `src/routes/perspective_routes.py` | batch-history / batch-delete 엔드포인트 | 🔲 예정 |
| `web/templates/perspective_test.html` | 배치 이력 UI | 🔲 예정 |

---

> **최종 업데이트**: 2026-05-27
