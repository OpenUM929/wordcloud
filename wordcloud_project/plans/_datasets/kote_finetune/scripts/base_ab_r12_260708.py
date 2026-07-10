# -*- coding: utf-8 -*-
"""모델링 레버 F — **베이스 인코더 A/B**(MODELING_LEVERS_PLAN §F).

가설: KoTE(44감정 멀티라벨 프리트레인)가 3분류 경계에 편향일 수 있다. 범용 한국어
(KLUE-RoBERTa-base)가 더 붙을 여지. → 동일 TRAIN·field-token으로 base만 교체 A/B.

KoTE 팔은 이미 측정됨(ensemble_eval_260708.json 단일런 분포). 이 스크립트는 **KLUE 팔**만
seed{42,43,44} 학습·평가하고 KoTE 단일런 평균과 대조한다(동일 seed·동일 4슬라이스).
공개모델 다운로드는 데이터 반출 아님(모델을 받는 것) — PII 게이트 무관. model_out 미덮어씀.
성공기준(§F): 4슬라이스 acc·부recall이 KoTE 대비 우위 + 긍↔부 0. 유의미하면 base 교체 검토.
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from finetune_sentiment import (TRAIN_FILES, TEST_SETS, load, metrics,  # noqa: E402
                                LAB2ID, ID2LAB, DATASET_DIR)

BASE = 'klue/roberta-base'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', default='42,43,44')
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--bs', type=int, default=16)
    ap.add_argument('--lr', type=float, default=2e-5)
    ap.add_argument('--field-token', choices=['on', 'off'], default='on')
    ap.add_argument('--base', default=BASE)
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(',') if s.strip()]

    import torch
    from torch.utils.data import Dataset
    from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                              Trainer, TrainingArguments, set_seed)

    def apply_field(text, field):
        return f'{field} 평가: {text}' if (args.field_token == 'on' and field) else text

    train = []
    for f in TRAIN_FILES:
        train += load(f)
    tests = {name: load(fn) for name, fn in TEST_SETS.items()}
    all_test = {t for ts in tests.values() for t, _, _ in ts}
    train = [(t, y, fld) for t, y, fld in train if t not in all_test]
    print(f'train {len(train)} · base={args.base} · seeds={seeds}')

    tok = AutoTokenizer.from_pretrained(args.base)   # 다운로드 허용(공개모델)

    class DS(Dataset):
        def __init__(self, rows):
            self.rows = rows
        def __len__(self):
            return len(self.rows)
        def __getitem__(self, i):
            t, y, fld = self.rows[i]
            enc = tok(apply_field(t, fld), truncation=True, padding='max_length',
                      max_length=64, return_tensors='pt')
            return {'input_ids': enc['input_ids'][0], 'attention_mask': enc['attention_mask'][0],
                    'labels': torch.tensor(y)}

    packs = {}
    for name, ts in tests.items():
        packs[name] = {'y': [yy for _, yy, _ in ts],
                       'mt': [apply_field(t, f) for t, _, f in ts]}

    def predict(model, texts):
        model.eval(); dev = model.device; out = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                          return_tensors='pt').to(dev)
                out += model(**enc).logits.argmax(-1).cpu().tolist()
        return out

    agg = {name: [] for name in tests}
    summary = {'base': args.base, 'field_token': args.field_token, 'n_train': len(train), 'runs': []}
    for seed in seeds:
        set_seed(seed)
        model = AutoModelForSequenceClassification.from_pretrained(
            args.base, num_labels=3, problem_type='single_label_classification')
        targs = TrainingArguments(
            output_dir=os.path.join(DATASET_DIR, 'model_base_tmp'), num_train_epochs=args.epochs,
            per_device_train_batch_size=args.bs, learning_rate=args.lr,
            fp16=torch.cuda.is_available(), logging_steps=60, save_strategy='no',
            report_to=[], seed=seed)
        trainer = Trainer(model=model, args=targs, train_dataset=DS(train))
        print(f'\n=== {args.base} seed={seed} 학습 ===')
        trainer.train()
        print(f'--- {args.base} seed={seed} 평가 ---')
        for name, pk in packs.items():
            r = metrics(f'{name} s{seed}', pk['y'], predict(model, pk['mt']))
            agg[name].append(r)
            summary['runs'].append({'seed': seed, 'slice': name, 'acc': r['acc'],
                                    'pos_neg_err': r['pos_neg_err'], 'neg_recall': r['recall']['neg'],
                                    'neu_recall': r['recall']['neu']})
        del model, trainer
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # KoTE 단일런 평균 로드(대조)
    kote = {}
    try:
        ke = json.load(open(os.path.join(DATASET_DIR, 'result', 'ensemble_eval_260708.json'), encoding='utf-8'))
        for name, s in ke['slices'].items():
            kote[name] = s['single_acc_mean']
    except Exception:
        pass

    print('\n' + '=' * 60)
    print(f'=== {args.base} vs KoTE(단일런 평균) ===')
    summary['agg'] = {}
    for name in tests:
        rs = agg[name]
        accs = [r['acc'] for r in rs]; pne = [r['pos_neg_err'] for r in rs]
        negs = [r['recall']['neg'] for r in rs if r['recall']['neg'] is not None]
        km = kote.get(name)
        d = (np.mean(accs) - km) if km is not None else None
        print(f'  {name:12s} KLUE acc {np.mean(accs):.4f}±{np.std(accs):.4f} · 긍↔부 {pne} · '
              f'부recall {np.mean(negs):.3f} · KoTE {km} · Δ {d:+.4f}' if d is not None else
              f'  {name:12s} KLUE acc {np.mean(accs):.4f} · 긍↔부 {pne}')
        summary['agg'][name] = {'klue_acc_mean': round(float(np.mean(accs)), 4),
                                'pos_neg_errs': pne, 'neg_recall_mean': round(float(np.mean(negs)), 3) if negs else None,
                                'kote_acc_mean': km, 'delta_vs_kote': round(float(d), 4) if d is not None else None}

    out = os.path.join(DATASET_DIR, 'result', 'base_ab_260708.json')
    json.dump(summary, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n리포트 → {os.path.relpath(out, DATASET_DIR)}')


if __name__ == '__main__':
    main()
