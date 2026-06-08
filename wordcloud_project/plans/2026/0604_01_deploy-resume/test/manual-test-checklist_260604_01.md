# 수동 테스트 체크리스트

- **작성일시**: 2026-06-04
- **대상**: T5 (브라우저 의존 3건) + T6 (Resume UX) + T7 (생성실패 처리)
- **총 시나리오**: 8건
- **상태**: 미수행

---

## 사전 준비

```
1. Flask 서버 실행 확인
2. 관리자 계정으로 로그인
3. 배치 데이터 1개 이상 로드됨 확인 (직원 5명 이상 포함)
4. 브라우저 DevTools 열기 (F12)
   - Console 탭: JS 오류 확인
   - Application > Local Storage: localStorage 확인
   - Network 탭: API 요청 확인
```

---

## T5. 세션 API — 브라우저 의존 시나리오

### T5-2. Resume — 브라우저 재접속

**전제조건**: 세션 진행 중 탭을 닫아 중단 상태 재현

| 단계 | 행동 | 기대 결과 | 확인 |
|------|------|-----------|------|
| 1 | `/perspective_test` 접속 → "제출용 저장" 클릭 (직원 10명 이상) | Chunk 폴링 시작, 진행 바 표시 | ☐ |
| 2 | 진행 바가 30~50% 지점에서 **탭을 강제로 닫음** | — | ☐ |
| 3 | DevTools Application → Local Storage → `deploy_session_id` 값 기록해 둠 | 세션 ID 존재 | ☐ |
| 4 | 동일 탭 또는 새 탭에서 `/perspective_test` 재접속 | "이전 작업 발견" 팝업 표시 | ☐ |
| 5 | 팝업 내용 확인: 중단 시각 + `완료 수 / 전체` 표시 | 30~50% 완료 수치가 맞음 | ☐ |
| 6 | "이어서 계속" 클릭 | Chunk 폴링 재개. 진행 바가 중단 지점부터 시작 | ☐ |
| 7 | 100% 완료 후 결과 화면 확인 | 총 완료 수 = 전체 직원 수. 중복 없음 | ☐ |
| 8 | Local Storage 확인 | `deploy_session_id` 키 삭제됨 | ☐ |

---

### T5-4. localStorage 세션 ID 우선순위

**전제조건**: 서버에 미완료 세션이 2개 이상 존재하고, localStorage에 그 중 하나의 ID가 저장된 상태

| 단계 | 행동 | 기대 결과 | 확인 |
|------|------|-----------|------|
| 1 | DevTools Console에서 세션 2개 생성:<br>`await fetch('/api/perspective/deploy-session/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({options:{}, employee_ids:['U001','U002']})}).then(r=>r.json())` 2회 실행 | 세션 A, 세션 B 두 ID 획득 | ☐ |
| 2 | Console에서 세션 A를 localStorage에 저장:<br>`localStorage.setItem('deploy_session_id', '<세션A_ID>')` | — | ☐ |
| 3 | 페이지 새로고침 | "이전 작업 발견" 팝업 표시 | ☐ |
| 4 | 팝업에 표시된 세션이 **세션 A** 임을 확인 (시각 또는 완료 수치로 구분) | localStorage의 세션 A 우선 표시 | ☐ |
| 5 | Network 탭에서 `deploy-session/cancel` 요청 확인 | 세션 B가 cancel API로 취소됨 | ☐ |
| 6 | `GET /api/perspective/deploy-session/active` 직접 호출:<br>`await fetch('/api/perspective/deploy-session/active').then(r=>r.json())` | sessions 배열에 세션 1개만 남음 (세션 A) | ☐ |

---

### T5-6. 오류 중단 후 localStorage 정리

| 단계 | 행동 | 기대 결과 | 확인 |
|------|------|-----------|------|
| 1 | DevTools Network 탭 → `deploy-session/chunk` URL 우클릭 → "Block request URL" | — | ☐ |
| 2 | "제출용 저장" 클릭 | 세션 생성 후 chunk 요청 시 네트워크 오류 발생 | ☐ |
| 3 | 콘솔에 `❌ 네트워크 오류` 메시지 확인 | 오류 처리 정상 | ☐ |
| 4 | Local Storage 확인 | `deploy_session_id` 키 **삭제됨** (`finally` 블록 동작) | ☐ |
| 5 | Network 블록 해제 후 재시도 | 신규 세션으로 정상 시작 | ☐ |

---

## T6. Resume UX 시나리오

### T6-1. 이전 작업 없을 때 팝업 미표시

| 단계 | 행동 | 기대 결과 | 확인 |
|------|------|-----------|------|
| 1 | Local Storage 비우기:<br>`localStorage.removeItem('deploy_session_id')` | — | ☐ |
| 2 | 서버의 미완료 세션이 없는지 확인:<br>`await fetch('/api/perspective/deploy-session/active').then(r=>r.json())` → `sessions: []` | — | ☐ |
| 3 | 페이지 새로고침 | 팝업 미표시 | ☐ |
| 4 | Console에서 확인:<br>`document.getElementById('resumePopupOverlay')` | `null` 반환 | ☐ |

---

### T6-2. "무시하고 새로 시작" 클릭

| 단계 | 행동 | 기대 결과 | 확인 |
|------|------|-----------|------|
| 1 | T5-2 1~4단계로 Resume 팝업 표시 상태 진입 | 팝업 표시됨 | ☐ |
| 2 | "무시하고 새로 시작" 버튼 클릭 | 팝업 즉시 제거됨 | ☐ |
| 3 | Local Storage 확인 | `deploy_session_id` 삭제됨 | ☐ |
| 4 | Network 탭에서 cancel API 호출 **없음** 확인 | 무시하기이므로 서버 취소 안 함 | ☐ |
| 5 | "제출용 저장" 클릭 | **신규 세션** 생성 (start API 호출됨) | ☐ |

---

### T6-3. "이어서 계속" 클릭 → Chunk 폴링 재개

| 단계 | 행동 | 기대 결과 | 확인 |
|------|------|-----------|------|
| 1 | T5-2 1~4단계로 Resume 팝업 표시 상태 진입 (30~50% 완료 기록) | 팝업 표시됨 | ☐ |
| 2 | "이어서 계속" 클릭 | 팝업 제거 | ☐ |
| 3 | Network 탭에서 `deploy-session/resume` POST 요청 확인 | `{"success": true}` 응답 | ☐ |
| 4 | 이어서 Chunk 폴링 시작 확인 | 진행 바가 중단 지점(30~50%)부터 표시 | ☐ |
| 5 | 100% 완료 대기 | 결과 화면 표시. 총 완료 수 = 전체 직원 수 | ☐ |
| 6 | Local Storage 확인 | `deploy_session_id` 삭제됨 | ☐ |

---

## T7. 생성실패 처리

### T7-1. 단일 직원 처리 실패 — 나머지 정상 완료

**재현 방법**: 배치 데이터에 없는 허위 직원 ID를 포함한 목록으로 저장 시작

| 단계 | 행동 | 기대 결과 | 확인 |
|------|------|-----------|------|
| 1 | 통합 ID 팝업에서 실제 존재하는 ID 3개 + 존재하지 않는 ID 1개 입력 | — | ☐ |
| 2 | "제출용 저장" 실행 | Chunk 폴링 진행 | ☐ |
| 3 | 결과 로그에서 존재하지 않는 ID 항목 확인 | `❌ {ID} 실패 - 평가 데이터 없음` 메시지 | ☐ |
| 4 | 나머지 3개 ID 정상 완료 확인 | `✅ {이름} 완료` 메시지 3건 | ☐ |
| 5 | 결과 화면의 요약 수치 확인 | 성공 3, 실패 1, 총 4 | ☐ |
| 6 | `GET /deploy-session/progress` 확인 | `completed_count: 3`, `failed_count: 1`, `status: 'completed'` | ☐ |

---

### T7-2. 처리 API 전체 실패 — Chunk 전체 failed 기록

**재현 방법**: DevTools에서 `/matrix/save-deploy` 요청 차단

| 단계 | 행동 | 기대 결과 | 확인 |
|------|------|-----------|------|
| 1 | DevTools Network → `/matrix/save-deploy` URL 블록 설정 | — | ☐ |
| 2 | "제출용 저장" 실행 (직원 5명) | Chunk 할당 후 처리 API 실패 | ☐ |
| 3 | 결과 로그 확인 | 5명 모두 `❌ 실패` 메시지 | ☐ |
| 4 | Network 탭에서 `deploy-session/complete` 요청 payload 확인 | `failed_items` 배열에 5개 ID 모두 포함 | ☐ |
| 5 | URL 블록 해제 후 다음 Chunk 진행 | 이후 Chunk는 정상 처리됨 | ☐ |

---

## 결과 기록

| ID | 시나리오 | 수행일 | 결과 | 비고 |
|----|----------|--------|------|------|
| T5-2 | Resume — 브라우저 재접속 | | ☐ Pass / ☐ Fail | |
| T5-4 | localStorage 세션 ID 우선순위 | | ☐ Pass / ☐ Fail | |
| T5-6 | 오류 중단 후 localStorage 정리 | | ☐ Pass / ☐ Fail | |
| T6-1 | 이전 작업 없을 때 팝업 미표시 | | ☐ Pass / ☐ Fail | |
| T6-2 | "무시하고 새로 시작" 클릭 | | ☐ Pass / ☐ Fail | |
| T6-3 | "이어서 계속" 클릭 → 재개 | | ☐ Pass / ☐ Fail | |
| T7-1 | 단일 직원 처리 실패 | | ☐ Pass / ☐ Fail | |
| T7-2 | 처리 API 전체 실패 | | ☐ Pass / ☐ Fail | |
