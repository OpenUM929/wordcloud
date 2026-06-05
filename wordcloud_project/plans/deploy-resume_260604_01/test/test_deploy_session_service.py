"""T4. deploy_session_service unit tests."""
import os
import sqlite3
import threading
import pytest

import src.services.deploy_session_service as dss


class TestT4DeploySessionService:
    """T4-1 ~ T4-5"""

    def test_t4_1_chunk_allocation_atomicity(self, tmp_db_path, monkeypatch):
        """10개 스레드 동시 allocate_chunk → 중복 없이 200개 모두 할당"""
        # ensure fresh DB for this test
        monkeypatch.setattr(dss, '_DB_PATH', tmp_db_path)
        dss._init_db()

        session_id = dss.create_session({}, [f"U{i:04d}" for i in range(200)])

        results = []
        lock = threading.Lock()

        def worker():
            chunk = dss.allocate_chunk(session_id, 50)
            with lock:
                results.extend(chunk)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 200, f"Expected 200, got {len(results)}"
        assert len(set(results)) == 200, "Duplicate allocation detected"

    def test_t4_2_orphan_recovery_not_triggered_under_5min(self, tmp_db_path, monkeypatch):
        """3분 경과 태스크는 고아 복원 안 됨"""
        monkeypatch.setattr(dss, '_DB_PATH', tmp_db_path)
        dss._init_db()

        session_id = dss.create_session({}, ['U001', 'U002', 'U003'])
        # allocate to put them into processing
        dss.allocate_chunk(session_id, 3)

        # Manually set assigned_at to 3 minutes ago via direct SQL
        conn = sqlite3.connect(tmp_db_path)
        three_mins_ago = "datetime('now', '-3 minutes')"
        conn.execute(
            f"UPDATE deploy_tasks SET assigned_at = {three_mins_ago} WHERE session_id = ?",
            (session_id,)
        )
        conn.commit()
        conn.close()

        # trigger orphan recovery via allocate_chunk
        dss.allocate_chunk(session_id, 1)

        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT status FROM deploy_tasks WHERE session_id = ?", (session_id,)
        ).fetchall()
        conn.close()

        statuses = [r['status'] for r in rows]
        assert all(s == 'processing' for s in statuses), f"Some tasks were recovered too early: {statuses}"

    def test_t4_3_orphan_recovery_triggered_over_5min(self, tmp_db_path, monkeypatch):
        """6분 경과 태스크는 고아 복원 됨 (pending으로)"""
        monkeypatch.setattr(dss, '_DB_PATH', tmp_db_path)
        dss._init_db()

        session_id = dss.create_session({}, ['U001', 'U002', 'U003'])
        dss.allocate_chunk(session_id, 3)

        conn = sqlite3.connect(tmp_db_path)
        six_mins_ago = "datetime('now', '-6 minutes')"
        conn.execute(
            f"UPDATE deploy_tasks SET assigned_at = {six_mins_ago} WHERE session_id = ?",
            (session_id,)
        )
        conn.commit()
        conn.close()

        # Trigger orphan recovery without allocating new tasks
        dss.get_active_sessions()

        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT status FROM deploy_tasks WHERE session_id = ?", (session_id,)
        ).fetchall()
        conn.close()

        statuses = [r['status'] for r in rows]
        assert all(s == 'pending' for s in statuses), f"Orphan recovery failed: {statuses}"

    def test_t4_4_session_auto_completion(self, tmp_db_path, monkeypatch):
        """모든 태스크 completed → 세션 completed"""
        monkeypatch.setattr(dss, '_DB_PATH', tmp_db_path)
        dss._init_db()

        session_id = dss.create_session({}, [f"U{i:04d}" for i in range(10)])
        ids = dss.allocate_chunk(session_id, 10)
        dss.report_chunk(session_id, ids, [])

        progress = dss.get_session_progress(session_id)
        assert progress['status'] == 'completed'
        assert progress['completed_count'] == 10
        assert progress['completed_at'] is not None

    def test_t4_5_cleanup_old_sessions(self, tmp_db_path, monkeypatch):
        """8일 경과 completed 세션 삭제, 현재 세션 유지"""
        monkeypatch.setattr(dss, '_DB_PATH', tmp_db_path)
        dss._init_db()

        old_session = dss.create_session({}, ['U_OLD1'])
        current_session = dss.create_session({}, ['U_CUR1'])

        # Complete old session and backdate it
        old_ids = dss.allocate_chunk(old_session, 1)
        dss.report_chunk(old_session, old_ids, [])

        conn = sqlite3.connect(tmp_db_path)
        eight_days_ago = "datetime('now', '-8 days')"
        conn.execute(
            f"UPDATE deploy_sessions SET status = 'completed', completed_at = {eight_days_ago} WHERE session_id = ?",
            (old_session,)
        )
        conn.commit()
        conn.close()

        dss.cleanup_old_sessions(days=7)

        conn = sqlite3.connect(tmp_db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT session_id FROM deploy_sessions").fetchall()
        conn.close()

        remaining_ids = [r['session_id'] for r in rows]
        assert old_session not in remaining_ids
        assert current_session in remaining_ids
        assert len(remaining_ids) == 1
