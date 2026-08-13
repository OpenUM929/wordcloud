# -*- coding: utf-8 -*-
"""메타데이터 통합 분석에 문장단위 감정보정(override)이 적용되는지 검증.

calculate_consolidated_analysis가 raw KoTE가 아니라 override-보정 라벨로
overall_sentiment·감정별 단어버킷을 산출하는지 확인한다.
sentence_emotion_cache를 직접 주입하므로 KoTE 로드/서버 불요.

검증:
  1) positive_rescue: raw 중립(neutral_dominant)인 긍정표지 문장 → 메타데이터 positive.
  2) no_response_neutral: raw 부정인 '잘 모르겠습니다' → 메타데이터 neutral(부정 아님).
  3) 진짜 부정(완곡부정/부정어) → 메타데이터 negative 유지.
  4) 단어버킷: 보정 라벨 기준으로 meaningful_words가 분류됨.
"""
import os
import sys

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, ROOT)

from src.modules.metadata_analysis import calculate_consolidated_analysis  # noqa: E402


def _ev(doc, cache, words):
    """가짜 평가 1건: gate 통과용 emotion_analysis_results + 캐시 + nlp 단어."""
    return {
        'evaluation_document': doc,
        'emotion_analysis_results': {},          # gate 키만 필요
        'sentence_emotion_cache': cache,
        'nlp_analysis_results': {'meaningful_words': words},
    }


def test_positive_rescue_reflected():
    # raw: neutral_dominant(neu>pos, neu>=neg-0.05) 이지만 긍정표지 → positive_rescue
    ev = _ev('대내외 소통을 통한 회사정책 홍보 능력 탁월',
             [{'sentence': '대내외 소통을 통한 회사정책 홍보 능력 탁월',
               'pos': 0.36, 'neg': 0.10, 'neutral': 0.54}],
             ['홍보', '능력'])
    out = calculate_consolidated_analysis([ev])
    assert out['overall_sentiment'] == 'positive', out['overall_sentiment']
    assert '홍보' in out['consolidated_emotion_words']['positive']
    print('[OK] positive_rescue → 메타데이터 positive + 긍정 단어버킷')


def test_no_response_neutralized():
    # raw 부정(neg 우세)인 '잘 모르겠습니다' → no_response_neutral → neutral
    ev = _ev('잘 모르겠습니다',
             [{'sentence': '잘 모르겠습니다', 'pos': 0.1, 'neg': 0.9, 'neutral': 0.0}],
             ['모름'])
    out = calculate_consolidated_analysis([ev])
    assert out['overall_sentiment'] == 'neutral', out['overall_sentiment']
    assert '모름' in out['consolidated_emotion_words']['neutral']
    print('[OK] no_response_neutral → 메타데이터 neutral(부정 아님)')


def test_real_negative_preserved():
    # 진짜 부정: 부정어 + is_last → 부정 유지(긍↔부 안전)
    ev = _ev('업무 분장이 불공평하고 책임을 회피함',
             [{'sentence': '업무 분장이 불공평하고 책임을 회피함',
               'pos': 0.05, 'neg': 0.9, 'neutral': 0.05}],
             ['책임', '회피'])
    out = calculate_consolidated_analysis([ev])
    assert out['overall_sentiment'] == 'negative', out['overall_sentiment']
    print('[OK] 진짜 부정 → 메타데이터 negative 유지')


def test_mixed_person_mass_decision():
    # 한 사람 = 긍정 강한 1 + 무응답 1 → 질량상 positive
    out = calculate_consolidated_analysis([
        _ev('홍보 능력 탁월',
            [{'sentence': '홍보 능력 탁월', 'pos': 0.5, 'neg': 0.05, 'neutral': 0.45}], ['홍보']),
        _ev('잘 모르겠습니다',
            [{'sentence': '잘 모르겠습니다', 'pos': 0.1, 'neg': 0.9, 'neutral': 0.0}], ['모름']),
    ])
    assert out['overall_sentiment'] == 'positive', out['overall_sentiment']
    print('[OK] 혼합 평가 → override 질량 기반 통합 감정 결정')


if __name__ == '__main__':
    test_positive_rescue_reflected()
    test_no_response_neutralized()
    test_real_negative_preserved()
    test_mixed_person_mass_decision()
    print('\n전체 통과')
