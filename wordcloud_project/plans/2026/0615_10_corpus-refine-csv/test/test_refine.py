"""정제 패스 / override 동작 보존 테스트 (배치·원데이터 불요)."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))

from src.services.perspective_service import (
    sentence_sentiment_override, _sentence_sentiment_override_explain,
    refine_acquired_row, export_acquired_sentences_refined_csv,
)


def test_override_behavior_preserved():
    """기존 float 반환 == explain[0] 동일성 (동작 보존)."""
    cases = [
        # (pos, neg, sentence, is_last, total, neutral)
        (0.8, 0.1, "업무 능력이 뛰어납니다.", False, 3, 0.1),
        (0.7, 0.2, "성실하지만 보고가 미흡합니다.", True, 2, 0.1),
        (0.1, 0.05, "보통 수준입니다.", False, 1, 0.85),
        (0.6, 0.1, "개선의 여지가 있습니다.", True, 1, 0.3),
        (0.2, 0.2, "그러나 결과가 아쉽습니다.", True, 4, 0.6),
        (0.9, 0.92, "보통 무난합니다.", True, 1, 0.0),
    ]
    for pos, neg, sent, is_last, total, neu in cases:
        legacy = sentence_sentiment_override(pos, neg, sent, is_last, total, neutral=neu)
        score, rule = _sentence_sentiment_override_explain(pos, neg, sent, is_last, total, neutral=neu)
        assert legacy == score, f"불일치: {sent} legacy={legacy} explain={score}"
        assert rule, "rule_id 비어있음"
    print("[OK] override 동작 보존 + 규칙 id 부여")


def test_refine_row_fields():
    """refine_acquired_row 출력 필드/플래그 정합."""
    row = {
        'id': 1,
        'sentence_text': '성실하지만 보고가 미흡합니다.',
        'context': '업무 태도는 좋습니다. 성실하지만 보고가 미흡합니다.',
        'user_label': 'negative',
        'sentence_index': 1,
        'model_label': 'positive',
        'confidence': 0.3,
    }
    r = refine_acquired_row(row)
    for k in ['kote_pos', 'kote_neg', 'kote_neutral', 'raw_model_label', 'applied_rule',
              'corrected_label', 'is_last', 'total_sentences', 'kote_vs_truth',
              'pipeline_vs_truth', 'rule_helped', 'rule_hurt']:
        assert k in r, f"필드 누락: {k}"
    assert r['total_sentences'] == 2, r['total_sentences']
    assert r['is_last'] is True, r['is_last']
    assert r['corrected_label'] in ('positive', 'negative', 'neutral')
    # rule_helped/hurt는 상호배타
    assert not (r['rule_helped'] and r['rule_hurt'])
    print(f"[OK] refine 필드 정합: {r}")


def test_export_empty_or_current():
    """현재 코퍼스(빈/현존)에서도 헤더 포함 CSV 생성."""
    csv_text = export_acquired_sentences_refined_csv(mismatch_only=False)
    lines = csv_text.strip().split('\n')
    header = lines[0].lstrip('﻿')
    assert header.startswith('id,sentence_text,user_label,kote_pos'), header
    print(f"[OK] 정제 CSV 생성: {len(lines)}행 (헤더 포함)")


if __name__ == '__main__':
    test_override_behavior_preserved()
    test_refine_row_fields()
    test_export_empty_or_current()
    print("\n전체 통과")
