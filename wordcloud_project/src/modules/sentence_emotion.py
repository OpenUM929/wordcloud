"""문장 단위 KoTE 원시 점수 — 배치 캐시 생성과 그룹 분석 fallback이 공유 (경량).

text_preprocessing(경량)만 직접 의존하므로 배치 워커에 matplotlib 미유입.
"""

import re


def compute_sentence_raw_scores(doc):
    """문서를 문장으로 분할 후 각 문장의 KoTE 원시 점수를 계산.

    Returns list[dict]: [{"sentence", "pos", "neg", "neutral"}, ...] (문장 없으면 [])
    반전 표지어 규칙·사용자 교정은 적용 전 — 원시 점수만 반환.
    """
    from src.modules.text_preprocessing import split_sentences
    from src.modules.emotion_analysis import analyze_emotion
    from src.modules.profanity_filter import advanced_filter_profanity

    out = []
    for sent in split_sentences(doc):
        try:
            # 영어 문장: 한국어 전용 KoTE 우회, 영어 욕설 필터로 부정/중립 결정
            total = len(sent.replace(' ', ''))
            if total > 0 and len(re.findall(r'[a-zA-Z]', sent)) / total > 0.7:
                prof = advanced_filter_profanity(sent)
                neg = 1.0 if prof.get('profanity_count', 0) > 0 else 0.0
                out.append({"sentence": sent, "pos": 0.0, "neg": neg, "neutral": 1.0 - neg})
                continue
            res = analyze_emotion(sent)
            s = (res.get('analysis', {}).get('base_result', {})
                    .get('mapped', {}).get('sentiment_scores', {}))
            out.append({"sentence": sent,
                        "pos": s.get('positive', 0.0) or 0.0,
                        "neg": s.get('negative', 0.0) or 0.0,
                        "neutral": s.get('neutral', 0.0) or 0.0})
        except Exception:
            out.append({"sentence": sent, "pos": 0.0, "neg": 0.0, "neutral": 0.0})
    return out


__all__ = ['compute_sentence_raw_scores']
