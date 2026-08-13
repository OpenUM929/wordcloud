# 0609_02_evaluation-db-migration — users/*.json → SQLite 정규화 계획서

> 상태: Done | 작성일: 2026-06-09 | 완료일: 2026-06-09

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-09 | 전체 | 최초 작성 |
| 2026-06-09 | 2.2, 3.4, 4, 5, 6, 9, 10 | 코드 검토 기반 보완: `remove_batch_from_all()` 시그니처, `schema_version` 독립성, N+1 제거, 구현 순서, 위험도 추가 |
| 2026-06-09 | 1.2, 3.2, 3.3, 3.5(신규), 5.1, 5.2, 8, 9 | 가명화 흐름 명시: DB 저장은 pseudo_id, 실명 복원은 기존 `_enrich_with_real_ids()` 유지. 현재 코드 기반 확인. |
| 2026-06-09 | 2.1, 2.2, 4, 9, 10 | 추가 호출부 발견: `web/app.py`의 `migrate_from_old_format()`, `batch_routes.py` DEPRECATED delete, `batch_manager.py` 고아 데이터 위험 반영 |
| 2026-06-09 | 1.2, 3.5, 7, 9, 10 | 사용자 코드 변경 반영: `perspective_routes.py` 대규모 수정, `_resolve_output_mode` 가명 비활성화, `deploy_session_service.py` `retry_failed_tasks()` 추가, `batch_title` 기능. 병합 충돌 방지 및 가명화 전략 업데이트 |
| 2026-06-09 | 5.1, 5.3, 6.1, 6.2, 4, 9 | 계획서 검토 결과 버그 수정: `_get_conn()` → `_get_eval_conn()`, `migrate()` 진입점 추가, employees 삭제 정책 일치, 마이그레이션 스크립트 위치 `plans/` → `scripts/` |
| 2026-06-09 | 6.2 | 최종 검토 버그 수정: `_auto_migrate_evaluations()`에서 `PROCESSED_DATA_DIR_PATH` 미정의 → `from src.config.settings import PROCESSED_DATA_DIR_PATH` import 추가 |
| 2026-06-09 | 전체 | **구현 완료**: `user_data_manager.py` DB 전환, `perspective_service.py` `load_all_batches` DB 전환, `deploy_session_service.py` DDL+마이그레이션 함수, `web/app.py` 마이그레이션 교체, `batch_routes.py`/`batch_manager.py` 수정, `scripts/migrate_evaluations.py` 신규 |

---

## 1. 배경 및 목적

### 1.1 문제 정의

현재 평가 데이터는 `processed_data/users/{employee_id}.json` 파일로 피평가자별로 저장된다.
각 파일에는 해당 피평가자에게 작성된 **모든 평가자의 평가 데이터**가 배열로 중첩되어 있다.

이 구조의 확장성 문제:

| 문제 | 내용 |
|------|------|
| **선형 스캔** | `load_all_batches()`가 9개 API 호출 지점에서 매번 모든 `users/*.json`을 전체 읽음 — 19,000명 시 O(n) I/O |
| **캐싱 불가** | 파일 기반이므로 메모리 캐시 적용이 복잡, 무효화 로직 필요 |
| **필드 확장성** | 새 분석 결과 필드 추가 시 기존 파일에 해당 필드 없어 fallback 코드 영구 잔존 |
| **동시성** | 배치 처리 중 `upsert()` 파일 I/O, 여러 프로세스 동시 쓰기 시 race condition 가능성 |
| **쿼리 불가** | "특정 batch_id의 모든 평가" 조회 시 전체 파일 순회 필요 |

### 1.2 목표

| 목표 | 내용 |
|------|------|
| **정규화** | `employees` + `evaluations` SQLite 테이블로 1 평가자 = 1 row 저장 |
| **인터페이스 보존** | `load_all_batches()` 반환 형식 유지 → 9개 route 호출부 변경 없음 |
| **DAO 일원화** | `user_data_manager.py` 내부만 파일→DB로 교체, 외부 인터페이스 동일 |
| **점진적 전환** | 기존 `users/*.json` 보존, 1회 마이그레이션 스크립트로 이전 |
| **가명화 보존** | 저장 시 pseudo_id 그대로 DB 유지. 실명 복원은 기존 `_enrich_with_real_ids()` 레이어 유지. 단, `_resolve_output_mode()`가 가명 기능을 비활성화하여 관리자는 항상 실명 모드로 처리됨 (§3.5 참조). |

---

## 2. "DAO 수정만으로 충분한가?" 분석

### 2.1 호출 경로 전체 검토

```
batch_processor.py:726      → user_data_manager.upsert()          ← 배치 저장
perspective_routes.py:756   → user_data_manager.remove_batch_from_all() ← 삭제
perspective_routes.py:44    → load_all_batches()                   ← 조회 (9곳)
perspective_service.py:536  → users/*.json 직접 읽기               ← load_all_batches() 내부
web/app.py:53               → user_data_manager.migrate_from_old_format()  ← 앱 시작 시 old format 마이그레이션
batch_routes.py:74          → batch_manager.delete_batch_directory() ← DEPRECATED 배치 삭제 (evaluations 미정리)
```

### 2.2 결론

| 수정 대상 | 변경 내용 | 외부 인터페이스 변경 여부 |
|-----------|-----------|---------------------------|
| `user_data_manager.upsert()` | JSON 파일 쓰기 → DB INSERT/UPSERT | **없음** (함수 시그니처 동일) |
| `user_data_manager.remove_batch()` | JSON 파일 수정 → DB DELETE | **없음** (내부 전용, 외부 호출 없음) |
| `user_data_manager.remove_batch_from_all()` | 전체 파일 순회 삭제 → DB DELETE WHERE | **없음** (시그니처 유지, `employee_ids`는 무시 또는 `IN` 조건 활용) |
| `perspective_service.load_all_batches()` | `users/*.json` 읽기 → DB SELECT | **없음** (반환 형식 동일) |
| **9개 route 호출부** | — | **변경 불필요** |
| `batch_processor.py` | — | **변경 불필요** (upsert 인터페이스 유지) |
| `web/app.py` | `migrate_from_old_format()` 호출 | **변경 필요** (DB 자동 마이그레이션으로 교체, §6.2 참조) |
| `batch_routes.py` (DEPRECATED) | `delete_batch_directory()`만 호출 | **변경 필요** (evaluations 정리 안 됨 → 고아 데이터, §6.4 참조) |

**→ DAO 레이어(`user_data_manager.py`) + 데이터 접근 레이어(`load_all_batches()`) 내부 수정으로 전환 완료.**

---

## 3. DB 스키마

### 3.1 위치

`0609_01_gallery-db-migration` 계획과 동일한 `deploy_sessions.db` 파일에 추가한다.

```python
# deploy_session_service.py 기준
_DB_PATH = os.path.join(BASE_DIR, '..', '.sessions', 'deploy_sessions.db')
```

### 3.2 `employees` 테이블

> ⚠️ **`employee_id` = pseudo_id (가명)**
> `batch_processor.py`가 `upsert()` 호출 전에 이미 `PseudonymManager.get_pseudonym()`을 적용한다.
> 따라서 DB에는 실명이 저장되지 않는다. 실명 조회는 §3.5의 복원 레이어에서 처리한다.

```sql
CREATE TABLE IF NOT EXISTS employees (
    employee_id  TEXT PRIMARY KEY,   -- pseudo_id (가명, PseudonymManager 생성값)
    name         TEXT,               -- 피평가자 이름 (가명 처리 대상에 따라 실명일 수 있음)
    department   TEXT,
    position     TEXT,
    updated_at   TEXT DEFAULT (datetime('now'))
);
```

### 3.3 `evaluations` 테이블

평가 데이터는 분석 결과 JSON이 복잡하므로 핵심 검색 컬럼 + `data` JSON blob 방식을 채택한다.
`evaluator_id` 등 PII 필드도 `batch_processor`에서 가명 처리된 뒤 이 테이블에 저장된다.

```sql
CREATE TABLE IF NOT EXISTS evaluations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,

    -- 핵심 검색/필터 컬럼 (인덱스 대상)
    employee_id      TEXT NOT NULL REFERENCES employees(employee_id),
    evaluator_id     TEXT,
    evaluation_date  TEXT,
    batch_id         TEXT,

    -- 원본 평가 데이터 전체 (JSON)
    -- nlp_analysis_results, emotion_analysis_results, leadership_analysis_results,
    -- profanity_analysis_results, sarcasm_analysis_results, evaluation_document 등 포함
    data             TEXT NOT NULL,

    -- 중복 방지용 fingerprint (evaluator_id + evaluation_date + content_preview 해시)
    fingerprint      TEXT,

    created_at       TEXT DEFAULT (datetime('now'))
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_ev_employee    ON evaluations (employee_id);
CREATE INDEX IF NOT EXISTS idx_ev_batch       ON evaluations (batch_id);
CREATE INDEX IF NOT EXISTS idx_ev_evaluator   ON evaluations (evaluator_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ev_fp   ON evaluations (fingerprint);
```

#### fingerprint 계산

```python
import hashlib, json

def _fingerprint(ev: dict) -> str:
    key = (
        ev.get('evaluator_id', ''),
        ev.get('evaluation_date', ''),
        str(ev.get('content', ''))[:100],
    )
    return hashlib.md5(json.dumps(key, ensure_ascii=False).encode()).hexdigest()
```

현재 `user_data_manager.py`의 중복 키 로직(`existing_keys` set)과 동일한 의미론.

### 3.5 가명화 흐름

DB 전환 후에도 기존 가명화 아키텍처가 그대로 유지된다.

```
[입력 CSV — 실명]
        ↓
batch_processor.py
  └─ PseudonymManager.get_pseudonym(real_id) → pseudo_id 생성
  └─ apply_pseudonyms_to_dict(ev, ...)        → 평가 dict 내 PII 필드 가명화
        ↓
user_data_manager.upsert(pseudo_id, ...)
        ↓
  ┌─────────────────────────────────────┐
  │ employees (employee_id = pseudo_id) │  ← DB 저장: 가명
  │ evaluations (data = 가명 처리된 JSON) │
  └─────────────────────────────────────┘
        ↓
load_all_batches()
  └─ employee_results[].metadata.target_employee_id = pseudo_id  ← 반환값: 가명
        ↓
_enrich_with_real_ids(results, ..., enrich=True)   ← 관리자 모드에서만
  └─ PseudonymManager.get_real_id(pseudo_id) → 실명 복원
        ↓
  [API 응답 — 관리자: 실명 포함 / 일반: 가명만]
```

**변경 없는 레이어**: `PseudonymManager`, `_enrich_with_real_ids()`, `pseudonym_mappings.enc`
**변경되는 레이어**: `upsert()` 내부 (파일→DB), `load_all_batches()` 내부 (파일→DB)

> **참고**: `_resolve_output_mode()`가 가명 기능을 비활성화하여 관리자 인증 시 항상 `real` 모드를 반환한다. 이는 API 응답 레이어의 변경이며, DB 저장 레이어는 여전히 `pseudo_id`를 유지한다. 따라서 `_enrich_with_real_ids()`는 관리자 모드에서만 호출되며, DB 스키마와 저장 로직에는 영향을 주지 않는다.

### 3.6 스키마 버전 테이블

`0609_01_gallery-db-migration`이 선행 구현되면 해당 `schema_version` 테이블을 공유한다.
`0609_01`이 아직 구현되지 않은 경우, 이 계획서에서 `_init_db()`에 `schema_version` 테이블을 **동시에 추가**하여 독립 실행 가능하도록 한다.

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);
```

`employees` + `evaluations` 테이블 도입 시 `schema_version`에 버전 번호를 INSERT한다.
(`0609_01`이 선행 구현된 경우 버전 번호를 이어서 증가시킨다.)

---

## 4. 수정 파일 목록

| 순서 | 파일 | 변경 유형 | 내용 |
|------|------|-----------|------|
| 1 | `src/services/user_data_manager.py` | **수정** | `upsert()`, `remove_batch_from_all()` 내부를 DB I/O로 교체. `remove_batch()`는 내부 전용으로 함께 수정. `get_user()`, `get_all_employee_results()`는 외부 호출 없으므로 제거 대상. `_get_eval_conn()` 헬퍼 추가. |
| 2 | `src/services/perspective_service.py` | **수정** | `load_all_batches()` 내 `users/*.json` 직접 읽기 → DB SELECT로 교체. 반환 dict 구조(`employee_results`, `batches`, `batch_info`) 동일 유지. `_count_batches()` / `_load_batch_list()` 헬퍼 추가. old format fallback 제거. |
| 3 | `src/services/deploy_session_service.py` | **수정** | `_init_db()`에 `employees` + `evaluations` + `schema_version` 테이블 생성 SQL 추가. |
| 4 | `web/app.py` | **수정** | `migrate_from_old_format()` 호출 → `_auto_migrate_evaluations()` 호출로 교체. `users/*.json` 기반 old format 마이그레이션은 DB 전환 후 불필요. |
| 5 | `src/routes/batch_routes.py` | **수정** | DEPRECATED `delete()` 엔드포인트에서 `remove_batch_from_all()` 선행 호출 추가, 또는 엔드포인트 제거. |
| 6 | `src/services/batch_manager.py` | **수정** | `delete_batch_directory()` docstring 업데이트: "users/*.json 미정리" → "evaluations 테이블 미정리" 명시. |
| 7 | `scripts/migrate_evaluations.py` | **신규** | 독립 실행 마이그레이션 스크립트. `users/*.json` → DB 1회 이전. `user_data_manager.upsert()`에 의존하지 않고 독립 DB 연결. 배포 대상 경로(`scripts/`)에 위치해야 자동 마이그레이션이 정상 동작한다. |

---

## 5. 상세 구현

### 5.1 `user_data_manager.upsert()` 변경

> `employee_id`는 `batch_processor.py`에서 이미 `PseudonymManager.get_pseudonym()`을 거쳐 넘어오므로
> 이 함수 내부에서 별도 가명화를 수행하지 않는다.

```python
def upsert(employee_id, metadata, evaluations, batch_id):
    """Upsert user data from a batch. DB 버전.
    
    employee_id는 pseudo_id (batch_processor에서 이미 가명화 완료).
    """
    conn = _get_eval_conn()

    # employees 테이블 upsert
    name = metadata.get('target_employee_name') or employee_id
    dept = metadata.get('target_employee_department') or ''
    pos  = metadata.get('target_employee_position') or ''
    conn.execute("""
        INSERT INTO employees (employee_id, name, department, position, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT(employee_id) DO UPDATE SET
            name       = COALESCE(NULLIF(excluded.name, ''), name),
            department = COALESCE(NULLIF(excluded.department, ''), department),
            position   = COALESCE(NULLIF(excluded.position, ''), position),
            updated_at = datetime('now')
    """, (employee_id, name, dept, pos))

    # evaluations 삽입 (fingerprint 중복 무시)
    inserted = 0
    for ev in evaluations:
        ev_copy = dict(ev)
        ev_copy['batch_id'] = batch_id
        fp = _fingerprint(ev_copy)
        try:
            conn.execute("""
                INSERT INTO evaluations (employee_id, evaluator_id, evaluation_date, batch_id, data, fingerprint)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                employee_id,
                ev_copy.get('evaluator_id', ''),
                ev_copy.get('evaluation_date', ''),
                batch_id,
                json.dumps(ev_copy, ensure_ascii=False),
                fp,
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # fingerprint 중복 → 건너뜀
    conn.commit()
    return inserted
```

### 5.2 `load_all_batches()` 반환 형식 보존

> `_get_eval_conn()`은 `user_data_manager.py` 내부에 정의하며, `deploy_session_service._get_conn()`와 동일한 DB를 연결한다.

```python
def load_all_batches(processed_data_dir=None):
    conn = _get_eval_conn()

    # 단일 JOIN 쿼리로 N+1 제거
    rows = conn.execute("""
        SELECT e.employee_id, e.name, e.department, e.position, ev.data
        FROM employees e
        LEFT JOIN evaluations ev ON e.employee_id = ev.employee_id
        ORDER BY e.employee_id, ev.id
    """).fetchall()

    from collections import defaultdict
    emp_evals = defaultdict(list)
    emp_meta = {}
    for emp_id, name, dept, pos, data in rows:
        if emp_id not in emp_meta:
            emp_meta[emp_id] = {
                'target_employee_name': name,
                'target_employee_department': dept,
                'target_employee_position': pos,
            }
        if data:
            emp_evals[emp_id].append(json.loads(data))

    employee_results = []
    total_evals = 0
    for emp_id, meta in emp_meta.items():
        evals = emp_evals[emp_id]
        total_evals += len(evals)
        employee_results.append({
            'metadata': {
                'target_employee_id': emp_id,
                'target_employee_name': meta['target_employee_name'],
                'target_employee_department': meta['target_employee_department'],
                'target_employee_position': meta['target_employee_position'],
                'evaluations': evals,
            }
        })

    # batches 목록은 기존 batch_summary.json 에서 유지 (배치 관리 별도 주제)
    merged = {
        'batch_info': {
            'total_evaluations': total_evals,
            'unique_employees': len(emp_meta),
            'batch_count': _count_batches(processed_data_dir),
        },
        'employee_results': employee_results,
        'batches': _load_batch_list(processed_data_dir),
    }
    return merged
```

반환 구조가 현재와 동일하므로 9개 호출부는 무변경.
`employee_results[].metadata.target_employee_id`는 pseudo_id이며, 실명 복원은 기존과 동일하게
`_enrich_with_real_ids()` → `PseudonymManager.get_real_id()` 경로를 사용한다.

### 5.3 `remove_batch_from_all()` 변경

> `employee_ids` 파라미터는 기존 라우트 호출부(`perspective_routes.py:767`)와의 호환성을 위해 유지하되, DB 버전에서는 사용하지 않는다.

```python
def remove_batch_from_all(batch_id, employee_ids):
    """Remove batch data from all users. DB 버전.
    
    employee_ids는 기존 인터페이스 호환성을 위해 유지되며 무시된다.
    """
    conn = _get_eval_conn()
    cursor = conn.execute(
        "DELETE FROM evaluations WHERE batch_id = ?", (batch_id,)
    )
    # 평가 없는 employee는 삭제하지 않는다 (정책: 유지)
    # 이력 보존 목적 — 필요 시 별도 cleanup API로 처리
    conn.commit()
    return cursor.rowcount
```

---

## 6. 마이그레이션 전략

### 6.1 1회 마이그레이션 스크립트 (`migrate_evaluations.py`)

> **독립 실행**: `user_data_manager.upsert()`에 의존하지 않고 자체 DB 연결을 사용한다.

```python
# 독립 실행: python migrate_evaluations.py
import os, json, glob, sqlite3
import hashlib

USERS_DIR = 'processed_data/users'
# scripts/ 폴더 기준: wordcloud_project/scripts/migrate_evaluations.py
DB_PATH = os.path.join(os.path.dirname(__file__), '..', '.sessions', 'deploy_sessions.db')

def _fingerprint(ev):
    key = (ev.get('evaluator_id', ''), ev.get('evaluation_date', ''), str(ev.get('content', ''))[:100])
    return hashlib.md5(json.dumps(key, ensure_ascii=False).encode()).hexdigest()

def migrate():
    conn = sqlite3.connect(DB_PATH)
    files = glob.glob(os.path.join(USERS_DIR, '*.json'))
    total = 0
    for path in files:
        with open(path, 'r', encoding='utf-8') as f:
            user = json.load(f)
        emp_id = user.get('employee_id', '')
        if not emp_id:
            continue
        # employees upsert
        conn.execute("""
            INSERT INTO employees (employee_id, name, department, position)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(employee_id) DO UPDATE SET
                name       = COALESCE(NULLIF(excluded.name, ''), name),
                department = COALESCE(NULLIF(excluded.department, ''), department),
                position   = COALESCE(NULLIF(excluded.position, ''), position)
        """, (emp_id, user.get('name', ''), user.get('department', ''), user.get('position', '')))

        evals = user.get('evaluations', [])
        for ev in evals:
            fp = _fingerprint(ev)
            try:
                conn.execute("""
                    INSERT INTO evaluations (employee_id, evaluator_id, evaluation_date, batch_id, data, fingerprint)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (emp_id, ev.get('evaluator_id', ''), ev.get('evaluation_date', ''), ev.get('batch_id', ''), json.dumps(ev, ensure_ascii=False), fp))
                total += 1
            except sqlite3.IntegrityError:
                pass
    conn.commit()
    conn.close()
    print(f"마이그레이션 완료: {total}건 삽입")


if __name__ == '__main__':
    migrate()
```

### 6.2 앱 시작 시 자동 마이그레이션

> `_init_db()` 내부에서 `user_data_manager`를 직접 임포트하지 않도록 주의 (순환 참조 방지). `migrate_evaluations.py`를 `subprocess`로 실행하거나, `_init_db()` 완료 후 별도 호출로 분리한다.

```python
# deploy_session_service.py — _init_db() 완료 후 별도 함수로 분리
# PROCESSED_DATA_DIR_PATH는 src/config/settings.py에서 import (다른 서비스와 동일 패턴)
import os
from src.config.settings import PROCESSED_DATA_DIR_PATH

def _auto_migrate_evaluations():
    conn = _get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
        if count > 0:
            return
    finally:
        conn.close()
    users_dir = os.path.join(PROCESSED_DATA_DIR_PATH, 'users')
    if os.path.exists(users_dir):
        import subprocess, sys
        script = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', 'migrate_evaluations.py')
        print("[EvalDB] 자동 마이그레이션 실행 중...")
        subprocess.run([sys.executable, script], check=False)
```

### 6.3 기존 `users/*.json` 처리

- 마이그레이션 완료 후 **삭제하지 않음** — 롤백 대비 보존
- `user_data_manager.py`의 파일 I/O 코드는 DB 전환 후 주석 처리 → 검증 완료 후 제거
- `perspective_service.load_all_batches()`의 old format fallback (batch_summary에서 `employee_results` 읽기)는 **DB 전환 시 제거**한다. DB가 없을 경우 자동 마이그레이션이 실행되므로 fallback이 불필요해진다.

### 6.4 DEPRECATED 엔드포인트 및 고아 데이터 방지

#### `batch_routes.py` — `/delete` (DEPRECATED)

```python
@batch_bp.route('/delete', methods=['POST'])
def delete():
    """DEPRECATED: This endpoint does NOT clean up evaluations data.
    Use DELETE /api/perspective/batch/<batch_id> instead for full cleanup.
    """
    try:
        data = request.json
        batch_path = data.get('batch_path')
        if not batch_path:
            return jsonify({'success': False, 'error': '배치 경로가 필요합니다.'}), 400

        # DB 전환: batch 디렉토리 삭제 전 evaluations 정리
        batch_id = os.path.basename(batch_path)
        from src.services.user_data_manager import remove_batch_from_all
        removed = remove_batch_from_all(batch_id, [])

        result, status = delete_batch_directory(batch_path)
        if result.get('success'):
            result['evaluations_removed'] = removed
        return jsonify(result), status
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
```

#### `batch_manager.py` — `delete_batch_directory()` docstring 업데이트

```python
def delete_batch_directory(batch_path):
    """
    Delete a batch directory.

    WARNING: This function only removes the batch directory on disk.
    It does NOT remove the batch's evaluation data from the evaluations table.
    For complete cleanup including evaluation data, use remove_batch_from_all()
    from user_data_manager before calling this function.
    """
```

---

## 7. `0609_01_gallery-db-migration`과의 관계

두 계획은 **독립적**이다. 같은 DB 파일(`deploy_sessions.db`)을 공유하지만 테이블이 분리된다.

| 계획 | 테이블 | 수정 파일 |
|------|--------|-----------|
| `0609_01` (gallery) | `gallery_entries` | `perspective_service.py`, `perspective_routes.py` (갤러리 API) |
| `0609_02` (evaluation) | `employees`, `evaluations` | `user_data_manager.py`, `perspective_service.py` (`load_all_batches`) |

`perspective_service.py`는 양쪽에서 수정되므로 **구현 순서**: `0609_01` → `0609_02` 권장 (충돌 최소화).

> ⚠️ **주의**: `perspective_routes.py`가 사용자에 의해 이미 대규모 수정되었음 (새 엔드포인트 5개, `batch_title` 기능, `_resolve_output_mode` 가명 비활성화 등). `0609_02` 구현 시 `perspective_service.py`만 수정하고 `perspective_routes.py`는 건드리지 않도록 주의 — 이미 수정된 `perspective_routes.py`와 병합 충돌 방지.
>
> 또한 `deploy_session_service.py`에 `retry_failed_tasks()`가 추가되어 있음. `_init_db()` 수정 시 이 함수와 충돌하지 않도록 주의.

---

## 8. 테스트 시나리오

| ID | 시나리오 | 예상 결과 |
|----|----------|-----------|
| T-01 | 앱 첫 시작 (users/*.json 존재) | 자동 마이그레이션 → evaluations 건수 일치 |
| T-02 | 앱 재시작 (DB에 이미 데이터) | 마이그레이션 건너뜀 |
| T-03 | 배치 업로드 (batch_processor) | evaluations에 INSERT, 중복 fingerprint 무시 |
| T-04 | `load_all_batches()` 호출 | 9개 route 반환 구조 동일, 데이터 일치 |
| T-05 | 매트릭스 생성 (19,000명 규모 시뮬레이션) | 전체 파일 I/O 없이 DB 조회로 처리 시간 감소 |
| T-06 | 배치 삭제 (`remove_batch_from_all`) | 해당 batch_id evaluations 전량 삭제 |
| T-07 | 동일 평가 중복 업로드 | fingerprint 충돌 → 중복 삽입 없음 |
| T-08 | 롤백 | users/*.json 복원 + load_all_batches 파일 읽기 코드 활성화 |
| T-09 | 관리자 모드 조회 | `_enrich_with_real_ids()` 통해 실명 정상 복원 (pseudo_id → real_id) |
| T-10 | 일반 모드 조회 | `employee_results`에 pseudo_id만 노출, 실명 미포함 |
| T-11 | 마이그레이션 후 가명 일치 확인 | DB `employees.employee_id` 값이 기존 JSON 파일명(pseudo_id)과 일치 |

---

## 9. 위험도

| 위험 | 수준 | 대응 |
|------|------|------|
| 마이그레이션 중 fingerprint 계산 오류로 중복 삽입 | 중간 | 마이그레이션 후 건수 검증 (DB count vs JSON 합산) |
| `load_all_batches()` 반환 구조 미세 차이 → 하위 함수 오작동 | 높음 | 기존 users/*.json 기반 결과와 DB 결과 전수 비교 테스트 |
| `remove_batch_from_all()` 시그니처 유지(`employee_ids` 무시)가 혼동 유발 | 낮음 | 함수 docstring에 "DB 버전에서는 무시됨" 명시, 코드 리뷰 시 주의 |
| `get_user()`, `get_all_employee_results()` 제거 시 잠재적 호출부 누락 | 낮음 | 전수 검색 (`grep`)으로 외부 호출 없음 확인 완료. 제거 전 재검증 |
| 배치 삭제 후 employees 잔여 여부 정책 미결 | 낮음 | 기본: 평가 없는 employee 유지 (삭제 여부는 별도 결정) |
| deploy_sessions.db 파일 손상 시 갤러리 + 평가 모두 영향 | 중간 | `.sessions/` 폴더 주기적 백업 권장 (`0609_01`과 동일 위험) |
| `load_all_batches()` 성능: 19,000명 × 전체 evaluations 로드 | 중간 | 단일 JOIN 쿼리로 N+1 제거. 이후 캐싱·페이징 별도 계획. |
| `batch_info.unique_employees` 계산 방식 변경 | 중간 | 기존: `batch_summary`의 `employee_ids` 집합 + `users/*.json` 기반. DB 버전: `employees` 테이블 row 수만. 값이 다를 수 있으므로 T-04 테스트에서 전수 비교 필요. |
| `migrate_evaluations.py` 경로 의존성 | 낮음 | `scripts/migrate_evaluations.py` 위치 기준으로 경로 계산. `wordcloud_project/` 루트에서 실행 권장. |
| DB에 실명 직접 저장 실수 | 중간 | `upsert()` 호출 전 `batch_processor`가 가명화를 보장함. `upsert()` docstring에 "pseudo_id 전제" 명시. 마이그레이션 시 JSON 파일명(pseudo_id)과 `employee_id` 필드 불일치 여부 검증 필요. |
| `pseudonym_mappings.enc` 소실 시 실명 복원 불가 | 높음 | 이 계획 범위 밖. 기존 백업 정책 그대로 유지. DB 전환으로 위험이 증가하지는 않음. |
| `web/app.py` old format 재마이그레이션 | 중간 | `users/*.json` 삭제 후 `batch_summary` old format이 남아있으면 `migrate_from_old_format()`이 DB에 중복 삽입 가능. `_auto_migrate_evaluations()`로 교체 후 `migrate_from_old_format()` 제거 필요. |
| DEPRECATED `batch_routes.py` delete 엔드포인트 | 중간 | `evaluations` 테이블 정리 없이 batch 디렉토리만 삭제 → 고아 데이터 발생. `remove_batch_from_all()` 선행 호출 추가 또는 엔드포인트 제거 필요. |
| `batch_manager.delete_batch_directory()` 문서 미갱신 | 낮음 | docstring에 "users/*.json 미정리"라고 되어 있으나 DB 전환 후에는 "evaluations 테이블 미정리"로 업데이트 필요. |
| **병합 충돌**: `perspective_routes.py`가 사용자에 의해 이미 대규모 수정됨 | 높음 | `0609_02` 구현 시 `perspective_routes.py`를 수정하지 않고 `perspective_service.py`만 수정해야 함. `load_all_batches()` 반환 형식 변경이 `perspective_routes.py`의 새 엔드포인트(`api_generate_and_save_matrix` 등)에 영향을 주는지 확인 필요. |
| **병합 충돌**: `deploy_session_service.py`에 `retry_failed_tasks()` 추가됨 | 중간 | `_init_db()` 수정 시 기존 코드와 충돌하지 않도록 주의. DDL 추가는 `_init_db()` 함수 끝단에 삽입 권장. |
| `_resolve_output_mode` 가명 비활성화 | 낮음 | API 응답 레이어 변경으로 DB 저장/조회 로직에는 영향 없음. 가명화 아키텍처 자체는 유지됨. |

---

## 10. 구현 순서

> **핵심 원칙**: 마이그레이션 스크립트는 DB DAO가 완성된 후 실행 가능하므로, DAO 구현(단계 2~3)이 마이그레이션(단계 4)보다 선행되어야 한다.

| 단계 | 작업 | 검증 |
|------|------|------|
| 1 | `deploy_session_service.py` — `_init_db()`에 `employees` + `evaluations` + `schema_version` 테이블 DDL 추가. **주의**: `retry_failed_tasks()`가 이미 추가되어 있음 — DDL 삽입 위치를 함수 끝단으로 지정하여 충돌 방지 | 앱 시작 후 테이블 존재 확인 |
| 2 | `user_data_manager.py` — `_get_eval_conn()` 추가, `upsert()`, `remove_batch_from_all()` DB 전환. `get_user()`, `get_all_employee_results()` 제거 | `remove_batch()` 내부 로직 확인, `_get_eval_conn()` 연결 테스트 |
| 3 | `perspective_service.py` — `_get_eval_conn()` 임포트, `load_all_batches()` DB 읽기 전환, `_count_batches()` / `_load_batch_list()` 추가, old format fallback 제거. **주의**: `perspective_routes.py`는 이미 사용자에 의해 대규모 수정됨 — `perspective_service.py`만 수정하고 `perspective_routes.py`는 건드리지 않음 | 반환 구조 동일성 검증, 매트릭스 생성 정상 동작. `api_generate_and_save_matrix` 등 새 엔드포인트에서 `load_all_batches()` 결과를 정상 사용하는지 확인 |
| 4 | `scripts/migrate_evaluations.py` 작성 + 실행 | DB 건수 vs JSON 합산 일치 |
| 5 | 자동 마이그레이션 연결 (`deploy_session_service.py`의 별도 함수) | 앱 재배포 후 자동 이전 확인 |
| 6 | `web/app.py` — `migrate_from_old_format()` 호출을 `_auto_migrate_evaluations()`로 교체. `migrate_from_old_format()`은 `user_data_manager.py`에서 제거 대상 | 앱 시작 시 old format 재마이그레이션 미발생 |
| 7 | `batch_routes.py` — DEPRECATED `delete()` 엔드포인트에 `remove_batch_from_all()` 선행 호출 추가, 또는 엔드포인트 완전 제거 | 배치 삭제 후 `evaluations` 테이블 동시 정리 확인 |
| 8 | `batch_manager.py` — `delete_batch_directory()` docstring 업데이트 | "evaluations 테이블 미정리" 명시 확인 |
| 9 | 기존 `users/*.json` 파일 I/O 코드 제거 (검증 완료 후) | `grep users_dir` 결과 0건 |
