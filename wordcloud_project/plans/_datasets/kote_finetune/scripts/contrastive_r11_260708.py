# -*- coding: utf-8 -*-
"""모델링 레버 E — **대조학습**(supervised contrastive, MODELING_LEVERS_PLAN §E).

동기(A/B/C 실측 후 갱신): B(비대칭손실)·C(임계값)가 긍↔부를 하드0으로 못 만든 원인은
**남은 긍↔부가 고확신 오류(중립대비 마진 큼)** — 결정층이 아니라 **표현**을 바꿔야 한다.
E는 표현공간을 직접 성형: 같은 극성 당기고 반대 극성 밀기(공유토큰 하드페어 특히).

설계: 공유 인코더(KoTE) + 극성헤드 + 투영헤드(128d). L = CE(극성) + β·SupCon(투영CLS, 극성라벨).
SupCon(Khosla): 앵커별 positives=배치내 동일극성, temperature 0.1. β=0=대조군(이 아키텍처 순수 CE).
스윕: β∈{0.0,0.2}, seed{42,43,44}=6런. c7 멀티태스크가 순이득 없었으므로 기대 보수적.
성공기준(§E): c3_neu149·sa_speech74 부recall↑ 동시 중립 비열화·긍↔부 0. model_out 미덮어씀.
"""
import argparse
import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from finetune_sentiment import (TRAIN_FILES, TEST_SETS, load, metrics,  # noqa: E402
                                LAB2ID, ID2LAB, DATASET_DIR, MODEL_PATH)
from transformers import (AutoTokenizer, AutoModel, Trainer,  # noqa: E402
                          TrainingArguments, set_seed)


def supcon(z, labels, temp=0.1):
    """supervised contrastive loss (Khosla 2020). z: (B,d) L2정규화 전. labels: (B,)."""
    z = F.normalize(z, dim=1)
    sim = z @ z.t() / temp                                    # (B,B)
    B = z.size(0)
    mask_self = torch.eye(B, dtype=torch.bool, device=z.device)
    neg_inf = torch.finfo(sim.dtype).min                     # fp16 안전(-1e9는 Half 오버플로)
    sim = sim.masked_fill(mask_self, neg_inf)
    logp = sim - torch.logsumexp(sim, dim=1, keepdim=True)    # log softmax(행)
    pos = (labels.unsqueeze(0) == labels.unsqueeze(1)) & ~mask_self
    pos_cnt = pos.sum(1)
    valid = pos_cnt > 0
    if valid.sum() == 0:
        return z.new_zeros(())
    loss = -(logp * pos).sum(1)[valid] / pos_cnt[valid].clamp(min=1)
    return loss.mean()


class ConModel(nn.Module):
    def __init__(self, beta):
        super().__init__()
        self.base = AutoModel.from_pretrained(MODEL_PATH, local_files_only=True)
        h = self.base.config.hidden_size
        self.drop = nn.Dropout(0.1)
        self.pol = nn.Linear(h, 3)
        self.proj = nn.Sequential(nn.Linear(h, h), nn.ReLU(), nn.Linear(h, 128))
        self.beta = beta
        self.ce = nn.CrossEntropyLoss()

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        out = self.base(input_ids=input_ids, attention_mask=attention_mask)
        cls = out.last_hidden_state[:, 0]
        logits = self.pol(self.drop(cls))
        loss = None
        if labels is not None:
            loss = self.ce(logits, labels)
            if self.beta > 0:
                loss = loss + self.beta * supcon(self.proj(cls), labels)
        return {'loss': loss, 'logits': logits}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--betas', default='0.0,0.2')
    ap.add_argument('--seeds', default='42,43,44')
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--bs', type=int, default=32)   # 대조학습은 배치 클수록 유리
    ap.add_argument('--lr', type=float, default=2e-5)
    ap.add_argument('--field-token', choices=['on', 'off'], default='on')
    args = ap.parse_args()
    betas = [float(b) for b in args.betas.split(',') if b.strip()]
    seeds = [int(s) for s in args.seeds.split(',') if s.strip()]

    def apply_field(text, field):
        return f'{field} 평가: {text}' if (args.field_token == 'on' and field) else text

    train = []
    for f in TRAIN_FILES:
        train += load(f)
    tests = {name: load(fn) for name, fn in TEST_SETS.items()}
    all_test = {t for ts in tests.values() for t, _, _ in ts}
    train = [(t, y, fld) for t, y, fld in train if t not in all_test]
    print(f'train {len(train)} · betas={betas} · seeds={seeds} · bs={args.bs}')

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

    def collate(b):
        return {k: torch.stack([x[k] for x in b]) for k in b[0]}

    packs = {}
    for name, ts in tests.items():
        packs[name] = {'y': [yy for _, yy, _ in ts],
                       'mt': [apply_field(t, f) for t, _, f in ts]}

    def predict(model, texts):
        model.eval(); dev = next(model.parameters()).device; out = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                          return_tensors='pt').to(dev)
                out += model(input_ids=enc['input_ids'],
                             attention_mask=enc['attention_mask'])['logits'].argmax(-1).cpu().tolist()
        return out

    agg = {b: {name: [] for name in tests} for b in betas}
    summary = {'field_token': args.field_token, 'n_train': len(train), 'runs': []}
    for beta in betas:
        for seed in seeds:
            set_seed(seed)
            model = ConModel(beta)
            targs = TrainingArguments(
                output_dir=os.path.join(DATASET_DIR, 'model_con_tmp'), num_train_epochs=args.epochs,
                per_device_train_batch_size=args.bs, learning_rate=args.lr,
                fp16=torch.cuda.is_available(), logging_steps=40, save_strategy='no',
                report_to=[], seed=seed, remove_unused_columns=False)
            trainer = Trainer(model=model, args=targs, train_dataset=DS(train), data_collator=collate)
            print(f'\n=== β={beta} seed={seed} 학습 ===')
            trainer.train()
            print(f'--- β={beta} seed={seed} 평가 ---')
            for name, pk in packs.items():
                r = metrics(f'{name} b{beta}s{seed}', pk['y'], predict(model, pk['mt']))
                agg[beta][name].append(r)
                summary['runs'].append({'beta': beta, 'seed': seed, 'slice': name, 'acc': r['acc'],
                                        'pos_neg_err': r['pos_neg_err'], 'neg_recall': r['recall']['neg'],
                                        'neu_recall': r['recall']['neu']})
            del model, trainer
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    print('\n' + '=' * 60)
    print('=== β별 다중런 집계 (CE only=대조 vs SupCon) ===')
    summary['agg'] = {}
    for beta in betas:
        summary['agg'][str(beta)] = {}
        print(f'\n[β={beta}]')
        for name in tests:
            rs = agg[beta][name]
            accs = [r['acc'] for r in rs]; pne = [r['pos_neg_err'] for r in rs]
            negs = [r['recall']['neg'] for r in rs if r['recall']['neg'] is not None]
            print(f'  {name:12s} acc {np.mean(accs):.4f}±{np.std(accs):.4f} · 긍↔부 {pne} · 부recall {np.mean(negs):.3f}')
            summary['agg'][str(beta)][name] = {
                'acc_mean': round(float(np.mean(accs)), 4), 'acc_std': round(float(np.std(accs)), 4),
                'pos_neg_errs': pne, 'neg_recall_mean': round(float(np.mean(negs)), 3) if negs else None}

    out = os.path.join(DATASET_DIR, 'result', 'contrastive_260708.json')
    json.dump(summary, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n리포트 → {os.path.relpath(out, DATASET_DIR)}')


if __name__ == '__main__':
    main()
