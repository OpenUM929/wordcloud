# -*- coding: utf-8 -*-
"""사람 정렬 라벨러 — 사람 gold vs AI 불일치(2026-06-24)에서 학습한 규칙.

학습 출처(analyze_disagreements): G1 380건 약점부재→중립 · g4 요청/무종결 · field_conflict.
3원칙([[feedback_incomplete_fragment_neutral]]) + 약점부재·표지 결합.

label(text) → (polarity, confidence). confidence='high'면 사람과 잘 맞아 자동 처리 가능,
'low'(uncertain)면 사람 검토 필요. → baseline은 uncertain만 남겨 축소.
"""
import re

# 1) 약점부재 선언: (보완/단점/개선점/특이사항…) 직후 창에 (없/않/아니) → 중립/긍정.
#    ⚠️ '장점'은 제외 — "장점이 없다"=장점부재=부정(아래 _NOSTRENGTH로 별도 처리).
_NOWEAK_NOUN = ['보완필요점', '보완 필요점', '보완점', '보완사항', '보완 사항', '보완',
                '단점', '개선점', '개선 사항', '개선사항', '특이사항', '특이 사항',
                '문제점', '결점', '지적사항', '미흡한 점', '아쉬운 점']
_NEG_TOK = ('없', '않', '아니', '보이지', '딱히')
# 장점부재("장점이 없다/하나도 없음/딱히 없")=강점 없음=부정.
_STRENGTH_NOUN = ('장점', '강점', '잘하는', '뛰어난 점')

# 2) 요청표지 → 부정(개선요청). 명사형(향상/제고)·동사화(개선하)·관형사('필요한 N')는 오탐 → 제외.
#    '필요한'(관형: "필요한 전문지식")은 요청 아님 → 부정 lookahead로 차단.
_REQ = re.compile(r'필요(?!\s*없|함이 없|한 |한[가-힣])|권고|해야|요구(?!사항 없)|요망|당부|바람|바랍|했으면|면 좋겠|면 좋을|하면 좋|권장')

# 3) 종결(서술어) 감지 — 없으면 무종결 단편(단, 명확표지 없을 때만 중립)
_END = re.compile(r'(합니다|습니다|니다|함|했|한다|됨|된다|임|있음|없음|뛰어남|많음|높음|강함|'
                  r'우수함|성실함|좋음|다|요|까|네|죠|보임|드림|줌|옴|감|짐|킴|냄|봄)$')

# 4) 명확 표지 — 부분문자열 함정 제거(기여=성과기여도, 책임=무책임, 성실=불성실 → 제외).
_POS = re.compile(r'우수|탁월|뛰어|훌륭|적극|원활|친절|모범|열정|꼼꼼|능숙|끈기|집념|'
                  r'솔선수범|배려|몰입|도전적|최선|열의|화합|공정|신중|풍부|해박|친화|성취|앞장|멘토')
# 부정표지(고정밀, 부분문자열 함정 적음). 직후 재부정(없/않/아니)이면 제외.
# ⚠️ 한글 부분문자열 함정 제외: '무능'(⊂업**무능**력)·'태만'(⊂상**태만**)·'안함'(⊂편**안함**) 미수록.
_NEG = ['부족', '미흡', '결여', '부재', '소홀', '저조', '불만', '비협조', '이기주의', '이기적',
        '고압', '갈등', '치우침', '전가', '기회주의', '모호', '회피', '독단', '불성실',
        '미숙', '못함', '못합', '떨어짐', '떨어집', '결함', '폄하', '강압', '무책임', '비도덕',
        '아쉽', '아쉬움', '아쉬운', '오해', '미비', '힘들', '힘듦', '곤란', '버거']
# 대조/양보 연결어미 — 있으면 진짜 혼합(절 분리 권장), 없으면 결핍술어가 트레이트를 부정 → 부정.
_CONTRAST = ('지만', '으나', '하나', '는데', '라도', '어도', '에도', '반면', '그러나')


def _is_noweakness(t):
    for n in _NOWEAK_NOUN:
        i = t.find(n)
        while i != -1:
            if any(g in t[i + len(n):i + len(n) + 6] for g in _NEG_TOK):
                return True
            i = t.find(n, i + len(n))
    return False


def _is_nostrength(t):
    """장점부재("장점이 없다/하나도 없음")=강점 없음=부정."""
    for n in _STRENGTH_NOUN:
        i = t.find(n)
        while i != -1:
            if any(g in t[i + len(n):i + len(n) + 7] for g in ('없', '않', '못', '아니')):
                return True
            i = t.find(n, i + len(n))
    return False


# 과잉(긍정 트레이트가 '너무/과도'면 비판) / 긍정표지 직접부정('적극적이지 않음')
# '너무'는 양가적("너무 잘함"=긍정)이라 제외 — 명확한 과잉어만.
_EXCESS = re.compile(r'과도|과하게|과한|지나치|과할 때|과함|과해서')
_POSNEG = re.compile(r'지 않|지않|지 못|지못|이 없|가 없|않음|않다|않고|못함|못하')
# '필요'가 요청이 아닌 경우(약점부재/부정의 부정): 불필요·필요하지 않·필요 없·필요한…없
_REQ_FALSE = re.compile(r'불필요|필요하지\s*않|필요치\s*않|필요\s*없|필요없|필요한[^.]{0,10}없|필요점[^.]{0,8}없|필요[^.]{0,8}없')
_COND = ('다면', '하면 ', '보다 더', '보다 적', '보다 좀', '보다 많', '된다면', '진다면', '갖는다면')
_HOPE = ('기대', '좋겠', '좋을', '바람', '것으로', '면 좋', '성장할', '발전할')


def _is_suggestion(t):
    """조건부('~다면/하면/보다 더') + 기대('기대/좋/것으로') = 개선제언(보완점) → 부정.

    "더 적극적이라면 중추로 성장할 것으로 기대됨"처럼 칭찬어가 있어도 실은 보완점.
    조건 없는 순수 기대("향후 발전 기대됨")는 미발동(긍정 보존).
    """
    return any(c in t for c in _COND) and any(h in t for h in _HOPE)


def _has_unnegated_neg(t):
    """부정표지가 직후 창에서 재부정(없/않/아니)되지 않고 등장하면 True."""
    for w in _NEG:
        i = t.find(w)
        while i != -1:
            tail = t[i + len(w):i + len(w) + 5]
            if not any(r in tail for r in ('없', '않', '아니')):
                return True
            i = t.find(w, i + len(w))
    return False


def label(text):
    t = (text or '').strip()
    if not t:
        return ('neutral', 'low')
    if _is_nostrength(t):
        return ('negative', 'high')         # 장점부재("장점이 없다") → 부정
    if _is_noweakness(t):                    # 약점부재("보완점 없음")
        return ('positive', 'high') if _POS.search(t) else ('neutral', 'low')  # +칭찬=긍정 / 맨=중립
    pos = bool(_POS.search(t))
    if pos and _EXCESS.search(t) and not any(c in t for c in _CONTRAST):  # "너무 적극적"=과잉 비판
        return ('negative', 'high')
    if pos and _POSNEG.search(t):            # 긍정표지 직접 부정 "적극적이지 않음/열의가 없"
        return ('negative', 'high')
    neg = _has_unnegated_neg(t)
    if neg and not pos:                      # 부정표지 우선(무종결보다 먼저) — "대화 부재"
        return ('negative', 'high')
    if _REQ.search(t) and not _REQ_FALSE.search(t):   # 개선요청(단, 불필요/필요없 오인 제외)
        return ('negative', 'high')
    if _is_suggestion(t):                     # 조건부 개선제언("~다면 …기대됨") — 칭찬어보다 우선
        return ('negative', 'high')
    if pos and not neg:
        return ('positive', 'high')
    if pos and neg:                          # 긍정표지 + 결핍술어
        if any(c in t for c in _CONTRAST):
            return ('neutral', 'low')        # 대조("원활하나 부족") → 혼합, 분리 권장
        return ('negative', 'high')          # "배려가 아쉽다" = 트레이트 부정 → 부정
    if not _END.search(t):
        return ('neutral', 'low')            # 무종결 + 표지없음 → 사람(precision 낮음, 자동 금지)
    return ('neutral', 'low')


def reason(text):
    t = (text or '').strip()
    if _is_nostrength(t):
        return '장점부재("장점 없다") → 부정'
    if _is_noweakness(t):
        return '약점부재+칭찬 → 긍정' if _POS.search(t) else '약점부재(맨) → 중립'
    pos = bool(_POS.search(t))
    if pos and _EXCESS.search(t) and not any(c in t for c in _CONTRAST):
        return '과잉(너무/과도+긍정트레이트) → 부정'
    if pos and _POSNEG.search(t):
        return '긍정표지 직접부정 → 부정'
    neg = _has_unnegated_neg(t)
    if neg and not pos:
        return '부정표지 → 부정'
    if _REQ.search(t) and not _REQ_FALSE.search(t):
        return '요청표지 → 부정(개선요청)'
    if _is_suggestion(t):
        return '조건부 개선제언(~다면 기대) → 부정'
    if pos and not neg:
        return '긍정표지 → 긍정'
    if pos and neg:
        return '대조(혼합) → 분리 권장' if any(c in t for c in _CONTRAST) else '긍정표지+결핍술어 → 부정'
    if not _END.search(t):
        return '무종결+표지없음 → 사람'
    return '표지없음 → 사람'


if __name__ == '__main__':
    # 검증: 완료 gold 3종에서 사람과 일치율(이전 ai_reference 대비)
    import json
    import os
    import sys
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass
    D = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'eval'))
    from collections import Counter
    for fn in ['group_needs_human_260624.jsonl', 'group_needs_human_g4_260624.jsonl',
               'field_conflict_review_260624.jsonl']:
        rows = [json.loads(l) for l in open(os.path.join(D, fn), encoding='utf-8')]
        done = [r for r in rows if r.get('human_decision') and r['human_decision'] != 'skip']
        if not done:
            continue
        agree = hi = hi_agree = 0
        conf = Counter()
        for r in done:
            pol, c = label(r['text'])
            hd = r['human_decision']
            if pol == hd:
                agree += 1
            if c == 'high':
                hi += 1
                if pol == hd:
                    hi_agree += 1
            conf[c] += 1
        n = len(done)
        print(f'{fn}: 전체일치 {agree}/{n}={100*agree/n:.0f}% · '
              f'high {hi}({100*hi/n:.0f}%) 그중 일치 {100*hi_agree/max(1,hi):.0f}% · low {conf["low"]}')
