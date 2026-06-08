# 전역 인증 + 원본 데이터 호출 정책 변경 계획서

- **작성일시**: 2026-06-05
- **작업 유형**: 기능 개선 + 정책 변경 (Backend API + Frontend UI + 인증 시스템)
- **상태**: PND (Pending, 승인 대기)
- **계획서 경로**: `wordcloud_project/plans/global-auth-real_260605_01/global-auth-real_260605_01.md`

---

## 1. 개요

### 1.1 배경
현재 시스템은 다음과 같은 문제가 있습니다.

1. **페이지별 인증 분산**: `perspective_test.html`에서만 비밀번호 입력이 필요하고, 페이지 새로고침 시 인증 상태가 초기화됨 (`_adminAuthed`가 JS 변수)
2. **가명/원본 불일치**: 데이터 저장은 `PseudonymManager`로 가명(`김철수_01EED6`) 처리되나, 사용자가 원본 ID(`U008`)로 검색하면 "존재하지 않음"으로 처리됨
3. **개인정보 유출 위험**: 원데이터 모드切替 시 비밀번호를 요구하지만, 전역 인증 체계가 없어 타 페이지에서 우회 접근 가능성이 있음

### 1.2 목표
1. **전역 인증 체계**: 사이트 접속 시 관리자 비밀번호 입력 필수. 인증되지 않으면 모든 원본 데이터 API에 접근 불가
2. **저장=가명, 호출=원본**: 데이터 저장은 가명으로 유지하되, API 응답 및 UI 표시 시 원본 ID/이름으로 변환
3. **가명/원본 양방향 검색**: 사용자가 원본 ID(`U008`) 입력 시, 내부에서 가명(`김철수_01EED6`)으로 변환하여 정상 검색

---

## 2. 범위 및 영향도

### 2.1 수정 대상 파일

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `src/routes/admin_routes.py` | 수정 | `/admin/api/check` 확장, 인증 상태 반환 강화 |
| `src/routes/perspective_routes.py` | 수정 | 19개 API의 `_is_admin()` 체크 유지 + 응답 데이터 원본 변환 적용 |
| `src/services/perspective_service.py` | 수정 | `load_all_batches()` 등 데이터 로드 함수에 원본 변환 옵션 추가 |
| `src/modules/pseudonym_manager.py` | 수정 (필요시) | `get_real_id` 안정성 확인 |
| `web/templates/base.html` | 수정 | 전역 인증 UI 추가 (비밀번호 입력 모달 또는 인증 상태 표시) |
| `web/templates/perspective_test.html` | 수정 | 기존 `adminLogin()` 제거, 전역 인증에 맞춰 UI 정리 |
| `web/templates/index.html` | 수정 | 인증되지 않은 경우 분석 기능 제한 |
| `web/templates/*.html` (기타) | 수정 | 필요시 전역 인증 상태 확인 JS 추가 |

### 2.2 영향도 분석

- **기존 기능**: 모든 관리자 전용 API는 기존 `_is_admin()` 체크를 유지하되, 인증 체계를 Flask Session 기반으로 통일
- **DB/스키마**: 변경 없음. 내부 저장은 계속 가명으로 유지
- **성능**: `PseudonymManager.get_real_id()` 호출이 API 응답 시마다 추가되나, 인메모리 캐시 있어 미미함
- **보안**: 전역 인증으로 개인정보 보호 강화

---

## 3. 상세 설계

### 3.1 기능 1: 전역 인증 체계

#### 3.1.1 현재 문제

- `_adminAuthed`는 `perspective_test.html`의 로컬 JS 변수 → 페이지 이동/새로고침 시 초기화
- 다른 페이지(`/`, `/batch`, `/wordcloud` 등)는 인증 없이 원본 데이터 조회 가능

#### 3.1.2 변경 내용

**백엔드:**
- Flask `session['admin_logged_in']`은 이미 존재하므로 이를 활용
- `base.html`이 로드될 때마다 `/admin/api/check`를 호출하여 인증 상태 확인
- 인증되지 않은 상태에서 원본 데이터 API 호출 시 401 반환 (기존 유지)

**프론트엔드:**
- `base.html`에 전역 인증 체크 JavaScript 추가:
  ```javascript
  // 모든 페이지 로드 시 실행
  async function checkGlobalAuth() {
      const r = await fetch('/admin/api/check', {credentials: 'include'});
      const d = await r.json();
      window._globalAdminAuthed = d.admin_logged_in;
      if (!d.admin_logged_in) {
          // 비밀번호 입력 모달 표시
          showGlobalLoginModal();
      }
  }
  ```
- 인증되지 않으면 사이트 전체에서 원본 데이터 표시/입력 UI를 숨김 처리

#### 3.1.3 인증 흐름

```
사용자가 any 페이지 접속
    ↓
base.html 로드 → /admin/api/check 호출
    ↓
인증됨?
    YES → 정상 표시 (원본 데이터 노출 가능)
    NO  → 비밀번호 입력 모달 표시 (배경 블러 처리)
            ↓
        비밀번호 입력 → /admin/login
            ↓
        성공 → 페이지 새로고침 또는 모달 닫기
        실패 → 재시도
```

---

### 3.2 기능 2: 저장=가명, 호출=원본

#### 3.2.1 현재 문제

- `processed_data/users/김철수_01EED6.json`에 `employee_id: "김철수_01EED6"` 저장
- `api_parse_ids()`에서 `emp_map`의 키가 가명이므로, 사용자가 `U008` 입력 시 매칭 실패
- 최근 수정으로 `api_parse_ids()`에 `pseudo_mgr`을 추가하여 `emp_map`에 원본 ID도 키로 등록하는 임시 조치 적용

#### 3.2.2 표준 정책

| 단계 | 처리 방식 | 예시 |
|------|-----------|------|
| **저장** | 가명으로 저장 | `김철수_01EED6` |
| **API 응답** | 원본 ID + 원본 이름 반환 | `employee_id: "U008"`, `name: "홍길동"` |
| **사용자 검색** | 원본 ID 입력 → 내부 매핑 → 가명 데이터 조회 | 사용자 입력 `U008` → `pseudo_mgr.get_pseudonym("U008")` → `김철수_01EED6` |
| **UI 표시** | 원본 이름/ID 표시 | `홍길동 (U008)` |

#### 3.2.3 핵심 API 수정

**`api_parse_ids()` (이미 부분 수정됨):**
- `emp_map` 구성 시 가명뿐 아니라 원본 ID도 키로 등록
- 응답 시 `employee_id`를 원본 ID로 변환

**`api_csv_parse()`:**
- 동일한 `pseudo_mgr` 기반 양방향 매핑 적용

**`api_get_meta()`:**
- `employee_id` 반환 시 원본 ID로 변환 (`enrich=True`인 경우)
- `employee_name`도 원본 이름 반환

**`generate_perspective_matrix()` / `generate_all_employee_matrix()`:**
- 결과의 `employee_id`를 원본으로 변환하여 반환

---

### 3.3 기능 3: 가명/원본 양방향 매핑 검색

#### 3.3.1 매핑 관계

`pseudonym_mappings.enc` 내부 구조:
```json
{
  "real_to_pseudo": {
    "U008": "김철수_01EED6",
    "홍길동": "김철수_01EED6"
  },
  "pseudo_to_real": {
    "김철수_01EED6": "U008"
  }
}
```

#### 3.3.2 검색 우선순위

사용자 입력 `U008`:
1. `emp_map`에 `U008`이 직접 있는지 확인 → 없음
2. `pseudo_mgr.get_pseudonym("U008")` → `김철수_01EED6`
3. `emp_map["김철수_01EED6"]` 조회 → 성공

사용자 입력 `김철수_01EED6`:
1. `emp_map`에 `김철수_01EED6`이 직접 있는지 확인 → 있음 (기존 흐름)

---

## 4. 작업 단위 및 우선순위

### Phase 1: 전역 인증 기반 구축
- [ ] **4.1** `base.html`에 전역 인증 체크 JS 추가 (`/admin/api/check` 폴링)
- [ ] **4.2** `base.html`에 비밀번호 입력 모달 추가 (미인증 시 강제 표시)
- [ ] **4.3** `perspective_test.html`의 기존 `adminLogin()`, `adminAuthArea`, `csvArea` 인증 로직 제거 (전역 인증으로 대체)
- [ ] **4.4** 기타 템플릿에서 `outputMode` 토글 시 비밀번호 요구 로직 제거

### Phase 2: 저장=가명, 호출=원본 정책 적용
- [ ] **4.5** `api_get_meta()` 응답 시 `employee_id`, `employee_name` 원본 변환 (`enrich=True`)
- [ ] **4.6** `api_csv_parse()`에 `pseudo_mgr` 기반 양방향 매핑 적용
- [ ] **4.7** `api_parse_ids()` 응답 시 `employee_id`를 원본 ID로 변환
- [ ] **4.8** `generate_perspective_matrix()` 결과의 `employee_id` 원본 변환
- [ ] **4.9** `generate_all_employee_matrix()` 결과의 `employee_id` 원본 변환
- [ ] **4.10** `perspective_test.html` UI 표시 시 원본 이름/ID 사용

### Phase 3: 안정화 및 테스트
- [ ] **4.11** 인증되지 않은 상태에서 원본 데이터 API 호출 시 401 확인
- [ ] **4.12** 원본 ID(`U008`) 입력 시 정상 매칭 확인
- [ ] **4.13** 가명(`김철수_01EED6`) 입력 시 정상 매칭 확인 (하위 호환)
- [ ] **4.14** 페이지 이동 후 인증 상태 유지 확인 (Flask Session)

---

## 5. 테스트 계획

### 5.1 단위 테스트

| 테스트 시나리오 | 기대 결과 |
|-----------------|-----------|
| `/admin/api/check` 미인증 상태 | `{"admin_logged_in": false}` |
| `/admin/api/check` 인증 상태 | `{"admin_logged_in": true}` |
| 미인증 상태에서 `/api/perspective/parse-ids` 호출 | 401 응답 |
| 인증 상태에서 `U008` 입력 후 `parse-ids` | 원본 ID `U008`로 매칭됨 |
| 인증 상태에서 `김철수_01EED6` 입력 후 `parse-ids` | 원본 ID `U008`로 매칭됨 (응답은 원본) |
| `api_get_meta()` 응답의 `employees[0].employee_id` | 원본 ID (예: `U008`) |
| `api_get_meta()` 응답의 `employees[0].employee_name` | 원본 이름 (예: `홍길동`) |

### 5.2 통합 테스트

| 테스트 시나리오 | 기대 결과 |
|-----------------|-----------|
| 사이트 접속 → 비밀번호 입력 → 페이지 이동 → 원본 데이터 표시 | 인증 유지됨, 원본 데이터 정상 노출 |
| 사이트 접속 → 비밀번호 미입력 | 모든 원본 데이터 숨김, 입력 모달 유지 |
| 저장 작업 후 데이터 조회 | 저장은 가명, 조회는 원본으로 표시 |

---

## 6. 리스크 및 대응

| 리스크 | 영향도 | 대응 방안 |
|--------|--------|-----------|
| `PseudonymManager` 복호화 실패 | 모든 원본 변환 불가 | `try/except`로 fallback 가명 유지, 로깅 강화 |
| 세션 만료로 인한 인증 해제 | 작업 중 원본 노출 중단 | 클라이언트에서 세션 만료 감지 시 자동 로그인 모달 표시 |
| `real_to_pseudo`에 없는 원본 ID | 검색 실패 | `get_pseudonym()` 호출 시 없으면 새로 생성하는 대신, 데이터 파일에 존재 여부 먼저 확인 |
| 대량 데이터 원본 변환 성능 저하 | API 응답 지연 | `PseudonymManager`의 `_mapping_cache` 활용 (이미 인메모리) |
| 기존 사용자 혼란 (가명 → 원본 표시 변경) | UX 저하 | 변경 사항을 UI에 명확히 안내 ("원본 ID로 표시됩니다") |

---

## 7. 예상 소요 시간

| Phase | 예상 소요 | 비고 |
|-------|-----------|------|
| Phase 1 (전역 인증) | 3~4시간 | 모달 UI + base.html 수정 + 기존 인증 로직 제거 |
| Phase 2 (원본 변환) | 4~5시간 | 5개 API 응답 수정 + 프론트엔드 표시 수정 |
| Phase 3 (테스트) | 2시간 | 시나리오 테스트 + 버그 수정 |
| **총계** | **9~11시간** | 테스트 및 디버깅 포함 |

---

## 8. 결론

본 계획은 다음 3가지 핵심 개선을 포함합니다.

1. **전역 인증 체계**: 사이트 접속 시 관리자 비밀번호 입력 필수로, 개인정보 보호 강화
2. **저장=가명, 호출=원본**: 내부 저장은 가명으로 유지하되, 사용자에게는 원본 ID/이름으로 표시
3. **양방향 매핑 검색**: 원본 ID(`U008`) 입력 시에도 정상 검색 가능

사용자가 **"수행"**을 명시적으로 요청하면 Phase 1부터 순차적으로 구현을 시작합니다.
