# -*- coding: utf-8 -*-
"""L5 베이스 교체 A/B — klue/roberta-large(340M) vs 배포 KoTE-base(110M) (사용자 지시 260714).

가설: 천장 원인이 데이터가 아니라 모델 용량인지 확인. 채용 기준 = 정합 후 배포본
(baseline 97.7 · 8c 90.7 · c3 76.5 · sa 83.8 · 긍↔부 총 0)을 넘고 긍↔부 0.

변형:
  --stage gold        : gold 4,016만 4ep (배포 레시피 동일 조건)
  --stage silver+gold : silver_v2(정제 대량, 최대 60k) 2ep → gold 4ep 커리큘럼

6GB VRAM 대응: fp16 + gradient_checkpointing + adafactor + bs8(accum2). OOM 시 bs4.
평가: finetune_sentiment의 4슬라이스 동일 지표(정확도·긍↔부·재현율).
프리픽스: '{field} 평가: {text}' — 학습·평가 동일(현행 규약).
"""
import argparse
import io
import json
import os
import sys

import numpy as np

try:
    import truststore
    truststore.inject_into_ssl()   # 사내 SSL 인터셉트 대응(HF 다운로드)
except ImportError:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
WP = os.path.abspath(os.path.join(DS, '..', '..', '..'))
sys.path.insert(0, WP)
sys.path.insert(0, HERE)
from finetune_sentiment import TRAIN_FILES, TEST_SETS, LAB2ID, ID2LAB, load, metrics  # noqa: E402

BASE = 'klue/roberta-large'
SILVER = os.path.join(DS, 'emotion', 'silver_v2_260714.jsonl')


def apply_field(text, field):
    return f'{field} 평가: {text}' if field else text


def make_ds(pairs, tok):
    import torch

    class D(torch.utils.data.Dataset):
        def __init__(self):
            self.enc = tok([apply_field(t, f) for t, y, f in pairs], padding=False,
                           truncation=True, max_length=128)
            self.y = [y for t, y, f in pairs]

        def __len__(self):
            return len(self.y)

        def __getitem__(self, i):
            d = {k: v[i] for k, v in self.enc.items()}
            d['labels'] = self.y[i]
            return d
    return D()


def train_stage(model, tok, pairs, epochs, lr, seed, tag):
    from transformers import Trainer, TrainingArguments, DataCollatorWithPadding
    args = TrainingArguments(
        output_dir=os.path.join(HERE, f'_tmp_el_{tag}'), num_train_epochs=epochs,
        per_device_train_batch_size=8, gradient_accumulation_steps=2, learning_rate=lr,
        fp16=True, gradient_checkpointing=True, optim='adafactor', seed=seed,
        logging_steps=200, save_strategy='no', report_to=[], warmup_ratio=0.06,
    )
    Trainer(model=model, args=args, train_dataset=make_ds(pairs, tok),
            data_collator=DataCollatorWithPadding(tok)).train()


def evaluate(model, tok, name, rows):
    import torch
    model.eval()
    preds = []
    for i in range(0, len(rows), 64):
        ch = rows[i:i + 64]
        xs = [apply_field(t, f) for t, y, f in ch]
        enc = tok(xs, padding=True, truncation=True, max_length=128, return_tensors='pt').to(model.device)
        with torch.no_grad():
            preds += model(**enc).logits.argmax(-1).cpu().tolist()
    return metrics(name, [y for t, y, f in rows], preds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', choices=['gold', 'silver+gold'], default='gold')
    ap.add_argument('--seed', type=int, default=45)
    ap.add_argument('--silver-cap', type=int, default=60000)
    ap.add_argument('--save-dir', default=None)
    a = ap.parse_args()

    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, set_seed
    set_seed(a.seed)

    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForSequenceClassification.from_pretrained(BASE, num_labels=3).cuda()

    gold = []
    for fn in TRAIN_FILES:
        gold += load(fn)
    # 테스트 누수 최종가드
    test_rows = {}
    test_texts = set()
    for name, fn in TEST_SETS.items():
        rs = load(fn)
        test_rows[name] = rs
        test_texts |= {t for t, y, f in rs}
    gold = [(t, y, f) for t, y, f in gold if t not in test_texts]
    print(f'base={BASE} stage={a.stage} seed={a.seed} gold={len(gold)}')

    if a.stage == 'silver+gold':
        silver = []
        for line in io.open(SILVER, encoding='utf-8'):
            r = json.loads(line)
            if r['text'] in test_texts:
                continue
            silver.append((r['text'], LAB2ID[r['sentiment_silver']], r['field']))
        silver = silver[:a.silver_cap]
        print(f'stage A: silver_v2 {len(silver)} · 2ep')
        train_stage(model, tok, silver, 2, 2e-5, a.seed, 'A')
    print('stage B: gold 4ep')
    train_stage(model, tok, gold, 4, 1e-5, a.seed, 'B')

    print(f'=== 평가(정합 gold 기준) — 채용기준: 97.7/90.7/76.5/83.8·긍↔부0 ===')
    for name, rs in test_rows.items():
        evaluate(model, tok, name, rs)

    if a.save_dir:
        out = os.path.join(HERE, a.save_dir)
        model.save_pretrained(out)
        tok.save_pretrained(out)
        print('저장 →', out)


if __name__ == '__main__':
    main()
