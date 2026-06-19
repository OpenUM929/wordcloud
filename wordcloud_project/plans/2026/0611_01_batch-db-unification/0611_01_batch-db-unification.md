# 배치 처리 DB 일원화 완성

> 상태: DN | 작성일: 2026-06-11 | 완료확인: 2026-06-18

## 완료 확인 (2026-06-18 코드 대조)

`batch_manager.py`(`_get_eval_conn` 재사용, `FROM evaluations`/`employees`)·`wordcloud_data_service.py`(`FROM evaluations`)가 모두 DB 읽기로 전환됨. `batch_processor.py`의 per-employee imeta/tmeta 쓰기(Stage 4/5: `save_imeta_single`/`save_tmeta_single`)는 `0615_01` CSV 스트리밍 리팩토링으로 제거되고 staging.db 경유로 대체됨. `batch_summary.json`(tmeta)만 `0615_02` display_name 보관용으로 의도적으로 잔존(하이브리드 구조 확정). → 본 계획의 DB 일원화 목표 달성.

---

## 1. 배경 및 문제

`employees` / `evaluations` SQLite 테이블로의 마이그레이션이 **부분 완료** 상태다.

- `perspective_service.load_all_batches()` → DB 읽기 완료 ✅
- `batch_processor.py` → 파일(imeta/tmeta) **여전히 쓰고 있음** ❌
- `batch_manager.py` → 파일에서 읽음 ❌
- `wordcloud_data_service.py` → 파일에서 읽음 ❌

배치 처리 시 `no such table: employees` 에러 발생 원인:
- `user_data_manager._get_eval_conn()`이 테이블을 생성하지 않음
- 테이블 생성은 `deploy_session_service._init_db()`에만 의존
- 어떤 이유로 DB 파일 또는 테이블이 없는 상태면 `upsert()` 실패

---

## 2. 현재 파일↔DB 사용 현황

### 파일에 쓰는 곳 (제거 대상)

| 위치 | 내용 |
|------|------|
| `batch_processor.py` Stage 4 | `imeta/` JSON 저장 |
| `batch_processor.py` Stage 5 | `tmeta/employee_{id}.json` 저장 |
| `batch_processor.py` `create_batch_summary()` | `tmeta/batch_summary.json` |
| `batch_processor.py` `initialize_batch_directory()` | imeta/tmeta/word 폴더 생성 |

### 파일에서 읽는 곳 (DB 전환 대상)

| 위치 | 읽는 파일 | DB 대체 방법 |
|------|-----------|-------------|
| `batch_manager.get_batch_list()` | `tmeta/batch_summary.json` | `SELECT DISTINCT batch_id, COUNT(DISTINCT employee_id) FROM evaluations GROUP BY batch_id` |
| `batch_manager.load_batch_metadata()` | `tmeta/employee_*.json` | `SELECT data FROM evaluations WHERE batch_id = ?` |
| `batch_manager.get_sample_metadata_from_results()` | `tmeta/batch_summary.json` | DB 직접 조회 |
| `wordcloud_data_service.get_employee_wordcloud_data()` | `tmeta/employee_{id}.json` | evaluations.data + on-the-fly 집계 |
| `wordcloud_data_service.get_batch_employee_list()` | `tmeta/batch_summary.json` | `SELECT DISTINCT employee_id FROM evaluations WHERE batch_id = ?` |
| `wordcloud_data_service.get_batch_aggregate_data()` | `tmeta/employee_*.json` 다수 | evaluations.data 루프 집계 |

### DB에만 쓰는 곳 (유지)

| 위치 | 내용 |
|------|------|
| `batch_processor.py` → `user_data_manager.upsert()` | employees + evaluations 저장 |

---

## 3. DB 스키마 갭 분석

`wordcloud_data_service`는 `consolidated_analysis.word_frequency`를 사용한다.
이 값은 tmeta JSON에만 있고 DB에는 없다.

**해결 방법**: `evaluations.data`의 `nlp_analysis_results.analysis.meaningful_words`를
on-the-fly로 집계하여 word_frequency를 계산한다. (이미 `wordcloud_data_service._calc_emotion_from_evaluations()`와 동일한 패턴으로 구현 가능)

별도 DB 컬럼 추가 없이 처리한다.

---

## 4. 선행 확인 사항 (작업 전 필수)

작업 시작 전 현재 데이터 위치를 확인해야 한다.

```bash
# DB 데이터 존재 여부
python -c "
import sqlite3, os
p='wordcloud_project/.sessions/deploy_sessions.db'
print('DB exists:', os.path.exists(p))
c=sqlite3.connect(p)
try:
    print('employees:', c.execute('SELECT COUNT(*) FROM employees').fetchone())
    print('evaluations:', c.execute('SELECT COUNT(*) FROM evaluations').fetchone())
except Exception as e:
    print('Error:', e)
c.close()
"

# 파일 데이터 존재 여부
dir wordcloud_project\processed_data\batch /s /b 2>nul | find /c "employee_"
```

**시나리오별 대응:**

| 상황 | 대응 |
|------|------|
| DB에 데이터 있음 | 바로 진행 |
| DB 비어있고 파일 있음 | `migrate_evaluations.py` 먼저 실행 후 진행 |
| DB 없음 (테이블 없음) | `_init_db()` 실행 확인 후 진행 |

---

## 5. 구현 범위

### 5-1. `user_data_manager.py` — 테이블 초기화 보장

```python
def _get_eval_conn():
    os.makedirs(_DB_DIR, exist_ok=True)
    from src.services.deploy_session_service import _init_db
    _init_db()
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn
```

### 5-2. `batch_processor.py` — 파일 쓰기 제거

제거 대상:
- `initialize_batch_directory()` 내 `imeta/`, `tmeta/`, `word/` 폴더 생성 (checkpoint 폴더는 유지)
- Stage 4 전체 (`save_imeta_single`, ThreadPoolExecutor imeta 블록)
- Stage 5 전체 (`save_tmeta_single`, ThreadPoolExecutor tmeta 블록)
- `create_batch_summary()` 호출 및 함수 자체

batch_id 생성 로직(`initialize_batch_directory`)은 유지 — DB의 `batch_id` 컬럼에 저장되므로 고유 ID는 여전히 필요.

### 5-3. `batch_manager.py` — DB 읽기로 전환

`get_batch_list()`:
```python
def get_batch_list(processed_data_dir=None):
    conn = _get_eval_conn()
    try:
        rows = conn.execute("""
            SELECT batch_id,
                   COUNT(DISTINCT employee_id) AS employee_count,
                   MIN(created_at) AS created_at
            FROM evaluations
            GROUP BY batch_id
            ORDER BY created_at DESC
        """).fetchall()
    finally:
        conn.close()
    batches = []
    for row in rows:
        batch_id = row['batch_id']
        batches.append({
            'name': batch_id,
            'original_name': batch_id,
            'path': None,
            'employee_count': row['employee_count'],
            'created_at': (row['created_at'] or '')[:10],
        })
    return batches
```

`get_sample_metadata_from_results()`: DB에서 해당 batch_id의 첫 번째 직원 데이터 조회로 대체.

`load_batch_metadata()`: evaluations 테이블에서 batch_id 기준 조회로 대체.

### 5-4. `wordcloud_data_service.py` — DB 읽기로 전환

`get_employee_wordcloud_data()`:
- evaluations 테이블에서 `employee_id + batch_id` 조건으로 데이터 조회
- `nlp_analysis_results.analysis.meaningful_words`를 집계하여 word_frequency 계산
- `_calc_emotion_from_evaluations()`는 그대로 사용

`get_batch_employee_list()`:
```python
SELECT DISTINCT employee_id FROM evaluations WHERE batch_id = ?
```

`get_batch_aggregate_data()`:
- DB에서 batch_id 기준 모든 evaluations 조회 후 동일 로직 적용

### 5-5. `_get_eval_conn` 공통화

`batch_manager.py`와 `wordcloud_data_service.py`에도 DB 연결 함수가 필요하다.
`user_data_manager._get_eval_conn()`을 import해서 재사용한다.

---

## 6. 변경 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `src/services/user_data_manager.py` | `_get_eval_conn()` 테이블 초기화 보장 추가 |
| `src/services/batch_processor.py` | Stage 4, 5 제거 / create_batch_summary 제거 / initialize_batch_directory 폴더 생성 축소 |
| `src/services/batch_manager.py` | DB 읽기로 전환 |
| `src/services/wordcloud_data_service.py` | DB 읽기 + on-the-fly 집계로 전환 |

---

## 7. 테스트 항목

| 항목 | 확인 방법 |
|------|-----------|
| 배치 처리 시작 → 에러 없이 완료 | 배치 처리 UI에서 실행 |
| DB에 employees/evaluations 저장 확인 | sqlite3 SELECT 조회 |
| 배치 목록 표시 | `/api/batch/list` 응답 확인 |
| 퍼스펙티브 분석 정상 동작 | 매트릭스 화면 로드 |
| 워드클라우드 데이터 조회 | `/api/wordcloud-data/...` 응답 확인 |
| 파일 미생성 확인 | processed_data/batch 내 imeta/tmeta 없음 |
