# -*- coding: utf-8 -*-
"""0623_02 — rule3_last_low 긍→부 보강(역량표지 append + 접미부정/반어 가드 + no_weakness 저신뢰).

배경: 23년_장점 코퍼스(523,715행) 재판정에서 한 줄짜리 장점("보고능력 우수")이 곧 끝문장이라
  rule3_last_low로 무조건 부정화되던 긍→부 오분류를 발견. positive_rescue 표지를 보강해 먼저 구제.
검증: KoTE 재실행 없이 s값으로 보정 규칙만 호출(서버·GPU 불요). 긍↔부 오분류 0 잠금.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from src.services.perspective_service import _sentence_sentiment_override_explain as ov


def _lab(pos, neg, neu, sent, is_last=True, total=1):
    sc, rid = ov(pos, neg, sent, is_last, total, neutral=neu)
    return ('positive' if sc > 0 else ('negative' if sc < 0 else 'neutral')), rid


# (sent, pos, neg, neu, expected_label) — 끝문장(is_last=True) = 한 줄짜리 장점 평가 모델
POSITIVE_CASES = [
    ('보고능력 우수', 0.49, 0.39, 0.12),
    ('공정한 업무 수행', 0.44, 0.28, 0.28),
    ('능동적 사고방식으로 업무처리', 0.49, 0.44, 0.06),
    ('원만한 갈등 해결', 0.42, 0.37, 0.20),
    ('조작 및 상황대응이 신속정확함', 0.47, 0.36, 0.17),
    ('탁월한업무능력을 지닌 리더직원', 0.56, 0.38, 0.07),
    ('업무에 열성적입니다', 0.41, 0.39, 0.20),
    ('신속한 의사결정 및 적기 필요한 지시', 0.51, 0.32, 0.17),   # '필요한' 관형 → 긍정 유지
    ('부당한 사적이득 취하지 않고 공정한 업무를 수행', 0.44, 0.28, 0.28),  # 이중부정 긍정
]

# 진짜 부정 — 표지 보강 후에도 절대 긍정으로 새면 안 됨(긍↔부 0)
NEGATIVE_CASES = [
    ('업무실적이 없으며 열성적이지 않습니다', 0.10, 0.49, 0.41),       # 접미부정 '~지 않'
    ('상황을 본인에게만 유리하도록 유도하는 능력이 탁월함', 0.17, 0.69, 0.14),  # 반어
    ('업무능력을 탁월하나, 편향적인 생각과 이기적인 판단이 장점입니다', 0.40, 0.41, 0.19),  # 반어
    ('불공정한 업무처리', 0.44, 0.28, 0.28),                        # 불공정 context
    ('보완할 점이 많습니다', 0.43, 0.31, 0.26),                      # 결핍
    ('직원들간의 의사소통 필요', 0.17, 0.66, 0.17),                   # 건설적 필요
    ('업무에 관심이 없습니다', 0.09, 0.69, 0.22),                     # 직접 부정
]

# no_weakness 저신뢰 → 중립(긍↔부 무관). 약점-없음 선언.
NEUTRAL_CASES = [
    ('같이 근무해보니 보완할점 없음', 0.50, 0.44, 0.06),
]


def test_positive_rescued():
    for sent, p, n, u in POSITIVE_CASES:
        lab, rid = _lab(p, n, u, sent)
        assert lab == 'positive', '긍→부 누락: %s -> %s (%s)' % (sent, lab, rid)
    print('[OK] 역량 표지 긍정 구제 %d건 — 전부 positive' % len(POSITIVE_CASES))


def test_negative_preserved():
    for sent, p, n, u in NEGATIVE_CASES:
        lab, rid = _lab(p, n, u, sent)
        assert lab == 'negative', '부→긍 위반(핵심가치): %s -> %s (%s)' % (sent, lab, rid)
    print('[OK] 진짜 부정 보존 %d건 — 부→긍 0 (접미부정/반어/불공정/결핍/필요 가드)' % len(NEGATIVE_CASES))


def test_noweakness_neutral():
    for sent, p, n, u in NEUTRAL_CASES:
        lab, rid = _lab(p, n, u, sent)
        assert lab == 'neutral', 'no_weakness 중립화 실패: %s -> %s (%s)' % (sent, lab, rid)
    print('[OK] 약점-없음 선언 저신뢰 중립화 %d건' % len(NEUTRAL_CASES))


if __name__ == '__main__':
    test_positive_rescued()
    test_negative_preserved()
    test_noweakness_neutral()
    print('\n전체 통과 — 긍↔부 오분류 0')
