# -*- coding: utf-8 -*-
"""improvement_request_neutral 규칙 골든/회귀 (KoTE 불요, 빠름).

배경(0630_03): 단점필드 결핍·개선요청("보완 필요"·"자기관리 필요")이 KoTE 긍정우세로
  rule4_default를 그대로 긍정 통과하던 부→긍 누수(전수 24,384건)를 *중립*으로 강등.
핵심: ① 부정 아닌 중립으로만 강등 → 긍↔부 0. ② 트랩(필요 인물·어려움 조력·재부정·양보) 보존.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from src.services.perspective_service import (
    _sentence_sentiment_override_explain as explain,
    has_constructive_need as hcn,
    _has_improvement_request_core as hirc,
    has_improvement_request as hir,
)


def test_deficiency_framing_demoted_to_neutral():
    # pos>neg(긍정으로 갈 것)인 결핍/개선요청 → 부정 확정.
    # 0709 갱신: 0630_03 당시엔 중립 강등이었으나 0702_03 사용자 정책 재정(요청형=결여=부정,
    #   pos>=0.75 강긍정만 중립 보류)으로 기대값을 부정으로 교체 — 부→긍 위반 제거 취지는 동일.
    cases = [
        '근면 성실 장점 보완 필요',        # 원 케이스(#6): 부→긍 위반 제거
        '더욱더 적극적인 자세가 필요',
        '꾸준한 자기관리 필요',
        '소통 능력 보완해야 함',
        '새로운 도전의식 배양 필요',
    ]
    for s in cases:
        score, rule = explain(0.55, 0.25, s, True, 1, neutral=0.20)
        assert rule == 'improvement_request_neg', f'{s} -> {rule}'
        assert score < 0, f'{s} score={score}'
    print('[OK] 결핍/개선요청(pos>neg) → 부정 확정(0702_03 정책)')


def test_neutral_only_never_flips_to_negative():
    # 중립으로만 강등 — 어떤 점수에서도 음수(부정) 반환 금지(긍↔부 0 구조 보장)
    for pos, neg in [(0.9, 0.05), (0.55, 0.25), (0.51, 0.49)]:
        score, rule = explain(pos, neg, '자기관리 필요', True, 1, neutral=0.05)
        if rule == 'improvement_request_neutral':
            assert score == 0.0, f'중립 강등이 음수 점수: {score}'
    print('[OK] improvement_request_neutral은 중립(0.0)만 — 부정 미생성')


def test_trap_indispensable_person_preserved():
    # '필요 인물'(불가결=긍정)은 has_constructive_need=False → 중립화 미발동, 긍정 보존
    assert hcn('강원본부에 절대적 필요 인물') is False
    score, rule = explain(0.72, 0.16, '강원본부에 절대적 필요 인물', True, 1, neutral=0.12)
    assert rule != 'improvement_request_neutral', f'필요 인물 오강등: {rule}'
    assert score > 0, f'필요 인물 score={score}'
    print('[OK] 필요 인물(불가결) → 긍정 보존')


def test_trap_helping_difficulty_preserved():
    # '어려움을 해결/도와줌'(남을 돕는 긍정)은 core 트리거에서 제외 → 긍정 보존
    helping = [
        '동료의 어려움을 잘 해결해 주십니다',
        '부서원이 어려움에 처할때 적극적으로 도와줌',
        '타 직원의 어려움을 결코 지나치지않음',
    ]
    for s in helping:
        assert hirc(s) is False, f'core가 조력문 오포착: {s}'
        score, rule = explain(0.9, 0.05, s, True, 1, neutral=0.05)
        assert rule != 'improvement_request_neutral', f'{s} 오강등: {rule}'
        assert score > 0, f'{s} score={score}'
    # 단, has_improvement_request(곤란 포함)는 기존 동작 보존 — 진짜 곤란호소는 여전히 True
    assert hir('협업에 어려움이 많음') is True
    print('[OK] 어려움 조력문 → 긍정 보존 / 곤란호소 포착은 불변')


def test_trap_renegation_concession_preserved():
    # 재부정("필요 없")·양보·부재선언은 개선요청 미발동 — 부정으로 안 감(긍↔부 안전).
    # 0709 갱신: 0702 무결점 정책으로 무보완 선언("보완할 점이 없다")은 긍정 아닌
    #   no_weakness_neutral(중립)이 정답 — 기대를 score>0 에서 score>=0 + 규칙 확인으로 교체.
    for s, want_rules in [
            ('보완할 점이 없다', ('no_weakness_neutral', 'no_weakness_positive')),
            ('어려움을 극복함', None),                       # 긍정 유지(rule4/구제)
            ('추가 보완은 필요 없음', ('no_weakness_neutral', 'no_weakness_positive'))]:
        score, rule = explain(0.8, 0.1, s, True, 1, neutral=0.1)
        assert rule != 'improvement_request_neutral' and rule != 'improvement_request_neg', \
            f'{s} 오강등: {rule}'
        assert score >= 0, f'{s} score={score}'
        if want_rules:
            assert rule in want_rules, f'{s} -> {rule}'
        else:
            assert score > 0, f'{s} score={score}'
    print('[OK] 재부정/양보/부재선언 → 부정 미생성(무결점=중립, 0702 정책)')


def test_excess_not_guarded_stays_critical():
    # '필요 이상'(과도=비판)은 불가결 가드에 없음 → has_constructive_need=True 유지(부→긍 차단)
    assert hcn('필요 이상으로 많은 회의') is True
    assert hcn('필요이상의 일에 시달림') is True
    print('[OK] 필요 이상(과도) → 건설적필요 유지(긍정 오구제 차단)')


if __name__ == '__main__':
    test_deficiency_framing_demoted_to_neutral()
    test_neutral_only_never_flips_to_negative()
    test_trap_indispensable_person_preserved()
    test_trap_helping_difficulty_preserved()
    test_trap_renegation_concession_preserved()
    test_excess_not_guarded_stays_critical()
    print('\n전체 통과 — improvement_request_neutral 골든·트랩 회귀')
