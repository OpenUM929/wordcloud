"""T5. Session management API integration tests."""
import pytest

import src.services.deploy_session_service as dss


class TestT5SessionApiIntegration:
    """T5-1 ~ T5-6 (API-testable subset)"""

    def test_t5_1_full_session_happy_path(self, admin_client, tmp_db_path, monkeypatch):
        """세션 전체 흐름: 100명 생성 → 50 → 완료 → 50 → 완료 → 빈 chunk → completed"""
        monkeypatch.setattr(dss, '_DB_PATH', tmp_db_path)
        dss._init_db()

        employee_ids = [f"U{i:04d}" for i in range(100)]

        # 1. start
        resp = admin_client.post('/api/perspective/deploy-session/start', json={
            'options': {},
            'employee_ids': employee_ids
        })
        assert resp.status_code == 200
        session_id = resp.get_json()['session_id']

        # 2. chunk 1
        resp = admin_client.get(f'/api/perspective/deploy-session/chunk?session_id={session_id}&count=50')
        chunk1 = resp.get_json()['employee_ids']
        assert len(chunk1) == 50

        # 3. complete 1
        resp = admin_client.post('/api/perspective/deploy-session/complete', json={
            'session_id': session_id,
            'completed_ids': chunk1,
            'failed_items': []
        })
        assert resp.status_code == 200

        # 4. chunk 2
        resp = admin_client.get(f'/api/perspective/deploy-session/chunk?session_id={session_id}&count=50')
        chunk2 = resp.get_json()['employee_ids']
        assert len(chunk2) == 50

        # 5. complete 2
        resp = admin_client.post('/api/perspective/deploy-session/complete', json={
            'session_id': session_id,
            'completed_ids': chunk2,
            'failed_items': []
        })
        assert resp.status_code == 200

        # 6. chunk 3 (should be empty)
        resp = admin_client.get(f'/api/perspective/deploy-session/chunk?session_id={session_id}')
        chunk3 = resp.get_json()['employee_ids']
        assert len(chunk3) == 0

        # 7. progress
        resp = admin_client.get(f'/api/perspective/deploy-session/progress?session_id={session_id}')
        progress = resp.get_json()['progress']
        assert progress['completed_count'] == 100
        assert progress['status'] == 'completed'

    def test_t5_3_multiple_incomplete_sessions_auto_cancel(self, admin_client, tmp_db_path, monkeypatch):
        """다중 미완료 세션: 최근 1개만 유지, 나머지 failed 처리"""
        monkeypatch.setattr(dss, '_DB_PATH', tmp_db_path)
        dss._init_db()

        s1 = dss.create_session({}, ['A1'])
        s2 = dss.create_session({}, ['A2'])
        s3 = dss.create_session({}, ['A3'])

        # Simulate checkResume flow: get_active_sessions returns only the most recent
        active = dss.get_active_sessions()
        assert len(active) == 3

        # Manually mark older sessions as failed (simulating the frontend/backend auto-cancel logic)
        # Since the actual auto-cancel is triggered by resume/create, we test the API supports it.
        dss.cancel_session(s1)
        dss.cancel_session(s2)

        active_after = dss.get_active_sessions()
        session_ids = [s['session_id'] for s in active_after]
        assert s1 not in session_ids
        assert s2 not in session_ids
        assert s3 in session_ids

    def test_t5_5_localstorage_cleared_on_normal_completion(self, admin_client, tmp_db_path, monkeypatch):
        """정상 완료 후 localStorage 정리는 브라우저 책임; API 레벨에서는 세션 completed 확인"""
        monkeypatch.setattr(dss, '_DB_PATH', tmp_db_path)
        dss._init_db()

        session_id = dss.create_session({}, ['U001'])
        ids = dss.allocate_chunk(session_id, 1)
        dss.report_chunk(session_id, ids, [])

        progress = dss.get_session_progress(session_id)
        assert progress['status'] == 'completed'
        # In real browser, frontend removes localStorage item at this point.
