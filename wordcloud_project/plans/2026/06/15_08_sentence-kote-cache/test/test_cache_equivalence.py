"""캐시 경로 == fallback 경로 동일성 검증 (점수-only 재도출 포함).

KoTE 모델을 로딩하지 않도록 analyze_emotion / advanced_filter_profanity 를
결정론적 스텁으로 monkeypatch 한 뒤, 세 경로의 결과가 동일한지 확인한다:

  A. fallback        : sentence_cache=None  → compute_sentence_raw_scores 즉석 계산
  B. full cache      : {"sentence","pos","neg","neutral"} 포함 캐시
  C. score-only cache: sentence 필드 제거 → 읽기 측에서 split_sentences(doc)로 재도출

세 결과의 (sent, score, pos, neg) 튜플 리스트가 모두 같아야 한다.

실행: 프로젝트 루트(wordcloud_project)에서
  python plans/2026/0615_08_sentence-kote-cache/test/test_cache_equivalence.py
KoTE 미로딩이라 별도 허락 없이 실행 가능(경량).
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# --- 결정론적 스텁 주입 (KoTE/욕설필터 모델 로딩 회피) ---
import src.modules.emotion_analysis as _emo
import src.modules.profanity_filter as _prof


def _fake_analyze_emotion(text):
    """단어 기반 결정론적 감정 점수."""
    if '뛰어' in text or '훌륭' in text or '우수' in text:
        scores = {'positive': 0.85, 'negative': 0.10, 'neutral': 0.05}
    elif '아쉽' in text or '부족' in text or '미흡' in text:
        scores = {'positive': 0.15, 'negative': 0.75, 'neutral': 0.10}
    else:
        scores = {'positive': 0.20, 'negative': 0.20, 'neutral': 0.60}
    return {'analysis': {'base_result': {'mapped': {'sentiment_scores': scores}}}}


def _fake_profanity(text):
    return {'profanity_count': 1 if 'damn' in text.lower() else 0}


_emo.analyze_emotion = _fake_analyze_emotion
_prof.advanced_filter_profanity = _fake_profanity

from src.modules.sentence_emotion import compute_sentence_raw_scores
from src.services.perspective_service import _get_sentence_level_scores

SAMPLES = [
    "업무 능력이 뛰어납니다. 소통은 아쉽습니다. 전반적으로 우수한 직원입니다.",
    "성실하고 책임감이 훌륭합니다. 다만 협업이 미흡한 편입니다.",
    "this is a damn bad attitude. 하지만 성장 가능성은 뛰어납니다.",
    "",  # 빈 문서
    "짧음.",  # 5자 미만 → 필터됨
]


def _run():
    failures = 0
    for i, doc in enumerate(SAMPLES):
        cache = compute_sentence_raw_scores(doc)

        result_a = _get_sentence_level_scores(doc)                          # fallback
        result_b = _get_sentence_level_scores(doc, sentence_cache=cache)    # full cache
        score_only = [{k: v for k, v in e.items() if k != 'sentence'} for e in cache]
        result_c = _get_sentence_level_scores(doc, sentence_cache=score_only)  # score-only

        ok_ab = result_a == result_b
        ok_ac = result_a == result_c
        status = 'OK' if (ok_ab and ok_ac) else 'FAIL'
        if status == 'FAIL':
            failures += 1
        print(f"[{status}] sample#{i} (sentences={len(cache)})  A==B:{ok_ab}  A==C:{ok_ac}")
        if status == 'FAIL':
            print(f"    A(fallback)   = {result_a}")
            print(f"    B(full cache) = {result_b}")
            print(f"    C(score-only) = {result_c}")

    print("-" * 60)
    if failures == 0:
        print("ALL EQUIVALENT - cache/score-only/fallback results identical [OK]")
        return 0
    print(f"{failures} sample(s) FAILED - equivalence violated")
    return 1


if __name__ == '__main__':
    sys.exit(_run())
