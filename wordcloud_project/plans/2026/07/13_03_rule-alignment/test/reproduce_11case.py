# -*- coding: utf-8 -*-
"""13_03 Track2 baseline 재현 — 현 배포 모델이 11-case에서 규칙을 몇 건 어기는지 확정.

규칙상 정답(rule_gold):
  - human_decision ∈ {positive,negative,neutral} → 그대로.
  - human_decision == not_group → 무서술어 필드의존 단편 → 필드 극성(장점→positive/단점→negative).
현 모델(필드 프리픽스 적용) argmax 라벨과 대조 → 위반(모델≠규칙, 특히 긍↔부) 카운트.
override 설계 전/후 동일 하네스로 5→0 확인용. self-check: 케이스 수·긍↔부 위반 별도 집계.
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 저장소 루트 → wordcloud_project 를 sys.path 에 (from src... 임포트)
WP = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '..'))  # wordcloud_project
sys.path.insert(0, WP)
DS = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '_datasets', 'kote_finetune'))
REVIEW = os.path.join(DS, 'eval', 'review', 'gold_crossing_review_260713.jsonl')

FIELD_POL = {'장점': 'positive', '단점': 'negative'}


def rule_gold(rec):
    hd = rec.get('human_decision')
    if hd in ('positive', 'negative', 'neutral'):
        return hd
    if hd == 'not_group':  # 무서술어 필드의존 단편 → 필드 극성
        return FIELD_POL.get(rec.get('field'), 'neutral')
    return None


def load(path):
    return [json.loads(l) for l in io.open(path, encoding='utf-8') if l.strip()]


def main():
    recs = load(REVIEW)
    texts = [r['text'] for r in recs]
    fields = [r.get('field') for r in recs]

    from src.modules.hr_sentiment import predict_sentiments
    labels = predict_sentiments(texts, fields=fields)
    if labels is None:
        raise SystemExit('모델 추론 실패(None) — 모델 로드 확인')

    rows = []
    for r, lab in zip(recs, labels):
        g = rule_gold(r)
        viol = (g is not None and lab != g)
        pn = viol and {g, lab} == {'positive', 'negative'}  # 긍↔부 위반
        rows.append({'rec_id': r['rec_id'], 'field': r.get('field'), 'text': r['text'][:34],
                     'rule_gold': g, 'model': lab, 'viol': viol, 'pn': pn})

    n = len(rows)
    n_viol = sum(1 for x in rows if x['viol'])
    n_pn = sum(1 for x in rows if x['pn'])
    print(f'{"rec_id":32s} {"field":4s} {"gold":8s} {"model":8s} {"":4s} text')
    for x in rows:
        flag = ('PN!' if x['pn'] else ('VIO' if x['viol'] else '  .'))
        print(f'{x["rec_id"]:32s} {str(x["field"]):4s} {str(x["rule_gold"]):8s} {x["model"]:8s} {flag:4s} {x["text"]}')
    print('── self-check ──')
    print(f'  케이스 {n} · 위반(모델≠규칙) {n_viol} · 그중 긍↔부 {n_pn}')
    # 결과 JSON (override 적용본과 비교용)
    out = os.path.join(HERE, 'baseline_11case_result.json')
    with io.open(out, 'w', encoding='utf-8') as f:
        json.dump({'n': n, 'n_viol': n_viol, 'n_pn': n_pn, 'rows': rows}, f, ensure_ascii=False, indent=2)
    print(f'  저장: {os.path.relpath(out, HERE)}')


if __name__ == '__main__':
    main()
