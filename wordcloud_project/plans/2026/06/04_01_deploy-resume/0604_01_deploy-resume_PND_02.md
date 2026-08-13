# 제출용 저장 Resume + 직원 ID 입력 팝업 + 원데이터 이름 표시 개선 계획서

- **작성일시**: 2026-06-04
- **작업 유형**: 기능 개선 (Backend API + Frontend UI)
- **상태**: PND (Pending, 승인 대기)
- **계획서 경로**: `wordcloud_project/plans/deploy-resume_260604_01/deploy-resume_260604_01.md`

---

## 수정 이력

| 버전 | 일시 | 내용 |
|------|------|------|
| v1.0 | 2026-06-04 | 최초 작성 |
| v1.1 | 2026-06-04 | 검토 의견 반영: Chunk 원자적 UPDATE 명세 추가, 고아 복원 트리거 보완, 다중 세션 정책 추가, localStorage 복원 흐름 추가, 재시도 세션 일관성 수정, parse-ids 의존성 명시, 세션 정리 정책 추가, DB 경로 명확화 |

---

## 1. 개요

### 1.1 배경
현재 `/perspective_test` 페이지의 **"제출용 저장"** 기능은 단일 HTTP 스트리밍 요청으로 전체 직원을 순차 처리합니다. 19,000명 이상의 대량 처리 시 다음과 같은 문제가 발생할 수 있습니다.

- 브라우저 탭 닫힘 / 네트워크 단절 시 **진행 상황이 전부 소실**되어 처음부터 다시 시작해야 함
- 현재 `PseudonymManager`가 Thread-Safe하지 않아, **원데이터 모드**에서 병렬 처리 시 가명-원본 매핑 파일이 손상될 위험이 있음
- CSV 파일 업로드만 지원되어, 사용자가 직접 사번 목록을 텍스트로 입력할 수 없음
- 원데이터 모드에서 `employee_name`이 역변환되지 않고 가명 그대로 노출되는 버그 존재

### 1.2 목표
1. **대량 저장 Resume**: Chunk 단위 폴링 + SQLite 세션 관리 + Worker Sharding 병렬 처리. 중단 후 페이지 복귀 시 "이어하기" 가능.
2. **통합 직원 ID 입력 팝업**: CSV 파일 선택 시 자동으로 팝업 오픈. 좌측 텍스트 입력 영역 + 우측 인식된 직원 미리보기. 합집합 처리.
3. **원데이터 이름 역변환 버그 수정**: `get_matrix_meta()`에서 `employee_name`도 `pseudo_mgr.get_real_id()`로 역변환.

---

## 2. 범위 및 영향도

### 2.1 수정 대상 파일

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `src/routes/perspective_routes.py` | 추가/수정 | 세션 관리 API 6개 신규, 기존 `save-deploy-stream` 유지 또는 Deprecated 마킹 |
| `src/services/perspective_service.py` | 수정 | `get_matrix_meta()` 이름 역변환 버그 수정. 세션 관리 헬퍼 함수 추가 |
| `src/services/deploy_session_service.py` | **신규** | SQLite 세션/태스크 관리 서비스 |
| `web/templates/perspective_test.html` | 수정 | 통합 팝업 UI 추가, Resume "이어하기" 버튼/팝업, Chunk 폴링 로직 |
| `src/modules/pseudonym_manager.py` | 수정 | Thread-Safe화 (락 추가) |
| `.gitignore` | 수정 | `.sessions/` 디렉터리 추가 |

### 2.2 영향도 분석

- **기존 기능**: `save-deploy-stream`은 기존 흐름을 유지하되, 내부적으로 새 세션 서비스를 호출하도록 위임. 단일 직원 저장에도 영향 없음.
- **DB/스키마**: SQLite 파일 `wordcloud_project/.sessions/deploy_sessions.db` 신규 생성. 기존 데이터 마이그레이션 불필요.
- **성능**: Chunk 폴링으로 네트워크 부하가 늘어나지만, Chunk 내부 Worker Sharding으로 처리 속도는 기존 이상 유지.

---

## 3. 상세 설계

### 3.1 기능 1: 대량 저장 Resume (Chunk + Worker Sharding)

#### 3.1.1 SQLite 스키마

```sql
-- deploy_sessions
CREATE TABLE deploy_sessions (
    session_id   TEXT PRIMARY KEY,        -- UUID v4
    created_at   TEXT NOT NULL,            -- ISO 8601
    status       TEXT NOT NULL             -- 'running' | 'paused' | 'completed' | 'failed'
        DEFAULT 'running',
    options      TEXT NOT NULL,            -- JSON 직렬화된 옵션
    total_count  INTEGER NOT NULL,
    completed_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    paused_at    TEXT,                     -- ISO 8601, status='paused' 시 기록
    completed_at TEXT
);

-- deploy_tasks
CREATE TABLE deploy_tasks (
    session_id    TEXT NOT NULL,
    employee_id   TEXT NOT NULL,
    status        TEXT NOT NULL            -- 'pending' | 'processing' | 'completed' | 'failed'
        DEFAULT 'pending',
    result_path   TEXT,                    -- 완료 시 파일 경로
    error_message TEXT,
    assigned_at   TEXT,
    completed_at  TEXT,
    PRIMARY KEY (session_id, employee_id)
);

-- 인덱스: Chunk 조회 성능
CREATE INDEX idx_tasks_session_status ON deploy_tasks (session_id, status);
```

#### 3.1.2 API 명세

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| `POST` | `/api/perspective/deploy-session/start` | 세션 생성. Body: `{options, employee_ids}` |
| `GET`  | `/api/perspective/deploy-session/chunk` | Chunk 할당. Query: `session_id`, `count` (기본 50). **고아 복원 + 원자적 UPDATE** 수행 후 반환 (3.1.7 참조) |
| `POST` | `/api/perspective/deploy-session/complete` | Chunk 완료 보고. Body: `{session_id, completed_ids[], failed_items[]}` |
| `GET`  | `/api/perspective/deploy-session/active` | 미완료 세션 목록. 페이지 로드 시 호출. **고아 복원** 수행 후 반환 |
| `POST` | `/api/perspective/deploy-session/resume` | 중단된 세션 상태를 `running`으로 변경 |
| `POST` | `/api/perspective/deploy-session/cancel` | 세션 취소 (status='failed') |

> **고아 복원 로직**: `active` API와 `chunk` API 양쪽에서 모두 실행한다. "이어하기" 버튼을 누른 후 곧바로 `chunk` API를 호출하는 경우에도 고아 태스크가 복원되도록 하기 위함. 로직: `assigned_at`이 현재 시각 기준 5분 이상 경과한 `processing` 상태 태스크를 `pending`으로 자동 복원.

#### 3.1.3 클라이언트 흐름 (Worker Sharding)

```javascript
// 1. 세션 시작
const session = await fetch('/api/perspective/deploy-session/start', {
    method: 'POST',
    body: JSON.stringify({ options, employee_ids })
}).then(r => r.json());

const sessionId = session.session_id;
// 세션 ID를 localStorage에 저장 → 탭 닫힘 후 복원에 사용
localStorage.setItem('deploy_session_id', sessionId);

const workerCount = 4;  // 설정 가능

// 2. Chunk 폴링 루프
while (true) {
    const chunk = await fetch(
        `/api/perspective/deploy-session/chunk?session_id=${sessionId}&count=50`
    ).then(r => r.json());
    if (chunk.employee_ids.length === 0) break; // 전체 완료

    // 3. Worker Sharding: 각 워커가 겹치지 않는 subset 처리
    const promises = [];
    for (let w = 0; w < workerCount; w++) {
        const subset = chunk.employee_ids.filter((_, i) => i % workerCount === w);
        if (subset.length === 0) continue;
        promises.push(processSubset(subset, sessionId));
    }
    await Promise.all(promises);

    // 4. 완료 보고
    await fetch('/api/perspective/deploy-session/complete', {
        method: 'POST',
        body: JSON.stringify({ session_id: sessionId, completed_ids: [...], failed_items: [...] })
    });
}

// 5. 완료 후 localStorage 정리
localStorage.removeItem('deploy_session_id');
```

#### 3.1.4 Resume UX

**페이지 로드 시 세션 복원 흐름:**

```
페이지 로드
  ├─ localStorage에 deploy_session_id 존재?
  │    YES → GET /api/perspective/deploy-session/active (해당 session_id 포함)
  │    NO  → GET /api/perspective/deploy-session/active (전체 미완료 세션 조회)
  └─ 미완료 세션 목록 수신
       ├─ 0개 → 정상 진입
       ├─ 1개 → 이어하기 팝업 표시
       └─ 2개 이상 → 가장 최근 세션 1개만 이어하기 팝업 표시, 나머지는 자동 취소(status='failed')
```

**이어하기 팝업:**
- 제목: "이전 작업 발견"
- 내용: `"2026-06-04 14:32에 시작된 저장 작업이 중단되었습니다. (3,450 / 19,000 완료)"`
- 버튼: `[이어서 계속]  [무시하고 새로 시작]`

**"이어서 계속" 클릭 시:**
1. `POST /api/perspective/deploy-session/resume` 호출
2. `localStorage.setItem('deploy_session_id', sessionId)` 갱신
3. Chunk 폴링 루프 재개 (3.1.3과 동일 흐름)

**"무시하고 새로 시작" 클릭 시:**
1. `POST /api/perspective/deploy-session/cancel` 호출 (기존 세션 취소)
2. `localStorage.removeItem('deploy_session_id')`
3. 신규 세션으로 처음부터 시작

#### 3.1.5 생성실패 vs 작업 중 정지 — 처리 방식 차이

| 구분 | 생성실패 (Task Failure) | 작업 중 정지 (Work Stoppage) |
|------|------------------------|------------------------------|
| **정의** | 특정 직원의 워드클라우드 생성/저장 중 **예외 발생** 또는 데이터 부재로 처리 불가 | 브라우저 탭 닫힘, 네트워크 단절, 서버 재시작 등으로 **전체 작업이 중단** |
| **영향 범위** | 해당 직원 **1명만** 실패, 나머지 직원은 정상 처리 | 중단 시점 기준, 처리 중이던 Chunk 전체가 완료되지 않음 |
| **태스크 상태** | `failed`로 기록. `error_message`에 예외 메시지 저장 | 중단 시 `processing` 상태였던 태스크들은 **고아(orphan)** 상태로 남음 |
| **Resume 시 처리** | `failed` 태스크는 기본적으로 **스킵**. 재시도 옵션은 별도 UI 제공 (`❌ 3명 실패 → [재시도]`) | `processing` 상태 태스크 중 `assigned_at`이 **5분 이상 경과**한 것은 `pending`으로 **자동 복원** 후 재할당 |
| **사용자 알림** | 실패 목록 팝업 + 각각의 실패 사유 표시 | 중단 시점(마지막 완료 시간) + 처리률 팝업 |

**구현상 차이점:**
- **생성실패**: `save_to_deploy()` 내부 `try/except`에서 잡히며, `complete` API 호출 시 `failed_items` 배열에 포함.
- **작업 중 정지**: 클라이언트가 `complete` API를 호출하지 못하고 연결이 끊김. `active` API 및 `chunk` API 호출 시 `processing` 태스크의 `assigned_at` 타임스탬프를 확인하여 오래된 것을 `pending`으로 롤백.

#### 3.1.6 생성실패 재시도 — 텍스트 붙여넣기 연동

**UX 흐름:**
1. 대량 저장 완료 후 결과 화면에 실패 목록 표시:
   ```
   ❌ 3명 생성 실패
   - 김철수(U001): 평가 데이터 없음
   - 이영희(U002): 워드클라우드 생성 중 메모리 부족
   - 박민수(U003): 평가 데이터 없음
   
    [선택한 인원 텍스트로 복사]  [통합 팝업에서 다시 시도]  [무시하고 완료]
    ```
2. 사용자가 **"통합 팝업에서 다시 시도"** 버튼 클릭
3. 기존 **통합 직원 ID 입력 팝업(`#idInputModal`)**이 오픈되되, **좌측 `textarea`에 실패한 직원 ID 목록이 자동 입력됨**
4. 사용자가 실패 사유를 확인하며 필요 시 ID 수정/추가 가능
5. **"확인"** 클릭 시 해당 ID 목록으로 **신규 세션을 생성**하여 재처리 (Resume 시스템과 일관성 유지)

> **v1.1 수정**: 재시도도 "세션 생성 없이 직접 호출"이 아니라 **신규 세션 생성 → Chunk 폴링** 흐름으로 통일한다. 재시도 중 브라우저를 닫더라도 이어하기가 가능하도록 하기 위함.

**기술 구현:**
- 결과 화면의 `failed_items` 데이터를 `_failedEmployeeIds` 전역 변수에 저장
- "통합 팝업에서 다시 시도" 버튼 클릭 시 `_failedEmployeeIds.join('\n')`을 `#idInputModal`의 `textarea`에 주입
- `_csvEmployeeIds`에 실패 목록을 할당하고 `startDeploySession()` 호출 (신규 세션 생성)
- 기존 옵션(워드클라우드 설정, 배포 모드 등)은 그대로 유지하여 동일 조건으로 재처리

#### 3.1.7 Chunk 할당 원자적 UPDATE 명세

Flask `threaded=True` 환경에서 SQLite 기본 격리 수준은 `BEGIN DEFERRED`이므로, 여러 스레드가 동시에 `pending → processing` 전환을 시도하면 중복 할당이 발생할 수 있다. `BEGIN IMMEDIATE`로 트랜잭션을 명시적으로 잠궈야 한다.

```python
def allocate_chunk(conn, session_id: str, count: int) -> list[str]:
    with conn:  # 자동 commit/rollback
        conn.execute("BEGIN IMMEDIATE")
        # 1. 고아 복원: assigned_at이 5분 이상 경과한 processing 태스크를 pending으로
        conn.execute("""
            UPDATE deploy_tasks
               SET status = 'pending', assigned_at = NULL
             WHERE session_id = ?
               AND status = 'processing'
               AND assigned_at < datetime('now', '-5 minutes')
        """, (session_id,))
        # 2. pending 태스크 선택
        rows = conn.execute("""
            SELECT employee_id FROM deploy_tasks
             WHERE session_id = ? AND status = 'pending'
             LIMIT ?
        """, (session_id, count)).fetchall()
        ids = [r[0] for r in rows]
        if ids:
            placeholders = ','.join('?' * len(ids))
            conn.execute(f"""
                UPDATE deploy_tasks
                   SET status = 'processing', assigned_at = datetime('now')
                 WHERE session_id = ? AND employee_id IN ({placeholders})
            """, (session_id, *ids))
    return ids
```

> WAL 모드(`PRAGMA journal_mode=WAL`) 활성화로 읽기/쓰기 동시성을 높이고 잠금 경합을 줄인다.

---

### 3.2 기능 2: 통합 직원 ID 입력 팝업

#### 3.2.1 UI 구성

- **트리거**: `<input type="file">` 파일 선택 완료 시 자동으로 통합 모달(`#idInputModal`) 오픈
- **모달 내부**:
  - **좌측 영역**: 텍스트 입력
    - `textarea` (placeholder: "사번을 입력하세요. 쉼표, 줄바꿈, 공백으로 구분 가능")
    - 설명 문구: "파일에서 읽어온 목록이 우측에 표시됩니다. 직접 추가/수정 가능합니다."
  - **우측 영역**: 인식된 직원 목록 미리보기
    - 테이블 헤더: 사번 | 이름 | 부서 | 직책 | 평가 건수
    - 파일 파싱 결과를 미리 채워둠
    - 매칭되지 않은 ID는 빨간색으로 표시
  - **하단 버튼**: `[확인]` `[취소]`

#### 3.2.2 동작 흐름

1. 사용자가 CSV 파일 선택 → 파일 파싱 API 호출 (`/api/perspective/csv-parse`)
2. 파싱 완료 → 통합 모달 오픈
3. 모달 우측에 파일 결과 자동 표시
4. 사용자가 좌측 textarea에 직접 추가 입력 가능
5. "확인" 클릭 시:
   - 좌측 textarea 내용 파싱 (`,`, `\n`, 공백 구분)
   - 파일 결과와 **합집합**
   - `/api/perspective/parse-ids` 호출 → 매칭된 직원 상세 정보 재확인
   - `_csvEmployeeIds`에 최종 ID 목록 저장
   - `employeeSelect` / `allEmployeesCheck` 비활성화

#### 3.2.3 API 명세

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| `POST` | `/api/perspective/parse-ids` | ID 목록 매칭 + 상세 정보 반환. Body: `{ids: ["U001", ...]}` |

**Response 예시**:
```json
{
  "success": true,
  "total": 10,
  "matched": 8,
  "matched_ids": ["U001", "U002"],
  "not_found": ["U009", "U010"],
  "details": [
    {"employee_id": "U001", "name": "김철수", "department": "개발팀", "position": "대리", "evaluation_count": 5},
    ...
  ]
}
```

> **v1.1 추가**: `parse-ids`의 `name`, `department`, `position`, `evaluation_count` 필드는 기존 `get_employees_list()` 또는 동등한 직원 조회 API에서 가져온다. 해당 API 존재 여부를 Phase 2 착수 전에 확인하고, 없으면 신규 구현을 Phase 2 범위에 포함한다.

---

### 3.3 기능 3: 원데이터 모드 이름 역변환 버그 수정

#### 3.3.1 문제 지점

`src/services/perspective_service.py`의 `get_matrix_meta()` 함수, 약 line 1199:

```python
# 현재 (버그)
entry['employee_name'] = meta.get('target_employee_name') or None
```

#### 3.3.2 수정 내용

```python
# 수정 후
raw_name = meta.get('target_employee_name')
entry['employee_name'] = _dr(raw_name) if raw_name else None
```

`_dr()` 함수는 이미 동일 함수 내에 정의되어 있음 (`pseudo_mgr.get_real_id()` 래퍼).

---

### 3.4 기능 4: PseudonymManager Thread-Safe화

#### 3.4.1 문제

`PseudonymManager`는 인스턴스별 `_mapping_cache`를 가지며, 파일 I/O에 동기화가 없음. 다중 스레드가 동시에 `_load_mappings()` → `_save_mappings()`를 실행하면 **파일 덮어쓰기로 인해 데이터 손실** 가능.

#### 3.4.2 수정 내용

1. **싱글톤화**: `_get_pseudo_mgr()`가 이미 호출되는 곳에서 매번 `PseudonymManager(...)`를 새로 생성함. 이를 모듈 레벨 싱글톤으로 변경.
2. **락 추가**: `threading.RLock()`을 추가하여 `_load_mappings()` / `_save_mappings()` / `get_pseudonym()` / `get_real_id()` / `link_mapping()` 등 모든 읽기/쓰기 메서드 보호.
3. **파일 쓰기 원자성**: 임시 파일에 쓰고 `os.replace()`로 교체 (Windows 호환).

---

### 3.5 세션 정리(Cleanup) 정책

세션이 누적되지 않도록 아래 정책을 `deploy_session_service.py`에 구현한다.

| 조건 | 처리 방법 | 트리거 시점 |
|------|-----------|-------------|
| `completed` 상태이고 `completed_at`이 7일 이상 경과 | 해당 세션 및 태스크 행 삭제 | `start` API 호출 시 (신규 세션 생성 전) |
| `failed` 상태이고 `paused_at` 또는 `created_at`이 7일 이상 경과 | 동일 |  동일 |

```python
def cleanup_old_sessions(conn, days: int = 7):
    cutoff = f"datetime('now', '-{days} days')"
    conn.execute(f"""
        DELETE FROM deploy_tasks WHERE session_id IN (
            SELECT session_id FROM deploy_sessions
             WHERE status IN ('completed', 'failed')
               AND COALESCE(completed_at, paused_at, created_at) < {cutoff}
        )
    """)
    conn.execute(f"""
        DELETE FROM deploy_sessions
         WHERE status IN ('completed', 'failed')
           AND COALESCE(completed_at, paused_at, created_at) < {cutoff}
    """)
```

---

### 3.6 DB 경로 및 .gitignore

**DB 파일 위치**: Flask 앱 루트(`wordcloud_project/`) 기준 `.sessions/deploy_sessions.db`

```python
# deploy_session_service.py
import os

_DB_DIR  = os.path.join(os.path.dirname(__file__), '..', '..', '.sessions')
_DB_PATH = os.path.join(_DB_DIR, 'deploy_sessions.db')

def get_conn():
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
```

**`.gitignore` 추가:**

```
# Deploy session DB
wordcloud_project/.sessions/
```

---

## 4. 작업 단위 및 우선순위

### Phase 1: 핫픽스 (병렬 처리 안전성)
- [ ] **4.1** `PseudonymManager` Thread-Safe화 (`pseudonym_manager.py`)
- [ ] **4.2** `get_matrix_meta()` 이름 역변환 버그 수정 (`perspective_service.py`)

### Phase 2: 통합 입력 팝업
- [ ] **4.3** 직원 조회 API 존재 여부 확인 → 없으면 신규 구현
- [ ] **4.4** `POST /api/perspective/parse-ids` API 구현 (`perspective_routes.py`)
- [ ] **4.5** 통합 모달 UI 구현 (`perspective_test.html`)
- [ ] **4.6** 파일 선택 트리거 → 모달 오픈 연동

### Phase 3: Resume 시스템
- [ ] **4.7** `deploy_session_service.py` 신규 생성 (SQLite 초기화 + CRUD + WAL 모드 + 세션 정리)
- [ ] **4.8** Chunk 할당 원자적 UPDATE 구현 (`BEGIN IMMEDIATE` 트랜잭션)
- [ ] **4.9** 세션 관리 API 6개 구현 (`perspective_routes.py`) — `active`/`chunk` API에 고아 복원 로직 포함
- [ ] **4.10** 클라이언트 Chunk 폴링 + Worker Sharding + localStorage 세션 ID 저장/복원 (`perspective_test.html`)
- [ ] **4.11** Resume 팝업 UX ("이어하기" / "무시") + 다중 미완료 세션 처리 정책
- [ ] **4.12** `.gitignore`에 `.sessions/` 추가

---

## 5. 테스트 계획

### 5.1 단위 테스트

| 테스트 시나리오 | 기대 결과 |
|-----------------|-----------|
| `PseudonymManager` 동시 `get_pseudonym()` 100회 호출 | 파일 손상 없음, 모든 매핑 유지 |
| Chunk 할당 동시 요청 10회 (같은 session_id) | 동일 `pending` 태스크가 중복 할당되지 않음 |
| 세션 생성 → 50명 Chunk 2개 처리 → 브라우저 새로고침 → Resume | 남은 0명 정상 완료, 총 100명 `completed` |
| 텍스트 입력 `"U001, U002\nU003 U004"` + 파일 결과 `U001, U005` | 최종 합집합 `U001, U002, U003, U004, U005` |
| Chunk 처리 중 4분 경과 (orphan 임박) | 5분 미만이므로 복원 안 됨, 6분 경과 시 `pending` 복원 |
| 미완료 세션 2개 존재 시 페이지 로드 | 최근 1개만 이어하기 팝업, 나머지 자동 취소 |
| 완료 후 8일 경과 세션에서 `start` 호출 | 오래된 세션/태스크 자동 삭제 후 신규 세션 생성 |

### 5.2 통합 테스트

| 테스트 시나리오 | 기대 결과 |
|-----------------|-----------|
| 19,000명 원데이터 모드 저장 → 중간에 서버 재시작 → Resume | 중단 지점부터 재개, 가명 매핑 파일 무결성 유지 |
| 원데이터 모드 매트릭스 생성 | `employee_name`이 실제 이름으로 표시됨 |
| 생성실패 3명 → "통합 팝업에서 다시 시도" → 재처리 중 탭 닫힘 → Resume | 신규 세션으로 이어하기 정상 동작 |

---

## 6. 예상 소요 시간

| Phase | 예상 소요 | 비고 |
|-------|-----------|------|
| Phase 1 (핫픽스) | 2시간 | 상대적으로 단순한 수정 |
| Phase 2 (팝업) | 4~5시간 | 직원 조회 API 존재 여부에 따라 변동 |
| Phase 3 (Resume) | 9시간 | SQLite 세션 + Chunk 폴링 + Worker Sharding + UX + 정리 정책 |
| **총계** | **15~16시간** | 테스트 및 디버깅 포함 |

---

## 7. 리스크 및 대응

| 리스크 | 영향도 | 대응 방안 |
|--------|--------|-----------|
| SQLite 파일 손상 (서버 비정상 종료) | Resume 불가 | WAL 모드(`PRAGMA journal_mode=WAL`) 사용. 주기적 백업은 Phase 3 이후 고려 |
| Chunk 중복 할당 | 동일 직원 중복 처리 | `BEGIN IMMEDIATE` 트랜잭션으로 원자적 UPDATE 보장 (3.1.7 참조) |
| Chunk 폴링으로 인한 네트워크 오버헤드 | 대량 처리 시 속도 저하 | Chunk 크기를 50~100으로 조정. Worker Sharding으로 내부 병렬성 확보 |
| 브라우저 `localStorage` 용량 초과 | 세션 정보 저장 불가 | 세션 ID만 `localStorage`에 저장. 상세 상태는 서버 SQLite로 이관 |
| 기존 `save-deploy-stream` API와의 충돌 | 하위 호환성 문제 | 기존 API 유지. 새 API는 별도 엔드포인트. 추후 Deprecated 고려 |
| **고아 태스크 (Orphan)** | 작업 중 정지 후 `processing` 상태로 남아 재할당 불가 | `active` API와 `chunk` API 양쪽에서 5분 이상 경과 태스크를 `pending`으로 자동 복원 |
| **생성실패 누적** | 특정 직원이 반복 실패하여 전체 완료가 되지 않음 | 최종 결과 화면에 실패 목록 + `[재시도]` 버튼 제공. 3회 이상 실패 시 수동 확인 유도 |
| **세션 누적** | SQLite 파일 크기 무한 증가 | `start` API 호출 시 7일 이상 경과 완료/실패 세션 자동 삭제 (3.5 참조) |
| **직원 조회 API 미존재** | Phase 2 범위 증가 | Phase 2 착수 전 확인. 없으면 4.3 태스크에서 신규 구현 |

---

## 8. 결론

본 계획은 다음 4가지 개선을 포함합니다.

1. **대량 저장 Resume**: Chunk 폴링 + SQLite 세션 + Worker Sharding으로 19,000명 처리도 중단 후 재개 가능
2. **통합 ID 입력 팝업**: CSV 파일 + 텍스트 입력을 하나의 UI로 통합, 실시간 매칭 미리보기 제공
3. **원데이터 이름 표시 버그 수정**: `get_matrix_meta()`에서 `employee_name` 역변환 적용
4. **PseudonymManager Thread-Safe화**: 대량 원데이터 처리 시 데이터 무결성 보장

### 부록: 생성실패 vs 작업 중 정지 — 핵심 요약

| 구분 | 상태 변화 | Resume 시 | 사용자 화면 |
|------|-----------|-----------|-------------|
| **생성실패** | `processing` → `failed` | 스킵 (또는 사용자가 재시도 선택) | `❌ 3명 실패 — 김철수: 데이터 없음, 이영희: 메모리 부족... [재시도]` |
| **작업 중 정지** | `processing`이 **그대로 고아 상태**로 남음 | `assigned_at` > 5분 경과 시 `pending`으로 자동 복원 | `"14:32에 중단됨 (87% 완료). 마지막 완료: 김철수(U001)" [이어서 계속]` |

사용자가 **"수행"**을 명시적으로 요청하면 Phase 1부터 순차적으로 구현을 시작합니다.
