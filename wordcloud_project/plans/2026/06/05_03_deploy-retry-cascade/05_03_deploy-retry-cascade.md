# 계획서 — deploy-retry-cascade_260605_03

- **작업명**: 제출용 저장 실패 시 재시도 UX 및 세션 연결 고도화
- **작성일시**: 2026-06-05
- **작업 유형**: 기능 개선 (기존 버그 수정 + UX 개선)
- **상태**: PND (Pending)
- **계획서**: `wordcloud_project/plans/deploy-retry-cascade_260605_03/deploy-retry-cascade_260605_03.md`

---

## 1. 배경 및 문제 정의

사용자 요구사항 3가지:

### 1-A. 재생성 시 기존 결과에 추가되지 않음
- **현상**: 49/50 성공 후 1명 실패 → "실패 사번 수정"으로 재시도 → 새 세션 생성 → 결과 영역에 1명만 표시, 기존 49명은 보이지 않음
- **원인**: `saveDeploy()`가 실패 후 재시도 시 `resumeSessionId` 없이 실행되어 **새 세션**이 생성됨. 프론트엔드 `successData`에 기존 성공 결과가 누적되지 않음.
- **기대**: 재시도 후 결과 영역에 기존 49명 + 재시도 1명 = 50명이 모두 표시되어야 함.

### 1-B. 실패 정보 위치 불편
- **현상**: 실패 목록이 결과 영역 **맨 아래**에 존재
- **원인**: `renderDeployComplete()`에서 실패 목록 HTML을 결과 하단에 렌더링
- **기대**: summary-bar(`갤러리에서 확인 →` 링크가 있는 상단바)에 **실패 사번 수정 버튼**을 배치하여 즉각적인 재시도 접근 제공

### 1-C. 재시도 성공 시 기록 미갱신
- **현상**: 49/50 → 재시도 성공 → 갤러리/세션 목록에 여전히 49/50 또는 별도 세션으로 남음
- **원인**: 새 세션이 생성되므로 기존 세션의 `completed_count`/`failed_count`는 그대로 유지됨
- **기대**: 동일 세션 내에서 failed 태스크를 재시도하여 `49/50 → 50/50`으로 갱신

---

## 2. 영향도 분석

| 파일 | 변경 유형 | 영향 범위 |
|------|-----------|-----------|
| `src/services/deploy_session_service.py` | 함수 신규 + 수정 | `retry_failed_tasks()` 신규, 기존 세션/태스크 로직 영향 없음 |
| `src/routes/perspective_routes.py` | 신규 API 라우트 | `/deploy-session/retry` POST 추가, 기존 라우트 영향 없음 |
| `web/templates/perspective_test.html` | 수정 | `openIdInputModal()`, `saveDeploy()`, `confirmIdInput()`, `renderDeployComplete()` 수정 |

### 롤백 계획
- `deploy_session_service.py`: `retry_failed_tasks()` 함수만 삭제하면 롤백 완료
- `perspective_routes.py`: `/deploy-session/retry` 라우트만 삭제하면 롤백 완료
- `perspective_test.html`: Git diff 기준 이전 버전으로 복원 가능

---

## 3. 구현 상세

### 3.1 백엔드: `deploy_session_service.py`

**`retry_failed_tasks(session_id)` 신규 함수:**
```python
def retry_failed_tasks(session_id):
    """세션 내 실패한 태스크를 pending으로 리셋하고 세션을 running 상태로 복원."""
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        with conn:
            # failed 태스크를 pending으로 리셋
            conn.execute(
                """
                UPDATE deploy_tasks
                   SET status = 'pending', error_message = NULL, completed_at = NULL, assigned_at = NULL
                 WHERE session_id = ? AND status = 'failed'
                """,
                (session_id,),
            )
            # 세션 상태를 running으로 복원, completed_at 초기화
            conn.execute(
                """
                UPDATE deploy_sessions
                   SET status = 'running', completed_at = NULL
                 WHERE session_id = ?
                """,
                (session_id,),
            )
        return True
    finally:
        conn.close()
```

### 3.2 백엔드: `perspective_routes.py`

**`/deploy-session/retry` (POST) 신규 라우트:**
```python
@perspective_bp.route('/deploy-session/retry', methods=['POST'])
def api_deploy_session_retry():
    if not _is_admin():
        return jsonify({'success': False, 'error': '관리자 로그인이 필요합니다.'}), 401
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id', '')
    if not session_id:
        return jsonify({'success': False, 'error': 'session_id가 필요합니다.'}), 400
    
    # 세션 존재 여부 확인
    progress = get_session_progress(session_id)
    if not progress:
        return jsonify({'success': False, 'error': '세션을 찾을 수 없습니다.'}), 404
    
    retry_failed_tasks(session_id)
    return jsonify({'success': True, 'session_id': session_id})
```

**`/deploy-session/tasks` 활용:**
- 프론트엔드가 `saveDeploy(resumeSessionId)` 호출 시, 해당 세션의 기존 `completed` 태스크 목록을 `/deploy-session/tasks?session_id=`로 조회하여 `result_path`를 파싱, `successData`에 사전 로드.

### 3.3 프론트엔드: `perspective_test.html`

#### A. `openIdInputModal(failedIds, sessionId = null)` 확장
- `sessionId` 파라미터 추가. 제공되면 `window._retrySessionId = sessionId`에 저장.
- 모달 열릴 때 타이틀에 재시도임을 표시: "✏️ 실패 사번 수정 (재시도)"

#### B. `confirmIdInput()` 수정
- 확인 버튼 클릭 시 `window._retrySessionId`가 존재하면:
  - `_csvEmployeeIds = matchedIds`
  - `saveDeploy(window._retrySessionId)` 호출
  - `window._retrySessionId = null` 초기화
- 없으면 기존 동작 유지

#### C. `saveDeploy(resumeSessionId)` 수정
1. **기존 성공 결과 사전 로드 (resumeSessionId 있을 때만):**
   ```javascript
   let existingSuccessData = [];
   let existingFailData = [];
   if (resumeSessionId) {
       const tasksRes = await fetch(`/api/perspective/deploy-session/tasks?session_id=${resumeSessionId}`);
       const tasksData = await tasksRes.json();
       if (tasksData.success) {
           tasksData.tasks.forEach(t => {
               if (t.status === 'completed' && t.result_path) {
                   try {
                       const rd = JSON.parse(t.result_path);
                       existingSuccessData.push({...rd, employee_id: t.employee_id});
                   } catch(_) {}
               } else if (t.status === 'failed') {
                   existingFailData.push({employee_id: t.employee_id, error: t.error_message || '처리 실패'});
               }
           });
       }
       // retry API 호출하여 failed 태스크를 pending으로 리셋
       await fetch('/api/perspective/deploy-session/retry', {
           method: 'POST',
           headers: {'Content-Type': 'application/json'},
           body: JSON.stringify({session_id: resumeSessionId})
       });
       sessionId = resumeSessionId;
   }
   ```
2. **successData, failData 초기화:**
   ```javascript
   let successData = [...existingSuccessData];
   let failData = [...existingFailData];
   ```
3. **total 계산:**
   - resume 시: `total = existingSuccessData.length + existingFailData.length` (기존 세션의 전체 태스크 수)
   - 또는 progress API에서 `total_count`를 그대로 사용

4. **chunk 루프:**
   - `allocate_chunk`가 pending 태스크(= failed에서 리셋된)만 할당하므로 자동으로 실패분만 처리
   - 처리 완료 후 `successData`에 push, `failData`에서 해당 employee_id 제거

#### D. `renderDeployComplete()` 수정
- **summary-bar에 실패 사번 수정 버튼 추가:**
  ```javascript
  h += '<a href="/deploy-gallery" style="margin-left:auto;color:#155724;font-size:12px;font-weight:bold;text-decoration:underline;">갤러리에서 확인 →</a>';
  // 이 라인 앞(또는 summary-bar 내부 우측)에 실패 버튼 삽입
  ```
  - `failCountItems > 0`일 경우 summary-bar 우측에 빨간색 "✏️ 실패 사번 수정 →" 버튼 추가
  - 단, 이 버튼은 summary-bar 내부에서 클릭 가능해야 하며, 모달을 열고 `window._lastDeploySessionId`를 전달

- **실패 목록 위치:** 결과 영역 하단에서 제거하지 않되, summary-bar에 빠른 접근 버튼을 추가하여 **이중 접근** 제공
  - 또는 사용자 요구에 맞춰 summary-bar에만 버튼을 두고, 하단 실패 목록은 축소/접기 형태로 변경

#### E. 실패 후 재시도 성공 시 갱신 흐름
- `saveDeploy()` 완료 후 `renderDeployComplete({success: successData, fail: failData, total})` 호출
- `successData`는 기존 completed + 신규 completed가 합산됨
- `failData`는 재시도 성공 시 해당 employee가 제거됨
- `renderDeployComplete`의 summary-bar는 `successCount/totalItems`를 표시하므로 자동으로 `49/50 → 50/50`으로 표시됨

---

## 4. 검증 방법

| 시나리오 | 검증 방법 |
|----------|-----------|
| 49명 성공 + 1명 실패 후 재시도 | 결과 영역에 50명 모두 표시, summary-bar `50/50 성공` 확인 |
| 재시도 시 세션 재사용 | 브라우저 Network 탭에서 `/deploy-session/start`가 아닌 `/deploy-session/retry`와 `/deploy-session/chunk` 호출 확인 |
| 실패 버튼 위치 | summary-bar 우측에 "✏️ 실패 사번 수정 →" 버튼 존재 확인 |
| 갤러리 기록 갱신 | `/deploy-gallery` 접속 후 해당 세션이 `50/50`으로 표시되는지 확인 |
| 기존 성공 파일 보존 | 재시도 후 기존 49명의 PNG 파일 경로가 그대로인지 확인 (덮어쓰지 않음) |
| 재시도 실패 시 | 실패한 직원이 여전히 `failData`에 남아있고, summary-bar에 다시 버튼 표시 |

---

## 5. 알려진 제약 및 리스크

| 항목 | 우선순위 | 설명 |
|------|----------|------|
| `save_to_deploy` 파일 덮어쓰기 | 중간 | `save_to_deploy`는 동일 파일명으로 PNG를 생성하므로 재시도 시 기존 파일이 덮어써질 수 있음. 이는 의도된 동작(최신 결과 유지)이며, 기존 결과를 "보존"하는 것은 이미 `successData`에 URL이 저장되어 있으므로 프론트엔드에서 계속 볼 수 있음. |
| `result_path` JSON 파싱 | 낮음 | 기존 completed 태스크의 `result_path`는 `save_to_deploy`의 반환값이 JSON 문자열로 저장됨. 구조가 일관적이므로 파싱 안전. |
| 다중 재시도 | 낮음 | 1명 실패 → 재시도 → 또 실패 → 또 재시도. 세션은 계속 동일 세션을 재사용하며, `retry_failed_tasks`는 매번 failed 태스크를 pending으로 리셋하므로 반복 재시도 가능. |
| 대량 재시도 시 로딩 | 낮음 | `/deploy-session/tasks`로 전체 태스크를 조회할 때 수천 건의 JSON 파싱이 있을 수 있으나, SQLite 메모리 내에서 처리되므로 성능 문제 적음. |

---

## 6. 결론 및 다음 단계

1. 본 계획서 승인 후 구현 진행
2. 구현 완료 후 4장 검증 시나리오 전체 실행
3. 완료 보고서 작성

**핵심 달성 목표:**
1. 실패 후 재시도 시 **동일 세션을 재사용**하여 기존 성공 결과와 신규 결과를 캐스케이드 합산
2. summary-bar에 **즉각 재시도 버튼** 배치하여 UX 개선
3. 재시도 성공 시 **49/50 → 50/50**으로 세션 기록 자동 갱신

---

## 7. 코드 리뷰 결과 (2026-06-05)

### 결함 1 (심각) — `failData` 재시도 성공 시 제거 코드 없음

**위치**: 3.3.C  
**현상**: 계획서에 "처리 완료 후 `failData`에서 해당 employee_id 제거"라고만 언급하고 구체 코드 없음.  
`existingFailData` 사전 로드 후 `processOne()` 성공 시 제거하지 않으면 `failData`에 재시도 성공자가 그대로 남아 summary-bar가 "1건 실패"로 계속 표시됨 → 1-C 목표 달성 불가.

**수정**: `processOne()` 성공 분기에 아래 코드 추가:
```javascript
successData.push({...d, employee_id: eid});
const fi = failData.findIndex(f => f.employee_id === eid);
if (fi !== -1) failData.splice(fi, 1);  // 재시도 성공 시 실패 목록에서 제거
```

### 결함 2 (중간) — 기존 하단 "실패 사번 수정 →" 버튼에 `sessionId` 미전달

**위치**: 3.3.D  
**현상**: 계획서 3.3.D는 summary-bar 신규 버튼에만 `window._lastDeploySessionId` 전달을 언급함. 그러나 현재 결과 하단 기존 버튼 (`renderDeployComplete()` 라인 1327)도 `openIdInputModal(failedIds)` 형태라 `sessionId`가 전달되지 않음 → 하단 버튼으로 재시도 시 여전히 **새 세션 생성**됨.

**수정**: 하단 버튼도 함께 수정:
```javascript
// 기존
h += `<button onclick="openIdInputModal(${safeJson})">✏️ 실패 사번 수정 →</button>`;
// 수정
const _sid = window._lastDeploySessionId ? `,'${window._lastDeploySessionId}'` : '';
h += `<button onclick="openIdInputModal(${safeJson}${_sid})">✏️ 실패 사번 수정 →</button>`;
```

### 결함 3 (낮음) — 모달 제목 동적 변경 위치 미명시

**위치**: 3.3.A  
**현상**: 계획서에 "타이틀에 재시도임을 표시"라고만 언급. 현재 `<h3>` 정적 태그이므로 `openIdInputModal()` 내에 변경 코드 추가 필요.

**수정**: `openIdInputModal(failedIds, sessionId)` 내부에 추가:
```javascript
const titleEl = document.querySelector('#idInputModal h3');
if (titleEl) titleEl.textContent = sessionId ? '✏️ 실패 사번 수정 (재시도)' : '✏️ 직원 ID 입력';
```

### 정상 확인 항목

| 항목 | 결과 |
|------|------|
| `/deploy-session/tasks` 라우트 존재 여부 | ✅ `perspective_routes.py:263` |
| `get_session_tasks()` 반환 필드 (`employee_id`, `result_path` 포함) | ✅ `deploy_session_service.py:289` |
| `resumeSessionId` 있을 때 `output_mode` 체크 우회 (`saveDeploy` 라인 961) | ✅ 이미 구현됨 |
| `report_chunk` 완료 후 `completed_count`/`failed_count` 자동 재계산 | ✅ 정확 |
| `allocate_chunk` — `pending` 상태만 조회하여 재시도 대상 자동 선별 | ✅ 정확 |
| 다중 재시도 가능성 (`retry_failed_tasks` 반복 호출) | ✅ 정확 |
| `window._retrySessionId = null` 초기화 위치 | ✅ 명시됨 |
| `confirmIdInput()` 호출 순서 (matchedIds 설정 → 모달 닫기 → saveDeploy) | ✅ 순서 문제없음 |

---

## 7. 추가 요청사항 (사용자 직접 요청)

### 7-A. 확인 버튼 클릭 시 워드클라우드 생성 과정으로 진입하지 않음

**문제**: 실패한 사번 수정 버튼을 누르고 `idInputModal`에서 확인 버튼을 누르면, `_csvEmployeeIds`만 교체되고 실제 `saveDeploy()`가 호출되지 않아 워드클라우드 생성 과정으로 이동하지 않음.

**원인 분석**: 현재 `confirmIdInput()`의 흐름은 `_csvEmployeeIds = matchedIds` → 모달 닫기까지만 수행. `saveDeploy()` 호출 루트가 없음.

**해결 방안**: `confirmIdInput()` 함수 끝에 `window._retrySessionId`가 존재할 때 `saveDeploy(window._retrySessionId)`를 명시적으로 호출. 재시도가 아닌 일반 입력(초기 배치)일 경우에는 기존처럼 `saveDeploy()`를 호출하지 않음(사용자가 직접 "제출용 저장" 버튼을 눌러야 함).

```javascript
function confirmIdInput() {
    const matchedIds = parseIdsFromTextarea();
    if (matchedIds.length === 0) {
        document.getElementById('idInputStatus').textContent = '⚠ 유효한 직원 ID가 없습니다.';
        return;
    }
    _csvEmployeeIds = matchedIds;
    document.getElementById('csvStatus').textContent = `선택: ${_csvEmployeeIds.length}명`;
    document.getElementById('idInputModal').classList.remove('open');

    // --- 추가 ---
    if (window._retrySessionId) {
        saveDeploy(window._retrySessionId);
        window._retrySessionId = null;
    }
    // ------------
}
```

### 7-B. 직접 입력 텍스트 박스 높이 확장

**요청**: 실패한 사번 수정 버튼을 눌렀을 때 `idInputModal`의 직접 입력 textarea 높이를 현재의 5배로 늘려줄 것.

**현재 상태**: textarea에 `style="flex:1;"`이 적용되어 있어 좌측 패널 전체 높이를 채움. 그러나 `max-height:80vh` 제약으로 인해 실제 textarea 높이는 제한됨.

**해결 방안**: `idInputModal` 전체 모달의 `max-height`를 `90vh`로 상향하고, textarea에 `min-height`를 추가하거나, 실패 사번 수정 모달 열릴 때 textarea의 `rows` 속성을 동적으로 조정. 가장 단순한 방법은 textarea `style`에 `min-height: 300px` 추가(약 5배). 대량 입력 시 300px은 충분하지 않으므로, 모달 전체를 화면에 거의 꽉 차게(`95vh`) 늘리고 textarea에 `height: 60vh`를 주는 것이 더 적합.

**권장 구현**:
```css
/* 실패 수정 모달일 때 */
#idInputModal.retry-mode .modal-content {
    max-height: 95vh;
}
#idInputModal.retry-mode #idInputTextarea {
    min-height: 400px;
}
```

또는 JavaScript 동적 조정:
```javascript
function openIdInputModal(failedIds, sessionId = null) {
    const ta = document.getElementById('idInputTextarea');
    if (sessionId) {
        ta.style.minHeight = '400px';
        document.querySelector('#idInputModal .modal-content').style.maxHeight = '95vh';
    } else {
        ta.style.minHeight = '';
        document.querySelector('#idInputModal .modal-content').style.maxHeight = '80vh';
    }
    // ... 기존 로직
}
```
