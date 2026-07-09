"""문장 단위 KoTE 원시 점수 — 배치 캐시 생성과 그룹 분석 fallback이 공유 (경량).

text_preprocessing(경량)만 직접 의존하므로 배치 워커에 matplotlib 미유입.
"""

import re

# 문장 묶음당 1회 GPU forward pass로 처리할 최대 문장 수
# (벤치마크 기준 배치 32에서 speedup이 가장 컸고, 그 이상은 VRAM 대비 이득이 줄어듦)
_SENTENCE_BATCH_SIZE = 32


def compute_sentence_raw_scores(doc):
    """문서를 문장으로 분할 후 각 문장의 KoTE 원시 점수를 계산.

    Returns list[dict]: [{"sentence", "pos", "neg", "neutral", "top3"}, ...] (문장 없으면 [])
    반전 표지어 규칙·사용자 교정은 적용 전 — 원시 점수만 반환.

    top3: 매핑된 44개 감정 중 상위 3개 [[label, confidence], ...]. KoTE 후처리가
    이미 계산한 값이라 추가 추론 비용 0. 영어 우회 문장은 []. 감정 단위 분석 시
    KoTE 재실행을 피하기 위한 핸드오프 코퍼스 원천(0622_01).

    한국어 문장은 모아서 배치로 추론(GPU 커널 launch 오버헤드 절감 — 개별 호출 대비
    벤치마크 기준 최대 약 7배). 영어 문장은 기존처럼 KoTE를 우회한다.
    """
    from src.modules.text_preprocessing import split_sentences
    from src.modules.emotion_analysis import analyze_emotion_batch
    from src.modules.profanity_filter import advanced_filter_profanity

    sentences = split_sentences(doc)
    out = [None] * len(sentences)
    korean_idx = []
    korean_sents = []

    for idx, sent in enumerate(sentences):
        # 영어 문장: 한국어 전용 KoTE 우회, 영어 욕설 필터로 부정/중립 결정
        total = len(sent.replace(' ', ''))
        if total > 0 and len(re.findall(r'[a-zA-Z]', sent)) / total > 0.7:
            prof = advanced_filter_profanity(sent)
            neg = 1.0 if prof.get('profanity_count', 0) > 0 else 0.0
            out[idx] = {"sentence": sent, "pos": 0.0, "neg": neg, "neutral": 1.0 - neg, "top3": []}
        else:
            korean_idx.append(idx)
            korean_sents.append(sent)

    for i in range(0, len(korean_sents), _SENTENCE_BATCH_SIZE):
        chunk_idx = korean_idx[i:i + _SENTENCE_BATCH_SIZE]
        chunk_sents = korean_sents[i:i + _SENTENCE_BATCH_SIZE]
        try:
            batch_res = analyze_emotion_batch(chunk_sents)
        except Exception:
            batch_res = [None] * len(chunk_sents)

        for idx, sent, res in zip(chunk_idx, chunk_sents, batch_res):
            try:
                mapped = (res.get('analysis', {}).get('base_result', {})
                             .get('mapped', {}))
                s = mapped.get('sentiment_scores', {})
                top3 = [[t.get('label'), t.get('confidence', 0.0) or 0.0]
                        for t in (mapped.get('top_3') or [])[:3]]
                out[idx] = {"sentence": sent,
                            "pos": s.get('positive', 0.0) or 0.0,
                            "neg": s.get('negative', 0.0) or 0.0,
                            "neutral": s.get('neutral', 0.0) or 0.0,
                            "top3": top3}
            except Exception:
                out[idx] = {"sentence": sent, "pos": 0.0, "neg": 0.0, "neutral": 0.0, "top3": []}

    return out


__all__ = ['compute_sentence_raw_scores']
