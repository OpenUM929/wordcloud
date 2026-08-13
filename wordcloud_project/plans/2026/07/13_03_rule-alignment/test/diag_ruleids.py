# -*- coding: utf-8 -*-
"""5개 위반문 + 11-case 전체에 대해, 현 override cascade가 어떤 rule_id를 내는지 진단.

목적: lexical 고정밀 규칙이 각 위반을 실제로 잡는지 확인(override 레이어 화이트리스트 설계 근거).
KoTE 원점수는 compute_sentence_raw_scores 로 실제 값 사용(서비스와 동일).
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WP = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '..'))
sys.path.insert(0, WP)
DS = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '_datasets', 'kote_finetune'))
REVIEW = os.path.join(DS, 'eval', 'review', 'gold_crossing_review_260713.jsonl')

FIELD_POL = {'장점': 'positive', '단점': 'negative'}


def rule_gold(rec):
    hd = rec.get('human_decision')
    if hd in ('positive', 'negative', 'neutral'):
        return hd
    if hd == 'not_group':
        return FIELD_POL.get(rec.get('field'), 'neutral')
    return None


def main():
    recs = [json.loads(l) for l in io.open(REVIEW, encoding='utf-8') if l.strip()]
    from src.modules.sentence_emotion import compute_sentence_raw_scores
    from src.services.perspective_service import _sentence_sentiment_override_explain
    from src.modules.hr_sentiment import predict_sentiments

    texts = [r['text'] for r in recs]
    fields = [r.get('field') for r in recs]
    model_labels = predict_sentiments(texts, fields=fields)

    out = []
    for r, ml in zip(recs, model_labels):
        text = r['text']
        cache = compute_sentence_raw_scores(text)
        # 문서 첫(보통 유일) 문장 기준
        if cache:
            e = cache[0]
            pos, neg, neu = e['pos'], e['neg'], e['neutral']
        else:
            pos = neg = neu = 0.0
        score, rid = _sentence_sentiment_override_explain(pos, neg, text, True, 1)
        ov_label = 'positive' if score > 0.01 else ('negative' if score < -0.01 else 'neutral')
        out.append({
            'rec_id': r['rec_id'], 'field': r.get('field'), 'gold': rule_gold(r),
            'model': ml, 'override_rule': rid, 'override_label': ov_label,
            'kote': [round(pos, 3), round(neg, 3), round(neu, 3)], 'text': text,
        })

    dst = os.path.join(HERE, 'diag_ruleids_result.json')
    json.dump(out, io.open(dst, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    for x in out:
        print(f'[{x["field"]}] gold={x["gold"]:8s} model={x["model"]:8s} ovr={x["override_label"]:8s}'
              f' rule={x["override_rule"]:26s} kote={x["kote"]}')
    print('saved', os.path.relpath(dst, HERE))


if __name__ == '__main__':
    main()
