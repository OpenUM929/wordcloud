"""Deploy session service — SQLite-based chunked task tracking for large-scale deploy operations."""
import os
import json
import sqlite3
import uuid
from datetime import datetime

_DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '.sessions')
_DB_PATH = os.path.join(_DB_DIR, 'deploy_sessions.db')


def _get_conn():
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS deploy_sessions (
                session_id   TEXT PRIMARY KEY,
                created_at   TEXT NOT NULL,
                status       TEXT NOT NULL DEFAULT 'running',
                options      TEXT NOT NULL,
                total_count  INTEGER NOT NULL,
                completed_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                paused_at    TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS deploy_tasks (
                session_id    TEXT NOT NULL,
                employee_id   TEXT NOT NULL,
                status        TEXT NOT NULL DEFAULT 'pending',
                result_path   TEXT,
                error_message TEXT,
                assigned_at   TEXT,
                completed_at  TEXT,
                PRIMARY KEY (session_id, employee_id)
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_session_status ON deploy_tasks (session_id, status);

            -- gallery_entries (deploy_manifest.json 대체)
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

            -- employees + evaluations (users/*.json 대체)
            CREATE TABLE IF NOT EXISTS employees (
                employee_id  TEXT PRIMARY KEY,
                name         TEXT,
                department   TEXT,
                position     TEXT,
                updated_at   TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS evaluations (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id      TEXT NOT NULL REFERENCES employees(employee_id),
                evaluator_id     TEXT,
                evaluation_date  TEXT,
                batch_id         TEXT,
                data             TEXT NOT NULL,
                fingerprint      TEXT,
                created_at       TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_ev_employee  ON evaluations (employee_id);
            CREATE INDEX IF NOT EXISTS idx_ev_batch     ON evaluations (batch_id);
            CREATE INDEX IF NOT EXISTS idx_ev_evaluator ON evaluations (evaluator_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ev_fp ON evaluations (employee_id, fingerprint);

            -- batch_work_orders (배치 작업서: 설정 스냅샷 + 진행상황 영구 보존 → Resume 지원)
            CREATE TABLE IF NOT EXISTS batch_work_orders (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id             TEXT UNIQUE NOT NULL,
                batch_dir            TEXT NOT NULL,
                status               TEXT NOT NULL DEFAULT 'running',
                settings             TEXT NOT NULL,
                file_info            TEXT NOT NULL,
                total_employees      INTEGER DEFAULT 0,
                processed_employees  INTEGER DEFAULT 0,
                success_count        INTEGER DEFAULT 0,
                error_count          INTEGER DEFAULT 0,
                total_rows           INTEGER DEFAULT 0,
                completed_employees  TEXT DEFAULT '[]',
                created_at           TEXT DEFAULT (datetime('now','localtime')),
                updated_at           TEXT DEFAULT (datetime('now','localtime')),
                completed_at         TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_wo_status ON batch_work_orders (status);
            CREATE INDEX IF NOT EXISTS idx_wo_created ON batch_work_orders (created_at DESC);

            -- batch_work_order_items (작업서별 완료 직원 목록 — 1직원 1행, 대용량 O(델타) append)
            CREATE TABLE IF NOT EXISTS batch_work_order_items (
                batch_id    TEXT NOT NULL,
                employee_id TEXT NOT NULL,
                PRIMARY KEY (batch_id, employee_id)
            );

            -- 스키마 버전 관리
            CREATE TABLE IF NOT EXISTS schema_version (
                version    INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL,
                note       TEXT
            );
            INSERT OR IGNORE INTO schema_version (version, applied_at, note)
                VALUES (1, datetime('now'), 'initial: gallery_entries, employees, evaluations');
        """)
        conn.commit()
    finally:
        conn.close()


def _apply_schema_migrations():
    """스키마 버전별 마이그레이션 실행."""
    conn = _get_conn()
    try:
        current = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version").fetchone()[0]

        if current < 2:
            conn.execute("DROP INDEX IF EXISTS idx_ev_fp")
            conn.execute("DELETE FROM evaluations")
            conn.execute("DELETE FROM employees")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_ev_fp ON evaluations (employee_id, batch_id, fingerprint)"
            )
            conn.execute(
                "INSERT INTO schema_version (version, applied_at, note) VALUES (2, datetime('now'), ?)",
                ('fix fingerprint index scope: (employee_id, batch_id, fingerprint)',)
            )
            conn.commit()
            print("[DB] Schema v2: fingerprint 인덱스 재정의, 평가 데이터 초기화 완료")
            current = 2

        if current < 3:
            # 동일 직원의 동일 평가가 배치가 달라도 중복 저장되지 않도록
            # UNIQUE 범위를 (employee_id, batch_id, fingerprint) → (employee_id, fingerprint)로 축소.
            # 기존 중복 행은 id가 가장 작은(먼저 삽입된) 행만 남기고 제거.
            conn.execute("""
                DELETE FROM evaluations
                WHERE id NOT IN (
                    SELECT MIN(id) FROM evaluations
                    GROUP BY employee_id, fingerprint
                )
            """)
            conn.execute("DROP INDEX IF EXISTS idx_ev_fp")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_ev_fp ON evaluations (employee_id, fingerprint)"
            )
            conn.execute(
                "INSERT INTO schema_version (version, applied_at, note) VALUES (3, datetime('now'), ?)",
                ('dedup: unique index (employee_id, fingerprint) — no cross-batch duplicates',)
            )
            conn.commit()
            print("[DB] Schema v3: 배치 간 중복 평가 제거, 인덱스 재정의 완료")
            current = 3

        if current < 4:
            conn.execute("ALTER TABLE evaluations ADD COLUMN sentiment_corrections TEXT DEFAULT '{}'")
            conn.execute(
                "INSERT INTO schema_version (version, applied_at, note) VALUES (4, datetime('now'), ?)",
                ('add sentiment_corrections column for sentence-level sentiment override',)
            )
            conn.commit()
            print("[DB] Schema v4: sentiment_corrections 컬럼 추가 완료")
            current = 4

        if current < 5:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS acquired_sentences (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    sentence_text   TEXT NOT NULL,
                    user_label      TEXT CHECK(user_label IN ('positive','negative','neutral')),
                    model_label     TEXT CHECK(model_label IN ('positive','negative','neutral')),
                    confidence      REAL DEFAULT 0.0,
                    source_employee_id   TEXT DEFAULT '',
                    source_evaluation_id TEXT DEFAULT '',
                    source_batch_id      TEXT DEFAULT '',
                    sentence_index        INTEGER DEFAULT 0,
                    db_id                 INTEGER DEFAULT 0,
                    context         TEXT DEFAULT '',
                    memo            TEXT DEFAULT '',
                    analysis_results TEXT DEFAULT '{}',
                    created_at      TEXT DEFAULT (datetime('now','localtime')),
                    updated_at      TEXT DEFAULT (datetime('now','localtime')),
                    UNIQUE(sentence_text, source_evaluation_id, sentence_index)
                );
            """)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at, note) VALUES (5, datetime('now'), ?)",
                ('add acquired_sentences table for corpus collection',)
            )
            conn.commit()
            print("[DB] Schema v5: acquired_sentences 테이블 추가 완료")
            current = 5

        if current < 6:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS profanity_employees (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id        TEXT NOT NULL,
                    employee_id     TEXT NOT NULL,
                    profanity_count INTEGER NOT NULL,
                    profanity_words TEXT,
                    created_at      TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_pe_batch ON profanity_employees (batch_id);
                CREATE INDEX IF NOT EXISTS idx_pe_employee ON profanity_employees (employee_id);

                CREATE TABLE IF NOT EXISTS profanity_sentences (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    profanity_employee_id INTEGER NOT NULL,
                    original_text       TEXT,
                    filtered_text       TEXT,
                    detected_words      TEXT,
                    evaluator_id        TEXT,
                    FOREIGN KEY (profanity_employee_id) REFERENCES profanity_employees(id) ON DELETE CASCADE
                );
            """)
            conn.execute(
                "INSERT INTO schema_version (version, applied_at, note) VALUES (6, datetime('now'), ?)",
                ('add profanity_employees and profanity_sentences tables for profanity tracking',)
            )
            conn.commit()
            print("[DB] Schema v6: profanity_employees, profanity_sentences 테이블 추가 완료")
            current = 6

        if current < 7:
            # acquired_sentences에 분류 시점 KoTE 값 + 출처 구분 컬럼 추가 (additive, CHECK 재빌드 없음)
            for ddl in (
                "ALTER TABLE acquired_sentences ADD COLUMN kote_pos       REAL",
                "ALTER TABLE acquired_sentences ADD COLUMN kote_neg       REAL",
                "ALTER TABLE acquired_sentences ADD COLUMN kote_neutral   REAL",
                "ALTER TABLE acquired_sentences ADD COLUMN override_score REAL",
                "ALTER TABLE acquired_sentences ADD COLUMN source_kind    TEXT DEFAULT ''",
            ):
                try:
                    conn.execute(ddl)
                except sqlite3.OperationalError as e:
                    # 컬럼이 이미 존재하면 무시 (재실행 안전)
                    if 'duplicate column name' not in str(e).lower():
                        raise
            conn.execute(
                "INSERT INTO schema_version (version, applied_at, note) VALUES (7, datetime('now'), ?)",
                ('add kote_pos/neg/neutral, override_score, source_kind to acquired_sentences',)
            )
            conn.commit()
            print("[DB] Schema v7: acquired_sentences KoTE 값·source_kind 컬럼 추가 완료")
            current = 7

        if current < 8:
            conn.execute("ALTER TABLE deploy_sessions ADD COLUMN started_at TEXT")
            conn.execute(
                "INSERT INTO schema_version (version, applied_at, note) VALUES (8, datetime('now'), ?)",
                ('add started_at column to deploy_sessions for elapsed time display',)
            )
            conn.commit()
            print("[DB] Schema v8: deploy_sessions.started_at 컬럼 추가 완료")
            current = 8

        if current < 9:
            # 배치 병합(batch_merge_service) 지원 — 병합 이력 테이블 + 행 단위 원본 배치 추적.
            # orig_batch_id: 병합으로 batch_id가 재라벨되기 전 원래 값을 행마다 보존한다.
            # moved_count만으로는 어느 평가가 어느 원본 배치였는지 특정할 수 없어(R-1),
            # 되돌리기(수동 복구) 시 행 단위로 항상 원본을 알 수 있도록 컬럼으로 둔다.
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS batch_merges (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    merged_batch_id  TEXT NOT NULL,
                    source_batch_id  TEXT NOT NULL,
                    moved_count      INTEGER DEFAULT 0,
                    source_status    TEXT DEFAULT '',
                    created_at       TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_bm_merged ON batch_merges (merged_batch_id);
                CREATE INDEX IF NOT EXISTS idx_bm_source ON batch_merges (source_batch_id);
            """)
            try:
                conn.execute("ALTER TABLE evaluations ADD COLUMN orig_batch_id TEXT DEFAULT ''")
            except sqlite3.OperationalError as e:
                if 'duplicate column name' not in str(e).lower():
                    raise
            conn.execute(
                "INSERT INTO schema_version (version, applied_at, note) VALUES (9, datetime('now'), ?)",
                ('add batch_merges table + evaluations.orig_batch_id for batch merge feature',)
            )
            conn.commit()
            print("[DB] Schema v9: batch_merges 테이블, evaluations.orig_batch_id 컬럼 추가 완료")
            current = 9

        if current < 10:
            # 20_01: 그래프 저장(saveGraph)과 제출용 저장(saveDeploy)이 deploy_sessions를
            # 공유하면서 재개 시 항상 saveDeploy 경로로 처리되어 source 태그가 갈리던 버그 수정.
            # kind로 세션 종류를 기록해 재개 시 올바른 저장 함수로 분기한다.
            try:
                conn.execute("ALTER TABLE deploy_sessions ADD COLUMN kind TEXT DEFAULT 'deploy'")
            except sqlite3.OperationalError as e:
                if 'duplicate column name' not in str(e).lower():
                    raise
            conn.execute(
                "INSERT INTO schema_version (version, applied_at, note) VALUES (10, datetime('now'), ?)",
                ('add kind column to deploy_sessions to distinguish deploy/graph save sessions on resume',)
            )
            conn.commit()
            print("[DB] Schema v10: deploy_sessions.kind 컬럼 추가 완료")
            current = 10
    finally:
        conn.close()


def _cleanup_stale_running_orders():
    """서버 기동 시 running 상태의 작업서를 interrupted로 전환 (좀비 배치 정리).
    
    서버가 강제 종료되면 백그라운드 배치 스레드도 함께 죽지만
    DB의 status='running'은 그대로 남는다. 서버 기동 시점에 이들을
    'interrupted'로 표시하여 사용자가 Resume할 수 있게 한다.
    """
    conn = _get_conn()
    try:
        conn.execute("""
            UPDATE batch_work_orders
            SET status = 'interrupted',
                updated_at = datetime('now','localtime')
            WHERE status = 'running'
        """)
        conn.commit()
    finally:
        conn.close()


def _auto_migrate_manifest():
    """deploy_manifest.json → gallery_entries 자동 마이그레이션 (DB 비어있을 때 1회)."""
    conn = _get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM gallery_entries").fetchone()[0]
        if count > 0:
            return
    finally:
        conn.close()

    from src.config.settings import OUTPUTS_DIR_PATH
    manifest_path = os.path.join(OUTPUTS_DIR_PATH, 'deploy_manifest.json')
    if not os.path.exists(manifest_path):
        return

    from src.services.gallery_db_service import migrate_from_manifest
    result = migrate_from_manifest(manifest_path)
    print(f"[GalleryDB] 마이그레이션 완료: {result['migrated']}건")
    import shutil
    shutil.move(manifest_path, manifest_path + '.bak')


def _auto_migrate_evaluations():
    """users/*.json → evaluations 자동 마이그레이션 (DB 비어있을 때 1회)."""
    from src.config.settings import PROCESSED_DATA_DIR_PATH
    conn = _get_conn()
    try:
        count = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
        if count > 0:
            return
    finally:
        conn.close()

    users_dir = os.path.join(PROCESSED_DATA_DIR_PATH, 'users')
    if not os.path.exists(users_dir):
        return

    import subprocess
    import sys
    script = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts', 'migrate_evaluations.py')
    if not os.path.exists(script):
        print(f"[EvalDB] 마이그레이션 스크립트 없음: {script}")
        return
    print("[EvalDB] 자동 마이그레이션 실행 중...")
    subprocess.run([sys.executable, script], check=False)
    import shutil
    shutil.move(users_dir, users_dir + '.bak')
    print(f"[EvalDB] 마이그레이션 완료: {users_dir} → {users_dir}.bak")


_init_db()
_apply_schema_migrations()
_cleanup_stale_running_orders()
_auto_migrate_manifest()


def create_session(options, employee_ids, kind='deploy'):
    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO deploy_sessions (session_id, created_at, status, options, total_count, started_at, kind)
            VALUES (?, ?, 'running', ?, ?, ?, ?)
            """,
            (session_id, now, json.dumps(options, ensure_ascii=False), len(employee_ids), now, kind),
        )
        rows = [(session_id, eid) for eid in employee_ids]
        conn.executemany(
            "INSERT INTO deploy_tasks (session_id, employee_id) VALUES (?, ?)", rows
        )
        conn.commit()
    finally:
        conn.close()
    return session_id


def cleanup_old_sessions(days=7):
    cutoff = f"datetime('now', '-{days} days')"
    conn = _get_conn()
    try:
        conn.execute(
            f"""
            DELETE FROM deploy_tasks WHERE session_id IN (
                SELECT session_id FROM deploy_sessions
                 WHERE status IN ('completed', 'failed')
                   AND COALESCE(completed_at, paused_at, created_at) < {cutoff}
            )
            """
        )
        conn.execute(
            f"""
            DELETE FROM deploy_sessions
             WHERE status IN ('completed', 'failed')
               AND COALESCE(completed_at, paused_at, created_at) < {cutoff}
            """
        )
        conn.commit()
    finally:
        conn.close()


def _restore_orphans(conn, session_id=None):
    if session_id:
        conn.execute(
            """
            UPDATE deploy_tasks
               SET status = 'pending', assigned_at = NULL
             WHERE session_id = ?
               AND status = 'processing'
               AND assigned_at < datetime('now', '-5 minutes')
            """,
            (session_id,),
        )
    else:
        conn.execute(
            """
            UPDATE deploy_tasks
               SET status = 'pending', assigned_at = NULL
             WHERE status = 'processing'
               AND assigned_at < datetime('now', '-5 minutes')
            """
        )


def allocate_chunk(session_id, count=50):
    conn = _get_conn()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            _restore_orphans(conn, session_id)
            rows = conn.execute(
                """
                SELECT employee_id FROM deploy_tasks
                 WHERE session_id = ? AND status = 'pending'
                 LIMIT ?
                """,
                (session_id, count),
            ).fetchall()
            ids = [r[0] for r in rows]
            if ids:
                placeholders = ','.join('?' * len(ids))
                conn.execute(
                    f"""
                    UPDATE deploy_tasks
                       SET status = 'processing', assigned_at = datetime('now')
                     WHERE session_id = ? AND employee_id IN ({placeholders})
                    """,
                    (session_id, *ids),
                )
        return ids
    finally:
        conn.close()


def report_chunk(session_id, completed_items, failed_items):
    """
    completed_items: list of str (employee_id) or dict {employee_id, result_data}
    """
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        with conn:
            for item in completed_items:
                if isinstance(item, str):
                    eid, result_json = item, None
                else:
                    eid = item.get('employee_id')
                    rd = item.get('result_data')
                    result_json = json.dumps(rd, ensure_ascii=False) if rd else None
                conn.execute(
                    """
                    UPDATE deploy_tasks
                       SET status = 'completed', completed_at = ?,
                           result_path = ?
                     WHERE session_id = ? AND employee_id = ?
                    """,
                    (now, result_json, session_id, eid),
                )
            for item in failed_items:
                eid = item.get('employee_id')
                error = item.get('error', '')
                conn.execute(
                    """
                    UPDATE deploy_tasks
                       SET status = 'failed', error_message = ?, completed_at = ?
                     WHERE session_id = ? AND employee_id = ?
                    """,
                    (error, now, session_id, eid),
                )
            conn.execute(
                """
                UPDATE deploy_sessions
                   SET completed_count = (
                       SELECT COUNT(*) FROM deploy_tasks WHERE session_id = ? AND status = 'completed'
                   ),
                   failed_count = (
                       SELECT COUNT(*) FROM deploy_tasks WHERE session_id = ? AND status = 'failed'
                   )
                 WHERE session_id = ?
                """,
                (session_id, session_id, session_id),
            )
        _update_session_status(session_id)
    finally:
        conn.close()


def _update_session_status(session_id):
    conn = _get_conn()
    try:
        total = conn.execute(
            "SELECT total_count FROM deploy_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM deploy_tasks WHERE session_id = ? AND status = 'pending'",
            (session_id,),
        ).fetchone()[0]
        processing = conn.execute(
            "SELECT COUNT(*) FROM deploy_tasks WHERE session_id = ? AND status = 'processing'",
            (session_id,),
        ).fetchone()[0]

        if pending == 0 and processing == 0:
            conn.execute(
                "UPDATE deploy_sessions SET status = ?, completed_at = ? WHERE session_id = ?",
                ('completed', datetime.now().isoformat(), session_id),
            )
            conn.commit()
    finally:
        conn.close()


def get_active_sessions():
    conn = _get_conn()
    try:
        _restore_orphans(conn)
        conn.commit()
        rows = conn.execute(
            """
            SELECT session_id, created_at, status, options, total_count,
                   completed_count, failed_count, paused_at, kind
              FROM deploy_sessions
             WHERE status IN ('running', 'paused')
             ORDER BY created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def resume_session(session_id):
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE deploy_sessions SET status = 'running', paused_at = NULL WHERE session_id = ?",
            (session_id,),
        )
        conn.commit()
    finally:
        conn.close()


def cancel_session(session_id):
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE deploy_sessions SET status = 'failed', paused_at = ? WHERE session_id = ?",
            (datetime.now().isoformat(), session_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_session_progress(session_id):
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM deploy_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def get_session_tasks(session_id):
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT employee_id, status, result_path, error_message, completed_at
              FROM deploy_tasks
             WHERE session_id = ?
             ORDER BY rowid
            """,
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def retry_failed_tasks(session_id):
    """세션 내 실패한 태스크를 pending으로 리셋하고 세션을 running 상태로 복원."""
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


def get_recently_completed_sessions(hours=24):
    conn = _get_conn()
    try:
        rows = conn.execute(
            f"""
            SELECT session_id, created_at, status, options, total_count,
                   completed_count, failed_count, completed_at
              FROM deploy_sessions
             WHERE status = 'completed'
               AND completed_at >= datetime('now', '-{hours} hours')
             ORDER BY completed_at DESC
             LIMIT 5
            """,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
