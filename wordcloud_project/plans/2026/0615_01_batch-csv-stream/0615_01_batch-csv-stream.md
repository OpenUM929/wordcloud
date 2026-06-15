# 배치 처리 CSV 스트리밍 + Staging DB + 라인/직원 2단계 진행 표시

> 상태: PND | 작성일: 2026-06-15

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-15 | 전체 | 초안: 청크→`employee_buffer`(RAM) 누적 방식 |
| 2026-06-15 | 전체 | **개정: RAM 누적은 메모리를 줄이지 못함(섞인 직원 데이터가 전부 RAM 상주). Phase 1에서 원문을 per-batch staging SQLite로 스트리밍하고 Phase 2에서 직원별 재조회 분석하는 Option B로 재설계. 초안 검토 결함 C1~C5, M1 반영** |

---

## 1. 배경 및 목적

### 문제

현재 배치 처리(`batch_processor.py`)는 CSV를 **전체 메모리에 로드**한 뒤 처리한다.

```python
# :436~442 — 청크로 읽지만 결국 concat으로 전부 합침
chunks = []
for chunk in pd.read_csv(csv_file_path, chunksize=chunk_size):
    chunks.append(chunk)
df = pd.concat(processed_chunks, ignore_index=True)   # 전체 RAM

# :480 — 전체 df를 iterrows로 순회 (pandas 최악의 방식)
grouped_data = group_data_by_employee(df, target_id_column, mappings)
```

피크 시점에 `df`(전체) + `grouped_data`(전체 복사본)가 **동시에 RAM**에 존재한다. 데이터는 약 40만 라인.

### 초안(RAM 누적)이 기각된 이유

청크를 읽어 `employee_buffer` dict에 누적하는 1차 초안은 메모리를 줄이지 못한다. **라인은 여러 직원이 섞여 있어** 마지막 청크까지 읽어야 각 직원이 완성되므로, Phase 1이 끝나는 시점에 `employee_buffer`가 40만 라인 전체를 RAM에 들고 있게 된다. dict-of-list-of-dict는 필드명이 행마다 반복되어 pandas df보다 오히려 더 무겁다.

### 해결 구조 (Option B)

수집 단계와 분석 단계 사이의 데이터를 **RAM이 아닌 디스크(staging SQLite)** 에 둔다.

```
Phase 1 (수집, 라인 기반 진행)
  CSV 청크 읽기 → 원문 평가를 staging.db에 즉시 INSERT → 청크 메모리 해제
  RAM 상주 = 청크 1개 + INSERT 배치 1개

Phase 2 (분석, 직원 기반 진행)
  staging.db에서 직원 1명씩 SELECT → NLP/감정/통합 분석 → 최종 DB upsert
  RAM 상주 = 직원 1명분 + metadata 1개

종료 시 staging.db 삭제
```

### 목표

1. **메모리**: 피크를 (전체 df + 전체 grouped) → (청크 1개 / 직원 1명분)으로 감소
2. **속도**: `iterrows()` → `groupby()`, 중복 `concat` 제거
3. **진행 표시 Phase 1**: `데이터 수집 중 (약 N / 400,000 라인)` (0~40%)
4. **진행 표시 Phase 2**: `분석 처리 중 (N / M명)` (45~90%)

---

## 2. 현재 코드 분석 (검증 완료)

### 2.1 batch_processor.py — `df` 참조 전수 (grep 확인)

| 라인 | 코드 | Option B 처리 |
|------|------|--------------|
| `:90~133` | `group_data_by_employee(df, ...)` 정의 (iterrows) | **삭제**, 청크 추출 함수로 대체 |
| `:104` | `for _, row in df.iterrows()` | 제거 |
| `:137,149` | `process_employee_metadata(..., df)` 시그니처/docstring | `df` 파라미터 **제거** |
| `:163~167` | `metadata[...] = df.iloc[0].get(mappings[...])` | `evaluations[0].get('field')`로 교체 |
| `:420,442,444,446` | `df = pd.concat/read_csv/read_excel` | Phase 1 스트리밍으로 교체 |
| `:480` | `grouped_data = group_data_by_employee(df, ...)` | 제거 (staging으로 대체) |
| `:604` | `process_single_employee` → `process_employee_metadata(..., df)` | 인자에서 `df` 제거 |
| `:662` | `update_work_order_progress(total_rows=len(df))` | `_ingested_rows` 카운터 사용 |
| `:786` | `batch_processing_state['total_rows'] = len(df)` | `_ingested_rows` 사용 |

### 2.2 batch_processor.py — progress/current_step 할당 전수 (grep 확인)

| 라인 | 현재 값 | Option B 재배치 |
|------|--------|----------------|
| `:451` | progress=5 (파일 로드 후) | Phase 1 시작 (5) |
| `:715` | `int(10 + (completed/total)*40)` | `int(45 + (completed/total)*45)` |
| `:738` | progress=50, step=2 | progress=90, step=2 |
| `:776` | progress=60, step=3 | progress=92, step=3 |
| `:789` | progress=100, step=4 | progress=100, step=4 |
| `:568,579,583,588,591,592` | Stage2 init step=1, progress=10 | step=1, progress=40~45 |

> **검토 결함 M1 해결**: 초안은 루프를 40~90으로 두면서 `:738=50`, `:776=60`을 방치해 `90→50→60` 역행이 발생했다. 위 표로 전 구간을 단조 증가하도록 재정의한다.

### 2.3 가명화 로직 (`:482~512`, `:607~611`)

- `:482~496`: `forced_pseudo` 6개 필드 강제 + `PseudonymManager` 생성
- `:500~505`: target_employee_id 가명화로 grouped_data re-key
- `:508~512`: 각 evaluation dict에 `apply_pseudonyms_to_dict`
- `:607~611`: process_single_employee에서 metadata의 dept/position **추가 가명화**

> **검토 결함 C2 해결**: Option B는 Phase 1 ingest에서 가명화를 1회만 적용(emp_id + evaluation dict)하고, staging에는 가명화된 원문을 저장한다. metadata dept/pos는 `evaluations[0]`(이미 가명화됨)에서 가져오므로 `:607~611` 후처리 가명화는 **삭제**한다 (이중 적용 방지).

### 2.4 SQLite 인프라 (확인 완료)

- 최종 DB: `.sessions/deploy_sessions.db`, WAL, `check_same_thread=False` (`deploy_session_service.py:14~15`)
- `upsert(employee_id, metadata, evaluations, batch_id)` (`user_data_manager.py:44`) — 최종 저장(employees + evaluations 테이블). **변경 없음, Phase 2에서 그대로 호출**
- staging은 **최종 DB와 분리된 per-batch 임시 파일** `batch_dir/staging.db`로 둔다 (스키마 오염·락 경합 방지, 종료 시 삭제)

### 2.5 batch_service.py / batch_events.py / JS

- `batch_processing_state` 딕셔너리(`batch_service.py:22~35`): `total_lines`, `processed_lines` 필드 없음 → 추가
- `process_batch_metadata` 초기화 블록(`:311~328`): 신규 필드 리셋 추가
- `stream_batch_events`(`batch_events.py:23~38`): SSE payload에 `total_lines`, `processed_lines` 추가
- `metadata_batch.js` SSE 핸들러(`:771~860`): `data.status` 우선 표시는 이미 적용됨(`:787`). 라인 기반 progress 수신 로직 추가

---

## 3. 변경 설계 (Option B)

### 3.1 신규 모듈: `batch_staging.py`

per-batch 임시 SQLite를 다루는 헬퍼. (신규 파일 — 현재 코드베이스에 존재하지 않음)

```python
# src/services/batch_staging.py (신규)
import os, json, sqlite3

def open_staging(batch_dir):
    path = os.path.join(batch_dir, 'staging.db')
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS staging (
            employee_id TEXT NOT NULL,
            data        TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_staging_emp ON staging(employee_id)")
    conn.commit()
    return conn

def insert_evaluations(conn, rows):
    """rows: list[(employee_id, json_str)]"""
    conn.executemany("INSERT INTO staging (employee_id, data) VALUES (?, ?)", rows)
    conn.commit()

def distinct_employee_ids(conn):
    return [r[0] for r in conn.execute("SELECT DISTINCT employee_id FROM staging")]

def load_employee_evaluations(conn, employee_id):
    cur = conn.execute("SELECT data FROM staging WHERE employee_id = ?", (employee_id,))
    return [json.loads(r[0]) for r in cur]

def close_and_remove(conn, batch_dir):
    try:
        conn.close()
    finally:
        for suffix in ('', '-wal', '-shm'):
            p = os.path.join(batch_dir, 'staging.db' + suffix)
            if os.path.exists(p):
                try: os.remove(p)
                except OSError: pass
```

### 3.2 청크 → 원문 평가 추출 (groupby, iterrows 대체)

`group_data_by_employee`(`:90~133`)를 삭제하고 청크 단위 추출 함수로 대체.

```python
def _extract_rows_from_chunk(chunk, target_id_column, mappings,
                             _pseudo_mgr, pseudonym_fields):
    """청크 DataFrame → [(pseudo_emp_id, json(evaluation)), ...]"""
    out = []
    for raw_id, group in chunk.groupby(target_id_column):
        emp_id = str(raw_id)
        if _pseudo_mgr and 'target_employee_id' in pseudonym_fields:
            emp_id = _pseudo_mgr.get_pseudonym(emp_id)
        for _, row in group.iterrows():          # 소규모 그룹 내부만 iterrows
            ev = {}
            for field, column in mappings.items():
                if field != 'target_employee_id' and column in row.index:
                    val = row[column]
                    if isinstance(val, str):
                        val = val.strip()
                    ev[field] = val
            # evaluator_id 생성 (현행 :119~121 동일)
            if 'evaluator_id' not in ev and 'evaluation_date' in ev:
                date_str = str(ev.get('evaluation_date', '')).replace('-', '')
                ev['evaluator_id'] = f"eval-{emp_id}-{date_str}"
            # evaluator_hierarchy_level 기본값 (현행 :124~129 동일)
            if 'evaluator_hierarchy_level' not in ev:
                pos = ev.get('evaluator_position', '')
                ev['evaluator_hierarchy_level'] = (
                    'manager' if any(p in pos for p in ['과장','팀장','관리자','总监','manager'])
                    else 'staff'
                )
            # 가명화 1회 적용 (검토 C2: 여기서만, 후처리 삭제)
            if _pseudo_mgr:
                ev = _pseudo_mgr.apply_pseudonyms_to_dict(ev, pseudonym_fields)
            out.append((emp_id, json.dumps(ev, ensure_ascii=False)))
    return out
```

> 주의: `pd.notna` 처리 — 현행 group_data_by_employee는 NaN을 그대로 넣었다. 동작 보존을 위해 동일하게 둔다(필요 시 별도 정제 단계에서 처리).

### 3.3 Phase 1 — 청크 스트리밍 ingest

`process_batch`의 CSV 로드 구간(`:366~480`)을 아래로 교체. (가명화 매니저 준비 `:482~497`는 **이 앞으로 이동**하여 ingest 중 사용)

```python
import os, json
from src.services import batch_staging
CHUNK_SIZE = 10_000

# (가명화 매니저 _pseudo_mgr / pseudonym_fields 준비를 여기서 먼저 수행)

staging_conn = batch_staging.open_staging(batch_dir)
emp_id_set = set()          # Phase 2 직원 수 (ID 문자열만, ~수만개 = 경량)
_ingested_rows = 0

# 총량 추정 (검토 C3/C4: 정확한 레코드 수는 임베디드 개행으로 알 수 없음 → 추정)
def _estimate_total(path):
    if os.path.isfile(path) and path.endswith('.csv'):
        size = os.path.getsize(path)
        return size  # 바이트 기준 추정 (첫 청크 후 행당 바이트로 환산)
    return 0

batch_processing_state['current_step'] = 0
batch_processing_state['progress'] = 5
batch_processing_state['status_message'] = '데이터 수집 준비 중...'

def _chunk_iter(path):
    if os.path.isfile(path):
        if path.endswith('.csv'):
            yield from pd.read_csv(path, chunksize=CHUNK_SIZE)
        else:  # Excel: streaming 불가 → 1회 로드 후 슬라이스 (보통 소형)
            xl = pd.read_excel(path)
            for i in range(0, len(xl), CHUNK_SIZE):
                yield xl.iloc[i:i+CHUNK_SIZE]
    else:  # 폴더
        import glob
        files = (glob.glob(os.path.join(path,'*.csv'))
                 + glob.glob(os.path.join(path,'*.xlsx'))
                 + glob.glob(os.path.join(path,'*.xls')))
        for fp in files:
            if fp.endswith('.csv'):
                yield from pd.read_csv(fp, chunksize=CHUNK_SIZE)
            else:
                xl = pd.read_excel(fp)
                for i in range(0, len(xl), CHUNK_SIZE):
                    yield xl.iloc[i:i+CHUNK_SIZE]

_total_bytes = _estimate_total(csv_file_path)
_bytes_per_row = None

for chunk in _chunk_iter(csv_file_path):
    rows = _extract_rows_from_chunk(chunk, target_id_column, mappings,
                                    _pseudo_mgr, pseudonym_fields)
    if rows:
        batch_staging.insert_evaluations(staging_conn, rows)
        for emp_id, _ in rows:
            emp_id_set.add(emp_id)
    _ingested_rows += len(chunk)

    # 진행률 추정 (CSV: 바이트 기반, Excel/폴더: 단순 카운트 표시)
    if _total_bytes and _bytes_per_row is None and _ingested_rows:
        _bytes_per_row = max(_total_bytes / max(_ingested_rows, 1), 1)
    if _total_bytes and _bytes_per_row:
        est_total = int(_total_bytes / _bytes_per_row)
        batch_processing_state['total_lines'] = est_total
        pct = min(_ingested_rows / max(est_total, 1), 1.0)
        batch_processing_state['progress'] = int(5 + pct * 35)
        batch_processing_state['status_message'] = (
            f'데이터 수집 중 (약 {_ingested_rows:,} / {est_total:,} 라인)'
        )
    else:
        batch_processing_state['status_message'] = f'데이터 수집 중 ({_ingested_rows:,} 라인)'
    batch_processing_state['processed_lines'] = _ingested_rows

batch_processing_state['progress'] = 40
batch_processing_state['total_lines'] = _ingested_rows   # 완료 시 실제값 확정
batch_processing_state['status_message'] = f'데이터 수집 완료: {len(emp_id_set):,}명'
```

> **검토 C3/C4 해결**: 정확한 레코드 수는 임베디드 개행 때문에 사전 카운트가 불가·부정확하고 파일 2회 읽기 비용도 크다. 따라서 **바이트 기반 추정**으로 표시하고("약 N / 추정 M"), 완료 시 `total_lines`를 실제 ingest 수로 확정한다. Excel/폴더는 카운트만 표시.

### 3.4 Phase 2 — staging에서 직원별 분석

기존 `process_single_employee` + ThreadPoolExecutor 루프(`:596~738`)를 staging 조회 기반으로 변경.

```python
employee_ids = sorted(emp_id_set)

# Resume: 완료된 직원 제외 (검토 §8.2 — 현행 :640~643과 동일 정책)
if _is_resume and prior_completed:
    employee_ids = [e for e in employee_ids if str(e) not in prior_completed]

total_employee_count = len(employee_ids)

def process_single_employee(emp_id):
    # 워커별 staging 읽기 전용 커넥션 (WAL 동시 읽기 안전)
    conn = batch_staging.open_staging(batch_dir)
    try:
        evaluations = batch_staging.load_employee_evaluations(conn, emp_id)
    finally:
        conn.close()
    metadata, success, error, _ = process_employee_metadata(
        metadata_manager, emp_id, evaluations, batch_dir,
        data.get('target_employee_department', '생산부'),
        data.get('target_employee_position', '사원'),
        mappings           # df 인자 제거 (검토 C5)
    )
    # ... (성공 시 upsert, profanity, employee_results append — 현행 :680~711 유지)
```

`process_employee_metadata` 내부(`:163~167`)는 `df` 대신 `evaluations[0]` 사용:

```python
if evaluations and 'target_employee_department' in evaluations[0]:
    metadata['target_employee_department'] = evaluations[0].get('target_employee_department', '생산부')
if evaluations and 'target_employee_position' in evaluations[0]:
    metadata['target_employee_position'] = evaluations[0].get('target_employee_position', '사원')
```

> **부수 효과(긍정)**: 현행은 `df.iloc[0]`(전체 첫 행)을 모든 직원에 적용하는 잠재 버그였다. `evaluations[0]`로 바꾸면 **직원별 정확한 값**으로 교정된다. (가명화는 §3.2에서 이미 적용됨 → `:607~611` 후처리 삭제)

Phase 2 progress (검토 M1):
```python
batch_processing_state['progress'] = int(45 + (completed / max(total_employee_count,1)) * 45)
batch_processing_state['status_message'] = f'분석 처리 중 ({completed:,} / {total_employee_count:,}명)'
```

### 3.5 종료 처리

`process_batch` 반환 직전(현행 `:804~812` 작업서 완료 처리 부근)에 staging 정리:

```python
batch_staging.close_and_remove(staging_conn, batch_dir)
```

`len(df)` 참조였던 `:662`, `:786`는 `_ingested_rows`로 교체.

---

## 4. 변경 파일 목록

### 4.1 `src/services/batch_staging.py` (신규)
- §3.1 헬퍼 모듈 신규 작성

### 4.2 `src/services/batch_processor.py`
| 위치 | 변경 |
|------|------|
| `:90~133` | `group_data_by_employee` 삭제 → `_extract_rows_from_chunk` 신규 |
| `:137,149,604` | `process_employee_metadata` / 호출부에서 `df` 파라미터 제거 |
| `:163~167` | `df.iloc[0]` → `evaluations[0]` |
| `:366~480` | CSV 로드 + grouped 생성 → Phase 1 staging ingest |
| `:482~512` | 가명화 매니저 준비를 ingest 앞으로 이동, re-key/dict 루프 삭제(ingest에 통합) |
| `:596~738` | Phase 2 staging 조회 기반 루프로 변경, progress 45~90 |
| `:607~611` | metadata dept/pos 후처리 가명화 **삭제** (이중 적용 방지) |
| `:662,786` | `len(df)` → `_ingested_rows` |
| `:738,776,789` | progress 90/92/100 재배치 |
| 반환 직전 | `batch_staging.close_and_remove` 호출 |

### 4.3 `src/services/batch_service.py`
| 위치 | 변경 |
|------|------|
| `:22~35` | state에 `total_lines:0`, `processed_lines:0` 추가 |
| `:311~328` | 초기화 블록에 두 필드 리셋 추가 |

### 4.4 `src/services/batch_events.py`
| 위치 | 변경 |
|------|------|
| `:23~38` | SSE payload에 `total_lines`, `processed_lines` 추가 |

### 4.5 `web/static/js/metadata_batch.js`
| 위치 | 변경 |
|------|------|
| `:776~808` | `data.total_lines`/`data.processed_lines` 수신 시 Phase 1 progress 보조 표시 |

### 4.6 `web/templates/metadata_batch.html` (선택)
| 위치 | 변경 |
|------|------|
| `:363~366` | proc-step "파일 로드" → "데이터 수집" 라벨 |

---

## 5. SSE payload 변경

```json
// 변경 후
{
  "step": 0,
  "progress": 22,
  "status": "데이터 수집 중 (약 100,000 / 400,000 라인)",
  "total_lines": 400000,
  "processed_lines": 100000,
  "unique_employees": 0,
  ...
}
```

---

## 6. 메모리/속도 효과 (정량 예상)

| 항목 | 현재 | Option B |
|------|------|----------|
| Phase 1 피크 RAM | 전체 df + 전체 grouped | 청크 1개(1만 행) + INSERT 배치 + emp_id set |
| Phase 2 피크 RAM | (동일 grouped 상주) | 직원 1명분 evals + metadata |
| 그룹핑 | 40만 행 `iterrows()` | 청크별 `groupby` |
| 파일 읽기 | 청크 후 concat(중복) | 청크 1패스 |
| 추가 비용 | — | staging DB write 40만 행 + Phase 2 직원당 SELECT |

> 트레이드오프: staging write/read I/O가 늘지만, executemany 배치 + WAL + 인덱스로 흡수. 40만 행 규모에서 RAM 수 GB 절감이 I/O 증가분보다 우선한다(=둘 다 필요 판단).

---

## 7. 구현 순서

1. `batch_staging.py` 신규 작성 + 단독 단위테스트(insert/select/distinct/remove)
2. `batch_service.py` state 필드 + 초기화
3. `batch_events.py` SSE payload 필드
4. `batch_processor.py`
   - 4-1. `_extract_rows_from_chunk` 작성, `group_data_by_employee` 제거
   - 4-2. 가명화 매니저 준비 위치 이동
   - 4-3. Phase 1 ingest 루프
   - 4-4. Phase 2 staging 조회 루프 + progress 재배치
   - 4-5. `process_employee_metadata` df 제거 + `evaluations[0]` 적용, `:607~611` 삭제
   - 4-6. `len(df)`→`_ingested_rows`, staging 정리 호출
5. `metadata_batch.js` 라인 진행 표시
6. `metadata_batch.html` 라벨(선택)

---

## 8. 주의사항 및 제약

### 8.1 staging 동시 읽기
Phase 2 ThreadPoolExecutor 워커가 각자 `open_staging`으로 읽기 커넥션을 연다. WAL 모드에서 다중 읽기는 안전. 쓰기는 Phase 1에서 단일 스레드로 완료된 상태.

### 8.2 Resume 호환
Resume 시 staging.db는 직전 실행에서 삭제되었을 수 있으므로 **Phase 1 ingest를 다시 수행**(원본/`original.csv`에서)하고, Phase 2에서 `prior_completed`(작업서 items 테이블)로 완료 직원을 제외한다. ingest는 분석 대비 저비용이라 재수행 허용.

### 8.3 retry-failed 경로
`batch_service.retry_failed_employees`(`:463~`)도 `process_batch`를 호출한다. Option B 진입 시 동일하게 staging을 거치며 정상 동작해야 함 → 테스트 항목 포함.

### 8.4 NaN/타입 보존
`_extract_rows_from_chunk`는 현행 group_data_by_employee의 값 처리(문자열 strip, NaN 그대로)를 보존. json 직렬화 시 NaN은 `null`로 저장되므로 Phase 2 로드 시 None — 현행 분석 모듈이 None/빈문자 허용하는지 확인 필요.

### 8.5 staging 디스크 사용량
40만 행 원문 JSON ≈ 수백 MB 임시 디스크. `batch_dir` 동일 볼륨 여유 확인. 종료/실패 시 `close_and_remove`로 정리(실패 경로 `_run_batch_process` except 블록에도 정리 추가 검토).

---

## 9. 테스트 계획

| 항목 | 검증 |
|------|------|
| 40만 라인 CSV 피크 메모리 | 처리 중 프로세스 RSS 측정, 현재 대비 감소 확인 |
| staging 생성/삭제 | 처리 후 `batch_dir/staging.db` 잔존 없음 |
| Phase 1 진행 표시 | "데이터 수집 중 (약 N / M 라인)" 갱신 |
| Phase 2 진행 표시 | "분석 처리 중 (N / M명)" 갱신, progress 단조 증가(45→90→100) |
| 가명화 1회 적용 | 결과 dept/pos가 이중 가명화 아님 확인 |
| 직원별 dept 정확성 | 서로 다른 부서 직원이 각자 값 갖는지(기존 df.iloc[0] 버그 교정 확인) |
| Resume | 중단 후 재개 시 완료 직원 skip, 중복 없음 |
| retry-failed | 실패 건 재배치 정상 |
| 폴더/Excel 입력 | 다중 CSV·xlsx 정상 |
| 소규모(<100행) | 정상 처리, progress 정상 종료 |

---

## 10. 미해결/결정 필요

- **staging 위치**: `batch_dir/staging.db`(권장) vs 메인 DB 내 임시 테이블. 권장은 per-batch 파일(오염·락 회피).
- **진행률 정확도**: CSV는 바이트 기반 추정(±오차). 정확 표기가 필요하면 ingest 전 1패스 카운트를 옵션으로 추가(파일 2회 읽기 비용 감수).
