# deploy-resume 테스트 시나리오

- **작성일시**: 2026-06-04
- **작업 유형**: 테스트 계획서
- **대상 계획서**: `deploy-resume_260604_01_rev-01.md`
- **상태**: PND (Pending)

---

## 개요

`deploy-resume_260604_01` 구현의 기능 검증을 위한 테스트 시나리오 모음.  
Phase 1 (핫픽스) → Phase 2 (입력 팝업) → Phase 3 (Resume 시스템) 순서로 수행.

---

## T1. PseudonymManager Thread-Safe화

### T1-1. 동시 `get_pseudonym()` — 파일 무결성

| 항목 | 내용 |
|------|------|
| **전제조건** | 매핑 파일 없는 초기 상태 |
| **절차** | 100개 스레드에서 동시에 `get_pseudonym(f"U{i:04d}")` 호출 |
| **기대 결과** | 매핑 파일 손상 없음. `real_to_pseudo` 키 100개 정확히 저장 |
| **검증** | 완료 후 `_load_mappings()` 호출 → `len(data["real_to_pseudo"]) == 100` |

### T1-2. 동시 읽기/쓰기 혼합

| 항목 | 내용 |
|------|------|
| **전제조건** | 매핑 50개 사전 등록 |
| **절차** | 50 스레드: `get_real_id()` / 50 스레드: `get_pseudonym()` 동시 실행 |
| **기대 결과** | 예외 없음. 기존 50개 매핑 손상 없음 |
| **검증** | 실행 중 Exception 없음. 기존 매핑 재확인 |

### T1-3. 싱글톤 — 단일 인스턴스 보장

| 항목 | 내용 |
|------|------|
| **전제조건** | `perspective_service` 모듈 로드 |
| **절차** | `_get_pseudo_mgr()` 10회 연속 호출, `is` 연산자로 동일성 비교 |
| **기대 결과** | 10회 모두 동일한 인스턴스 반환 (`id()` 값 일치) |
| **검증** | `assert _get_pseudo_mgr() is _get_pseudo_mgr()` |

### T1-4. 원자적 파일 쓰기 — 중간 상태 없음

| 항목 | 내용 |
|------|------|
| **전제조건** | 매핑 파일 경로 접근 가능 |
| **절차** | `_save_mappings()` 실행 중 매핑 파일 읽기 시도 |
| **기대 결과** | `.tmp` 파일이 존재했다가 즉시 사라짐. 최종 파일은 항상 완전한 내용 |
| **검증** | `os.replace()` 호출 전후 파일 상태 확인. 중간에 빈 파일이 존재하지 않음 |

---

## T2. get_matrix_meta() 이름 역변환

### T2-1. 원데이터 모드 — `employee_name` 역변환 확인

| 항목 | 내용 |
|------|------|
| **전제조건** | 원데이터 모드(`output_mode='real'`). 가명 매핑 파일에 `"평가자_AB1234" → "홍길동"` 등록 |
| **절차** | `get_matrix_meta(unified_data, enrich=True)` 호출 |
| **기대 결과** | `entry['employee_name']` 이 `"홍길동"` (가명이 아닌 실제 이름) |
| **검증** | 반환값의 `employees[0]['employee_name']` 값 확인 |

### T2-2. 가명 모드 — `employee_name` 변환 없음

| 항목 | 내용 |
|------|------|
| **전제조건** | 가명 모드(`output_mode='pseudonym'`) |
| **절차** | `get_matrix_meta(unified_data)` 호출 |
| **기대 결과** | `entry['employee_name']` 이 가명 그대로 (`"평가자_AB1234"`) |
| **검증** | `employees[0]['employee_name']`이 `_dr()` 통과 전 원본과 동일 |

### T2-3. `employee_name` 없음 — None 처리

| 항목 | 내용 |
|------|------|
| **전제조건** | 메타에 `target_employee_name` 키 없음 |
| **절차** | `get_matrix_meta()` 호출 |
| **기대 결과** | `entry['employee_name']` 이 `None`. 예외 없음 |
| **검증** | `employees[0]['employee_name'] is None` |

---

## T3. parse-ids API

### T3-1. 정상 ID 목록 — 매칭 + 상세 정보 반환

| 항목 | 내용 |
|------|------|
| **전제조건** | 배치 데이터에 `U001`, `U002`, `U003` 존재 |
| **절차** | `POST /api/perspective/parse-ids` `{"ids": ["U001", "U002", "U009"]}` |
| **기대 결과** | `matched: 2`, `not_found: ["U009"]`, `details` 배열에 U001·U002 상세 포함 |
| **검증** | Response JSON 필드: `matched_ids`, `not_found`, `details[].name`, `details[].evaluation_count` |

### T3-2. 합집합 동작 — 파일 + 텍스트 입력

| 항목 | 내용 |
|------|------|
| **전제조건** | 파일에서 `U001`, `U005` 파싱됨 |
| **절차** | 모달 textarea에 `"U001, U002\nU003 U004"` 입력 후 "확인" |
| **기대 결과** | `parse-ids` 호출 시 `ids: ["U001", "U002", "U003", "U004", "U005"]` (중복 제거 합집합) |
| **검증** | 네트워크 요청 payload 및 `_csvEmployeeIds` 값 확인 |

### T3-3. 빈 목록

| 항목 | 내용 |
|------|------|
| **전제조건** | — |
| **절차** | `POST /api/perspective/parse-ids` `{"ids": []}` |
| **기대 결과** | `400 Bad Request`, `{"success": false, "error": "ids가 필요합니다."}` |
| **검증** | HTTP 상태코드 및 에러 메시지 확인 |

---

## T4. deploy_session_service — 단위 테스트

### T4-1. Chunk 할당 원자성 (BEGIN IMMEDIATE)

| 항목 | 내용 |
|------|------|
| **전제조건** | 세션 1개 생성, `pending` 태스크 200개 |
| **절차** | 10개 스레드에서 동시에 `allocate_chunk(session_id, 50)` 호출 |
| **기대 결과** | 총 할당 ID 수 = 200 (중복 없음). 동일 `employee_id`가 두 스레드에 중복 할당되지 않음 |
| **검증** | 모든 반환 목록을 합산하여 `set` 크기 == 200 |

### T4-2. 고아 복원 (Orphan Recovery)

| 항목 | 내용 |
|------|------|
| **전제조건** | `processing` 상태 태스크 3개, `assigned_at` = 현재 - 3분 |
| **절차** | `allocate_chunk()` 또는 `get_active_sessions()` 호출 |
| **기대 결과** | 3분 경과이므로 복원 **안 됨** (5분 기준 미만) |
| **검증** | 태스크 상태 여전히 `processing` |

### T4-3. 고아 복원 — 5분 초과

| 항목 | 내용 |
|------|------|
| **전제조건** | `processing` 상태 태스크 3개, `assigned_at` = 현재 - 6분 |
| **절차** | `allocate_chunk()` 또는 `get_active_sessions()` 호출 |
| **기대 결과** | 3개 태스크가 `pending`으로 복원 |
| **검증** | `SELECT status FROM deploy_tasks WHERE session_id = ?` → 3개 모두 `pending` |

### T4-4. 세션 자동 완료

| 항목 | 내용 |
|------|------|
| **전제조건** | 세션 1개, 태스크 10개 |
| **절차** | `report_chunk()` 호출하여 10개 모두 `completed` 처리 |
| **기대 결과** | `deploy_sessions.status` = `'completed'`, `completed_at` 기록됨 |
| **검증** | `get_session_progress(session_id)['status'] == 'completed'` |

### T4-5. 세션 정리 (7일 자동 삭제)

| 항목 | 내용 |
|------|------|
| **전제조건** | `completed` 세션 1개 (`completed_at` = 현재 - 8일), `running` 세션 1개 (현재) |
| **절차** | `cleanup_old_sessions(days=7)` 호출 |
| **기대 결과** | 8일 경과 세션 및 하위 태스크 삭제. 현재 세션 유지 |
| **검증** | `SELECT COUNT(*) FROM deploy_sessions` = 1 (현재 세션만 남음) |

---

## T5. 세션 관리 API — 통합 테스트

### T5-1. 세션 전체 흐름 (Happy Path)

| 항목 | 내용 |
|------|------|
| **전제조건** | 로그인 상태 |
| **절차** | ① `POST /start` (employee_ids 100개) → ② `GET /chunk?count=50` → ③ 50개 처리 → ④ `POST /complete` → ⑤ `GET /chunk?count=50` → ⑥ 50개 처리 → ⑦ `POST /complete` → ⑧ `GET /chunk` |
| **기대 결과** | ⑧에서 `employee_ids: []`. 세션 `status = 'completed'` |
| **검증** | `GET /progress` 응답의 `completed_count == 100`, `status == 'completed'` |

### T5-2. Resume — 브라우저 재접속

| 항목 | 내용 |
|------|------|
| **전제조건** | 세션 1개 생성, 50명 완료, 50명 미완료 상태에서 브라우저 탭 닫음 |
| **절차** | ① 페이지 재접속 → ② `checkResume()` 실행 → ③ "이어서 계속" 클릭 → ④ `POST /resume` → ⑤ Chunk 폴링 재개 |
| **기대 결과** | 나머지 50명 처리 후 `status = 'completed'`. 총 `completed_count == 100` |
| **검증** | 최종 `GET /progress` 확인. 중복 처리된 employee_id 없음 |

### T5-3. 다중 미완료 세션 자동 취소

| 항목 | 내용 |
|------|------|
| **전제조건** | `running` 세션 3개 존재 (생성 시각 다름) |
| **절차** | 페이지 로드 → `checkResume()` 실행 |
| **기대 결과** | 가장 최근 세션 1개만 팝업 표시. 나머지 2개는 `status = 'failed'`로 변경됨 |
| **검증** | `GET /active` 재호출 시 세션 1개만 반환 |

### T5-4. localStorage 세션 ID 우선순위

| 항목 | 내용 |
|------|------|
| **전제조건** | `localStorage`에 `deploy_session_id = "세션A"` 저장됨. 서버에 `세션A`(오래된 것)와 `세션B`(최신) 2개 미완료 |
| **절차** | 페이지 로드 → `checkResume()` 실행 |
| **기대 결과** | 팝업에 `세션A` 표시 (localStorage 우선). `세션B`는 자동 취소 |
| **검증** | 팝업의 세션 ID 및 완료 수치 확인. `세션B` status = `failed` |

### T5-5. localStorage 정리 — 정상 완료 후

| 항목 | 내용 |
|------|------|
| **전제조건** | 세션 진행 중. `localStorage`에 세션 ID 저장됨 |
| **절차** | 모든 Chunk 완료 (chunk 반환 `employee_ids: []`) |
| **기대 결과** | `localStorage.getItem('deploy_session_id')` == `null` |
| **검증** | 브라우저 DevTools → Application → localStorage 확인 |

### T5-6. 오류 중단 후 localStorage 정리

| 항목 | 내용 |
|------|------|
| **전제조건** | 세션 진행 중 |
| **절차** | 네트워크 오류 발생 → `catch` 블록 진입 후 `finally` 실행 |
| **기대 결과** | `localStorage`에서 세션 ID 제거됨 |
| **검증** | 오류 후 `localStorage.getItem('deploy_session_id')` == `null` |

---

## T6. Resume UX — UI 시나리오

### T6-1. 이전 작업 없을 때 — 팝업 미표시

| 항목 | 내용 |
|------|------|
| **전제조건** | 미완료 세션 없음 |
| **절차** | 페이지 로드 |
| **기대 결과** | `#resumePopupOverlay` 생성되지 않음 |
| **검증** | `document.getElementById('resumePopupOverlay')` == `null` |

### T6-2. "무시하고 새로 시작" 클릭

| 항목 | 내용 |
|------|------|
| **전제조건** | 미완료 세션 1개, 팝업 표시된 상태 |
| **절차** | "무시하고 새로 시작" 버튼 클릭 |
| **기대 결과** | 팝업 제거. `localStorage`에서 세션 ID 제거. 기존 세션은 서버에서 취소되지 않음 (무시) |
| **검증** | 팝업 없어짐. `localStorage` 비워짐. 다음 "제출용 저장" 클릭 시 신규 세션 생성됨 |

### T6-3. "이어서 계속" 클릭 — Chunk 폴링 재개

| 항목 | 내용 |
|------|------|
| **전제조건** | 미완료 세션 (30/100 완료 상태), 팝업 표시 |
| **절차** | "이어서 계속" 클릭 |
| **기대 결과** | `POST /resume` 호출 후 `saveDeploy(sessionId)` 실행. 남은 70명 처리 시작 |
| **검증** | 진행 바가 30%에서 시작하여 100%까지 증가 |

---

## T7. 생성실패 처리

### T7-1. 단일 직원 처리 실패 — 나머지 계속

| 항목 | 내용 |
|------|------|
| **전제조건** | 세션 5명. 그 중 `U003`은 평가 데이터 없음 |
| **절차** | 정상 Chunk 폴링 실행 |
| **기대 결과** | U001·U002·U004·U005 `completed`. U003 `failed`. 전체 세션은 `completed` |
| **검증** | `GET /progress` → `completed_count: 4`, `failed_count: 1`, `status: completed` |

### T7-2. 처리 API 전체 실패 — 청크 전체 failed 처리

| 항목 | 내용 |
|------|------|
| **전제조건** | `/matrix/save-deploy` API가 500 오류 반환 |
| **절차** | Chunk 폴링 실행 |
| **기대 결과** | 해당 Chunk의 모든 employee_id가 `failed`로 기록. 다음 Chunk 계속 시도 |
| **검증** | `complete` API payload의 `failed_items` 배열에 모든 ID 포함 |

---

## 테스트 수행 순서

```
T1 (PseudonymManager 단위)
  → T2 (get_matrix_meta 단위)
  → T3 (parse-ids API)
  → T4 (deploy_session_service 단위)
  → T5 (세션 API 통합)
  → T6 (Resume UX)
  → T7 (생성실패 처리)
```

---

## 참고: 테스트 파일 위치

실제 테스트 코드는 아래 위치에 작성한다 (수행 시).

```
wordcloud_project/plans/deploy-resume_260604_01/
└── test/
    ├── test_pseudonym_manager.py     ← T1
    ├── test_perspective_service.py   ← T2
    ├── test_parse_ids_api.py         ← T3
    ├── test_deploy_session_service.py ← T4
    └── test_session_api.py           ← T5
```

UI 시나리오(T6·T7)는 브라우저 수동 테스트 또는 Playwright 스크립트로 수행.
