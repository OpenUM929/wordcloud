# -*- coding: utf-8 -*-
"""데이터셋 파이프라인 신규 컴포넌트 골든/회귀 (KoTE 불요, 빠름).

잠그는 핵심가치:
  1) split_clauses: 혼합극성 분해 + 부정범위 보존(절 중간에서 '않/없' 끊지 않음).
  2) leadership_lf: polarity 재게이트 — risk 후보는 극성 negative일 때만(긍↔부=positive↔risk 0).
     특히 '강압적이지 않음'(negation 칭찬)은 risk 후보 차단.
"""
import os
import sys

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, HERE)

from src.modules.text_preprocessing import split_clauses
from leadership_lf import build_leadership_candidates, load_tree


def test_split_basic_contrast():
    assert split_clauses('업무품질은 좋으나 퀄리티가 낮음') == ['업무품질은 좋으나', '퀄리티가 낮음']
    out = split_clauses('책임감이 강한 반면 융통성이 부족하다')
    assert len(out) == 2 and '반면' in out[1], out
    print('[OK] 반전 연결어미에서 절 분리')


def test_split_preserves_negation():
    # 부정범위 보존: '않으나'가 한 절 안에 통째로 남아야(극성 보존 → 긍↔부 안전)
    out = split_clauses('강압적이지 않으나 결단력이 부족함')
    assert out[0] == '강압적이지 않으나', out
    # 부정의 부정 단문은 분리하지 않음
    assert split_clauses('강압적이지 않음') == ['강압적이지 않음']
    print('[OK] 부정범위 보존(절 중간에서 않/없 안 끊음)')


def test_split_no_false_split():
    # 반전표지 없으면 한 덩어리 유지
    assert split_clauses('소통이 원활하고 배려심이 깊다') == ['소통이 원활하고 배려심이 깊다']
    assert split_clauses('리더십이 뛰어남') == ['리더십이 뛰어남']
    print('[OK] 반전 없으면 미분할')


def test_lf_risk_blocked_on_negation_praise():
    tree = load_tree()
    # '강압적이지 않음' = negation 칭찬 → 극성 positive → risk 후보 차단(긍↔부 0)
    out = build_leadership_candidates('강압적이지 않음', 'positive', True, tree)
    assert all(c['polarity'] != 'risk' for c in out['candidates']), out
    assert not out['is_leadership'] or all(c['polarity'] == 'positive' for c in out['candidates'])
    print('[OK] negation 칭찬 → risk 오귀속 차단')


def test_lf_polarity_gate():
    tree = load_tree()
    # 진짜 부정(극성 negative) → risk 대그룹 후보
    out = build_leadership_candidates('세세한 지시 감독과 강압으로 일방적 지시', 'negative', False, tree)
    assert out['is_leadership'] and any(c['polarity'] == 'risk' for c in out['candidates']), out
    # 긍정 → positive 대그룹만, risk 없음
    out2 = build_leadership_candidates('수평적 의사소통과 경청으로 팀워크를 이끈다', 'positive', False, tree)
    assert out2['is_leadership'] and all(c['polarity'] == 'positive' for c in out2['candidates']), out2
    print('[OK] polarity 게이트(negative→risk만, positive→positive만)')


def test_lf_grouped_default_and_evidence():
    tree = load_tree()
    out = build_leadership_candidates('성장 피드백과 격려로 후배를 육성함', 'positive', False, tree)
    c = out['candidates'][0]
    assert c['level'] == 1 and c['status_hint'] == 'grouped', c   # 기본 대그룹
    assert c['evidence'], c                                       # 근거표지 보존(재정렬 가능)
    assert c['node'].startswith('G_'), c                          # 불변 안정 id
    print('[OK] 기본 grouped + evidence/node id 보존(택소노미 변경 시 재정렬용)')


if __name__ == '__main__':
    test_split_basic_contrast()
    test_split_preserves_negation()
    test_split_no_false_split()
    test_lf_risk_blocked_on_negation_praise()
    test_lf_polarity_gate()
    test_lf_grouped_default_and_evidence()
    print('\n전체 통과')
