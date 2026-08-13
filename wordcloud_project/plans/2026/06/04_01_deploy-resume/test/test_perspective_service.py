"""T2. get_matrix_meta() name restoration tests."""
import pytest

from src.services.perspective_service import get_matrix_meta


def _make_mock_unified(emp_id, emp_name, emp_dept='개발팀', emp_pos='대리', evals=None):
    evals = evals if evals is not None else [{}]
    return {
        'employee_results': [
            {
                'metadata': {
                    'target_employee_id': emp_id,
                    'target_employee_name': emp_name,
                    'target_employee_department': emp_dept,
                    'target_employee_position': emp_pos,
                    'evaluations': evals,
                }
            }
        ],
        'batch_info': {'batch_count': 1, 'total_evaluations': len(evals)}
    }


class TestT2GetMatrixMetaNameRestoration:
    """T2-1 ~ T2-3"""

    def test_t2_1_real_mode_employee_name_restored(self, monkeypatch, tmp_mappings_path, reset_pseudo_mgr):
        """원데이터 모드에서 employee_name이 실제 이름으로 역변환"""
        from src.modules.pseudonym_manager import PseudonymManager
        import src.services.perspective_service as ps

        mgr = PseudonymManager(tmp_mappings_path, 'testpass')
        mgr.link_mapping("평가자_AB1234", "홍길동")

        monkeypatch.setattr(ps, '_get_pseudo_mgr', lambda: mgr)

        unified = _make_mock_unified('U001', '평가자_AB1234')
        result = get_matrix_meta(unified, enrich=True)
        emp = result['employees'][0]
        assert emp['employee_name'] == '홍길동'

    def test_t2_2_pseudonym_mode_no_restoration(self, monkeypatch, tmp_mappings_path, reset_pseudo_mgr):
        """가명 모드에서는 employee_name 변환 없음"""
        import src.services.perspective_service as ps

        # enrich=False 이면 _get_pseudo_mgr 호출 안 함
        unified = _make_mock_unified('U001', '평가자_AB1234')
        result = get_matrix_meta(unified, enrich=False)
        emp = result['employees'][0]
        assert emp['employee_name'] == '평가자_AB1234'

    def test_t2_3_missing_employee_name_is_none(self, monkeypatch, tmp_mappings_path, reset_pseudo_mgr):
        """target_employee_name 키가 없으면 None, 예외 없음"""
        unified = {
            'employee_results': [
                {
                    'metadata': {
                        'target_employee_id': 'U001',
                        # 'target_employee_name' intentionally omitted
                        'target_employee_department': '개발팀',
                        'target_employee_position': '대리',
                        'evaluations': [{}],
                    }
                }
            ],
            'batch_info': {'batch_count': 1, 'total_evaluations': 1}
        }
        result = get_matrix_meta(unified, enrich=False)
        emp = result['employees'][0]
        assert emp['employee_name'] is None
