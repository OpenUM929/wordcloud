# -*- coding: utf-8 -*-
"""leadership_polarity 골든/회귀 테스트 (KoTE·DB 불요, 빠름).

검증 (계획서 §12-2 코퍼스 실측 + §12-5):
  1) negation 칭찬(부정의 부정)은 positive로 판정 — 절대 negative로 망가지지 않음.
  2) 진짜 부정(~4건)은 negative로 판정.
  3) 긍정표지(방향제시/솔선수범…)는 positive.
  4) 표지 없는 일반 문장은 neutral → 호출부 기존 동작 보존(회귀 안전).
  5) 핵심가치: 긍↔부 오분류 0.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from src.modules.hr_context_lexicon import leadership_polarity as lp


def test_negation_praise_is_positive():
    praise = [
        '강압적이지 않음',
        '강압적이지않다',
        '고압적인 태도를 보이지 않음',
        '권위의식이 없음',
        '잔소리를 안한다',
        '부드러운 권위와 소통',          # '권위의식'이 아니라 '권위' → 부정표지 미매칭, 소통=긍정
    ]
    for s in praise:
        assert lp(s) == 'positive', f'negation 칭찬이 망가짐: {s} -> {lp(s)}'
    print('[OK] negation 칭찬 → positive (긍↔부 오분류 없음)')


def test_real_negatives_are_negative():
    neg = [
        '세세한 지시 감독하는 성향이 강함',
        '수직적 의사소통과 강력한 상관 마인드로 문제해결을 강요하며 구성원의 수동적 참여를 유도함',
        '출세의지가 강하고 회의 시 발언시간이 길다',
        '매사에 독단적으로 결정하고 일방적으로 지시한다',
    ]
    for s in neg:
        assert lp(s) == 'negative', f'진짜 부정 미검출: {s} -> {lp(s)}'
    print('[OK] 진짜 부정 → negative')


def test_positive_markers():
    pos = [
        '명확한 방향제시로 팀을 이끈다',
        '솔선수범하여 모범을 보임',
        '구성원에게 권한을 위임하고 자율적으로 일하게 한다',
        '경청하고 수평적으로 소통한다',
        '동기부여와 격려를 잘한다',
    ]
    for s in pos:
        assert lp(s) == 'positive', f'긍정표지 미검출: {s} -> {lp(s)}'
    print('[OK] 긍정표지 → positive')


def test_no_marker_is_neutral():
    neutral = [
        '업무 보고서를 작성하였다',
        '오전에 회의에 참석함',
        '엑셀 자료를 정리함',
        '',
    ]
    for s in neutral:
        assert lp(s) == 'neutral', f'표지 없는데 중립이 아님: {s!r} -> {lp(s)}'
    print('[OK] 표지 없음 → neutral (회귀 안전)')


if __name__ == '__main__':
    test_negation_praise_is_positive()
    test_real_negatives_are_negative()
    test_positive_markers()
    test_no_marker_is_neutral()
    print('\n전체 통과')
