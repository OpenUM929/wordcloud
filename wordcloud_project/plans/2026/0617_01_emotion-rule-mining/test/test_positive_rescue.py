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
    positive_marker_directly_negated as pmdn,
    has_unnegated_strong_negative as husn,
    has_unnegated_deficiency as hud,
    is_no_weakness_declaration as inwd,
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


def test_directly_negated_positive_not_rescued():
    """긍정표지 직접 부정("관심이 없다")은 구제 차단 → 부정(부→긍 핵심가치, batch_20260622_0 실측 27건).

    '관심/책임감/업무열의'가 긍정표지라 기존 positive_rescue가 긍정 상향하던 부→긍 오분류를 닫는다.
    """
    neg = ['업무에 관심이 없다', '책임감이 없습니다', '사적통화를 크게 하고 업무열의가 없음',
           '업무 등 모든일에 적극성이 없음', '회사에 관심이 없으신 분입니다', '업무에 대한 의지가 없음']
    for s in neg:
        assert pmdn(s), f'직접부정 미탐: {s}'
        score, rule = explain(0.1, 0.8, s, True, 1, neutral=0.1)
        assert rule != 'positive_rescue', f'직접부정인데 구제됨: {s} -> {rule}'
        assert score < 0, f'{s} score={score} (부정이어야)'
    print('[OK] 긍정표지 직접부정 → 구제차단·부정(부→긍 0)')


def test_directly_negated_traps_preserved():
    """trap은 구제 차단되면 안 됨(긍→부 0): 강조어(아낌없이)·상쇄(부족함이 없다)·양면표지(개선)·없이/없는."""
    not_blocked = [
        '그동안 쌓은 노하우를 아낌없이 전수한다',   # 아낌없이=후하게(강조어)
        '전문지식을 끊임없이 학습한다',            # 끊임없이=계속
        '부드러운 리더십과 막힘없는 일처리',        # 막힘없는=원활
        '의견 경청, 고집없음',                    # 고집 없음=좋음(표지·negation 사이 단어)
        '특별히 개선할점없음',                    # 개선=양면표지(가드 제외)
        '직원들과 소통이 원활하여 불만이 없다',     # 불만이 없다=좋음
        '부당한 업무지시 없이 청렴하고 충실함',     # 없이=강조
    ]
    for s in not_blocked:
        assert not pmdn(s), f'trap이 잘못 차단됨(긍→부 위험): {s}'
    print('[OK] 강조어/상쇄/양면표지/없이·없는 trap → 차단 안 됨(긍→부 0)')


def test_euphemistic_negative_respects_negation():
    """euphemistic_negative는 negation 인식: "보완이 필요하지 않으며"=칭찬 → 긍→부 반전 금지."""
    # 부정된 강조부정구 → euphemistic_negative 미발동(긍정 유지)
    s_pos = '보완이 필요하지 않으며 높은 평가를 드리고 싶음'
    assert not husn(s_pos), '부정된 강조부정구가 미부정으로 처리됨'
    score, rule = explain(0.94, 0.03, s_pos, True, 1, neutral=0.03)
    assert rule != 'euphemistic_negative' and score > 0, f'{s_pos} -> {rule}/{score}'
    # 진짜 완곡부정은 그대로 부정
    s_neg = '개선이 필요한 부분이 많음'
    assert husn(s_neg)
    score2, rule2 = explain(0.6, 0.3, s_neg, True, 1, neutral=0.1)
    assert rule2 == 'euphemistic_negative' and score2 < 0, f'{s_neg} -> {rule2}/{score2}'
    print('[OK] euphemistic_negative negation 인식(긍→부 0, 진짜 완곡부정 보존)')


def test_deficiency_predicate_blocks_rescue():
    """긍정표지 + 결함 술어(소홀)는 구제 차단 → 부정(batch_20260622_0 부→긍 실측).

    '업무에 무관심하고 소홀함' 류는 KoTE가 부정인데 positive_rescue가 긍정 상향하던 구멍.
    '무관심'은 '업무관심도'(긍정) 부분문자열 trap으로 제외 — 동일 문장은 '소홀'이 포착.
    """
    neg = ['업무에 무관심하고 소홀함', '엄무에 무관심하고 모든 업무에 소홀함',
           '맡은 업무에 소홀하며 책임감이 부족']
    for s in neg:
        assert hud(s), f'결함 술어 미탐: {s}'
        _, rule = explain(0.2, 0.6, s, True, 1, neutral=0.1)
        assert rule != 'positive_rescue', f'결함인데 구제됨: {s} -> {rule}'
    print('[OK] 긍정표지+결함술어(소홀) → 구제 차단(부→긍 0)')


def test_deficiency_traps_preserved():
    """trap 보존(긍→부 0): negation 칭찬(소홀히 하지 않음)·부분문자열 오탐(업무관심도)."""
    # negation 칭찬 = 결함 아님
    assert not hud('업무에 소홀히 하지 않고 성실함')
    # 🔴 부분문자열 trap 회귀(실측 긍→부 4건): '업무관심'(업무+관심=긍정)에 '무관심' 오탐 금지
    assert not hud('업무관심이 많음 요청기한적기 지킴')
    assert not hud('업무참여도 업무관심도 높음')
    assert not hud('업무관심도를 바탕으로한 부서운영')
    assert not hud('자기개발에 열의가 강함')         # 결함 술어 무관
    # 깨끗한 긍정은 여전히 구제(결함 술어 없음)
    score, rule = explain(0.2, 0.4, '업무 전문성과 열의가 높음', True, 1, neutral=0.5)
    assert rule == 'positive_rescue' and score > 0
    print('[OK] 결함 가드 trap 보존(negation 칭찬·업무관심도 부분문자열·깨끗한 긍정 불변)')


def test_constructive_need_blocks_rescue():
    """긍정표지 + 건설적 필요/요구(필요함/요구됨)는 구제 차단 → 부정(약점 섹션 부→긍 실측).

    '경청 필요'·'소통이 필요함'·'적극적인 자세가 필요함'·'책임감이 요구됨'은 약점 섹션의
    "더 ~하면 좋겠다" 건설적 비판인데, 긍정표지 때문에 positive_rescue가 긍정 상향하던 구멍.
    """
    neg = ['상대방의 의견 경청 필요', '부서간의 소통이 좀 더 필요합니다',
           '업무에 대한 적극적인 자세가 필요함', '업무에 대한 책임감이 좀 더 요구됨',
           '의사소통 능력 향상이 필요하다']
    for s in neg:
        _, rule = explain(0.3, 0.6, s, True, 1, neutral=0.1)
        assert rule != 'positive_rescue', f'건설적 필요인데 구제됨: {s} -> {rule}'
    print('[OK] 긍정표지+건설적 필요/요구 → 구제 차단(부→긍 0)')


def test_constructive_need_traps_preserved():
    """trap 보존(긍→부 0): 관형형 '필요한'(필요한 업무=긍정)·부정칭찬('필요하지 않')은 구제 유지."""
    # '필요한 [명사]' = 긍정/중립 → 깨끗한 긍정이면 여전히 구제
    score, rule = explain(0.2, 0.4, '업무에 필요한 전문 지식이 풍부함', True, 1, neutral=0.5)
    assert rule == 'positive_rescue' and score > 0, f'필요한+명사 오차단: {rule}'
    # 부정의 부정(필요하지 않음=칭찬)은 STRONG에 '필요하' 미수록으로 미발동
    s = '보완이 필요하지 않으며 높은 평가를 드림'
    assert not husn(s), '필요하지 않(칭찬)이 강조부정으로 처리됨'
    print('[OK] 건설적 필요 trap 보존(관형형 필요한·부정칭찬 불변)')


def test_no_weakness_declaration_neutral():
    """'약점 없음' 선언(보완점 없음/단점 없습니다)은 부정이 아님 → KoTE 부정 오분류 교정(batch 23.8%).

    핵심 요구 = '부정으로 떨어지지 않는다'(중립 또는 긍정). neg 우세분은 no_weakness_neutral로 중립화.
    """
    noweak = ['보완할 점이 없습니다', '특별한 단점이 없음', '보완필요점이 없습니다',
              '보완 필요점은 없음', '달리 보완할점이 없음', '보완사항 없습니다']
    for s in noweak:
        assert inwd(s), f'약점없음 미탐: {s}'
        sc, rule = explain(0.13, 0.55, s, True, 1, neutral=0.32)   # KoTE 부정 우세
        assert sc >= 0.0, f'약점없음이 부정으로: {s} -> {rule}/{sc}'
        assert rule == 'no_weakness_neutral', f'{s} -> {rule}'
    print('[OK] 약점없음 선언 → 중립(부정 오분류 교정, 긍↔부 무관)')


def test_no_weakness_mixed_stays_negative():
    """혼합("보완점 없으나 소통 부족")·진짜 부정은 미발동 → 부정 보존(부정 손실 0)."""
    # 약점선언 + 진짜 부정 결합 → 약점선언 미발동(혼합은 부정)
    assert not inwd('보완점은 없으나 소통이 부족함')        # 결함술어 부족
    assert not inwd('단점은 없지만 적극성이 필요함')        # 건설적필요
    # 진짜 부정엔 애초에 미매칭
    assert not inwd('협업능력이 부족합니다')
    assert not inwd('업무에 무관심하고 소홀함')
    print('[OK] 혼합/진짜부정 → 약점없음 미발동(부정 보존)')


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
    test_directly_negated_positive_not_rescued()
    test_directly_negated_traps_preserved()
    test_euphemistic_negative_respects_negation()
    test_deficiency_predicate_blocks_rescue()
    test_deficiency_traps_preserved()
    test_constructive_need_blocks_rescue()
    test_constructive_need_traps_preserved()
    test_no_weakness_declaration_neutral()
    test_no_weakness_mixed_stays_negative()
    test_legacy_preserved()
    print('\n전체 통과')
