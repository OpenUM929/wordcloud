"""Gallery DB service — gallery_entries CRUD and migration from deploy_manifest.json."""
import os
import json
import sqlite3

from src.config.settings import OUTPUTS_DIR_PATH

_DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '.sessions')
_DB_PATH = os.path.join(_DB_DIR, 'deploy_sessions.db')


def _get_conn():
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")  # 병렬 저장 시 쓰기 경합 대기(즉시 lock 에러 방지, 작업5)
    conn.row_factory = sqlite3.Row
    return conn


def init_gallery_db():
    """gallery_entries 테이블 및 인덱스 생성. _init_db()에서 호출."""
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS gallery_entries (
                id               TEXT PRIMARY KEY,
                employee_id      TEXT NOT NULL,
                deploy_name      TEXT,
                batch_title      TEXT,
                timestamp        TEXT NOT NULL,
                created_at       TEXT DEFAULT (datetime('now')),
                output_mode      TEXT DEFAULT 'real',
                source           TEXT DEFAULT 'deploy',
                analysis_type    TEXT,
                row_field        TEXT,
                row_values       TEXT,
                row_combine_all  INTEGER DEFAULT 0,
                images           TEXT,
                row_results      TEXT,
                options          TEXT,
                extra            TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_ge_employee    ON gallery_entries (employee_id);
            CREATE INDEX IF NOT EXISTS idx_ge_timestamp   ON gallery_entries (timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_ge_batch_title ON gallery_entries (batch_title);
            CREATE INDEX IF NOT EXISTS idx_ge_source      ON gallery_entries (source);
            CREATE INDEX IF NOT EXISTS idx_ge_date        ON gallery_entries (substr(timestamp, 1, 8));
            CREATE TABLE IF NOT EXISTS schema_version (
                version    INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                note       TEXT
            );
            INSERT OR IGNORE INTO schema_version (version, applied_at, note)
                VALUES (1, datetime('now'), 'initial gallery_entries schema');
        """)
        conn.commit()
    finally:
        conn.close()


def upsert_entry(entry):
    """엔트리 추가 또는 id 기준 업데이트. entry_id 반환."""
    import uuid as _uuid
    entry_id = entry.get('id') or str(_uuid.uuid4())
    conn = _get_conn()
    try:
        conn.execute("""
            INSERT INTO gallery_entries
                (id, employee_id, deploy_name, batch_title, timestamp, output_mode, source,
                 analysis_type, row_field, row_values, row_combine_all, images, row_results, options, extra)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                employee_id     = excluded.employee_id,
                deploy_name     = excluded.deploy_name,
                batch_title     = excluded.batch_title,
                timestamp       = excluded.timestamp,
                output_mode     = excluded.output_mode,
                source          = excluded.source,
                analysis_type   = excluded.analysis_type,
                row_field       = excluded.row_field,
                row_values      = excluded.row_values,
                row_combine_all = excluded.row_combine_all,
                images          = excluded.images,
                row_results     = excluded.row_results,
                options         = excluded.options,
                extra           = excluded.extra
        """, (
            entry_id,
            entry.get('employee_id', ''),
            entry.get('deploy_name'),
            entry.get('batch_title') or None,
            entry.get('timestamp', ''),
            entry.get('output_mode', 'real'),
            entry.get('source', 'deploy'),
            entry.get('analysis_type'),
            entry.get('row_field'),
            json.dumps(entry.get('row_values'), ensure_ascii=False) if entry.get('row_values') is not None else None,
            1 if entry.get('row_combine_all') else 0,
            json.dumps(entry.get('images') or {}, ensure_ascii=False),
            json.dumps(entry.get('row_results') or {}, ensure_ascii=False),
            json.dumps(entry.get('options') or {}, ensure_ascii=False),
            json.dumps(entry['extra'], ensure_ascii=False) if entry.get('extra') is not None else None,
        ))
        conn.commit()
    finally:
        conn.close()
    return entry_id


def _row_to_dict(row):
    d = dict(row)
    for key in ('images', 'row_results', 'options'):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                d[key] = {}
        else:
            d[key] = {}
    if d.get('row_values'):
        try:
            d['row_values'] = json.loads(d['row_values'])
        except Exception:
            pass
    if d.get('extra'):
        try:
            d['extra'] = json.loads(d['extra'])
        except Exception:
            pass
    d['row_combine_all'] = bool(d.get('row_combine_all'))
    return d


def get_entry(entry_id):
    """단일 엔트리 조회."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM gallery_entries WHERE id = ?", (entry_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def list_entries(
    page=1, per_page=20, fetch_all=False,
    employee_id=None, source=None,
    output_mode=None, date_from=None, date_to=None,
    dates=None, batch_titles=None,
    is_admin=False,
):
    """필터·페이징 적용 목록 조회. {total, entries} 반환."""
    conditions = []
    params = []

    if not is_admin:
        conditions.append("output_mode != 'real'")

    if employee_id:
        conditions.append("employee_id = ?")
        params.append(employee_id)

    if source:
        conditions.append("source = ?")
        params.append(source)

    if output_mode:
        conditions.append("output_mode = ?")
        params.append(output_mode)

    if date_from:
        conditions.append("substr(timestamp, 1, 8) >= ?")
        params.append(date_from)

    if date_to:
        conditions.append("substr(timestamp, 1, 8) <= ?")
        params.append(date_to)

    if dates:
        ph = ','.join('?' for _ in dates)
        conditions.append(f"substr(timestamp, 1, 8) IN ({ph})")
        params.extend(sorted(dates))

    if batch_titles:
        ph = ','.join('?' for _ in batch_titles)
        conditions.append(f"batch_title IN ({ph})")
        params.extend(sorted(batch_titles))

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    order = (
        "ORDER BY "
        "CASE WHEN batch_title IS NULL OR batch_title = '' THEN 1 ELSE 0 END ASC, "
        "batch_title ASC, timestamp DESC"
    )

    conn = _get_conn()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM gallery_entries {where}", params
        ).fetchone()[0]

        if fetch_all:
            # 슬림 페이로드: 삭제/다운로드 선택용 — 이미지 JSON 미파싱, 컬럼 값만 반환.
            # (전 행 images/row_results JSON 파싱·MB 단위 전송 제거 → 서버 CPU·전송량↓)
            rows = conn.execute(
                f"SELECT id, employee_id, deploy_name, batch_title, timestamp, "
                f"output_mode, source FROM gallery_entries {where} {order}",
                params
            ).fetchall()
            entries = [{
                'id': r['id'],
                'employee_id': r['employee_id'],
                'deploy_name': r['deploy_name'],
                'batch_title': r['batch_title'],
                'display_title': r['batch_title'] or r['deploy_name'] or r['employee_id'],
                'timestamp': r['timestamp'],
                'output_mode': r['output_mode'],
                'source': r['source'] or 'deploy',
            } for r in rows]
            return {'total': total, 'entries': entries}

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"SELECT * FROM gallery_entries {where} {order} LIMIT ? OFFSET ?",
            params + [per_page, offset]
        ).fetchall()

        entries = []
        for row in rows:
            e = _row_to_dict(row)
            images = e.get('images', {})
            row_results = e.get('row_results', {})
            top_count = sum(1 for v in images.values() if v)
            row_count = sum(
                1 for rv in row_results.values()
                for v in (rv.values() if isinstance(rv, dict) else [])
                if v
            )
            entries.append({
                'id': e['id'],
                'employee_id': e.get('employee_id'),
                'deploy_name': e.get('deploy_name'),
                'batch_title': e.get('batch_title'),
                'display_title': e.get('batch_title') or e.get('deploy_name') or e.get('employee_id'),
                'timestamp': e.get('timestamp'),
                'output_mode': e.get('output_mode'),
                'source': e.get('source', 'deploy'),
                'image_count': top_count + row_count,
                'thumbnail_url': images.get('combined'),
            })

        return {'total': total, 'entries': entries}
    finally:
        conn.close()


def delete_entries(entry_ids):
    """엔트리 삭제. 연관 이미지 파일 삭제 포함."""
    if not entry_ids:
        return {'deleted_count': 0, 'file_errors': []}

    id_list = list(entry_ids)
    ph = ','.join('?' for _ in id_list)

    conn = _get_conn()
    file_errors = []
    try:
        rows = conn.execute(
            f"SELECT * FROM gallery_entries WHERE id IN ({ph})", id_list
        ).fetchall()

        if not rows:
            return {'deleted_count': 0, 'file_errors': [], 'not_found': True}

        def _url_to_path(url):
            clean = url.split('?')[0]
            if clean.startswith('/outputs/'):
                return os.path.join(OUTPUTS_DIR_PATH, clean[len('/outputs/'):])
            return None

        for row in rows:
            e = _row_to_dict(row)
            urls = [v for v in e.get('images', {}).values() if v]
            for rv in e.get('row_results', {}).values():
                if isinstance(rv, dict):
                    urls.extend(v for v in rv.values() if v)
            for url in urls:
                path = _url_to_path(url)
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as ex:
                        file_errors.append(str(ex))

        cursor = conn.execute(
            f"DELETE FROM gallery_entries WHERE id IN ({ph})", id_list
        )
        conn.commit()
        return {'deleted_count': cursor.rowcount, 'file_errors': file_errors}
    finally:
        conn.close()


def get_distinct_dates(is_admin=False):
    """고유 날짜(YYYYMMDD) 목록 반환."""
    conn = _get_conn()
    try:
        where = "" if is_admin else "WHERE output_mode != 'real'"
        rows = conn.execute(
            f"SELECT DISTINCT substr(timestamp, 1, 8) d FROM gallery_entries {where} ORDER BY d"
        ).fetchall()
        return [r[0] for r in rows if r[0]]
    finally:
        conn.close()


def get_distinct_batch_titles(is_admin=False):
    """고유 batch_title 목록 반환."""
    conn = _get_conn()
    try:
        conds = ["batch_title IS NOT NULL", "batch_title != ''"]
        if not is_admin:
            conds.append("output_mode != 'real'")
        where = "WHERE " + " AND ".join(conds)
        rows = conn.execute(
            f"SELECT DISTINCT batch_title FROM gallery_entries {where} ORDER BY batch_title"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def get_entries_by_ids(entry_ids, is_admin=False):
    """여러 ID로 전체 엔트리 조회 (이미지·row_results 포함)."""
    if not entry_ids:
        return []
    id_list = list(entry_ids)
    ph = ','.join('?' for _ in id_list)
    conn = _get_conn()
    try:
        rows = conn.execute(
            f"SELECT * FROM gallery_entries WHERE id IN ({ph})", id_list
        ).fetchall()
        result = []
        for row in rows:
            e = _row_to_dict(row)
            if not is_admin and e.get('output_mode') == 'real':
                continue
            result.append(e)
        return result
    finally:
        conn.close()


def check_batch_title(batch_title):
    """배치 명칭 중복 확인. {exists, count, sources} 반환."""
    if not batch_title:
        return {'exists': False, 'count': 0, 'sources': []}
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT source FROM gallery_entries WHERE batch_title = ?",
            (batch_title,)
        ).fetchall()
        sources = list({r[0] for r in rows if r[0]})
        return {'exists': len(rows) > 0, 'count': len(rows), 'sources': sources}
    finally:
        conn.close()


def migrate_from_manifest(manifest_path):
    """deploy_manifest.json → gallery_entries 1회 마이그레이션."""
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    entries = manifest.get('entries', [])
    migrated = 0
    for entry in entries:
        try:
            upsert_entry(entry)
            migrated += 1
        except Exception:
            pass

    return {'migrated': migrated}
