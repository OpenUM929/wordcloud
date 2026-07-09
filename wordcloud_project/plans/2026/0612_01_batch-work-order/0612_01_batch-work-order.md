# 배치 작업서 기반 Resume 시스템

> 상태: Done | 작성일: 2026-06-12 | 완료일: 2026-06-12 | 테스트: ✅ 2026-06-15

---

## 구현 시 반영된 변경 (계획 대비)

| 항목 | 계획 | 실제 구현 |
|------|------|-----------|
| DB 접근 계층 | `user_data_manager.get_db_path()` / `_init_db()` | 실제 DB(`deploy_sessions.db`)는 `deploy_session_service._init_db()`가 초기화하고 연결은 `_get_conn()`이 담당. → `batch_work_orders` DDL을 `deploy_session_service._init_db()`에 추가, 서비스는 `_get_conn`/`_init_db` 재사용 (순환임포트 방지 의도 동일하게 유지) |
| `fail_work_order` 호출처 | `process_batch` 최상위 try/except | `batch_processing_state['batch_id']`를 기록하고, `_run_batch_process`의 except에서 호출 (대규모 재들여쓰기 회피, 동일 효과). 새 실행 초기화 시 stale `batch_id` 제거 |
| resume skip 위치 | 가명화 이후 | 동일 — `employee_items` 생성 직후, pseudo_id 기준 필터 |
| **DB 저장 시점 (테스트로 발견한 결함 수정)** | 계획서는 진행상황 flush만 명시, 실제 데이터 영구 저장 시점 미고려 | **기존 코드는 Stage 3(메모리 메타 생성) 완료 후 Stage 4에서 일괄 `upsert`. 중간 종료 시 DB에 0건 저장 → resume이 0건으로 동작.** 수정: `upsert`를 Stage 3 루프 안으로 이동(직원 완료 즉시 영구 저장), 작업서에는 **실제 저장(persisted)된 직원만** 기록, flush 주기 100→10명. "작업서 완료 기록 = DB 저장 완료" 보장 |
| **대용량(약 19,000명) 확장성** | `completed_employees`를 단일 JSON TEXT 컬럼에 누적 append(set 병합) | **JSON 배열 통째 재기록이 flush마다 O(n) → 전체 O(n²)로 19,000명에서 수백 MB 쓰기 발생.** 별도 테이블 `batch_work_order_items`(1직원 1행)로 전환: flush 시 신규 직원만 `INSERT OR IGNORE`(O(델타)), resume skip은 `SELECT ... WHERE batch_id=?`. 추가로 저장 후 `employee_results`의 metadata를 `None`으로 비워 19,000명분 메모리 해제 |
| **`batch_id` 재사용 방지 (테스트 중 발견)** | `initialize_batch_directory()`가 파일시스템만 조회 | **디렉토리를 삭제해도 DB 레코드는 잔존 → 같은 batch_id가 채번되어 이전 카운터(processed_employees 등)가 유령값으로 노출되고, items 테이블의 이전 직원이 Resume skip 대상에 오염됨.** 수정: `initialize_batch_directory()`가 `get_work_order_by_batch_id()`로 DB도 이중 확인 (파일시스템도 없고 DB도 없어야 채번). 방어층: `create_work_order()` ON CONFLICT 시 카운터를 0으로 리셋 + `DELETE FROM batch_work_order_items WHERE batch_id=?` 실행 |
|:--|:--|:--|
| **서버 강제 종료 대응 (테스트 중 발견)** | `except Exception:`이 `KeyboardInterrupt`/프로세스 kill을 잡지 못함 → 강제 종료 시 `status='running'` 좀비 상태 잔존 | **백그라운드 스레드가 서버와 함께 죽지만 DB status는 아무도 바꾸지 않음 → 서버 재기동 시 `_cleanup_stale_running_orders()`가 `UPDATE batch_work_orders SET status='interrupted' WHERE status='running'` 실행 (시간 조건 불필요, 기동 시점의 `running`은 모두 죽은 배치).** 상태값 체계 확장: `running | completed | failed | interrupted`. 프론트엔드에서 `interrupted`="⏸ 중단됨" (Resume 가능), `failed`="⛔ 실패" (원인 확인 필요), `running`="🔄 처리 중" (Resume 버튼 미표시)로 분리 표시 |

> **알려진 한계:** 욕설(profanity) 데이터는 여전히 Stage 5에서 일괄 저장되므로, 중간 종료된 배치의 사전 처리분 욕설 정보는 resume 시 누락될 수 있다(평가 데이터 본체는 손실 없음). 필요 시 욕설도 직원별 저장으로 후속 개선.

> **대용량 설계 메모:** 대상 데이터가 약 19,000명 규모이므로 배치 추적 로직은 반드시 O(n) 이하로 유지한다. JSON 배열 누적 재기록 같은 O(n²) 패턴 금지.

---

## Context

배치 메타데이터 생성 중 중단(서버 재시작, 오류 등)이 발생하면 현재는 처음부터 전체 재처리해야 한다. `save_checkpoint()` / `load_checkpoint()` 함수가 정의되어 있지만 `load_checkpoint()`는 호출되지 않아 resume이 불가능하다. 상태 또한 메모리(`batch_processing_state` dict)에만 저장되므로 서버 재시작 시 소멸한다.

**구현 목표:**
- 배치 시작 시 **작업서(Work Order)**를 DB에 생성 — 설정 스냅샷 + 진행 상황 영구 보존
- 1단계(데이터 업로드) 하단에 **작업서 게시판** — 전체 작업 이력 표시
- 미완료 작업서에 **"이어서 작업" 버튼** → 클릭 시 설정 자동 입력 후 4단계로 이동
- 4단계에서 **"이어서 배치 처리 시작" 버튼** → 모달로 남은 작업량 확인 후 재개

---

## 구조 설계

### 처리 방식 전제

> **변경 이력 (2026-06-12 재검토 반영):** (1차) `file_info` 지속성 대책, `completed_employees` 저장 방식, DB 접근 방식, 프론트엔드 파일명 확정, `resume_batch_metadata` 세션 주입 구조 보강. (2차) `completed_employees` 누적 append 확정, `fail_work_order` 호출처 추가, `updated_at` 명시적 갱신, `resume` 분기 함수명 명시, 검증 시나리오 보강.

### 처리 방식 전제

현재 배치 처리는 `ThreadPoolExecutor`로 **직원 단위 병렬 처리**다. 직원 각각이 완료될 때마다 `completed_employees` 목록에 추가하고, 일정 주기(100명)로 work order DB에 flush한다.

Resume 시:
- DB에서 `completed_employees` 로드
- 전체 CSV 재파싱 후 완료된 직원 제외
- 나머지만 동일 방식(병렬)으로 처리 재개
- 동일 `batch_id` · `batch_dir` 재사용 → DB/파일 중복 없음

---

## 1. DB 테이블 추가: `batch_work_orders`

수정 파일: `wordcloud_project/src/services/user_data_manager.py` (`_init_db()`)

```sql
CREATE TABLE IF NOT EXISTS batch_work_orders (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id             TEXT UNIQUE NOT NULL,
    batch_dir            TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'running',  -- running | completed | failed | interrupted
    settings             TEXT NOT NULL,   -- JSON: mappings, enablePreprocessing, enableEmotionAnalysis 등
    file_info            TEXT NOT NULL,   -- JSON: csv_file_path, csv_filename, csv_rows, input_type
    total_employees      INTEGER DEFAULT 0,
    processed_employees  INTEGER DEFAULT 0,
    success_count        INTEGER DEFAULT 0,
    error_count          INTEGER DEFAULT 0,
    total_rows           INTEGER DEFAULT 0,
    completed_employees  TEXT DEFAULT '[]',  -- JSON array: 완료 처리된 employee_id 목록
    created_at           TEXT DEFAULT (datetime('now','localtime')),
    updated_at           TEXT DEFAULT (datetime('now','localtime')),
    completed_at         TEXT
);
```

> **검토 반영:** `file_info`의 `csv_file_path`는 절대 경로를 저장하되, **Resume 시 파일 존재 여부를 반드시 확인**한다. 파일이 사라진 경우 `batch_dir` 내에 원본 CSV 복사본(`original.csv`)을 두는 것을 권장하며, 복사본도 없으면 API가 `{"success": false, "error": "원본 파일을 찾을 수 없습니다."}`를 반환하고 프론트엔드에서 재업로드를 유도한다.

> **검토 반영:** `completed_employees`는 JSON TEXT로 저장한다. 직원 수가 수천 명 이상으로 길어질 경우, 100명 단위 `update_work_order_progress` 호출 시 **전체 배열을 덮어쓰는 대신 누적 append 방식**을 적용한다. 즉, `update_work_order_progress` 내부에서 기존 `completed_employees`를 로드 → `set`으로 병합 → 다시 저장하는 방식으로, 중복 `employee_id`를 방지하면서도 최신 상태를 유지한다. 별도 테이블로 분리는 현재 단계에서는 과하다고 판단, JSON TEXT 유지하되 append 로직으로 최적화한다.

---

## 2. 신규 서비스: `batch_work_order_service.py`

신규 파일: `wordcloud_project/src/services/batch_work_order_service.py`

```
create_work_order(batch_id, batch_dir, settings, file_info) -> int
update_work_order_progress(batch_id, processed_employees, success_count,
                            error_count, total_rows, completed_employee_ids)
complete_work_order(batch_id)
fail_work_order(batch_id)
get_all_work_orders(limit=20) -> list[dict]     # 게시판용 최신순 목록
get_latest_incomplete_work_order() -> dict|None
get_work_order_by_batch_id(batch_id) -> dict|None
```

DB 접근: `deploy_session_service._get_conn()`을 임포트하여 사용한다. 기존 `batch_work_order_service.py`는 이미 `from src.services.deploy_session_service import _get_conn, _init_db` 방식으로 접근 중이다. `_get_conn()`은 `sqlite3.connect(check_same_thread=False)` + `PRAGMA journal_mode=WAL`을 적용한 커넥션을 반환한다.

### `update_work_order_progress` 내부 구현 상세

`completed_employees`는 **누적 append 방식**으로 갱신한다. 매 호출마다 JSON 배열을 통째로 덮어쓰지 않고, 기존值을 로드 → `set` 병합 → 다시 저장한다:

```python
def update_work_order_progress(batch_id, processed_employees, success_count,
                                error_count, total_rows, completed_employee_ids):
    conn = _get_conn()
    try:
        # 1) 기존 completed_employees 로드
        cur = conn.execute("SELECT completed_employees FROM batch_work_orders WHERE batch_id = ?", (batch_id,))
        row = cur.fetchone()
        existing = set(json.loads(row[0])) if row else set()

        # 2) 신규 ID 병합 (중복 제거)
        existing.update(completed_employee_ids)
        updated = json.dumps(list(existing), ensure_ascii=False)

        # 3) updated_at 명시적 갱신
        conn.execute("""
            UPDATE batch_work_orders
            SET processed_employees = ?,
                success_count      = ?,
                error_count        = ?,
                total_rows         = ?,
                completed_employees = ?,
                updated_at         = datetime('now','localtime')
            WHERE batch_id = ?
        """, (processed_employees, success_count, error_count, total_rows, updated, batch_id))
        conn.commit()
    finally:
        conn.close()
```

> **핵심:** `updated_at`을 `DEFAULT` 값에 의존하지 않고 **명시적으로 UPDATE SET** 한다. SQLite의 `DEFAULT`는 INSERT 시에만 적용된다.

### `get_latest_incomplete_work_order()` 사용처

이 함수는 **페이지 로드 시 자동으로 최신 재개 가능한(interrupted/failed) 작업이 있는지 확인**하여, 있을 경우 프론트엔드에서 "중단된 작업이 있습니다" 알림을 표시하며(자동 펼침 + Resume 버튼 표시), **서버가 살아있어 직접 처리 중인 `running` 상태는 Resume 대상에서 제외**한다. (`metadata_batch.js`의 `DOMContentLoaded` 이벤트에서 `loadWorkOrders()` 호출, 내부에서 `get_all_work_orders()`로 전체 목록 조회 → 프론트엔드에서 `hasIncomplete` 판단)

---

## 3. `batch_processor.py` 수정

### 배치 시작 시 (새 배치 — `data.get('resume')` 가 False인 경우)
```python
# 1) 새 batch_dir 생성
batch_dir, batch_num = initialize_batch_directory(processed_data_dir)

# 2) 원본 CSV → batch_dir/original.csv 복사 (Resume 시 fallback용)
import shutil
original_csv_backup = os.path.join(batch_dir, "original.csv")
shutil.copy2(csv_file_path, original_csv_backup)

# 3) 작업서 생성
from services.batch_work_order_service import create_work_order
create_work_order(batch_id, batch_dir, settings_snapshot, file_info_snapshot)
```

`settings_snapshot`: `data` 파라미터 전체 (mappings, enablePreprocessing, enableEmotionAnalysis 등)  
`file_info_snapshot`: session에서 추출한 파일 정보 (csv_file_path, csv_filename, csv_rows, input_type)

### Resume 시 분기 — `process_batch()` 함수 내, `initialize_batch_directory()` 호출 전

> `process_batch(processed_data_dir, data, session_data)`는 `batch_processor.py`의 메인 진입점이다. (`batch_processor.py:341`)

`initialize_batch_directory()`를 **호출하지 않는다.** 대신 작업서에서 기존 `batch_dir`를 그대로 사용한다.

```python
# process_batch() 내, initialize_batch_directory() 호출 전에 resume 분기
if data.get('resume'):
    resume_batch_id = data.get('batch_id')
    resume_batch_dir = data.get('batch_dir')
    prior_completed = set(data.get('completed_employees', []))
    # csv_file_path -> data['csv_file_path'] (resume_batch_metadata에서 fallback 포함 주입)
    # initialize_batch_directory() 호출 건너뛰기 → batch_dir = resume_batch_dir
else:
    # 기존: 새 디렉토리 생성
    batch_dir, batch_num = initialize_batch_directory(processed_data_dir)
    # original.csv 복사 + 작업서 생성
```

### 처리 중 — 100명 단위로 progress flush
```python
if completed % 100 == 0:
    update_work_order_progress(
        batch_id,
        processed_employees=completed,
        success_count=..., error_count=..., total_rows=...,
        completed_employee_ids=[r['employee_id'] for r in employee_results if r.get('success')]
    )
```

### 완료 시
```python
complete_work_order(batch_id)
```

### 예외 처리 — 실패 시 `fail_work_order` 호출 (신규)

`process_batch()` 함수의 최상위 `try-except` 블록에서 `except` 시 호출한다.
```python
try:
    # ... 전체 처리 로직 ...
    complete_work_order(batch_id)
except Exception as e:
    fail_work_order(batch_id)
    raise
```

> 직원 단위 병렬 처리 내부의 개별 오류는 `fail_work_order`가 아니라 `error_count`만 증가시킨다. `fail_work_order`는 **전체 배치가 중단**되어야 할 때만 호출한다.

### `completed_employees` fallback 패턴 (신규)

`batch_processor.py`는 `data['completed_employees']`를 우선 사용하고, 없으면 `work_order`에서 직접 로드한다:
```python
if data.get('resume'):
    prior_completed = set(data.get('completed_employees', []))
```

이미 `batch_service.resume_batch_metadata`에서 `data['completed_employees']`를 주입하므로, `batch_processor`는 `data`만 참조하면 되며 DB를 다시 조회할 필요가 없다.

---

## 4. `batch_service.py` 수정

- `process_batch_metadata(data, session_obj)`: 기존 신규 배치 로직 유지
- `resume_batch_metadata(batch_id, session_obj)` 신규 함수 추가:
  1. `get_work_order_by_batch_id(batch_id)` 로드
  2. `file_info.csv_file_path` 존재 확인. **없으면 `batch_dir/original.csv`를 fallback으로 확인.** 둘 다 없으면 `None` 반환.
  3. `work_order['settings']` JSON을 파싱하여 `data` dict 형태로 재구성: `{'mappings': ..., 'enablePreprocessing': ..., 'enableEmotionAnalysis': ...}`
  4. `work_order['file_info']` JSON을 파싱하여 `data['file_info']`에 주입. `data['csv_file_path'] = file_info['csv_file_path']` (또는 fallback 경로)
  5. `data['batch_id'] = batch_id`, `data['resume'] = True` 플래그 추가
  6. `data['batch_dir'] = work_order['batch_dir']` 추가 — `batch_processor`가 기존 디렉토리를 재사용하도록 주입
  7. `data['completed_employees'] = json.loads(work_order['completed_employees'])` 추가
  8. `session_obj['batch_id'] = batch_id` 저장
  9. `process_batch_metadata(data, session_obj)`를 재호출 (resume 플래그로 `batch_processor`가 skip 로직을 실행하도록 위임)
     - `process_batch_metadata`는 내부에서 이미 `Thread(target=_run_batch_process, ...)`로 백그라운드 스레드를 시작하므로, `resume_batch_metadata`는 별도 스레드를 생성하지 않는다.

> **검토 반영:** `resume_batch_metadata`는 `data`와 `session_obj`를 **완전히 재구성**하여 기존 `process_batch_metadata`의 진입점을 재사용한다. `batch_processor.py` 내부에서 `resume` 플래그를 감지하면 `completed_employees` skip 로직을 실행한다.

---

## 5. `batch_routes.py` 엔드포인트 추가

```
GET  /api/batch/work-orders           게시판용 전체 목록 (limit=20)
POST /api/batch/resume                작업서 기반 이어서 처리 시작
```

`POST /api/batch/resume` body:
```json
{ "batch_id": "batch_20260612_0" }
```

응답 (성공): `{"success": true, "status": "started"}`  
응답 (CSV 없음): `{"success": false, "error": "원본 파일을 찾을 수 없습니다."}`

---

## 6. 프론트엔드 변경

> **검토 반영:** 실제 파일명 확인 결과 — HTML: `web/templates/metadata_batch.html`, JS: `web/static/js/metadata_batch.js`.

> **검토 반영:** 1단계(데이터 업로드)에 이전 작업 이력을 함께 두면 사용자가 "새 파일 업로드"와 "이전 작업 재개" 중 어떤 게 우선인지 혼란스러울 수 있다. 따라서 **"최근 작업 이력"은 별도 접이식 섹션(collapsible card)**으로 배치하며, 기본 상태는 접힌 상태로 한다. 미완료 작업이 1개 이상 존재할 때만 자동으로 펼친다.

### 6-1. 1단계 하단: 작업서 게시판

**대상 파일:** `metadata_batch.html` (1단계 영역 하단), `metadata_batch.js` (게시판 렌더링 로직)

페이지 로드 시 `GET /api/batch/work-orders` 호출 → 테이블 렌더링

```
┌ 최근 작업 이력 (미완료 시 자동 펼침) ─────────────────────────────────────┐
│ 작업 ID       │ 파일명    │ 작업 일시       │ 진행/전체  │ 상태    │ 액션  │
├───────────────┼───────────┼─────────────────┼────────────┼─────────┼──────┤
│ batch_..._0   │ data.csv  │ 2026-06-12 14:23 │  45 / 100  │ ⏸ 미완료 │ [이어서 작업] │
│ batch_..._1   │ data.csv  │ 2026-06-11 09:10 │ 100 / 100  │ ✅ 완료  │      │
└───────────────┴───────────┴─────────────────┴────────────┴─────────┴──────┘
```

**"이어서 작업" 버튼 클릭 동작:**
1. 해당 work order의 `settings` → 컬럼 매핑 UI 자동 선택 (select dropdown 값 설정)
2. `enablePreprocessing` / `enableEmotionAnalysis` 체크박스 설정 (checked 속성)
3. `file_info` → 파일명·행 수 표시 (읽기 전용 텍스트로 1단계에 노출)
4. 4단계 섹션으로 스크롤 이동 (`#step4` anchor 또는 JS scrollIntoView)
5. "이어서 배치 처리 시작" 버튼 활성화 + 선택된 `batch_id`를 `window.selectedResumeBatchId` 전역 변수에 저장

### 6-2. 4단계 버튼 영역

```html
<!-- 기존 버튼 유지 -->
<button class="btn btn-primary" onclick="startBatchProcessing()">배치 처리 시작</button>

<!-- 신규: 이어서 작업서 선택 시만 표시 -->
<button class="btn btn-warning" id="resumeBtn" style="display:none"
        onclick="showResumeModal()">이어서 배치 처리 시작</button>
```

### 6-3. 이어서 작업 확인 모달

```
┌────────────────────────────────────┐
│      이어서 배치 처리 시작          │
├────────────────────────────────────┤
│  원본 파일:  data.csv               │
│  작업 시작:  2026-06-12 14:23       │
│  이미 처리:  45명 완료              │
│  남은 작업:  55명                   │
│  총 작업:    100명                  │
├────────────────────────────────────┤
│           [취소]    [확인]          │
└────────────────────────────────────┘
```

확인 클릭 → `POST /api/batch/resume` 호출 → SSE 연결 → 기존 진행 UI 동일 표시

---

## 7. 수정 대상 파일 요약

| 파일 | 유형 | 내용 |
|------|------|------|
| `src/services/deploy_session_service.py` | 수정 | `_init_db()`에 `batch_work_orders` 테이블 DDL 추가 |
| `src/services/batch_work_order_service.py` | **신규** | work order CRUD 함수 7개 + `deploy_session_service._get_conn()` 임포트 사용 |
| `src/services/batch_processor.py` | 수정 | 작업서 생성/갱신/완료 호출 + resume skip 로직 + `file_info` fallback 경로 |
| `src/services/batch_service.py` | 수정 | `resume_batch_metadata()` 신규 함수 — `data`/`session_obj` 재구성 |
| `src/routes/batch_routes.py` | 수정 | `/work-orders`, `/resume` 엔드포인트 추가 |
| `web/templates/metadata_batch.html` | 수정 | 1단계 접이식 게시판 HTML + 4단계 resume 버튼 + 모달 |
| `web/static/js/metadata_batch.js` | 수정 | 게시판 렌더링·자동 입력·resume 로직 + `window.selectedResumeBatchId` |

---

## 8. 검증 시나리오 — ✅ 2026-06-15 전 항목 테스트 완료

### Phase 1: 신규 배치 CRUD

| # | 시나리오 | 결과 |
|---|----------|-------|
| 1 | 새 배치 시작 → `batch_work_orders` 레코드 생성, `status='running'` 확인 | ✅ |
| 2 | 처리 중 서버 강제 종료 → 재시작 후 게시판에 `interrupted` 행 표시 확인 (자동 펼침) | ✅ |
| 3 | "이어서 작업" 버튼 클릭 → 폼 자동 입력 + 4단계 이동 + resume 버튼 활성화 확인 | ✅ |
| 4 | 모달에서 `남은 작업 = 전체 - 완료` 숫자가 정확한지 확인 | ✅ |
| 5 | Resume 확인 클릭 → 완료된 직원은 건너뛰고 나머지만 처리되는지 로그/DB로 확인 | ✅ |
| 6 | 최종 완료 → `status='completed'`, 게시판 행에 "✅ 완료" 표시, resume 버튼 사라짐 확인 | ✅ |
| 7 | **원본 CSV 삭제 후 Resume 시도** → `batch_dir/original.csv` fallback 확인, 없으면 `{"success": false, "error": "원본 파일을 찾을 수 없습니다."}` 반환 | ✅ |
| 8 | **10명 단위 progress flush** → 처리 중 10초 간격 DB 폴링으로 `processed_employees`가 10씩 증가 확인 (20→30→40), `updated_at` 갱신 확인 | ✅ |
| 9 | **완료된 작업서 중복 Resume 차단** → `resume_batch_metadata()`에서 `status='completed'` 체크 → `{"success": false, "error": "이미 완료된 작업입니다."}` 반환 | ✅ |
| 10 | **배치 처리 중 예외 발생** → `_run_batch_process`의 `except Exception`에서 `fail_work_order(batch_id)` 호출 → `status='failed'` 확인 (Python 예외 시나리오) | ✅ |
| 11 | **`updated_at` 갱신 확인** → `update_work_order_progress` 호출 전후 `updated_at` 타임스탬프 변화 확인 | ✅ |
| 12 | **페이지 로드 시 `loadWorkOrders()` 자동 호출** → `DOMContentLoaded` 이벤트에서 `/api/batch/work-orders` 요청 발생, `hasIncomplete` 판단 후 자동 펼침 | ✅ |
| 13 | **`batch_id` 재사용 차단** → `initialize_batch_directory()`가 DB도 조회: 디렉토리 삭제해도 DB 레코드가 있으면 다음 번호 채번 (`batch_20260615_0` 삭제 후 `batch_20260615_1` → `batch_20260615_2`로 생성) | ✅ |
| 14 | **`create_work_order` 방어층 — ON CONFLICT 리셋** → 같은 `batch_id`로 `create_work_order` 재호출 시 `processed_employees=0`, `success_count=0`, `DELETE FROM batch_work_order_items WHERE batch_id=?` 실행 확인 | ✅ |

### Phase 2: 서버 강제 종료 내성 (신규 검증, 2026-06-15 추가)

| # | 시나리오 | 결과 |
|---|----------|-------|
| 15 | **서버 강제 종료 후 재기동 → `running`→`interrupted` 전환** → `_cleanup_stale_running_orders()`가 DB의 `status='running'`을 `'interrupted'`로 일괄 전환, `updated_at` 갱신 확인 (시간 조건 불필요, 기동 시점의 `running`은 모두 죽은 배치) | ✅ |
| 16 | **`interrupted` 상태 Resume 처리** → 기존 처리된 직원 skip + 나머지만 처리, `status`는 `interrupted` 유지 → 완료 시 `completed`로 전환 | ✅ |
| 17 | **`running` 상태 Resume 차단** → 서버가 살아있는 동안 Resume API 호출 시 `resume_batch_metadata()`에서 `status='running'` 체크 → `{"success": false, "error": "현재 처리 중인 작업입니다."}` 반환 | ✅ |
| 18 | **`failed` 상태 Resume 처리** → `failed` 배치도 Resume 가능 (`get_latest_incomplete_work_order()`에서 `status IN ('interrupted', 'failed')`로 조회), Resume 버튼 표시 | ✅ |
| 19 | **프론트엔드 상태 표시 분리** → `completed`="✅ 완료", `interrupted`="⏸ 중단됨" (Resume 버튼 있음), `failed`="⛔ 실패" (Resume 버튼 있음), `running`="🔄 처리 중" (Resume 버튼 없음) | ✅ |

---

## 9. 검토 의견 및 참고사항

> **2026-06-12 검토 반영 내역**

| # | 원래 이슈 | 반영 조치 | 위치 |
|---|-----------|-----------|------|
| 1 | `file_info.csv_file_path`가 절대 경로로 서버 이동/재시작 후 무효화될 수 있음 | `batch_dir` 내 `original.csv` fallback 추가, API에서 파일 없음 명시적 에러 반환 | 1. DB 테이블, 4. `batch_service.py` 수정, 8. 검증 시나리오 7 |
| 2 | `completed_employees` JSON TEXT가 커질 수 있음 | 100명 단위 flush 시 **누적 append 방식** 적용 (`set` 병합 후 저장). 별도 테이블 분리는 현재 단계 과다 | 1. DB 테이블 |
| 3 | `batch_work_order_service.py` DB 접근 시 순환 임포트 위험 | `deploy_session_service._get_conn()` **임포트하여 사용**. 기존 서비스들과 동일한 패턴(`_get_conn`) 적용 | 2. 신규 서비스 |
| 4 | `resume_batch_metadata`의 `data`/`session_obj` 주입 구조 불명확 | `data` dict를 **완전 재구성**하여 `process_batch_metadata` 재호출, `resume` 플래그로 위임 | 4. `batch_service.py` 수정 |
| 5 | 프론트엔드 파일명 불확실 | 실제 확인 결과: `metadata_batch.html`, `metadata_batch.js` | 6. 프론트엔드 변경 |
| 6 | 1단계 게시판이 "새 업로드"와 혼란 유발 가능 | **접이식 섹션(collapsible card)**으로 분리, 미완료 존재 시만 자동 펼침 | 6. 프론트엔드 변경 |
| 7 | `batch_id` 재사용 시 검증 부재 | Resume 시 `file_info`와 `batch_dir` 매칭 여부 확인, 완료된 작업서는 resume 버튼 미표시 | 8. 검증 시나리오 9 |
| 8 | `original.csv` 복사 시점 미명시 | 새 배치 시작 시 `initialize_batch_directory()` 직후 `shutil.copy2()` 로 `batch_dir/original.csv` 생성. Resume 시에는 복사 생략 | 3. `batch_processor.py` 수정 |
| 9 | Resume 시 `initialize_batch_directory()` 건너뛰기 미명시 | `data['resume']` 플래그 분기로 새 디렉토리 생성 없이 `work_order['batch_dir']` 재사용. `batch_service.py`가 `data['batch_dir']` 주입 | 3. `batch_processor.py` 수정, 4. `batch_service.py` 수정 |
| 10 | `update_work_order_progress` 내 `updated_at` 명시적 갱신 필요 | UPDATE SQL에 `updated_at = datetime('now','localtime')` 추가. `DEFAULT`는 INSERT 전용 | 2. 신규 서비스 (`update_work_order_progress` 구현 상세) |
| 11 | `fail_work_order(batch_id)` 호출처 부재 | `process_batch()` 최상위 `try-except`에서 예외 시 호출. 직원 단위 오류는 `error_count`만 증가 | 3. `batch_processor.py` 수정 (예외 처리) |
| 12 | `data['completed_employees']` vs DB 직접 로드 중복 가능 | `batch_processor`는 `data['completed_employees']`를 우선 사용. `batch_service`가 이미 주입하므로 DB 재조회 불필요 | 3. `batch_processor.py` 수정 (fallback 패턴) |
| 13 | `resume_batch_metadata` 스레드 시작 중복 | `process_batch_metadata`가 내부에서 `Thread`를 생성하므로, `resume_batch_metadata`는 추가 스레드 미생성 | 4. `batch_service.py` 수정 |
| 14 | `get_latest_incomplete_work_order()` 사용처 불명확 | 페이지 로드 시 자동 확인 → "중단된 작업이 있습니다" 알림용 | 2. 신규 서비스 |
| 15 | **`batch_id` 재사용 시 이전 카운터·items 오염 (테스트 중 발견)** | `initialize_batch_directory()`가 파일시스템만 확인 → 디렉토리 삭제 후 DB 레코드 잔존 시 같은 batch_id 재채번. 이전 `processed_employees`가 유령값으로 노출되고, items 테이블의 이전 직원이 Resume skip에 오염됨. **수정 ①** `initialize_batch_directory()`가 `get_work_order_by_batch_id()`로 DB도 이중 확인(파일시스템도 없고 DB도 없어야 채번). **수정 ②** `create_work_order()` ON CONFLICT 시 카운터 0 리셋 + `DELETE FROM batch_work_order_items WHERE batch_id=?` — 정상 경로에선 발생 안 하지만 방어층으로 유지 | `initialize_batch_directory()` (batch_processor.py), `create_work_order()` (batch_work_order_service.py) |
| 16 | **서버 강제 종료 시 `status='running'` 좀비 상태 (테스트 중 발견)** | `except Exception:`이 `KeyboardInterrupt`(BaseException 계열)를 잡지 못해 강제 종료 시 `fail_work_order`가 호출되지 않음. **수정:** `_cleanup_stale_running_orders()` 신규 작성, 서버 기동 시 `running`→`interrupted` 일괄 전환. `interrupted` 상태 추가로 UX 구분(`failed`="오류 발생" vs `interrupted`="중단됨, Resume 가능"). `resume_batch_metadata()`에 `running` 상태 Resume 차단 로직 추가 | `deploy_session_service.py` (`_cleanup_stale_running_orders`), `batch_service.py` (`resume_batch_metadata`), `metadata_batch.js` (`renderWorkOrders` 상태 표시 분리) |

---

*본 문서는 2026-06-12 초안 작성 후 동일일자 검토·보강, 2026-06-15 테스트 중 발견한 batch_id 재사용 버그 + 서버 강제 종료 좀비 상태 수정 반영, 전 항목 테스트 완료.*

---

> **테스트 환경:** 로컬 Flask 서버, SQLite(`deploy_sessions.db`), 2개 CSV 파일(15명/50명), 실시간 DB 폴링 기반 검증
