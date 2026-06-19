# -*- coding: utf-8 -*-
"""positive_rescue 규칙 골든/회귀 테스트 (KoTE 불요, 빠름).

검증:
  1) 긍정 표지 + 깨끗한 문맥 → positive_rescue 발동(긍정).
  2) 반전/완곡부정/부정암시어/도메인 부정문맥어/고neg → 미발동(true-negative 보존).
  3) 실데이터 진짜 부정 3건은 어떤 점수에서도 positive_rescue로 뒤집히지 않음.
  4) 기존 6개 동작보존 케이스 불변(legacy == explain).
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from src.services.perspective_service import (
    _sentence_sentiment_override_explain as explain,
    sentence_sentiment_override as legacy,
)


def test_rescue_fires_on_clean_positive():
    cases = ['리더십, 업무전문성, 창의력', '업무열의가 매우 높습니다', '수평적 의사소통으로 구성원들의 자발적 참여를 유도함',
             '최신 지식 정보를 꾸준히 학습', '솔선수범하여 모범을 보임']
    for s in cases:
        score, rule = explain(0.2, 0.3, s, True, 1, neutral=0.5)  # 중립우세여도 구제가 선행
        assert rule == 'positive_rescue', f'{s} -> {rule}'
        assert score > 0, f'{s} score={score}'
    print('[OK] 깨끗한 긍정 → positive_rescue 발동')


def test_rescue_blocked_by_gates():
    # 반전 / 완곡부정 / 부정암시어 / 도메인 부정문맥어 / 고neg
    blocked = [
        ('성실하지만 보고가 미흡합니다', 0.6, 0.2),          # 반전+부정암시어
        ('전문성은 있으나 개선의 여지가 있습니다', 0.6, 0.1),   # 반전+완곡부정
        ('리더십이 있으나 부족합니다', 0.5, 0.2),             # 반전+부정암시어
        ('수직적 의사소통으로 수동적 참여를 강요함', 0.3, 0.4),  # 도메인 부정문맥어
        ('리더십, 전문성', 0.1, 0.9),                       # 고neg(>=0.85)
    ]
    for s, p, n in blocked:
        _, rule = explain(p, n, s, True, 1, neutral=0.1)
        assert rule != 'positive_rescue', f'{s} 가 잘못 구제됨 -> {rule}'
    print('[OK] 게이트(반전/완곡부정/부정문맥/고neg) → 구제 차단')


def test_real_negatives_never_rescued():
    """실데이터 진짜 부정 3건: 저neg에서도 positive_rescue/negation_praise 미발동."""
    neg3 = ['세세한 지시 감독하는 성향이 강함',
            '수직적 의사소통과 강력한 상관 마인드로 문제해결을 강요하며 구성원의 수동적 참여를 유도함',
            '출세의지가 강하고 회의 시 발언시간이 길다']
    for s in neg3:
        for p, n in [(0.1, 0.1), (0.3, 0.2), (0.2, 0.4)]:
            _, rule = explain(p, n, s, True, 1, neutral=0.3)
            assert rule not in ('positive_rescue', 'negation_praise'), \
                f'진짜 부정 구제됨: {s} (p={p},n={n}) -> {rule}'
    print('[OK] 진짜 부정 3건 → 어떤 점수에서도 구제 안 됨(positive_rescue/negation_praise 모두)')


def test_negation_praise_rescued_to_positive():
    """negation 칭찬(부정의 부정): 중립/부정으로 강등되지 않고 negation_praise로 긍정 상향.

    이들은 부정표면어(강압/고압/권위의식/잔소리)를 가져 positive_rescue가 보류되고,
    is_last면 euphemistic_negative로 부정 반전될 위험까지 있던 케이스다(코퍼스 실측).
    핵심가치: 긍↔부 오분류 0 (진짜 부정은 위 테스트에서 미진입 확인).
    """
    cases = [
        '강압적이지 않음',
        '부서원들과 수평적 관계를 유지하며 고압적인 태도를 보이지 않음',
        '권위의식이 없음',
        '직원들에게 잔소리를 안한다',
        '수평적 의사소통과 강압적이지않다',
        '업무의 중요도에 따른 관심도에 차별을 두며 고압적이지 않습니다',
    ]
    for s in cases:
        # is_last + 중립우세 + 저neg: 신규 분기가 없었다면 중립/부정으로 갈 조건
        score, rule = explain(0.2, 0.4, s, True, 1, neutral=0.5)
        assert rule == 'negation_praise', f'negation 칭찬 미구제: {s} -> {rule}'
        assert score > 0, f'{s} score={score}'
    print('[OK] negation 칭찬 → negation_praise 긍정 상향(중립→긍정, 긍↔부 안전)')


def test_legacy_preserved():
    cases = [
        (0.8, 0.1, '업무 능력이 뛰어납니다.', False, 3, 0.1),
        (0.7, 0.2, '성실하지만 보고가 미흡합니다.', True, 2, 0.1),
        (0.1, 0.05, '보통 수준입니다.', False, 1, 0.85),
        (0.6, 0.1, '개선의 여지가 있습니다.', True, 1, 0.3),
        (0.2, 0.2, '그러나 결과가 아쉽습니다.', True, 4, 0.6),
        (0.9, 0.92, '보통 무난합니다.', True, 1, 0.0),
    ]
    for p, n, s, il, t, nu in cases:
        a = legacy(p, n, s, il, t, neutral=nu)
        b, _ = explain(p, n, s, il, t, neutral=nu)
        assert a == b, f'{s}: legacy={a} explain={b}'
    print('[OK] legacy == explain 동작 보존')


if __name__ == '__main__':
    test_rescue_fires_on_clean_positive()
    test_rescue_blocked_by_gates()
    test_real_negatives_never_rescued()
    test_negation_praise_rescued_to_positive()
    test_legacy_preserved()
    print('\n전체 통과')
