"""텍스트 전처리 모듈 — split_sentences 정의 (경량, 무거운 의존 없음)."""

import re

# 깨진 숫자 HTML 엔티티(&#NNNN; / &#xNN;) — CSV 인코딩 손상으로 코드포인트 자체가 어긋나
#   디코딩하면 엉뚱한 음절(&#48379;→'볻'≠보)이 나온다 → 복원 불가, 제거만 한다.
_HTML_ENTITY_RE = re.compile(r'&#[xX]?[0-9A-Fa-f]+;')
# 낱자모(ㅏ·ㅑ·ㄱ…) — 표준 한글은 조합형 음절(가~힣)이라 정상 평가문엔 낱자모가 거의 없다.
#   (조합형 음절 U+AC00–U+D7A3은 제외.)
_JAMO_RE = re.compile(r'[ᄀ-ᇿ㄰-㆏ꥠ-꥿ힰ-퟿]')


def _is_jamo_noise(s):
    """자모 난타/키보드 노이즈(예: 'ㅏㅐㅔ;/ㅑㅓ', '가나다라마바사')면 True → 채점 제외.

    보수적 임계(낱자모 비율 ≥ 0.5): 정상 문장은 낱자모 비율이 0에 가까우므로 진짜 평가문을
    떨어뜨리지 않는다(엔티티 제거로 남은 낱자모 1개 정도는 통과). '가나다라마바사'는 조합형이라
    비율로 안 잡혀 별도 처리.
    """
    nsp = [c for c in s if not c.isspace()]
    if not nsp:
        return True
    j = sum(1 for c in nsp if _JAMO_RE.match(c))
    return j / len(nsp) >= 0.5 or '가나다라마바사' in s


def split_sentences(text):
    """문서를 문장 단위로 분할. 인사말·깨진 HTML 엔티티·자모 노이즈 제외."""
    if not text:
        return []
    # 깨진 숫자 HTML 엔티티 제거(복원 불가) — 손상된 한 글자만 버리고 나머지 가독 텍스트는 보존.
    text = _HTML_ENTITY_RE.sub('', text)
    # 기본 분할: . ! ? \n
    raw = re.split(r'[.!?\n]+', text)
    sentences = [s.strip() for s in raw if s.strip()]
    # 인사말 필터
    greetings = {'감사합니다', '수고하셨습니다', '좋은 하루', '고맙습니다',
                 '감사드립니다', '수고 많으셨습니다'}
    filtered = []
    for s in sentences:
        if any(g in s for g in greetings):
            continue
        if len(s) < 5:  # 너무 짧은 문장 제외
            continue
        if _is_jamo_noise(s):  # 자모 난타/키보드 노이즈 제외(평가문 아님)
            continue
        filtered.append(s)
    return filtered


# ── 절(clause) 분리 — 혼합극성 문장을 단일극성 절로 쪼개기(데이터셋 빌드 전용) ──────
# 배경: split_sentences는 .!?\n 으로만 자르므로 "업무품질은 좋으나 퀄리티가 낮음" 같은
#   혼합극성 문장이 한 덩어리로 남아 극성 하나로 뭉개진다. 절 단위로 쪼개면 긍정절/부정절이
#   각각 독립 샘플이 되어 파인튜닝/리더십 라벨이 깨끗해진다(weak_labeling_lf 절 분리 합의).
# ⚠️ production split_sentences는 건드리지 않는다(집계·갤러리 영향 격리). 이 함수는
#   데이터셋 파이프라인에서만 호출한다.
# 핵심 안전: 절 경계는 '완결된 용언 + 연결어미' 뒤에 오므로 부정 범위(않/없/안)를 끊지
#   않는다. 예) "강압적이지 않으나 …" → '않으나'가 한 절 안에 통째로 남아 극성 보존.

# 연결어미가 '첫 절 끝'에 붙는 형태 — 경계는 표지 '뒤'. (역접·양보 연결어미 + 대조 관용구)
_CLAUSE_TRAILING = [
    '에도 불구하고', '기는 하지만', '기는 하나', '기는 했지만',
    '는 반면', '은 반면', '인 반면', '에 반해', '는 한편',
    '이지만', '지만', '건만', '더라도', '면서도', '으나', '는데', '은데', '기는',
]
# 대조 접속부사가 '둘째 절 시작'에 오는 형태 — 경계는 표지 '앞'.
# ('하지만'·'그렇지만'은 trailing '지만'이 이미 절단하므로 중복 제외)
_CLAUSE_LEADING = [
    '그럼에도', '그러나', '반면에', '반면',
    '그런데', '오히려', '도리어', '되레', '그래도', '다만',
]
_CLAUSE_MIN_LEN = 4  # 이보다 짧은 조각은 직전 절에 흡수(과분할 방지)


def split_clauses(sentence):
    """문장을 역접·양보 연결어미/접속부사 경계에서 절 단위로 분리한다.

    혼합극성("좋으나 낮음")을 단일극성 절들로 쪼개기 위한 데이터셋 빌드 전용 함수.
    표지가 없으면 [sentence] 한 개를 그대로 반환한다(분할 없음 = 안전한 기본값).

    부정 범위 보존: 연결어미는 완결된 용언 뒤에 오므로 '않/없/안' 같은 부정 토큰을
    절 중간에서 끊지 않는다(예: "강압적이지 않으나"는 한 절로 유지).
    """
    if not sentence:
        return []
    text = sentence.strip()
    if not text:
        return []

    # 경계 위치(문자 인덱스) 수집: trailing=표지 끝, leading=표지 시작.
    cuts = set()
    for mk in _CLAUSE_TRAILING:
        start = 0
        while True:
            pos = text.find(mk, start)
            if pos == -1:
                break
            end = pos + len(mk)
            # 앞에 용언 어간(2자 이상)이 있어야 연결어미로 인정(조사 '이나/나' 오탐 방지).
            if pos >= 2:
                cuts.add(end)
            start = end
    for mk in _CLAUSE_LEADING:
        start = 0
        while True:
            pos = text.find(mk, start)
            if pos == -1:
                break
            if pos >= 2:  # 문두 접속부사는 분리 불필요(이미 첫 절)
                cuts.add(pos)
            start = pos + len(mk)

    if not cuts:
        return [text]

    bounds = sorted(c for c in cuts if 0 < c < len(text))
    pieces, prev = [], 0
    for b in bounds:
        pieces.append(text[prev:b].strip())
        prev = b
    pieces.append(text[prev:].strip())

    # 과분할 흡수: 너무 짧은 조각은 직전 절에 합친다(첫 조각이 짧으면 다음에 합침).
    merged = []
    for p in pieces:
        if not p:
            continue
        if merged and len(p) < _CLAUSE_MIN_LEN:
            merged[-1] = (merged[-1] + ' ' + p).strip()
        elif merged and len(merged[-1]) < _CLAUSE_MIN_LEN:
            merged[-1] = (merged[-1] + ' ' + p).strip()
        else:
            merged.append(p)
    return merged or [text]


__all__ = ['split_sentences', 'split_clauses']
