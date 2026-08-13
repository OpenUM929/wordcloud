# -*- coding: utf-8 -*-
"""13_03 Track2 게이트 검증 — override 전/후를 4슬라이스 + 11case 로 대조.

성공기준(§1·§4-4):
  - 11-case: 위반(모델≠규칙) 5 → 0 목표(부→긍 3건은 Track1 몫으로 잔존 허용, 명시).
  - 4슬라이스: **긍↔부 신규 0**(override 후 긍↔부 ≤ override 전), 정확도 회귀 없음.
자기검산: 각 슬라이스 pre/post 정확도·긍↔부·override 발동수·전이표.
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WP = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '..'))
sys.path.insert(0, WP)
DS = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '_datasets', 'kote_finetune'))
sys.path.insert(0, HERE)

# 프로덕션 함수 직접 검증(프로토타입 override_layer 대신 이식된 실제 코드로 게이트).
from src.services.perspective_service import apply_model_label_override


def apply_override(model_label, sentence, field):
    final = apply_model_label_override(model_label, sentence, field)
    return final, ('R1_request_falsepos_to_neutral' if final != model_label else None)

SLICES = {
    'baseline399': 'baseline_eval_260624.jsonl',
    '8c_hard': 'gold_8c_test_260706.jsonl',
    'c3_neu149': 'gold_8c_test_c3neu_260707.jsonl',
    'sa_speech74': 'gold_speechact_test_260707.jsonl',
}
REVIEW = os.path.join(DS, 'eval', 'review', 'gold_crossing_review_260713.jsonl')
FIELD_POL = {'장점': 'positive', '단점': 'negative'}


def load(path):
    return [json.loads(l) for l in io.open(path, encoding='utf-8') if l.strip()]


def is_pn(a, b):
    return {a, b} == {'positive', 'negative'}


def run_slice(name, recs, predict_sentiments):
    texts = [r['text'] for r in recs]
    fields = [r.get('field') for r in recs]
    golds = [r.get('human_decision') for r in recs]
    model = predict_sentiments(texts, fields=fields)
    pre_acc = pre_pn = post_acc = post_pn = fired = 0
    flips = {}
    for t, f, g, ml in zip(texts, fields, golds, model):
        final, rid = apply_override(ml, t, f)
        if g in ('positive', 'negative', 'neutral'):
            if ml == g:
                pre_acc += 1
            if is_pn(ml, g):
                pre_pn += 1
            if final == g:
                post_acc += 1
            if is_pn(final, g):
                post_pn += 1
        if rid:
            fired += 1
            flips[f'{ml}->{final}({rid})'] = flips.get(f'{ml}->{final}({rid})', 0) + 1
    n = sum(1 for g in golds if g in ('positive', 'negative', 'neutral'))
    return {'name': name, 'n': n, 'pre_acc': pre_acc, 'post_acc': post_acc,
            'pre_pn': pre_pn, 'post_pn': post_pn, 'fired': fired, 'flips': flips}


def run_11case(predict_sentiments):
    recs = load(REVIEW)

    def rgold(r):
        hd = r.get('human_decision')
        if hd in ('positive', 'negative', 'neutral'):
            return hd
        if hd == 'not_group':
            return FIELD_POL.get(r.get('field'), 'neutral')
        return None
    texts = [r['text'] for r in recs]
    fields = [r.get('field') for r in recs]
    model = predict_sentiments(texts, fields=fields)
    pre_v = post_v = pre_pn = post_pn = 0
    rows = []
    for r, ml in zip(recs, model):
        g = rgold(r)
        final, rid = apply_override(ml, r['text'], r.get('field'))
        pv = (g is not None and ml != g)
        qv = (g is not None and final != g)
        pre_v += pv
        post_v += qv
        pre_pn += (pv and is_pn(ml, g))
        post_pn += (qv and is_pn(final, g))
        rows.append({'gold': g, 'model': ml, 'final': final, 'rule': rid,
                     'fixed': pv and not qv, 'text': r['text'][:30]})
    return {'pre_v': pre_v, 'post_v': post_v, 'pre_pn': pre_pn, 'post_pn': post_pn, 'rows': rows}


def main():
    from src.modules.hr_sentiment import predict_sentiments
    print('=== 4슬라이스 (pre=모델단독 / post=+override) ===')
    slice_res = []
    all_safe = True
    for name, fn in SLICES.items():
        recs = load(os.path.join(DS, 'eval', fn))
        r = run_slice(name, recs, predict_sentiments)
        slice_res.append(r)
        pn_new = r['post_pn'] - r['pre_pn']
        acc_d = r['post_acc'] - r['pre_acc']
        safe = pn_new <= 0
        all_safe = all_safe and safe
        print(f"  {name:12s} n={r['n']:3d} | acc {r['pre_acc']}->{r['post_acc']} ({acc_d:+d}) | "
              f"긍↔부 {r['pre_pn']}->{r['post_pn']} ({pn_new:+d}) {'OK' if safe else 'FAIL!!'} | fired={r['fired']}")
        for k, v in sorted(r['flips'].items()):
            print(f"       {k}: {v}")

    print('\n=== 11-case ===')
    c = run_11case(predict_sentiments)
    for x in c['rows']:
        tag = 'FIX' if x['fixed'] else ('ok' if x['gold'] == x['final'] else 'viol')
        print(f"  [{tag:4s}] gold={x['gold']:8s} model={x['model']:8s} final={x['final']:8s} "
              f"rule={str(x['rule']):32s} {x['text']}")
    print(f"  위반 {c['pre_v']}->{c['post_v']} | 긍↔부 {c['pre_pn']}->{c['post_pn']}")

    print('\n── 게이트 판정 ──')
    print(f"  슬라이스 긍↔부 신규 0: {'PASS' if all_safe else 'FAIL'}")
    print(f"  11-case 위반 감소: {c['pre_v']}->{c['post_v']} (부→긍 3건은 Track1 몫)")
    out = {'slices': slice_res, 'case11': {k: v for k, v in c.items() if k != 'rows'},
           'case11_rows': c['rows'], 'all_slices_pn_safe': all_safe}
    json.dump(out, io.open(os.path.join(HERE, 'verify_override_result.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print('  saved verify_override_result.json')


if __name__ == '__main__':
    main()
