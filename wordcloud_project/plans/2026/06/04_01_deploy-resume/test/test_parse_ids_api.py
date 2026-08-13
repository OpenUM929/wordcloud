"""T3. parse-ids API tests."""
import pytest


MOCK_UNIFIED = {
    'employee_results': [
        {
            'metadata': {
                'target_employee_id': 'U001',
                'target_employee_name': '김철수',
                'target_employee_department': '영업',
                'target_employee_position': '과장',
                'evaluations': [1, 2],
            }
        },
        {
            'metadata': {
                'target_employee_id': 'U002',
                'target_employee_name': '박영희',
                'target_employee_department': '개발',
                'target_employee_position': '대리',
                'evaluations': [1],
            }
        },
        {
            'metadata': {
                'target_employee_id': 'U003',
                'target_employee_name': '이민수',
                'target_employee_department': '인사',
                'target_employee_position': '팀장',
                'evaluations': [1, 2, 3],
            }
        },
    ],
    'batch_info': {}
}


class TestT3ParseIdsApi:
    """T3-1 ~ T3-3"""

    def test_t3_1_normal_id_list_with_details(self, admin_client, monkeypatch):
        """정상 ID 목록: matched 2, not_found 1, details 포함"""
        monkeypatch.setattr('src.routes.perspective_routes.load_all_batches', lambda: MOCK_UNIFIED)

        resp = admin_client.post('/api/perspective/parse-ids', json={
            'ids': ['U001', 'U002', 'U009']
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['matched'] == 2
        assert data['not_found'] == ['U009']
        assert len(data['details']) == 2
        detail_ids = [d['employee_id'] for d in data['details']]
        assert 'U001' in detail_ids
        assert 'U002' in detail_ids
        # verify fields
        for d in data['details']:
            assert 'name' in d
            assert 'department' in d
            assert 'position' in d
            assert 'evaluation_count' in d

    def test_t3_2_union_from_text_and_file(self, admin_client, monkeypatch):
        """API는 중복 제거된 ids 배열을 정상 처리 (프론트 합집합은 수동 테스트로 분리)"""
        monkeypatch.setattr('src.routes.perspective_routes.load_all_batches', lambda: MOCK_UNIFIED)

        # Simulate deduplicated union result that frontend would send
        resp = admin_client.post('/api/perspective/parse-ids', json={
            'ids': ['U001', 'U002', 'U003', 'U001']  # U001 duplicated
        })
        data = resp.get_json()
        assert data['matched'] == 3
        assert data['not_found'] == []

    def test_t3_3_empty_ids_bad_request(self, admin_client, monkeypatch):
        """빈 목록: 400 Bad Request"""
        monkeypatch.setattr('src.routes.perspective_routes.load_all_batches', lambda: MOCK_UNIFIED)

        resp = admin_client.post('/api/perspective/parse-ids', json={'ids': []})
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'ids' in data['error']
