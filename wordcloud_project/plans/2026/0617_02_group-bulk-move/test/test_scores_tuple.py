"""_get_sentence_level_scores 5-튜플화 회귀 테스트 (캐시 경로, KoTE 불요).

기존 (sent, score, pos, neg) 값이 불변이고 neutral이 5번째로 추가됨을 단언.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from src.services.perspective_service import _get_sentence_level_scores, sentence_sentiment_override

DOC = "목표의식이 강합니다. 그러나 보고는 미흡합니다. 무난한 수준입니다."
CACHE = [
    {'sentence': '목표의식이 강합니다.', 'pos': 0.40, 'neg': 0.03, 'neutral': 0.57},
    {'sentence': '그러나 보고는 미흡합니다.', 'pos': 0.02, 'neg': 0.88, 'neutral': 0.10},
    {'sentence': '무난한 수준입니다.', 'pos': 0.05, 'neg': 0.05, 'neutral': 0.90},
]


def test_five_tuple_shape_and_values():
    res = _get_sentence_level_scores(DOC, sentence_cache=CACHE)
    assert len(res) == 3, res
    total = len(CACHE)
    for i, tup in enumerate(res):
        assert len(tup) == 5, f"5-튜플 아님: {tup}"
        sent, score, pos, neg, neutral = tup
        c = CACHE[i]
        # 기존 (pos, neg) 값 불변
        assert pos == c['pos'] and neg == c['neg'], (i, tup)
        # neutral 신규 5번째 = 캐시값
        assert neutral == c['neutral'], (i, tup)
        # score = 독립 호출과 동일 (회귀 보존)
        expected = sentence_sentiment_override(
            c['pos'], c['neg'], c['sentence'], (i == total - 1), total, neutral=c['neutral']
        )
        assert abs(score - expected) < 1e-9, (i, score, expected)
    print('[OK] 5-튜플 + (pos,neg) 불변 + neutral 추가 + score 동일')


def test_correction_path():
    # 사용자 교정(긍정 강제) 반영 후에도 5-튜플 유지
    res = _get_sentence_level_scores(DOC, corrections={'1': 'positive'}, sentence_cache=CACHE)
    assert all(len(t) == 5 for t in res)
    assert res[1][1] > 0, res[1]   # idx1: 부정→긍정 강제 시 score>0
    print('[OK] 교정 경로 5-튜플 유지')


if __name__ == '__main__':
    test_five_tuple_shape_and_values()
    test_correction_path()
    print('\n전체 통과')
