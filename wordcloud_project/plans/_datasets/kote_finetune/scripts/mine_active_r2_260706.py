# -*- coding: utf-8 -*-
"""능동학습 2라운드 큐 — 미확정 8c 2,652건에 model_out_8c 추론 → 정보량 높은 표본 선별.

버킷 A(긍↔부 방어): 필드-극성 불일치(단점인데 pos / 장점인데 neg) = flip 위험군(우선).
버킷 B(불확실성): 최대 softmax(margin) 낮은 순 = 라벨 1개가 가장 크게 배우는 지점.
누수 가드: gold_8c_train/test·baseline 텍스트(정규화 동일) 제외.
산출: eval/review/active_r2_260706.jsonl (게시판 스키마, human_decision=null, ai_reference=모델힌트).
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
EVAL = os.path.join(DATASET_DIR, 'eval')
REVIEW = os.path.join(EVAL, 'review')
ID2LAB = {0: 'positive', 1: 'negative', 2: 'neutral'}
_WS = re.compile(r'\s+')


def norm(t):
    return _WS.sub(' ', (t or '').strip()).lower().strip(' .。!?！？·…-')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default=os.path.join(DATASET_DIR, 'model_out_8c'))
    ap.add_argument('--cap-a', type=int, default=150)   # 긍↔부 방어
    ap.add_argument('--cap-b', type=int, default=200)   # 불확실성
    args = ap.parse_args()

    # 1) 누수 제외 집합(정규화)
    exclude = set()
    for fn in ('gold_8c_train_260706.jsonl', 'gold_8c_test_260706.jsonl', 'baseline_eval_260624.jsonl'):
        p = os.path.join(EVAL, fn)
        if os.path.exists(p):
            for l in open(p, encoding='utf-8'):
                if l.strip():
                    exclude.add(norm(json.loads(l).get('text')))

    # 2) 미확정 8c 수집(human gold·not_group 제외), 정규화 중복제거
    rows = []
    seen = set()
    for f in sorted(glob.glob(os.path.join(REVIEW, '8c_auto__*.jsonl'))
                    + glob.glob(os.path.join(REVIEW, '8c_other_neu__*.jsonl'))):
        for l in open(f, encoding='utf-8'):
            if not l.strip():
                continue
            r = json.loads(l)
            if r.get('decision_source') == 'human':      # 이미 gold
                continue
            t = (r.get('text') or '').strip()
            n = norm(t)
            if not t or n in exclude or n in seen:
                continue
            seen.add(n)
            rows.append({'rec_id': r.get('rec_id'), 'text': t, 'field': r.get('field'),
                         'cur_rule_label': r.get('cur_rule_label'), 'group': r.get('group'),
                         'source_file': os.path.basename(f)})
    print(f'미확정·중복제거·누수제외 후보 {len(rows)}')

    # 3) model_out_8c 추론(softmax)
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    tok = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(args.model, local_files_only=True)
    model.eval()
    texts = [r['text'] for r in rows]
    with torch.no_grad():
        for i in range(0, len(texts), 64):
            enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                      return_tensors='pt')
            probs = torch.softmax(model(**enc).logits, -1)
            conf, pred = probs.max(-1)
            for j in range(len(conf)):
                r = rows[i + j]
                r['pred'] = ID2LAB[int(pred[j])]
                r['conf'] = round(float(conf[j]), 4)

    # 4) 버킷 선별
    def is_flip_risk(r):
        f = r.get('field') or ''
        return (('단점' in f and r['pred'] == 'positive')
                or ('장점' in f and r['pred'] == 'negative'))

    bucket_a = sorted([r for r in rows if is_flip_risk(r)],
                      key=lambda r: -r['conf'])[:args.cap_a]      # 확신 높은 flip부터(위험 큼)
    a_ids = {r['rec_id'] for r in bucket_a}
    bucket_b = sorted([r for r in rows if r['rec_id'] not in a_ids],
                      key=lambda r: r['conf'])[:args.cap_b]       # 저마진(불확실)
    for r in bucket_a:
        r['bucket'] = 'A_flip_risk'
    for r in bucket_b:
        r['bucket'] = 'B_uncertain'
    queue = bucket_a + bucket_b
    print(f'버킷 A(긍↔부 방어) {len(bucket_a)} · 버킷 B(불확실성) {len(bucket_b)} · 합 {len(queue)}')

    # 5) 게시판 스키마 출력
    out = os.path.join(REVIEW, 'active_r2_260706.jsonl')
    with open(out, 'w', encoding='utf-8') as w:
        for r in queue:
            w.write(json.dumps({
                'rec_id': r['rec_id'], 'text': r['text'], 'field': r.get('field'),
                'cur_rule_label': r.get('cur_rule_label'), 'group': r.get('group'),
                'human_decision': None, 'suggested_source': None, 'decision_source': None,
                'ai_reference': {'polarity': r['pred'], 'confidence': r['conf'],
                                 'reason': f"[{r['bucket']}] 모델={r['pred']} conf={r['conf']}"},
                'source_file': r.get('source_file'), 'note': 'active_r2',
            }, ensure_ascii=False) + '\n')
    print(f'→ {os.path.relpath(out, DATASET_DIR)}')


if __name__ == '__main__':
    main()
