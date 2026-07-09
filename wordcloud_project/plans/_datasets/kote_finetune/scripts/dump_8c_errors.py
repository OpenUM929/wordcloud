# -*- coding: utf-8 -*-
"""8c_hard held-out에서 파인튜닝 모델(model_out_8c)이 틀린 행을 추출 — 능동학습 큐.

CPU 추론만(학습 아님). 오류를 3범주로 분류:
  - flip_pn : 긍↔부 (핵심가치 위반, 최우선)
  - pol2neu : 극성→중립 (모델이 너무 보수적)
  - neu2pol : 중립→극성 (모델이 너무 공격적)
산출: result/error_8c_260706.jsonl (rec_id/text/field/gold/pred/err_type) + 콘솔 요약.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, PROJECT_ROOT)

LAB2ID = {'positive': 0, 'negative': 1, 'neutral': 2}
ID2LAB = {v: k for k, v in LAB2ID.items()}


def err_type(gold, pred):
    g, p = LAB2ID[gold], LAB2ID[pred]
    if {g, p} == {0, 1}:
        return 'flip_pn'          # 긍↔부
    if g in (0, 1) and p == 2:
        return 'pol2neu'          # 극성→중립
    if g == 2 and p in (0, 1):
        return 'neu2pol'          # 중립→극성
    return 'other'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default=os.path.join(DATASET_DIR, 'model_out_8c'))
    ap.add_argument('--test', default='gold_8c_test_260706.jsonl')
    args = ap.parse_args()

    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    rows = []
    for line in open(os.path.join(DATASET_DIR, 'eval', args.test), encoding='utf-8'):
        r = json.loads(line)
        hd = r.get('human_decision')
        if hd in LAB2ID and (r.get('text') or '').strip():
            rows.append(r)
    texts = [r['text'].strip() for r in rows]

    tok = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(args.model, local_files_only=True)
    model.eval()
    preds = []
    with torch.no_grad():
        for i in range(0, len(texts), 64):
            enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                      return_tensors='pt')
            preds += model(**enc).logits.argmax(-1).tolist()

    errs = []
    cnt = {'flip_pn': 0, 'pol2neu': 0, 'neu2pol': 0, 'other': 0}
    for r, pid in zip(rows, preds):
        gold = r['human_decision']
        pred = ID2LAB[pid]
        if gold == pred:
            continue
        et = err_type(gold, pred)
        cnt[et] += 1
        errs.append({'rec_id': r.get('rec_id'), 'text': r['text'].strip(),
                     'field': r.get('field'), 'gold': gold, 'pred': pred,
                     'err_type': et, 'group': r.get('group'),
                     'source_file': r.get('source_file')})

    out = os.path.join(DATASET_DIR, 'result', 'error_8c_260706.jsonl')
    order = {'flip_pn': 0, 'neu2pol': 1, 'pol2neu': 2, 'other': 3}
    errs.sort(key=lambda e: order[e['err_type']])
    with open(out, 'w', encoding='utf-8') as f:
        for e in errs:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')

    print(f'8c_hard n={len(rows)} · 오답 {len(errs)} ({100*len(errs)/len(rows):.1f}%)')
    print(f'  긍↔부 flip {cnt["flip_pn"]} (핵심가치) · 중립→극성 {cnt["neu2pol"]} · 극성→중립 {cnt["pol2neu"]} · 기타 {cnt["other"]}')
    print(f'→ {os.path.relpath(out, PROJECT_ROOT)}\n')
    print('--- 오답 목록 (범주순) ---')
    for e in errs:
        print(f'[{e["err_type"]}] gold={e["gold"]:<8} pred={e["pred"]:<8} | {e["text"][:70]}')


if __name__ == '__main__':
    main()
