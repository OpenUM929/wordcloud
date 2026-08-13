# 계획서 — 배치 병합 기능 (배치 리스트에서 복수 배치를 하나로 통합)

> 상태: Todo | 작성일: 2026-08-13
> 작업 유형: B (기능 개선/신규 기능) — DB 스키마 추가가 있어 E(마이그레이션) 필수 섹션을 §6에 병합
> 선행: 12_01 (연도별 긍정/부정 추이 라인 그래프 — 병합의 소비처)

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-08-13 | 전체 | 최초 작성 |

---

## 요구사항 원자화

> 절차: `기대` 열은 내가 코드 실측으로 채운 예측 답이다. 착수 전 사용자가 O/X 로 교정한다. `작업 후 답`은 구현·검증 후 근거(파일:라인·로그·테스트명)와 함께 채운다.

| # | 원자 질문 | 기대 (사용자 확인) | 작업 후 답 (근거) |
|---|-----------|--------------------|------------------|
| 1.1 | 병합 버튼이 붙는 화면은 `/admin/batch-management`(배치 리스트) 인가? | Y — `admin_routes.py:56` → `admin_batch_management.html:4` 제목이 "배치 리스트" | |
| 1.2 | 관점 분석 화면의 「배치 이력」 패널(`perspective_test.html:357`)에도 같은 버튼을 붙이는가? | N — 1차 범위는 배치 리스트 화면 1곳. 이력 패널은 목록 갱신만 | |
| 1.3 | 병합 대상은 2개 이상 배치를 **체크박스로 다중 선택**하는 방식인가? | Y | |
| 1.4 | 병합 결과 배치의 이름(예: `23년 통합`)을 사용자가 직접 입력하는가? | Y — 기존 명칭 편집 API(`perspective_routes.py:1108`)와 같은 `display_name` 필드에 저장 | |
| 1.5 | 병합 후 **원본 배치(23년 1차·2차)는 배치 리스트에서 사라지는가**? | Y — 목록에서는 숨긴다. 단 **데이터 삭제가 아니라** 작업서 `status='merged'` 표시이며 병합 이력 테이블로 되돌릴 수 있다 | |
| 1.6 | 병합은 평가 데이터를 **복사**하는가, `batch_id`만 바꾸는가? | `batch_id`만 바꾼다(재라벨). 복사는 `idx_ev_fp` UNIQUE(employee_id, fingerprint) 위반이라 **불가능** — `deploy_session_service.py:171` | |
| 1.7 | 두 배치에 같은 직원의 **같은 평가**가 들어 있으면 병합 시 2건이 되는가? | N — 스키마 v3 이후 배치가 달라도 동일 (employee_id, fingerprint) 은 애초에 1건만 저장된다(`deploy_session_service.py:158-179`). 따라서 병합으로 늘거나 줄지 않는다 | |
| 1.8 | 병합 후 총 평가 건수·직원 수가 원본 두 배치의 합과 일치하는가? | Y — 평가 건수는 합과 일치. 직원 수는 **양쪽에 모두 있는 직원이 1명으로 합쳐지므로 합보다 작거나 같다** | |
| 1.9 | 병합 후 관점 분석의 X축 「배치(회차)」에서 23년이 한 열로 나오는가? | Y — 축 값은 평가의 `batch_id`(`perspective_service.py:2392-2393`) | |
| 1.10 | 연도별 추이 그래프(12_01)는 병합 없이도 연도로 묶여 나오는가? | Y — X축 「평가 연도」가 이미 있고(`perspective_service.py:49`) `evaluation_date` 기준이라 배치와 무관. **병합의 실익은 「배치(회차)」 축과 배치 단위 선택 화면에 한정** | |
| 1.11 | 병합 대상 배치의 욕설 집계(`profanity_employees.batch_id`)도 새 배치로 따라가는가? | Y — 함께 재라벨한다(`deploy_session_service.py:222-231`) | |
| 1.12 | 병합을 되돌리는(분리) 기능도 이번 범위인가? | N — 되돌릴 수 있는 **기록**(`batch_merges` 테이블)만 남기고, 화면 기능은 범위 밖 | |
| 1.13 | 서로 다른 연도의 배치(23년 + 24년)도 병합할 수 있는가? | Y — 막지 않는다. 다만 확인 대화상자에 "서로 다른 연도가 섞여 있습니다" 경고를 띄운다 | |

---

## 1. 배경 및 목적

### 1.1 요청 원문

> 배치 리스트에서 각각의 배치를 합치는 기능이 필요하다. 예를 들어 23년 1차, 23년 2차 배치가 있을 경우 이 둘을 합쳐 23년 통합이라는 배치를 만들 수 있어야 한다. 향후 23·24년 감정어 분석 차트를 만들 때 데이터가 분산되는 것을 막기 위해서다.

### 1.2 실측으로 확인한 현재 상태 — "분산"이 실제로 일어나는 지점

계획을 세우기 전에 "배치가 나뉘어 있으면 정말 차트가 갈라지는가"를 코드로 확인했다. 결과는 **축에 따라 다르다**.

| 축(X축) | 정의 위치 | 배치가 2개면? |
|---------|-----------|---------------|
| 평가 연도 | `perspective_service.py:49` `evaluation_date__year` | **갈리지 않음** — `evaluation_date` 기준이라 배치와 무관 |
| 평가 월/일자 | `perspective_service.py:50,52` | 갈리지 않음 |
| 배치(회차) | `perspective_service.py:52` `'batch_id'` → 축 값은 `ev.get('batch_id')` (`:2392-2393`) | **갈림** — 23년 1차·2차가 별도 열이 된다 |

즉 연도별 추이 그래프(12_01, `aggregate_sentiment_trend` `perspective_service.py:3498`)는 연도 축을 쓰므로 병합 없이도 연도로 묶인다. **병합이 실제로 필요한 곳은 아래 두 가지**이며, 이것이 이 계획의 목적이다.

1. 관점 분석 매트릭스에서 X축을 「배치(회차)」로 놓을 때 같은 해가 여러 열로 갈리는 문제.
2. 배치를 단위로 고르는 화면 — 워드클라우드 배치 트리(`web/templates/wordcloud.html:674`), 배치 리스트(`admin_batch_management.html`) — 에서 "23년 전체"를 한 번에 다룰 수 없는 문제.

> ⚠️ 1.10 원자 질문으로 사용자 확인을 받는다. 만약 사용자가 겪은 분산이 **연도 축에서** 발생했다면 원인이 다른 곳(예: `evaluation_date` 값 불량)이므로 이 계획이 아니라 버그 계획서가 필요하다.

### 1.3 목적

배치 리스트에서 2개 이상의 배치를 선택해 하나의 통합 배치로 합치고, 통합 배치에 사용자가 지정한 이름(예: `23년 통합`)을 붙인다. 평가 데이터는 삭제·복사하지 않고 소속만 바꾼다.

---

## 2. 현재 시스템 분석 (전부 실측)

### 2.1 배치 목록 — 공급자 1개, 소비자 2개

| 구분 | 위치 | 내용 |
|------|------|------|
| API | `src/routes/perspective_routes.py:1055` `GET /api/perspective/batches` | 관리자 가드(`_is_admin()`) 후 `load_batch_history()` 호출 |
| 서비스 | `src/services/perspective_service.py:1801` `load_batch_history()` | `batch_info` 카운트 + `_load_batch_list()` |
| 목록 로더 | `src/services/perspective_service.py:1649` `_load_batch_list()` | **작업서(`batch_work_orders`) 레지스트리 기준**. 작업서에 없는 레거시 배치는 `evaluations` 집계로 보강 |
| 소비 화면 A | `web/templates/admin_batch_management.html` (라우트 `src/routes/admin_routes.py:56` `/admin/batch-management`, 좌측 메뉴 `base.html:202` 「📝 배치 관리」) | 배치 ID·생성일·직원수·평가수 + 삭제 버튼 |
| 소비 화면 B | `web/templates/perspective_test.html:357-367` + JS `:3431` `loadBatchHistory()` | 명칭(✏️ 편집)·배치 ID·생성일·직원·평가 + 삭제 버튼 |

별도 계통으로 `GET /get_batch_list`(`src/routes/ui_routes.py:81`)가 있고 이는 `integrated_data_service.get_batch_list()`(`:93`)로 **물리 폴더 `processed_data/batch/batch_*`를 스캔**한다. 워드클라우드 화면의 배치 트리(`wordcloud.html:674`)가 이 API를 쓴다. 또 `batch_manager.get_batch_list()`(`:18`)는 DB `evaluations` 집계 기반이다. **배치 목록 로더가 3종 병존**하므로 병합 후 표시가 화면마다 달라지지 않도록 §5 영향도에서 전부 점검한다.

### 2.2 기존 배치 단위 조작 API (병합 구현의 본보기)

| 기능 | 위치 | 동작 |
|------|------|------|
| 삭제 | `perspective_routes.py:1071` `DELETE /api/perspective/batch/<batch_id>` | ① `get_work_order_by_batch_id` 로 존재 확인 → ② `remove_batch_from_all(batch_id, [])` (evaluations DELETE + 욕설 DELETE) → ③ `delete_work_order` → ④ 물리 폴더 `rmtree` → ⑤ `log_action('batch_delete', ...)` |
| 명칭 변경 | `perspective_routes.py:1108` `PATCH /api/perspective/batch/<batch_id>/display-name` | `processed_data/batch/<batch_id>/tdata/batch_summary.json` 의 `batch_info.display_name` 에 기록. 파일이 없으면 만든다 |

명칭 표시 규칙: `_batch_display_name()`(`perspective_service.py:1636`)이 `tdata/batch_summary.json` 을 읽는다. 반면 `integrated_data_service.get_batch_list()`(`:104`)는 **`tmeta/batch_summary.json`** 을 읽는다 — 두 경로가 다르다(실측). 통합 배치는 양쪽 모두에 대응해야 화면 간 이름이 갈리지 않는다.

### 2.3 DB 구조 (`.sessions/deploy_sessions.db`, 스키마 정의 `src/services/deploy_session_service.py`)

```
evaluations (:80)
    id INTEGER PK AUTOINCREMENT, employee_id, evaluator_id, evaluation_date,
    batch_id TEXT, data TEXT, fingerprint TEXT, created_at, sentiment_corrections
    INDEX idx_ev_batch (batch_id)                       -- :91
    UNIQUE INDEX idx_ev_fp (employee_id, fingerprint)   -- :171 (스키마 v3)

batch_work_orders (:96)
    batch_id TEXT UNIQUE NOT NULL, batch_dir, status TEXT DEFAULT 'running',
    settings, file_info, total_employees, processed_employees,
    success_count, error_count, total_rows, completed_employees,
    created_at, updated_at, completed_at

batch_work_order_items (:117)
    batch_id TEXT, employee_id TEXT, PRIMARY KEY (batch_id, employee_id)

profanity_employees (:222)
    batch_id TEXT NOT NULL, employee_id, profanity_count, profanity_words
    INDEX idx_pe_batch (batch_id)

acquired_sentences (:193)
    source_batch_id TEXT DEFAULT ''  (학습 문장 적립 — 출처 표기용)
```

**핵심 실측 2가지**

- `idx_ev_fp` 는 스키마 v3에서 `(employee_id, batch_id, fingerprint)` → `(employee_id, fingerprint)` 로 축소됐다(`:158-179`). 주석 원문: *"동일 직원의 동일 평가가 배치가 달라도 중복 저장되지 않도록"*. 따라서 **서로 다른 배치에 같은 평가가 들어 있을 수 없다** → 병합 시 중복 합산 문제도, UNIQUE 충돌도 발생하지 않는다.
- 같은 이유로 **평가 행을 새 배치로 복제하는 방식(원본 유지 + 사본 생성)은 물리적으로 불가능**하다. UNIQUE 위반으로 INSERT가 막힌다.

현재 스키마 버전은 8까지 적용돼 있다(`deploy_session_service.py:143~277`, `if current < 8`).

### 2.4 작업서 서비스 (`src/services/batch_work_order_service.py`, 206줄)

`create_work_order(batch_id, batch_dir, settings, file_info, total_employees=0)` `:30` / `update_work_order_progress` `:70` / `add_completed_employees` `:92` / `get_completed_employee_ids` `:110` / `complete_work_order` `:123` / `fail_work_order` `:139` / `delete_work_order` `:154` / `get_all_work_orders(limit=20)` `:166` / `get_latest_incomplete_work_order` `:180` / `get_work_order_by_batch_id` `:198`.

**병합 상태를 표현할 함수는 없다 — 신규 필요.** `status` 컬럼은 TEXT이고 CHECK 제약이 없으므로 `'merged'` 값을 넣는 데 스키마 변경은 필요 없다.

---

## 3. 결정 필요 사항 (채택안 제시)

| # | 결정 | 선택지 | 채택안과 근거 |
|---|------|--------|---------------|
| D-1 | 병합 방식 | (A) 재라벨: 원본 평가의 `batch_id` 를 새 배치로 변경 / (B) 표시 전용 가상 그룹: 데이터는 그대로 두고 목록·축에서만 묶음 / (C) 복제 | **A 채택.** C는 `idx_ev_fp` UNIQUE 위반으로 불가(실측). B는 DB 변경이 없어 안전하지만 축 값(`ev['batch_id']`)·배치 단위 화면 3종·판정 패킷 등 소비처마다 그룹 해석 로직을 심어야 해 침범 범위가 오히려 넓다. A는 **UPDATE 한 문장**으로 끝나고 모든 소비처가 자동으로 통합 배치를 본다 |
| D-2 | 통합 배치 ID 형식 | (A) `batch_YYYYMMDD_NN` (기존 형식 유지) / (B) `merge_YYYYMMDD_NN` (병합본임을 ID로 구분) | **A 채택.** B를 쓰면 `integrated_data_service.get_batch_list():103` 의 `item.startswith('batch_')` 필터에 걸려 **워드클라우드 배치 트리에서 통합 배치가 보이지 않는다**(실측). 병합본 구분은 ID가 아니라 `batch_merges` 테이블과 작업서 `status` 로 한다 |
| D-3 | 원본 배치의 사후 처리 | (A) 목록에서 숨김(작업서 `status='merged'`) / (B) 목록에 남기고 「병합됨」 배지 / (C) 작업서까지 삭제 | **A 채택.** 사용자 요구가 "합쳐서 하나로 보이게"이므로 숨김이 자연스럽다. C는 되돌릴 근거가 사라져 기각 |
| D-4 | 병합 이력 보존 | (A) `batch_merges` 테이블 신설 / (B) 로그(`log_action`)만 | **A 채택.** B만으로는 역이관 대상 행을 특정할 수 없다. A는 스키마 v9 1회 추가로 끝난다 |
| D-5 | 물리 폴더 | (A) 통합 배치 폴더를 새로 만들고 `tdata`·`tmeta` 양쪽에 `batch_summary.json` 기록, 원본 폴더는 그대로 둠 / (B) 원본 폴더를 통째로 이동·병합 | **A 채택.** B는 되돌리기 불가 + 대용량 파일 이동 리스크. A는 이름 표시만 새 폴더에서 읽으면 되고 원본은 무손상 |
| D-6 | 서로 다른 연도 배치의 병합 | (A) 허용 + 경고 / (B) 차단 | **A 채택.** "23·24년을 한 배치로 보고 싶다"는 요구가 나중에 생길 수 있으므로 정책으로 막지 않고, 확인 대화상자에서 고지만 한다 |

---

## 4. 구현 상세

### 4.1 DB 마이그레이션 (스키마 v9)

`src/services/deploy_session_service.py` `_apply_schema_migrations()` 끝(현재 `if current < 8` 다음)에 v9 블록을 추가한다. 기존 블록의 형식을 그대로 따른다.

```sql
CREATE TABLE IF NOT EXISTS batch_merges (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    merged_batch_id  TEXT NOT NULL,          -- 통합 배치 ID
    source_batch_id  TEXT NOT NULL,          -- 원본 배치 ID
    moved_count      INTEGER DEFAULT 0,      -- 이 원본에서 옮겨간 평가 행 수
    source_status    TEXT DEFAULT '',        -- 병합 직전 작업서 status (복구용)
    created_at       TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_bm_merged ON batch_merges (merged_batch_id);
CREATE INDEX IF NOT EXISTS idx_bm_source ON batch_merges (source_batch_id);
```

`evaluations`·`batch_work_orders` 는 **컬럼 변경 없음**(기존 데이터 무영향).

### 4.2 백엔드 — 서비스 계층 (신규 파일)

`src/services/batch_merge_service.py` (신규)

```python
def merge_batches(source_batch_ids, display_name='', new_batch_id=None):
    """복수 배치를 하나의 통합 배치로 재라벨한다.

    반환: {'success': bool, 'batch_id': str, 'moved': int,
           'employee_count': int, 'total_evaluations': int, 'sources': [...]}
    """
```

동작 순서 (단일 커넥션·단일 트랜잭션):

| 순서 | 처리 | 근거/주의 |
|------|------|-----------|
| 1 | 입력 검증: 2개 미만이면 400, 존재하지 않는 배치가 섞이면 404 | 존재 판정은 `get_work_order_by_batch_id` **또는** `evaluations` 집계 — 작업서 없는 레거시 배치도 대상이 되어야 하므로 둘 중 하나라도 있으면 존재로 본다(`_load_batch_list` 와 동일 기준) |
| 2 | 새 배치 ID 생성: `batch_YYYYMMDD_NN` — 당일 `NN` 은 기존 최대값+1 (`batch_work_orders` + `evaluations` 양쪽 조회) | D-2 |
| 3 | `UPDATE evaluations SET batch_id=? WHERE batch_id IN (...)` — 원본별 `changes()` 를 따로 얻기 위해 원본 1개씩 UPDATE | `idx_ev_batch` 사용 → 배치당 O(선택 행수). 1.9만 명 규모에서도 인덱스 조회 (DL-3) |
| 4 | `INSERT OR IGNORE INTO batch_work_order_items (batch_id, employee_id) SELECT ?, employee_id FROM batch_work_order_items WHERE batch_id IN (...)` 후 원본 행 DELETE | PK가 (batch_id, employee_id)라 중복 직원은 `OR IGNORE` 로 흡수 |
| 5 | `UPDATE profanity_employees SET batch_id=? WHERE batch_id IN (...)` | `idx_pe_batch` 사용. `profanity_sentences` 는 FK로 딸려오므로 무변경 |
| 6 | `UPDATE acquired_sentences SET source_batch_id=? WHERE source_batch_id IN (...)` | 출처 표기 일관성. **학습 라벨 값은 건드리지 않는다** |
| 7 | 통합 작업서 생성: `create_work_order(new_batch_id, batch_dir, settings, file_info, total_employees)` 후 집계값(`success_count`·`total_rows`) 을 병합 결과로 갱신 | 목록이 작업서 기준이므로 필수(`_load_batch_list`) |
| 8 | 원본 작업서: `UPDATE batch_work_orders SET status='merged', updated_at=... WHERE batch_id IN (...)` | D-3. status는 TEXT·제약 없음(실측) |
| 9 | `batch_merges` 에 원본 1행씩 기록(`moved_count`, `source_status`) | D-4 |
| 10 | 물리 폴더 `processed_data/batch/<new_batch_id>/{tdata,tmeta}/batch_summary.json` 생성 — `batch_info.display_name`, `batch_id`, `unique_employees`, `total_evaluations`, `merged_from` | D-5. `tdata`·`tmeta` **양쪽** (§2.2 경로 불일치 대응) |
| 11 | commit → 실패 시 rollback | |

집계 확정: 통합 후 `SELECT COUNT(DISTINCT employee_id), COUNT(*) FROM evaluations WHERE batch_id=?` 로 실측해 작업서와 응답에 기록한다(추정 금지).

목록 필터: `_load_batch_list()`(`perspective_service.py:1649`)의 작업서 조회에 `WHERE status != 'merged'` 를 추가한다. 레거시 보강 루프는 `seen` 집합을 쓰므로, **숨긴 원본이 evaluations 보강 경로로 되살아나지 않도록** `seen` 에 merged 배치도 미리 넣는다(원본은 평가 행이 0건이 되지만 방어적으로 처리).

### 4.3 백엔드 — 라우트 계층

`src/routes/perspective_routes.py` 에 추가 (기존 배치 API와 같은 블루프린트·같은 관리자 가드):

```
POST /api/perspective/batches/merge
  body: {"source_batch_ids": ["batch_20260401_1", "batch_20260901_1"],
          "display_name": "23년 통합"}
  200 : {"success": true, "batch_id": "batch_20260813_1", "moved": 1234,
         "employee_count": 980, "total_evaluations": 1234}
  400 : 선택 2개 미만 / 동일 배치 중복
  401 : 관리자 미로그인  (_is_admin() — 기존 패턴)
  404 : 존재하지 않는 배치 포함
  500 : 트랜잭션 실패(rollback 완료)
```

성공 시 `log_action('batch_merge', {...}, request)` 기록 — `batch_delete` 와 동일 형식.

### 4.4 프론트엔드

`web/templates/admin_batch_management.html` (현재 91줄, 인라인 스크립트)

- 표 첫 열에 체크박스 추가, 헤더에 전체선택 체크박스.
- 표 위 버튼 줄에 `[선택 배치 병합]` 버튼 — 선택 2개 미만이면 비활성.
- 클릭 시: 통합 배치 이름 입력(`prompt`, 기존 명칭 편집 UX와 동일) → 확인 대화상자에 **대상 배치 목록·총 평가 건수·"평가 데이터는 삭제되지 않고 소속만 바뀝니다" 문구** 표시 → 서로 다른 연도가 섞였으면 경고 문장 1줄 추가(D-6).
- 진행 중에는 **버튼만 비활성화**하고 진행 문구를 표시한다(전면 차단 오버레이 금지 — 사용자 상시 지시).
- 완료 후 `loadBatches()` 재호출.

`web/templates/perspective_test.html` 「배치 이력」 패널은 이번 범위에서 **버튼을 붙이지 않는다**(원자 질문 1.2). 병합 후 새로고침하면 통합 배치가 그대로 보인다(같은 API 사용).

### 4.5 구현 순서

| 순서 | 작업 내용 | 의존 |
|------|-----------|------|
| 1 | 스키마 v9 (`batch_merges`) 추가 | — |
| 2 | `batch_merge_service.merge_batches()` 구현 | 1 |
| 3 | `_load_batch_list()` 에 `status='merged'` 숨김 반영 | 1 |
| 4 | `POST /api/perspective/batches/merge` 라우트 | 2 |
| 5 | 배치 리스트 화면 체크박스 + 병합 버튼 | 4 |
| 6 | 테스트 스크립트(§7) 작성·실행 | 2,3 |
| 7 | 사용자 실동작 검증 → 상태 Pre-Done → Done | 5,6 |

---

## 5. 영향도 분석

### 5.1 변경 파일

| 파일 | 변경 | 성격 |
|------|------|------|
| `src/services/deploy_session_service.py` | v9 마이그레이션 블록 추가 | 추가 |
| `src/services/batch_merge_service.py` | 신규 | 신규 |
| `src/services/perspective_service.py` `_load_batch_list()` (`:1649`) | 작업서 조회에 merged 제외 조건 | 수정(1개 함수) |
| `src/routes/perspective_routes.py` | 라우트 1개 추가 | 추가 |
| `web/templates/admin_batch_management.html` | 체크박스·병합 버튼·핸들러 | 수정 |

`batch_work_order_service.py` 는 **수정하지 않는다**(병합 전용 UPDATE는 신규 서비스 안에서 수행).

### 5.2 병합 후 표시가 달라지는 지점 (전수 점검 대상)

| 소비처 | 위치 | 예상 동작 | 점검 항목 |
|--------|------|-----------|-----------|
| 배치 리스트 | `admin_batch_management.html` | 통합 배치 1행, 원본 숨김 | 직원수·평가수가 §7 실측과 일치 |
| 배치 이력 패널 | `perspective_test.html:3431` | 동일 | 요약 문구(`n개 배치, n명, n개 평가`) 정합 |
| 관점 분석 X축 「배치(회차)」 | `perspective_service.py:52`, `:2392` | 통합 배치 1열 | 원본 배치 열이 사라졌는지 |
| 워드클라우드 배치 트리 | `wordcloud.html:674` → `/get_batch_list` → `integrated_data_service.py:93` | **물리 폴더 스캔** — 통합 배치 폴더를 §4.2-10에서 만들므로 노출됨. 원본 폴더도 남아 있어 **함께 보인다** | 폴더 기반 목록에서 원본을 숨길지 여부 → 리스크 R-3 |
| 갤러리 | `gallery_entries.batch_title` (`deploy_session_service.py:68`) | `batch_id` 가 아니라 저장 당시 제목 문자열 | 과거 산출물 제목은 바뀌지 않음(정상) |
| 판정 패킷 | `judgment_packet_service` (`perspective_routes.py:748` `build_judgment_packet(batch_id=...)`) | 통합 배치 ID로 조회 가능 | 기존에 뽑아 둔 패킷 파일명은 원본 배치 ID 유지(불변, 정상) |

### 5.3 도메인 잠금 점검 (`.clinerules/projects/wordcloud/domain-locks.md`)

| 잠금 | 판정 |
|------|------|
| DL-1 가명화 범위 | 해당 없음 — 병합은 `batch_id` 만 다루고 `employee_id`(이미 가명) 값을 만들거나 바꾸지 않는다 |
| DL-2 평가 키잉 | **준수** — `evaluation_id` 를 쓰지 않는다. 행 식별은 DB `id`/`batch_id` |
| DL-3 배치 복잡도 | **준수** — 전 구간 인덱스 기반 집합 연산(UPDATE … WHERE batch_id IN). 파이썬 루프로 행을 순회하지 않는다 → O(선택 행수) |
| DL-4 감정 극성 | 해당 없음 — 판정 로직·규칙·모델 무변경. 확인: 변경 파일에 감정 모듈 없음 |
| DL-5 필드 신호 보존 | 해당 없음 — `evaluations.data` blob 무변경 |
| DL-6 날짜/수치 타입 | **주의** — 새 배치 ID의 날짜부와 `created_at` 만 다루고 `evaluation_date` 는 건드리지 않는다(int 저장 이력 있음). 연도 혼합 경고(D-6)는 **배치 ID의 날짜가 아니라 배치명·생성일 기준**임을 UI 문구에 명시 |
| DL-7 학습 데이터 위치 | 해당 없음 |
| DL-8 공통 모듈 침범 | `_load_batch_list` 1개 함수만 수정. 호출처: `load_all_batches`(`:1796`)·`load_batch_history`(`:1830`) 2곳 — 둘 다 목록 표시 경로라 영향 동일 |
| DL-9 원데이터 취급 | 해당 없음 — 새로 만드는 `batch_summary.json` 에 직원 식별 정보를 쓰지 않는다(집계 수치·이름·ID 목록만) |
| DL-10 완료 판정 | 실동작 검증 전 `Done` 금지 → §7 |
| DL-11 저장 규약 | 준수(본 문서 경로·`_index.md` 갱신) |
| DL-12 서버 무단 기동 | **준수** — §7 검증은 임시 DB 대상 독립 스크립트. 서버 실행은 사용자 승인 후 사용자가 수행 |

---

## 6. 마이그레이션·복구 (E 유형 필수 섹션)

- **이전 호환**: `batch_merges` 는 신규 테이블이라 기존 코드 경로가 참조하지 않는다. v9 미적용 DB에 새 코드가 붙으면 `_init_db()`→`_apply_schema_migrations()` 가 기동 시 자동 생성한다(기존 v2~v8과 동일 방식).
- **역방향(구 코드 + v9 DB)**: 구 코드는 `batch_merges` 를 모르고 `status='merged'` 도 모르므로 **원본 배치가 목록에 다시 보인다**(데이터 손상 없음).
- **되돌리기(수동)**: `batch_merges` 에서 `merged_batch_id` 로 원본 목록을 얻어
  1) `UPDATE evaluations SET batch_id=source_batch_id WHERE batch_id=merged_batch_id AND ...` — 단 어느 행이 어느 원본에서 왔는지는 `moved_count` 만으로 특정되지 않는다. **행 단위 복구가 필요하면 `batch_merges` 에 `evaluation_ids` 를 JSON으로 저장해야 한다** → 리스크 R-1.
  2) 원본 작업서 `status` 를 `source_status` 로 복원, 통합 작업서 삭제.
- **백업**: 병합 실행 전 `.sessions/deploy_sessions.db` 를 `.sessions/backup/deploy_sessions_YYYYMMDD_HHMM.db` 로 복사하는 단계를 서비스 진입부에 넣는다(`18-backup-before-modify.md`).

---

## 7. 테스트/검증 계획

`test/` 폴더: `plans/2026/08/13_01_batch-merge/test/`

| # | 시나리오 | 방법 | 기대 |
|---|----------|------|------|
| T1 | 스키마 v9 적용 | 임시 sqlite 파일에 `_init_db()`+마이그레이션 실행 | `batch_merges` 테이블·인덱스 2개 생성, `schema_version` 최대값 9 |
| T2 | 2개 배치 병합 — 평가 보존 | 임시 DB에 A(3직원 5평가)·B(2직원 3평가) 구성 후 `merge_batches(['A','B'], '23년 통합')` | 통합 배치 평가 8건, 원본 배치 평가 0건, **총 행수 8로 불변**(삭제·복제 없음) |
| T3 | 직원 중복 흡수 | A·B에 동일 employee_id 1명 포함 | 통합 배치 `COUNT(DISTINCT employee_id)` = 4 (3+2−1) |
| T4 | 작업서 items 병합 | A·B의 `batch_work_order_items` 에 겹치는 직원 포함 | PK 충돌 없이 통합 배치로 이동, 원본 행 0 |
| T5 | 욕설·적립 문장 동반 이동 | `profanity_employees`·`acquired_sentences` 에 원본 배치 행 삽입 | 전부 통합 배치 ID로 갱신, 누락 0 |
| T6 | 목록에서 원본 숨김 | 병합 후 `_load_batch_list()` 호출 | 통합 배치 1건만, 원본 2건 미노출 |
| T7 | 실패 시 롤백 | 5단계에서 강제 예외 주입 | 모든 테이블이 병합 전 상태와 동일(행수·batch_id 분포 대조) |
| T8 | 배치 ID 형식 호환 | 생성된 ID를 `integrated_data_service.get_batch_list()` 의 파싱 로직에 통과 | `batch_` prefix 필터 통과, `split('_')[2]` int 변환 예외 없음 |
| T9 | 입력 검증 | 1개 선택 / 없는 배치 / 같은 배치 2번 | 각각 400·404·400 |

**실동작 검증(사용자 승인 후, 사용자가 서버 기동)**

1. `/admin/batch-management` 에서 배치 2개 선택 → 병합 → 목록에 `23년 통합` 1행.
2. 관점 분석에서 X축 「배치(회차)」 선택 → 통합 배치 1열 확인.
3. 병합 전후 총 평가 건수(`배치 이력` 요약 문구)가 동일한지 대조.
4. 워드클라우드 배치 트리에서 통합 배치가 보이는지 확인(R-3 판단 자료).

위 4항 통과 전에는 상태를 `Done` 으로 올리지 않는다(DL-10).

---

## 8. 리스크 및 제약

| # | 리스크 | 영향 | 대응 |
|---|--------|------|------|
| R-1 | 되돌리기 정밀도 — `moved_count` 만으로는 어느 평가가 어느 원본이었는지 특정 불가 | 병합 취소 시 원상복구 불완전 | `batch_merges.evaluation_ids`(JSON 배열) 컬럼을 함께 넣을지 D-4 재확인. 1.9만 규모에서 배치당 수만 개 id → 텍스트 수 MB. **대안: `evaluations` 에 `orig_batch_id` 컬럼 추가**(행당 1값, 검색 불필요) — 구현 시 이 안을 우선 검토 |
| R-2 | 병합 중 다른 배치 작업이 동시 진행 | UPDATE 경합 | SQLite WAL + 단일 트랜잭션. 진행 중 배치가 있으면(`get_latest_incomplete_work_order()`) 병합을 거부하고 안내 |
| R-3 | 물리 폴더 기반 목록(`/get_batch_list`)에는 원본 폴더가 계속 보임 | 워드클라우드 배치 트리에 통합본과 원본이 동시 노출 | 실동작 검증 4항에서 확인 후, 필요하면 후속 계획서에서 폴더 목록에도 merged 필터 적용(이번 범위 밖) |
| R-4 | 대량 UPDATE 시간 | 수만 행 UPDATE 지연 | 인덱스 기반이라 O(선택 행수). 실측 시간을 결과에 기록 |
| R-5 | 사용자가 겪은 "분산"이 연도 축에서 발생한 것이라면 이 계획은 해법이 아님 | 헛작업 | 원자 질문 1.10 으로 착수 전 확인 |
| R-6 | 병합 대상에 진행 중(`status='running'`) 작업서 포함 | 진행 중 배치의 소속이 바뀌어 Resume 실패 | 입력 검증에서 `status='running'` 배치는 거부 |

**제약**

- 병합 취소(분리) 화면 기능은 범위 밖(원자 질문 1.12).
- 3개 이상 배치 동시 병합은 허용하되, 1차 검증은 2개 기준으로 수행한다.
- 감정 판정·규칙·모델은 이 작업에서 일절 수정하지 않는다.
