# -*- coding: utf-8 -*-
"""모델링 레버 B — **비대칭 비용민감 손실**(MODELING_LEVERS_PLAN §B).

목표: 긍↔부를 flutter 없이 **하드 0**으로 굳히고, 그 대가로 중립경계 자유도 확보.
핵심가치(긍↔부 오분류 방지)를 손실함수로 **직접** 강화하는 유일 레버.

가설: 평범 CE는 모든 오분류 등가 → 긍↔부가 우연히 0에 가깝지만 seed마다 flutter(8c 0↔1).
오분류 거리비용을 손실에 넣으면(반대극성 확률질량 페널티) 긍↔부가 구조적으로 억제.

손실: L = CE(logits, y) + α · penalty
  penalty = 극성 라벨 예제에서 **반대 극성 확률질량** 평균
           (y=neg면 p_pos, y=pos면 p_neg). 중립 방향 무처벌 = 중립→긍 허용 원칙 정렬.
스윕: α ∈ {0.0(대조=평범CE), 0.5, 1.0, 2.0}, seed {42,43,44}. 다중런 평균으로 판정.

성공기준(§B): 긍↔부=0(전 슬라이스·전 seed) — flutter보다 엄격 개선(주지표).
  c3_neu149·baseline acc 비열화(중립 자유도가 손해로 안 나타남). α 과대 시 중립 과교정 감시.
model_out 미덮어씀. 실행: python asym_loss_r9_260708.py [--alphas 0.0,0.5,1.0,2.0] [--seeds 42,43,44]
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from finetune_sentiment import (TRAIN_FILES, TEST_SETS, load, metrics,  # noqa: E402
                                LAB2ID, ID2LAB, DATASET_DIR, MODEL_PATH)

POS, NEG, NEU = 0, 1, 2   # LAB2ID 규약


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--alphas', default='0.0,0.5,1.0,2.0')
    ap.add_argument('--seeds', default='42,43,44')
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--bs', type=int, default=16)
    ap.add_argument('--lr', type=float, default=2e-5)
    ap.add_argument('--field-token', choices=['on', 'off'], default='on')
    args = ap.parse_args()
    alphas = [float(a) for a in args.alphas.split(',') if a.strip()]
    seeds = [int(s) for s in args.seeds.split(',') if s.strip()]

    import torch
    import torch.nn.functional as F
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
    from collections import Counter
    print(f'train {len(train)} · field-token={args.field_token} · alphas={alphas} · seeds={seeds}')
    print('  train 분포:', {ID2LAB[k]: v for k, v in Counter(l for _, l, _ in train).items()})

    tok = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)

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
        texts = [t for t, _, _ in ts]; y = [yy for _, yy, _ in ts]; fields = [fld for _, _, fld in ts]
        packs[name] = {'y': y, 'mt': [apply_field(t, f) for t, f in zip(texts, fields)]}

    class AsymTrainer(Trainer):
        """L = CE + α·(반대극성 확률질량). 중립 예제는 무페널티(중립→긍 허용 정렬)."""
        def __init__(self, *a, alpha=0.0, **kw):
            super().__init__(*a, **kw)
            self.alpha = alpha
        def compute_loss(self, model, inputs, return_outputs=False, **kw):
            labels = inputs.pop('labels')
            out = model(**inputs)
            logits = out.logits
            ce = F.cross_entropy(logits, labels)
            pen = logits.new_zeros(())
            if self.alpha > 0:
                p = F.softmax(logits, dim=-1)
                is_pos = labels == POS
                is_neg = labels == NEG
                # y=pos → 반대극성질량 p_neg ; y=neg → p_pos (중립방향 무처벌)
                pm = p[:, NEG] * is_pos.float() + p[:, POS] * is_neg.float()
                denom = (is_pos | is_neg).float().sum().clamp(min=1.0)
                pen = pm.sum() / denom
            loss = ce + self.alpha * pen
            return (loss, out) if return_outputs else loss

    def predict(model, texts):
        model.eval(); dev = model.device; out = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                          return_tensors='pt').to(dev)
                out += model(**enc).logits.argmax(-1).cpu().tolist()
        return out

    summary = {'field_token': args.field_token, 'n_train': len(train), 'runs': []}
    # 조건별 집계: (alpha) → 슬라이스별 seed 지표 리스트
    agg = {a: {name: [] for name in tests} for a in alphas}

    for alpha in alphas:
        for seed in seeds:
            set_seed(seed)
            model = AutoModelForSequenceClassification.from_pretrained(
                MODEL_PATH, num_labels=3, ignore_mismatched_sizes=True, local_files_only=True,
                problem_type='single_label_classification')
            targs = TrainingArguments(
                output_dir=os.path.join(DATASET_DIR, 'model_asym_tmp'), num_train_epochs=args.epochs,
                per_device_train_batch_size=args.bs, learning_rate=args.lr,
                fp16=torch.cuda.is_available(), logging_steps=60, save_strategy='no',
                report_to=[], seed=seed, remove_unused_columns=False)
            trainer = AsymTrainer(model=model, args=targs, train_dataset=DS(train), alpha=alpha)
            print(f'\n=== α={alpha} seed={seed} 학습 ===')
            trainer.train()
            print(f'--- α={alpha} seed={seed} 평가 ---')
            for name, pk in packs.items():
                r = metrics(f'{name} a{alpha}s{seed}', pk['y'], predict(model, pk['mt']))
                agg[alpha][name].append(r)
                summary['runs'].append({'alpha': alpha, 'seed': seed, 'slice': name,
                                        'acc': r['acc'], 'pos_neg_err': r['pos_neg_err'],
                                        'gp_to_neg': r['gp_to_neg'], 'neg_to_pos': r['neg_to_pos'],
                                        'neg_recall': r['recall']['neg'], 'neu_recall': r['recall']['neu']})
            del model, trainer
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    # ── α별 집계 요약(다중런 평균) ──
    print('\n' + '=' * 60)
    print('=== α별 다중런 집계 (핵심지표 긍↔부·acc) ===')
    summary['agg'] = {}
    for alpha in alphas:
        summary['agg'][str(alpha)] = {}
        print(f'\n[α={alpha}]')
        for name in tests:
            rs = agg[alpha][name]
            accs = [r['acc'] for r in rs]
            pne = [r['pos_neg_err'] for r in rs]
            negs = [r['recall']['neg'] for r in rs if r['recall']['neg'] is not None]
            pne_max = max(pne)
            hard0 = all(e == 0 for e in pne)
            print(f'  {name:12s} acc {np.mean(accs):.4f}±{np.std(accs):.4f} · '
                  f'긍↔부 {pne} (max {pne_max}{" ✔하드0" if hard0 else ""}) · '
                  f'부recall {np.mean(negs):.3f}' if negs else
                  f'  {name:12s} acc {np.mean(accs):.4f}±{np.std(accs):.4f} · 긍↔부 {pne}')
            summary['agg'][str(alpha)][name] = {
                'acc_mean': round(float(np.mean(accs)), 4), 'acc_std': round(float(np.std(accs)), 4),
                'pos_neg_errs': pne, 'pos_neg_hard0': bool(hard0),
                'neg_recall_mean': round(float(np.mean(negs)), 3) if negs else None}

    out = os.path.join(DATASET_DIR, 'result', 'asym_loss_260708.json')
    json.dump(summary, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n리포트 → {os.path.relpath(out, DATASET_DIR)}')


if __name__ == '__main__':
    main()
