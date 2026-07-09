# -*- coding: utf-8 -*-
"""인사평가 리더십 문맥 극성 어휘집 (negation 인식).

배경 (계획서 0617_01 §12):
  - 본 시스템에는 문맥을 파악하는 별도 AI가 없다. 리더십 모듈은 키워드 매칭 +
    감정점수만으로 채점하여, `수직적 의사소통…강요` 같은 부정 리더십도
    `소통/문제해결` 키워드 때문에 강점으로 오채점된다.
  - 그렇다고 단순 키워드 게이트(강요/수직 = 부정)를 두면, 코퍼스의 부정표지
    11건 중 대부분을 차지하는 "부정어의 부정 = 칭찬"(예: `강압적이지 않음`,
    `권위의식이 없음`, `잔소리를 안한다`)을 부정으로 망가뜨려 역효과가 난다.
  - 따라서 규칙 기반이되 **negation을 인식**하는 극성 판정이 필요하다.

데이터 근거 (refine_diag_260617.csv, 475문장 실측 §12-2):
  부정표지 문장 11건 중 진짜 부정은 ~4건, 나머지는 negation 칭찬.
  | 문장 예                              | 표면표지   | 실제   |
  |--------------------------------------|-----------|--------|
  | 강압적이지 않음 / 강압적이지않다     | 강압      | 긍정   |
  | 고압적인 태도를 보이지 않음          | 고압      | 긍정   |
  | 권위의식이 없음                      | 권위의식  | 긍정   |
  | 잔소리를 안한다                      | 잔소리    | 긍정   |
  | 세세한 지시 감독하는 성향이 강함     | 지시감독  | 부정   |
  | 수직적…강요하며…수동적 참여 유도     | 강요/수직 | 부정   |
  | 출세의지가 강하고 발언시간 길다      | 출세      | 부정   |

핵심 가치: 긍↔부 오분류만 방지(중립→긍정은 허용). 표지가 없으면 'neutral'을
반환하여 호출부의 기존 동작을 바꾸지 않는다(회귀 안전).

이 모듈은 KoTE·DB·서버에 의존하지 않는 순수 문자열 로직이다.
"""

# 리더십 강점(긍정) 표지 — 코퍼스 + word_boost.json 근거.
# 다어절 구문/특정 명사로 한정하여 오탐을 줄인다(예: '권위'가 아니라 '권위의식'은 부정쪽).
POSITIVE_MARKERS = [
    "방향제시", "방향 제시", "비전제시", "비전 제시", "비전",
    "솔선수범", "솔선 수범", "모범",
    "동기부여", "동기 부여", "격려", "칭찬", "인정해",
    "코칭", "코칭해", "지도해", "육성",
    "위임", "권한위임", "권한 위임", "자율", "자율적",
    "경청", "수평적", "소통", "의사소통",
    "배려", "존중", "신뢰", "헌신", "화합", "포용",
]

# 리더십 약점(부정) 표지 — 코퍼스 실측 부정표지.
# negation(않/없/안…)이 뒤따르면 '부정어의 부정 = 칭찬'으로 극성이 반전된다.
NEGATIVE_MARKERS = [
    "강요", "강압", "고압", "압박",
    "수직적", "일방적", "독단", "독선", "권위의식", "권위적",
    "세세한 지시", "세세히 지시", "지시 감독", "지시감독", "간섭",
    "잔소리", "상관 마인드", "상관마인드",
    "수동적 참여", "출세의지", "출세",
]

# 부정 종결/부정어 — 직전 부정표지를 무력화(부정의 부정 = 칭찬)한다.
NEGATION_TOKENS = ["않", "없", "아니", "안 ", "안한", "안하", "않으", "못하", "지마", "지 마"]

# 부정표지 뒤로 negation을 탐색하는 창(글자 수).
# 예) "고압적인 태도를 보이지 않음" → '고압' 뒤 12글자 내에 '않' 존재.
NEGATION_WINDOW = 14


def _has_negation_after(text, start):
    """start 위치부터 NEGATION_WINDOW 글자 내에 부정어가 있으면 True."""
    window = text[start:start + NEGATION_WINDOW]
    return any(tok in window for tok in NEGATION_TOKENS)


def leadership_polarity(text):
    """리더십 문맥의 극성을 'positive'|'negative'|'neutral'로 판정한다.

    규칙(데이터 근거, 추측 금지):
      1) 부정표지가 있고 그 직후 창에 negation이 있으면 = 칭찬(부정의 부정).
      2) 부정표지가 있고 negation이 없으면 = 진짜 부정.
      3) 진짜 부정이 하나라도 있으면 'negative'(가장 보수적).
      4) 진짜 부정이 없고, (negation 칭찬 OR 긍정표지)가 있으면 'positive'.
      5) 어떤 표지도 없으면 'neutral'(호출부 기존 동작 유지 → 회귀 안전).
    """
    if not text:
        return "neutral"

    has_real_negative = False
    has_negated_praise = False

    for marker in NEGATIVE_MARKERS:
        idx = 0
        while True:
            pos = text.find(marker, idx)
            if pos == -1:
                break
            after = pos + len(marker)
            if _has_negation_after(text, after):
                has_negated_praise = True
            else:
                has_real_negative = True
            idx = after

    if has_real_negative:
        return "negative"

    has_positive = any(m in text for m in POSITIVE_MARKERS)
    if has_negated_praise or has_positive:
        return "positive"

    return "neutral"


def is_negation_praise(text):
    """'부정어의 부정 = 칭찬'에 한정해 True를 반환한다(진짜 부정 0 + negation 칭찬 존재).

    감정보정(perspective_service)의 신규 분기 전용 술어. 진짜 부정표지(negation 없는
    강요·수직적 등)가 하나라도 있으면 False → 긍↔부 오분류를 원천 차단한다.
    긍정표지만 있는 일반 칭찬은 False(기존 positive_rescue가 처리하므로 영향 없음).
    """
    if not text:
        return False
    has_real_negative = False
    has_negated_praise = False
    for marker in NEGATIVE_MARKERS:
        idx = 0
        while True:
            pos = text.find(marker, idx)
            if pos == -1:
                break
            after = pos + len(marker)
            if _has_negation_after(text, after):
                has_negated_praise = True
            else:
                has_real_negative = True
            idx = after
    return has_negated_praise and not has_real_negative
