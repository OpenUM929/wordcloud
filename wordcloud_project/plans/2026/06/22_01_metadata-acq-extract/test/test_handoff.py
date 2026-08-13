"""0622_01 — 핸드오프 코퍼스 라이터 단위 검증.

검증 항목:
  - 경로 안전화: dest_label/batch_id가 데이터셋 루트를 벗어나지 못함(배포 유출 방지).
  - append 스키마: 레전드 1줄 + 문장당 x/y/s/e, s는 소수 2자리, e=top3 [[명,점],...].
  - 멱등(resume): 같은 파일 재append 시 레전드 중복 기록 없음.
  - 라벨 매핑: override 점수 부호 → p/n/u (그룹분석과 동일). 캐시 top3가 e로 전달.

KoTE/matplotlib 미의존 — perspective_service는 sys.modules 스텁으로 주입.
실행: python test_handoff.py
"""
import json
import os
import sys
import tempfile
import types

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.services import acquired_handoff as ah


def test_safe_segment_and_path_escape():
    assert ah._safe_segment('../../evil') == 'evil'
    assert ah._safe_segment('a/b\\c') == 'a_b_c'
    assert ah._safe_segment('') == ''
    # 경로 탈출 시도가 루트 안에 머무는지(세그먼트화로 차단)
    p = ah.resolve_handoff_path('../../../etc', 'batch_x')
    root = ah._HANDOFF_ROOT
    assert p.startswith(root + os.sep), p
    # 빈 라벨 → default
    p2 = ah.resolve_handoff_path('', '')
    assert os.path.basename(os.path.dirname(p2)) == 'default'
    print('OK test_safe_segment_and_path_escape')


def test_append_schema_and_rounding(tmp):
    ah._HANDOFF_ROOT = os.path.join(tmp, 'handoff')
    records = [
        ('맡은 업무를 성실히 수행함', 'p', 0.781, 0.044, 0.180,
         [['뿌듯함', 0.812], ['인정/신뢰', 0.553], ['기쁨', 0.421]]),
        ('지각이 잦고 보고가 누락됨', 'n', 0.030, 0.910, 0.060, []),
        ('평이한 수준임', 'u', 0.10, 0.10, 0.80, []),
    ]
    n = ah.append_handoff_records('teamA', 'batch_20260622_1', records)
    assert n == 3
    path = ah.resolve_handoff_path('teamA', 'batch_20260622_1')
    lines = open(path, encoding='utf-8').read().splitlines()
    assert len(lines) == 4  # 레전드 1 + 3

    legend = json.loads(lines[0])
    assert '#' in legend and legend['batch'] == 'batch_20260622_1'

    r0 = json.loads(lines[1])
    assert r0['x'] == '맡은 업무를 성실히 수행함'
    assert r0['y'] == 'p'
    assert r0['s'] == [0.78, 0.04, 0.18]            # 소수 2자리
    assert r0['e'][0] == ['뿌듯함', 0.81]
    assert len(r0['e']) == 3

    r1 = json.loads(lines[2])
    assert r1['y'] == 'n' and r1['e'] == []
    r2 = json.loads(lines[3])
    assert r2['y'] == 'u' and r2['s'] == [0.1, 0.1, 0.8]
    print('OK test_append_schema_and_rounding')


def test_resume_no_duplicate_legend(tmp):
    ah._HANDOFF_ROOT = os.path.join(tmp, 'handoff2')
    ah.append_handoff_records('teamB', 'b1', [('문장1', 'p', 0.9, 0.0, 0.1, [])])
    ah.append_handoff_records('teamB', 'b1', [('문장2', 'n', 0.0, 0.9, 0.1, [])])
    path = ah.resolve_handoff_path('teamB', 'b1')
    lines = open(path, encoding='utf-8').read().splitlines()
    assert len(lines) == 3  # 레전드 1 + 문장 2 (레전드 중복 없음)
    assert '#' in json.loads(lines[0])
    assert '#' not in json.loads(lines[1])
    print('OK test_resume_no_duplicate_legend')


def test_build_records_label_mapping():
    # perspective_service._get_sentence_level_scores 스텁 주입 (matplotlib 회피)
    stub = types.ModuleType('src.services.perspective_service')

    def _fake_scores(doc, sentence_cache=None, **kw):
        # (sent, score, pos, neg, neutral) — 부호로 p/n/u 결정
        return [
            ('좋은 성과를 냄', 0.7, 0.8, 0.05, 0.15),
            ('실수가 반복됨', -0.6, 0.05, 0.85, 0.10),
            ('보통임', 0.0, 0.1, 0.1, 0.8),
        ]
    stub._get_sentence_level_scores = _fake_scores
    sys.modules['src.services.perspective_service'] = stub
    try:
        metadata = {'evaluations': [{
            'evaluation_document': '문서',
            'sentence_emotion_cache': [
                {'sentence': '좋은 성과를 냄', 'pos': 0.8, 'neg': 0.05, 'neutral': 0.15,
                 'top3': [['뿌듯함', 0.8]]},
                {'sentence': '실수가 반복됨', 'pos': 0.05, 'neg': 0.85, 'neutral': 0.10,
                 'top3': [['실망', 0.7]]},
                {'sentence': '보통임', 'pos': 0.1, 'neg': 0.1, 'neutral': 0.8, 'top3': []},
            ],
        }]}
        recs = ah.build_records_from_metadata(metadata)
        assert [r[1] for r in recs] == ['p', 'n', 'u'], recs
        # 캐시 top3가 레코드로 전달되는지
        assert recs[0][5] == [['뿌듯함', 0.8]]
        assert recs[2][5] == []
        print('OK test_build_records_label_mapping')
    finally:
        sys.modules.pop('src.services.perspective_service', None)


if __name__ == '__main__':
    _orig_root = ah._HANDOFF_ROOT
    try:
        test_safe_segment_and_path_escape()
        with tempfile.TemporaryDirectory() as d:
            test_append_schema_and_rounding(d)
        with tempfile.TemporaryDirectory() as d:
            test_resume_no_duplicate_legend(d)
        test_build_records_label_mapping()
        print('\nALL PASS')
    finally:
        ah._HANDOFF_ROOT = _orig_root
