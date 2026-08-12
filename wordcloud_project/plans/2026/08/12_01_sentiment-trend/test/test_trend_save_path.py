"""12_01_sentiment-trend — save_trend_graph_to_deploy 저장 경로·파일명·갤러리 등록 검증.

서버를 띄우지 않고 서비스 함수만 호출한다. 실제 outputs/ 를 건드리지 않도록
DEPLOY_OUTPUT_DIR/OUTPUTS_DIR_PATH 를 임시 폴더로 바꾸고, 갤러리 DB 쓰기는 가로챈다.

검증 항목
  A. 저장 경로 — outputs/배포/그래프/<safe_name>_긍부정그래프.png
  B. 파일명 앞부분 — 제출용 저장(save_to_deploy)의 safe_name 규칙과 동일
  C. 반환 URL — /outputs/배포/그래프/....png?v=<timestamp>
  D. 갤러리 등록 — source='graph', images={'graph': url} (스키마 변경 없음)
  E. 데이터 없음 — 평가가 없으면 None 반환(예외 아님)

실행: python test_trend_save_path.py
"""
import os
import sys
import tempfile

_APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

from src.services import perspective_service as ps
from src.services import gallery_db_service

from test_sentiment_trend import ITEMS, _stub_sentence_scores


class _FakePseudoMgr:
    def get_real_id(self, v):
        return {'PSD001': '110110', 'PSD_NAME': '홍길동'}.get(v, v)


def main():
    failures = []

    def check(label, actual, expected):
        ok = actual == expected
        print(('  OK  ' if ok else ' FAIL ') + label + f' — 실제={actual} 기대={expected}')
        if not ok:
            failures.append(label)

    tmp_out = tempfile.mkdtemp(prefix='trend_out_')
    captured = {}

    # ── 스텁 주입 ────────────────────────────────────────────────────────
    ps._get_sentence_level_scores = _stub_sentence_scores
    ps._load_corrections_map = lambda employee_id: {}
    ps._get_pseudo_mgr = lambda: _FakePseudoMgr()
    ps._resolve_to_pseudo = lambda eid, mgr: 'PSD001'
    ps._get_employee_metadata = lambda ud, rid: {'target_employee_name': 'PSD_NAME'}
    ps._get_evaluations_for_employee = lambda ud, rid: ITEMS
    ps.OUTPUTS_DIR_PATH = tmp_out
    ps.DEPLOY_OUTPUT_DIR = os.path.join(tmp_out, '배포')
    gallery_db_service.upsert_entry = lambda entry: captured.update(entry)

    ps._setup_korean_font()

    print('[A~D] 단건 저장 — output_mode=real')
    result = ps.save_trend_graph_to_deploy(
        unified_data={}, employee_id='110110',
        row_field='evaluation_date__year', row_values=['2024', '2026'],
        metric='sentence_cnt', unit='pct',
        options={'output_mode': 'real', 'include_name': True, 'include_id': True,
                 'width': 800, 'height': 600, 'batch_title': '테스트배치'})

    if result is None:
        print(' FAIL 단건 저장이 None 을 반환')
        return 1

    expected_path = os.path.join(tmp_out, '배포', '그래프', '홍길동_110110_긍부정그래프.png')
    check('저장 파일 존재', os.path.exists(expected_path), True)
    check('반환 name(제출용 저장과 동일 규칙)', result['name'], '홍길동_110110')
    check('URL 경로', result['graph'].split('?')[0], '/outputs/배포/그래프/홍길동_110110_긍부정그래프.png')
    check('URL 캐시버스터', result['graph'].split('?v=')[1], result['timestamp'])
    check('연도', result['rows'], ['2024', '2026'])
    check('긍정 %', result['positive'], [66.7, 33.3])
    check('부정 %', result['negative'], [33.3, 66.7])
    check('원값(수량) 보존', [result['positive_raw'], result['negative_raw']], [[2, 1], [1, 2]])

    print('[D] 갤러리 등록 entry')
    check('source', captured.get('source'), 'graph')
    check('images 키', sorted((captured.get('images') or {}).keys()), ['graph'])
    check('images.graph == 반환 URL', captured.get('images', {}).get('graph'), result['graph'])
    check('batch_title 승계', captured.get('batch_title'), '테스트배치')
    check('analysis_type', captured.get('analysis_type'), 'trend')

    print('[E] 평가 0건 방어')
    ps._get_evaluations_for_employee = lambda ud, rid: []
    empty = ps.save_trend_graph_to_deploy(
        unified_data={}, employee_id='110110',
        row_field='evaluation_date__year', row_values=['2024'],
        metric='sentence_cnt', unit='pct', options={'output_mode': 'real'})
    check('평가 없으면 None', empty, None)

    print('[E-2] 선택 연도에 데이터가 전혀 없을 때')
    ps._get_evaluations_for_employee = lambda ud, rid: ITEMS
    none_year = ps.save_trend_graph_to_deploy(
        unified_data={}, employee_id='110110',
        row_field='evaluation_date__year', row_values=['2019'],
        metric='sentence_cnt', unit='pct', options={'output_mode': 'real'})
    check('해당 연도 없으면 None', none_year, None)

    print()
    print('출력 폴더:', tmp_out)
    if failures:
        print(f'FAIL {len(failures)}건: {failures}')
        return 1
    print('전 항목 통과')
    return 0


if __name__ == '__main__':
    sys.exit(main())
