# 0609_01_gallery-db-migration — deploy_manifest.json → SQLite 전환 계획서

> 상태: Done | 작성일: 2026-06-09 | 완료일: 2026-06-09

---

## 수정 이력

| 날짜 | 변경 섹션 | 변경 요약 |
|------|-----------|-----------|
| 2026-06-09 | 전체 | 최초 작성 |
| 2026-06-09 | 6.1 | 최종 검토 갭 보완: `_auto_migrate_manifest()` 코드에 `.bak` 리네이밍 로직 추가 (§6.2 설명과 코드 불일치 해소) |
| 2026-06-09 | 전체 | **구현 완료**: `gallery_db_service.py` 신규, `deploy_session_service.py` DDL+마이그레이션 함수, `perspective_service.py` manifest 함수 교체, `perspective_routes.py` 갤러리 API 7개 교체 |

---

## 1. 배경 및 목적

### 1.1 문제 정의

`outputs/deploy_manifest.json`은 갤러리 결과물의 단일 인덱스 파일이다.
현재 구조에서 **새 필드가 추가될 때마다** 다음 문제가 발생한다.

- 기존 엔트리에 해당 필드가 없어 코드 전체에 `.get()` fallback 분기 영구 잔존
- 파일이 단일 flat JSON 배열이므로 수천~수만 엔트리 시 파싱 시간 선형 증가
- 필드 기반 검색·정렬을 위해 전체 파일을 메모리에 올려야 함
- FileLock으로 동시성 제어 중 — DB에서는 불필요

이번 `batch_title` 추가만으로도 7~8곳에 방어 코드가 생긴 사례가 대표적이다.

### 1.2 목표

| 목표 | 내용 |
|------|------|
| **스키마 일원화** | `gallery_entries` SQLite 테이블 단일 저장소로 통합 |
| **확장성 확보** | 새 필드 추가 = `ALTER TABLE ADD COLUMN` 1줄, fallback 코드 불필요 |
| **성능 개선** | 인덱스 기반 O(log n) 조회, 전체 파일 파싱 제거 |
| **동시성 안정화** | FileLock 제거, DB 트랜잭션으로 원자성 보장 |
| **점진적 전환** | 기존 manifest 파일 보존, 마이그레이션 스크립트로 1회 이전 |

---

## 2. 확장성 설계 원칙

### 2.1 컬럼 vs JSON blob

새 필드가 추가될 때 두 가지 선택지가 있다.

| 방식 | 적합한 경우 | 예시 |
|------|-------------|------|
| **전용 컬럼** | 검색·정렬·필터 대상 필드 | `batch_title`, `timestamp`, `source` |
| **`extra` JSON blob** | 검색 불필요, 향후 확장 여지 | 메모, 태그, 커스텀 설정 |

`extra TEXT` 컬럼을 두어 스키마 변경 없이 임의 필드를 저장할 수 있게 한다.
필드 조회 빈도가 높아지면 그 때 전용 컬럼으로 승격(`ALTER TABLE ADD COLUMN`)한다.

### 2.2 스키마 버전 관리

```sql
CREATE TABLE schema_version (
    version   INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    note      TEXT
);
```

컬럼 추가 시 버전 번호를 1씩 올린다. 앱 시작 시 현재 버전 확인 → 미적용 마이그레이션 자동 실행.

---

## 3. DB 스키마

### 3.1 `gallery_entries` 테이블

```sql
CREATE TABLE IF NOT EXISTS gallery_entries (
    -- 식별자
    id               TEXT PRIMARY KEY,
    employee_id      TEXT NOT NULL,
    deploy_name      TEXT,
    batch_title      TEXT,

    -- 시간
    timestamp        TEXT NOT NULL,          -- YYYYMMDD_HHMMSS
    created_at       TEXT DEFAULT (datetime('now')),

    -- 분류
    output_mode      TEXT DEFAULT 'real',    -- 'real' | 'pseudonym'
    source           TEXT DEFAULT 'deploy',  -- 'deploy' | 'matrix'
    analysis_type    TEXT,

    -- 분석 설정
    row_field        TEXT,
    row_values       TEXT,                   -- JSON 배열
    row_combine_all  INTEGER DEFAULT 0,

    -- 결과 이미지 경로
    images           TEXT,                   -- JSON { combined, positive, negative }
    row_results      TEXT,                   -- JSON { rowKey: { combined, ... } }

    -- 옵션 전체 (wordcloud 설정 등)
    options          TEXT,                   -- JSON

    -- 향후 확장용 — 스키마 변경 없이 임의 필드 저장
    extra            TEXT                    -- JSON blob
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_ge_employee    ON gallery_entries (employee_id);
CREATE INDEX IF NOT EXISTS idx_ge_timestamp   ON gallery_entries (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ge_batch_title ON gallery_entries (batch_title);
CREATE INDEX IF NOT EXISTS idx_ge_source      ON gallery_entries (source);
CREATE INDEX IF NOT EXISTS idx_ge_date        ON gallery_entries (substr(timestamp, 1, 8));
```

### 3.2 `schema_version` 테이블

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    note       TEXT
);
INSERT OR IGNORE INTO schema_version (version, applied_at, note)
    VALUES (1, datetime('now'), 'initial gallery_entries schema');
```

### 3.3 DB 위치

기존 `deploy_sessions.db`와 **같은 DB 파일**에 추가한다.

```python
# src/services/deploy_session_service.py 기준 경로
_DB_PATH = os.path.join(BASE_DIR, '..', '.sessions', 'deploy_sessions.db')
```

이유: 배포 세션과 갤러리는 같은 워크플로우 내 데이터이며, 파일을 분리하면 관리 포인트가 늘어난다.

---

## 4. 신규 서비스: `gallery_db_service.py`

`src/services/gallery_db_service.py`를 새로 만든다.
`perspective_service.py`의 manifest 관련 함수를 이 파일로 이동한다.

### 4.1 주요 함수

```python
def init_gallery_db():
    """gallery_entries 테이블 및 인덱스 생성. 앱 시작 시 호출."""

def upsert_entry(entry: dict) -> str:
    """엔트리 추가 또는 id 기준 업데이트. entry_id 반환."""

def get_entry(entry_id: str) -> dict | None:
    """단일 엔트리 조회."""

def list_entries(
    page=1, per_page=20,
    employee_id=None, source=None,
    output_mode=None, date_from=None, date_to=None,
    dates: set = None,
    batch_titles: set = None,
    is_admin=False,
) -> dict:
    """필터·페이징 적용 목록 조회. {total, items} 반환."""

def delete_entries(entry_ids: list[str]) -> dict:
    """엔트리 삭제. 연관 이미지 파일 삭제 포함."""

def get_distinct_dates(is_admin=False) -> list[str]:
    """고유 날짜(YYYYMMDD) 목록 반환."""

def get_distinct_batch_titles(is_admin=False) -> list[str]:
    """고유 batch_title 목록 반환."""

def migrate_from_manifest(manifest_path: str) -> dict:
    """deploy_manifest.json → gallery_entries 1회 마이그레이션."""
```

### 4.2 정렬 구현

```python
# batch_title 있는 항목 먼저(가나다 오름차순), timestamp 내림차순
ORDER BY
    CASE WHEN batch_title IS NULL OR batch_title = '' THEN 1 ELSE 0 END ASC,
    batch_title ASC,
    timestamp DESC
```

---

## 5. 변경 파일 목록

| 순서 | 파일 | 변경 유형 | 내용 |
|------|------|-----------|------|
| 1 | `src/services/gallery_db_service.py` | **신규** | gallery_entries CRUD, 마이그레이션 함수 |
| 2 | `src/services/perspective_service.py` | 수정 | `_append_to_deploy_manifest` → `gallery_db_service.upsert_entry` 호출로 교체. `_index_matrix_to_manifest` 동일. `DEPLOY_MANIFEST_PATH` 참조 제거. |
| 3 | `src/routes/perspective_routes.py` | 수정 | `api_deploy_gallery_list`, `api_deploy_gallery_detail`, `api_deploy_gallery_delete`, `api_deploy_gallery_dates`, `api_deploy_gallery_batch_titles` → `gallery_db_service` 호출로 교체 |
| 4 | `src/services/deploy_session_service.py` | 수정 | `_init_db()` 내부에 `init_gallery_db()` 호출 추가 |
| 5 | `plans/2026/0609_01_gallery-db-migration/migrate.py` | **신규** | 독립 실행 마이그레이션 스크립트 |

---

## 6. 마이그레이션 전략

### 6.1 자동 마이그레이션 (앱 시작 시)

```python
# deploy_session_service.py _init_db()에 추가
def _init_db():
    ...
    init_gallery_db()   # gallery_entries 테이블 생성
    _auto_migrate_manifest()   # manifest 파일이 있고 DB가 비어있으면 실행
```

```python
def _auto_migrate_manifest():
    count = conn.execute("SELECT COUNT(*) FROM gallery_entries").fetchone()[0]
    if count > 0:
        return   # 이미 데이터 있음
    manifest_path = DEPLOY_MANIFEST_PATH
    if os.path.exists(manifest_path):
        result = migrate_from_manifest(manifest_path)
        print(f"[GalleryDB] 마이그레이션 완료: {result['migrated']}건")
        # §6.2: 마이그레이션 완료 후 .bak으로 이름 변경 (롤백 대비 보존)
        import shutil
        shutil.move(manifest_path, manifest_path + '.bak')
```

### 6.2 기존 manifest 파일 처리

- 마이그레이션 완료 후 `deploy_manifest.json` → `deploy_manifest.json.bak` 으로 이름 변경
- 삭제하지 않음 (롤백 대비)
- 기존 파일 참조 코드는 `gallery_db_service` 전환 후 제거

### 6.3 롤백 계획

1. `deploy_manifest.json.bak` 복원
2. `gallery_db_service` 호출 코드를 기존 manifest 함수 호출로 되돌림
3. `gallery_entries` 테이블 DROP (데이터 재마이그레이션 가능하므로 손실 없음)

---

## 7. 향후 필드 추가 절차 (확장성 가이드)

새 필드가 필요할 때:

### Case A: 검색·정렬 대상 필드

```python
# gallery_db_service.py _MIGRATIONS 리스트에 추가
_MIGRATIONS = [
    # version 1: 초기 스키마 (생략)
    (2, "ALTER TABLE gallery_entries ADD COLUMN tags TEXT"),       # 예시
    (3, "ALTER TABLE gallery_entries ADD COLUMN rating INTEGER"),  # 예시
]

def _apply_migrations(conn):
    current = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0
    for version, sql in _MIGRATIONS:
        if version > current:
            conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_version VALUES (?, datetime('now'), ?)",
                (version, sql)
            )
```

→ 앱 재시작 시 자동 적용. 기존 엔트리는 NULL.

### Case B: 검색 불필요 필드 (즉시 저장 가능)

```python
entry['extra'] = json.dumps({'note': '...', 'custom_tag': '...'})
upsert_entry(entry)
```

→ 스키마 변경 없이 바로 저장. 나중에 빈도가 높아지면 Case A로 승격.

---

## 8. 테스트 시나리오

| ID | 시나리오 | 예상 결과 |
|----|----------|-----------|
| T-01 | 앱 첫 시작 (manifest 있음) | 자동 마이그레이션 실행, gallery_entries에 기존 데이터 이전 |
| T-02 | 앱 재시작 (DB에 이미 데이터) | 마이그레이션 건너뜀 |
| T-03 | 새 배포 저장 | gallery_entries에 INSERT, manifest 파일 미수정 |
| T-04 | 갤러리 목록 API | DB 조회, 정렬·필터 정상 동작 |
| T-05 | 배치 명칭 필터 | INDEX 사용 확인 (EXPLAIN QUERY PLAN) |
| T-06 | 항목 삭제 | gallery_entries DELETE + 이미지 파일 삭제 |
| T-07 | 신규 컬럼 추가 (`ALTER TABLE`) | 기존 엔트리 NULL, 신규 엔트리 정상 저장 |
| T-08 | `extra` 필드 사용 | JSON.loads 정상 파싱, 코드 변경 없이 저장·조회 |
| T-09 | 동시 저장 2건 | FileLock 없이 DB 트랜잭션으로 정상 처리 |
| T-10 | 롤백 시나리오 | manifest.bak 복원 후 기존 API 정상 동작 |

---

## 9. 위험도

| 위험 | 수준 | 대응 |
|------|------|------|
| 마이그레이션 중 앱 재시작 | 중간 | 트랜잭션 일괄 처리 (전체 성공 or 전체 롤백) |
| manifest.json 레거시 참조 코드 잔존 | 낮음 | `DEPLOY_MANIFEST_PATH` 전역 검색으로 미사용 참조 일괄 제거 |
| deploy_sessions.db 파일 손상 시 갤러리도 영향 | 중간 | 주기적 `.sessions/` 폴더 백업 권장. 장기적으로 DB 분리 검토. |
| SQLite 동시 쓰기 한계 (다중 worker) | 낮음 | WAL 모드 활성화 (`PRAGMA journal_mode=WAL`) |
| 기존 코드에서 manifest 직접 읽는 부분 누락 | 중간 | `deploy_manifest.json` grep으로 잔여 참조 확인 후 제거 |

---

## 10. 구현 순서

| 단계 | 작업 | 검증 |
|------|------|------|
| 1 | `gallery_db_service.py` 작성 — 스키마 + CRUD | 단위 테스트로 INSERT/SELECT/DELETE 확인 |
| 2 | `migrate_from_manifest()` 구현 + 독립 스크립트 | manifest → DB 이전 후 건수 일치 확인 |
| 3 | `perspective_service.py` — manifest 쓰기 함수 교체 | 새 배포 저장 후 DB에 엔트리 확인 |
| 4 | `perspective_routes.py` — 갤러리 API 교체 | 목록/상세/삭제/날짜/배치명 API 응답 확인 |
| 5 | 자동 마이그레이션 (`_init_db` 연결) | 앱 재시작 후 자동 이전 확인 |
| 6 | 잔여 manifest 참조 제거 | `grep DEPLOY_MANIFEST_PATH` 결과 0건 확인 |
