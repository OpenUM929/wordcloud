# 배치 처리 CSV 스트리밍 + Staging DB + 라인/직원 2단계 진행 표시

> 상태: DONE | 작성일: 2026-06-15 | 구현 완료: 2026-06-15

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-15 | 전체 | 초안: 청크→`employee_buffer`(RAM) 누적 방식 |
| 2026-06-15 | 전체 | 개정: RAM 누적은 메모리를 줄이지 못함(섞인 직원 데이터가 전부 RAM 상주). Phase 1에서 원문을 per-batch staging SQLite로 스트리밍하고 Phase 2에서 직원별 재조회 분석하는 Option B로 재설계. 초안 검토 결함 C1~C5, M1 반영 |
| 2026-06-15 | §3.1,§3.3,§3.4,§4,§8 | **2차 검토 반영: ①실패 데이터 저장을 staging 재조회로 교체 ②state 필드 중복 제거(기존 total_rows/processed_rows 재사용, total_lines/processed_lines 폐기) ③Phase 2 워커 커넥션 threading.local 캐싱 ④Resume fallback은 기존 코드에 존재함을 명시** |
| 2026-06-15 | §3.3, §7 | **3차 검토 반영: ①바이트 기반 추정 수학적 오류 수정 → 정확 라인 카운트(1패스)로 회복. ②구현 순서(§7) 불필요 단계 제거(batch_service.py/batch_events.py/metadata_batch.js는 변경 없음)** |
| 2026-06-15 | 구현 | **구현 완료. 추가 처리: ①계획 미기재 `len(grouped_data)` 4곳(작업서 total_employees·worker count·Stage2 실패경로·Stage4 total_employees)을 `len(emp_id_set)`로 일괄 전환. ②Stage2 init progress=10→45로 보정(40→10 역행 방지, 전 구간 5→40→45→90→92→100 단조). ③처리 실패 시 staging 잔존 방지: `_active_staging_dir` state 키 + `batch_staging.remove_staging_files()` 추가하여 `batch_service._run_batch_process` except에서 정리(§4.3·§8.5 '검토' 항목 확정). ④batch_staging/_extract_rows_from_chunk 단위테스트 통과** |

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

### 2.5 batch_service.py / batch_events.py / JS — state 필드 재사용 (검토 2)

> **검토 결함 #2 해결**: 신규 `total_lines`/`processed_lines`는 기존 필드와 의미가 중복된다. 신규 필드를 추가하지 않고 **기존 필드를 재사용**한다.

기존 자산(확인 완료):
- `batch_service.py:22~35` state에 `total_rows`, `processed_rows` 이미 존재
- `batch_events.py:23~38`이 `total_processed`(=`total_rows`), `processed_rows`를 이미 방출
- `metadata_batch.js:854`가 결과 테이블 "총 처리된 행"에 `data.total_rows || data.total_processed` 사용

역할 정의(재사용):
| 필드 | Phase 1 | 완료 시 |
|------|---------|--------|
| `processed_rows` | ingest된 라인 수(라이브) | 최종 ingest 수 유지 |
| `total_rows` | 추정 총 라인(바이트 기반) | **실제 ingest 수로 확정** |

→ **신규 state 필드 없음, 신규 SSE 필드 없음.** 프론트엔드 Phase 1 표시는 `status_message`("데이터 수집 중 (약 N / M 라인)") + `progress` 바로 충분(둘 다 이미 SSE에 포함). 결과 테이블의 `total_rows`는 완료 시 실제값으로 노출되어 기존 동작과 일관.

- `metadata_batch.js` SSE 핸들러(`:771~860`): `data.status` 우선 표시는 이미 적용됨(`:787`). **추가 JS 변경 불필요** (status + progress로 Phase 1 표시 커버).

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

# ── Phase 2 워커용 read 커넥션 캐싱 (검토 #3) ──────────────────
import threading
_tls = threading.local()

def get_reader(batch_dir):
    """ThreadPoolExecutor 워커 스레드당 read 커넥션 1개를 재사용."""
    conn = getattr(_tls, 'conn', None)
    if conn is None:
        path = os.path.join(batch_dir, 'staging.db')
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA query_only=ON")
        _tls.conn = conn
    return conn

def close_reader():
    conn = getattr(_tls, 'conn', None)
    if conn is not None:
        try: conn.close()
        finally: _tls.conn = None

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

# 총량 (정확한 라인 카운트 — 1패스, 메모리 미사용)
def _count_total_lines(path):
    """CSV 파일의 총 레코드 수를 계산(헤더 제외)."""
    if os.path.isfile(path) and path.endswith('.csv'):
        try:
            return sum(1 for _ in open(path, 'r', encoding='utf-8')) - 1
        except Exception:
            return 0
    return 0

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

# 단일 CSV 파일: 정확한 카운트 (40MB 기준 1패스 ~200ms)
_total_lines = _count_total_lines(csv_file_path)

batch_processing_state['current_step'] = 0
batch_processing_state['progress'] = 5
batch_processing_state['status_message'] = '데이터 수집 준비 중...'

for chunk in _chunk_iter(csv_file_path):
    rows = _extract_rows_from_chunk(chunk, target_id_column, mappings,
                                    _pseudo_mgr, pseudonym_fields)
    if rows:
        batch_staging.insert_evaluations(staging_conn, rows)
        for emp_id, _ in rows:
            emp_id_set.add(emp_id)
    _ingested_rows += len(chunk)

    # 진행률 (정확한 총량 알 수 있을 때만)
    if _total_lines:
        batch_processing_state['total_rows'] = _total_lines
        pct = min(_ingested_rows / max(_total_lines, 1), 1.0)
        batch_processing_state['progress'] = int(5 + pct * 35)
        batch_processing_state['status_message'] = (
            f'데이터 수집 중 ({_ingested_rows:,} / {_total_lines:,} 라인)'
        )
    else:
        # Excel/폴더: 단순 카운트 표시
        batch_processing_state['status_message'] = f'데이터 수집 중 ({_ingested_rows:,} 라인)'
    batch_processing_state['processed_rows'] = _ingested_rows      # 기존 필드 재사용

batch_processing_state['progress'] = 40
batch_processing_state['total_rows'] = _ingested_rows   # 완료 시 실제값 확정
batch_processing_state['status_message'] = f'데이터 수집 완료: {len(emp_id_set):,}명'
```

> **검토 C3/C4 해결**: 정확한 레코드 수는 임베디드 개행으로 사전 카운트가 불가능하지만, `sum(1 for _ in open(...))`는 1패스에 수행되며 메모리를 사용하지 않는다. 40MB 파일 기준 ~200ms이므로 **정확한 라인 카운트**로 진행률을 표시하고, 완료 시 `_ingested_rows`로 확정한다. Excel/폴더는 카운트만 표시.

### 3.4 Phase 2 — staging에서 직원별 분석

기존 `process_single_employee` + ThreadPoolExecutor 루프(`:596~738`)를 staging 조회 기반으로 변경.

```python
employee_ids = sorted(emp_id_set)

# Resume: 완료된 직원 제외 (검토 §8.2 — 현행 :640~643과 동일 정책)
if _is_resume and prior_completed:
    employee_ids = [e for e in employee_ids if str(e) not in prior_completed]

total_employee_count = len(employee_ids)

def process_single_employee(emp_id):
    # 워커 스레드당 read 커넥션 1개 재사용 (검토 #3: open/close 반복 제거)
    conn = batch_staging.get_reader(batch_dir)
    evaluations = batch_staging.load_employee_evaluations(conn, emp_id)
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

### 3.4.1 실패 데이터 저장 — staging 재조회 (검토 #1)

현행 `:749~766`은 실패 직원 원본을 `grouped_data[emp_id]`에서 가져온다. Option B에는 `grouped_data`가 없으므로 staging에서 재조회한다.

```python
# 현행 :764~766
# if emp_id in grouped_data:
#     emp_df = pd.DataFrame(grouped_data[emp_id])
#     emp_df.to_csv(...)

# 변경
conn = batch_staging.get_reader(batch_dir)
emp_evals = batch_staging.load_employee_evaluations(conn, emp_id)
if emp_evals:
    emp_df = pd.DataFrame(emp_evals)
    emp_df.to_csv(os.path.join(emp_dir, 'data.csv'), index=False, encoding='utf-8-sig')
```

> 단, 이 시점에는 staging.db가 아직 살아 있어야 한다(§3.5 정리 호출보다 **앞**). 실패 데이터 저장은 Phase 2 루프 직후 실행되므로 순서상 안전.

### 3.4.2 워커 커넥션 정리

Phase 2 루프 + 실패 데이터 저장 완료 후 각 워커의 캐싱 커넥션을 닫는다. ThreadPoolExecutor가 종료되면 워커 스레드도 소멸하므로, 메인 스레드에서 `close_and_remove` 전에 staging 파일 핸들이 남지 않도록 한다(Windows 파일 잠금 회피).

```python
# ThreadPoolExecutor with 블록 종료(워커 스레드 소멸) 후
# 메인 스레드의 잔여 reader가 있으면 정리
batch_staging.close_reader()
```

> Windows 파일 잠금 주의: WAL 모드 staging.db 삭제(`close_and_remove`) 전에 모든 read 커넥션이 닫혀야 한다. 워커 스레드 종료 시 GC로 닫히지만, 확실히 하기 위해 삭제는 재시도/예외 무시(`close_and_remove` 내 try/except)로 처리한다. (참고: 커밋 1561a94의 Windows 파일 잠금 이슈)

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
| `:596~738` | Phase 2 staging 조회 기반 루프로 변경, progress 45~90, 워커 커넥션 캐싱(`get_reader`) |
| `:607~611` | metadata dept/pos 후처리 가명화 **삭제** (이중 적용 방지) |
| `:749~766` | 실패 데이터 저장을 `grouped_data` → staging 재조회로 교체 (검토 #1) |
| `:662,786` | `len(df)` → `_ingested_rows` |
| `:738,776,789` | progress 90/92/100 재배치 |
| Phase 2 직후 | `batch_staging.close_reader()` |
| 반환 직전 | `batch_staging.close_and_remove` 호출 |

### 4.3 `src/services/batch_service.py`
| 위치 | 변경 |
|------|------|
| — | **변경 없음** (검토 #2: 기존 `total_rows`/`processed_rows` 재사용, 신규 필드 미추가) |

> 단, `_run_batch_process` except 블록(`:281~291`)에 staging 정리(`close_and_remove`)를 추가할지 검토 — 처리 실패 시 staging.db 잔존 방지(§8.5).

### 4.4 `src/services/batch_events.py`
| 위치 | 변경 |
|------|------|
| — | **변경 없음** (검토 #2: `total_processed`/`processed_rows` 이미 방출, status_message로 라인 표시) |

### 4.5 `web/static/js/metadata_batch.js`
| 위치 | 변경 |
|------|------|
| — | **변경 없음** (검토 #2: `data.status` + `data.progress`로 Phase 1 표시 커버, `:787` 이미 적용) |

### 4.6 `web/templates/metadata_batch.html` (선택)
| 위치 | 변경 |
|------|------|
| `:363~366` | proc-step "파일 로드" → "데이터 수집" 라벨 |

---

## 5. SSE payload (변경 없음 — 기존 필드 재사용)

검토 #2에 따라 신규 필드를 추가하지 않는다. 기존 payload 그대로:

```json
// Phase 1 진행 중 (기존 필드만 사용)
{
  "step": 0,
  "progress": 22,
  "status": "데이터 수집 중 (약 100,000 / 400,000 라인)",
  "total_processed": 400000,   // = state.total_rows (추정→완료시 실제)
  "processed_rows": 100000,    // = ingest 라이브 카운트
  "unique_employees": 0,
  ...
}
```

프론트엔드 표시: `status`(사람이 읽는 라인 현황) + `progress`(바). 결과 테이블 "총 처리된 행"은 완료 시 `total_rows`(실제 ingest 수).

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

1. `batch_staging.py` 신규 작성 + 단독 단위테스트(insert/select/distinct/remove/get_reader)
2. `batch_processor.py`
   - 2-1. `_extract_rows_from_chunk` 작성, `group_data_by_employee` 제거
   - 2-2. 가명화 매니저 준비 위치 이동
   - 2-3. Phase 1 ingest 루프
   - 2-4. Phase 2 staging 조회 루프 + progress 재배치 + `get_reader`/`close_reader`
   - 2-5. `process_employee_metadata` df 제거 + `evaluations[0]` 적용, `:607~611` 삭제
   - 2-6. `len(df)`→`_ingested_rows`, 실패 데이터 저장을 staging 재조회로 교체
   - 2-7. staging 정리 호출(`close_reader` → `close_and_remove`)
3. `batch_service.py` — `_run_batch_process` except 블록에 staging 정리 추가 검토(§8.5)
4. `metadata_batch.html` 라벨(선택)

---

## 8. 주의사항 및 제약

### 8.1 staging 동시 읽기
Phase 2 ThreadPoolExecutor 워커가 각자 `open_staging`으로 읽기 커넥션을 연다. WAL 모드에서 다중 읽기는 안전. 쓰기는 Phase 1에서 단일 스레드로 완료된 상태.

### 8.2 Resume 호환 (검토 #4)
Resume 시 staging.db는 직전 실행에서 삭제되었을 수 있으므로 **Phase 1 ingest를 다시 수행**하고, Phase 2에서 `prior_completed`(작업서 items 테이블)로 완료 직원을 제외한다. ingest는 분석 대비 저비용이라 재수행 허용.

**`original.csv` fallback은 이미 구현됨** — `resume_batch_metadata`(`batch_service.py:382~389`)가 `csv_file_path` 무효 시 `batch_dir/original.csv`로 대체하고, 둘 다 없으면 에러 반환한다. `original.csv` 백업은 `process_batch:461~467`에서 단일 파일(`os.path.isfile`)일 때 생성되며, 폴더 입력도 merged temp csv가 file이므로 백업 대상이다. → **신규 코드 불필요**, Option B Phase 1은 서비스가 해석해 넘긴 `csv_file_path`를 그대로 읽으면 된다.

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
| 실패 데이터 저장(검토#1) | 일부러 실패 유발 → `failed/.../emp_X/data.csv`가 staging 재조회로 정상 생성 |
| 워커 커넥션 캐싱(검토#3) | 수천 명 처리 시 staging open 횟수 = 워커 수 수준인지 확인 |
| state 필드(검토#2) | 결과 테이블 "총 처리된 행"이 실제 ingest 수와 일치 |
| staging 정리 | 정상/실패 종료 모두 `batch_dir/staging.db`(+wal/shm) 잔존 없음 (Windows 잠금 포함) |

---

## 10. 미해결/결정 필요

- **staging 위치**: `batch_dir/staging.db`(권장) vs 메인 DB 내 임시 테이블. 권장은 per-batch 파일(오염·락 회피).
- **진행률 정확도**: CSV는 바이트 기반 추정(±오차). 정확 표기가 필요하면 ingest 전 1패스 카운트를 옵션으로 추가(파일 2회 읽기 비용 감수).
