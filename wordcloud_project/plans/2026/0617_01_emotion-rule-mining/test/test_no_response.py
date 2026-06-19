# -*- coding: utf-8 -*-
"""no_response_neutral 규칙 골든/회귀 테스트 (KoTE 불요, 빠름).

검증:
  1) 무응답/평가불가/내용없음/낙서 → no_response_neutral 발동(중립 0.0).
  2) 진짜 부정(부정암시어/완곡부정 혼합) → 미발동(부정 보존, 부→중 강등 차단).
  3) 진짜 긍정(긍정표지, 무응답 표지 없음) → positive_rescue 유지(중립화 안 됨).
  4) is_no_response 술어 단위 동작(낙서/구문/혼합).
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from src.services.perspective_service import (
    _sentence_sentiment_override_explain as explain,
    is_no_response, is_gibberish,
)


def test_no_response_neutralized():
    """평가불가/내용없음/낙서: 부정으로 강등되지 않고 no_response_neutral로 중립화."""
    cases = [
        '잘 모르겠습니다',
        '잘모르겠음',
        '뵌 적이 없어서 잘 모르겠습니다',
        '같이 일해 본적이 없어서 잘 모르겠어요',
        '본부장 이름도 모르겠음',
        '인사이동후 대면한 적이 없어서 평가 할 수가 없습니다',
        '특별한 장점을 알지 못합니다',
        '내용없음 내용없음 내용없음',
        '특이사항 및 해당사항 없음',
        '의견이 없습니다',
        '특별히 서술할 내용 없음',
        '장점은 딱히 잘모르겠습니다 10자 채우라니까 씀니다',
        'ㅈㅈㅈㅈㅈㅈㅈㅈㅈㅈ',
        '성실성실성실성실성실',
    ]
    for s in cases:
        # is_last + 고neg(코퍼스 실측): 신규 분기 없으면 rule4_default로 부정 갈 조건.
        # 고neg라 '성실' 반복 낙서도 positive_rescue(neg<0.85)가 아닌 무응답 분기로 수렴.
        score, rule = explain(0.1, 0.9, s, True, 1, neutral=0.05)
        assert rule == 'no_response_neutral', f'무응답 미중립화: {s} -> {rule}'
        assert score == 0.0, f'{s} score={score} (중립 0.0 기대)'
    print('[OK] 무응답/낙서 → no_response_neutral 중립화(중립→부정 오류 제거)')


def test_real_negative_with_noresp_marker_preserved():
    """무응답 표지가 섞여도 진짜 부정 신호가 있으면 중립화하지 않음(부정 보존)."""
    cases = [
        '소통이 부족한지 잘 모르겠습니다',     # 부정암시어 '부족'
        '개선의 여지가 있는지 잘 모르겠습니다',  # 완곡부정 '개선의 여지'
    ]
    for s in cases:
        assert is_no_response(s) is False, f'진짜 부정이 무응답으로 중립화됨: {s}'
    print('[OK] 무응답 표지 + 진짜 부정 신호 → 중립화 차단(부→중 강등 없음)')


def test_real_positive_not_neutralized():
    """무응답 표지가 없는 진짜 긍정은 positive_rescue 유지(중립화 안 됨)."""
    cases = ['업무열의가 매우 높습니다', '수평적 의사소통으로 자발적 참여를 유도함', '솔선수범하여 모범을 보임']
    for s in cases:
        score, rule = explain(0.2, 0.3, s, True, 1, neutral=0.5)
        assert rule == 'positive_rescue', f'긍정이 무응답으로 잘못 처리됨: {s} -> {rule}'
        assert score > 0, f'{s} score={score}'
    print('[OK] 진짜 긍정 → positive_rescue 유지(무응답 분기 미발동)')


def test_is_gibberish_predicate():
    assert is_gibberish('ㅂㅂㅂㅂㅂㅂㅂ')
    assert is_gibberish('11111111111111')
    assert is_gibberish('---------------')
    assert is_gibberish('ㄴㅇㄻㄴㅇㄻㄴㅇㄹ')
    assert is_gibberish('성실성실성실')          # 동일 토큰 3회+
    assert not is_gibberish('성실한 직원')        # 정상 문장
    assert not is_gibberish('소통')               # 짧은 정상어
    assert not is_gibberish('수평적 의사소통')
    print('[OK] is_gibberish 술어 동작(낙서 검출/정상어 보존)')


if __name__ == '__main__':
    test_no_response_neutralized()
    test_real_negative_with_noresp_marker_preserved()
    test_real_positive_not_neutralized()
    test_is_gibberish_predicate()
    print('\n전체 통과')
