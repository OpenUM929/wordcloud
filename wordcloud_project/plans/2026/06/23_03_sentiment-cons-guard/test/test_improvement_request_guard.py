# -*- coding: utf-8 -*-
"""0623_03 — 단점 맥락 부→긍 가드(has_improvement_request).

배경: 23_단점.csv(505,011행) 적대검증에서 positive_rescue가 역량/긍정 표지를 단점 프레이밍
  (개선 바람·요함/요망·보완요청·곤란)에서도 구제 → 부→긍 11,039(핵심가치 위반). 가드로 −2,237.
케이스 점수(kote)는 23_단점.csv 실측 s값. 끝문장(is_last=True)=한 줄 평가 모델. 긍↔부 0 잠금.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from src.services.perspective_service import _sentence_sentiment_override_explain as ov
from src.services.perspective_service import has_improvement_request


def _lab(p, n, u, sent, is_last=True, total=1):
    sc, rid = ov(p, n, sent, is_last, total, neutral=u)
    return ('positive' if sc > 0 else ('negative' if sc < 0 else 'neutral')), rid


# 단점 프레이밍 — 가드가 부→긍 구제를 차단해야 함(전부 negative). 점수는 23_단점.csv 실측.
NEGATIVE_CASES = [
    ('적극적으로 업무를 하는 모습을 보여주었으면 좋겠음', 0.18, 0.81, 0.01),   # wish
    ('좀 더 적극적인 행동으로 직원들에게 다가갔으면 함', 0.16, 0.83, 0.01),     # wish(았으면 함)
    ('자기개발에 좀 더 시간을 쓰면 좋겠음', 0.38, 0.58, 0.04),               # wish(면 좋겠)
    ('의사소통에 어려움이 있습니다', 0.05, 0.84, 0.11),                     # difficulty
    ('감정변화가 잦아 협업이 어려움', 0.06, 0.80, 0.14),                    # difficulty
    ('어학 공부에 대한 열의 요망', 0.23, 0.67, 0.10),                      # need(요망)
    ('좀더 적극적으로 생활요함', 0.34, 0.57, 0.09),                        # need(요함)
    ('주변 동료와의 관계게 있어서 보완해야함', 0.31, 0.42, 0.27),            # improve_request
]

# trap 보존 — 가드가 발동하면 안 됨(긍↔부 0 양방향). 긍정/중립 유지.
SAFE_CASES = [
    ('어려움을 극복하고 성과를 냄', 0.45, 0.30, 0.25, 'positive'),          # 어려움 극복
    ('개선 및 보완필요점 없음', 0.16, 0.60, 0.24, 'neutral'),               # 보완필요점 없음=약점없음
    ('업무가 매우 중요함을 인지하고 신속처리', 0.49, 0.36, 0.15, 'positive'),  # '중요함'⊅요함 trap
    ('신속한 의사결정 및 적기 필요한 지시', 0.51, 0.32, 0.17, 'positive'),    # '필요한' 관형
    ('탁월한업무능력을 지닌 리더직원', 0.56, 0.38, 0.07, 'positive'),         # 순수 긍정(가드 무관)
]


def test_cons_framing_negative():
    for sent, p, n, u in NEGATIVE_CASES:
        assert has_improvement_request(sent), '가드 미발동: %s' % sent
        lab, rid = _lab(p, n, u, sent)
        assert lab == 'negative', '부→긍 위반(핵심가치): %s -> %s (%s)' % (sent, lab, rid)
    print('[OK] 단점 프레이밍 부→긍 차단 %d건 — 전부 negative' % len(NEGATIVE_CASES))


def test_traps_preserved():
    for sent, p, n, u, exp in SAFE_CASES:
        lab, rid = _lab(p, n, u, sent)
        assert lab == exp, 'trap 위반(긍/중→부): %s -> %s (기대 %s, %s)' % (sent, lab, exp, rid)
    # '중요함'·'어려움 극복'·'보완…없음'에 가드가 발동하지 않아야 함
    assert not has_improvement_request('업무가 매우 중요함을 인지하고 신속처리')
    assert not has_improvement_request('어려움을 극복하고 성과를 냄')
    print('[OK] trap 보존 %d건 — 극복/약점없음/중요함/관형필요 안전' % len(SAFE_CASES))


if __name__ == '__main__':
    test_cons_framing_negative()
    test_traps_preserved()
    print('\n전체 통과 — 긍↔부 오분류 0 (양방향)')
