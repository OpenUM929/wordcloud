# -*- coding: utf-8 -*-
"""260715 교정 gold 재학습 A/B — 티어 분리로 게이트(긍↔부=0) 판단.

배경: gold_corrected_260715(2024) = T1 검증분(사람23+동의55+규칙정제중립234=312) +
  T2 패턴분(A~D 하드코딩 1712). 패턴이 압도적·미검증 → packet23처럼 게이트 깰 위험.
  한 번에 넣으면 실패해도 원인 못 가림 → 티어별로 학습·측정.

방법: 배포경로(seed45·field-token on·4epoch)와 동일. 배포모델 미덮어씀(임시 output_dir, save 안 함).
  각 config별로 현 TRAIN_FILES + (해당 티어) 로 학습 → 4슬라이스 측정.
  기준선: 배포본(정합측정 97.7/90.7/76.5/83.8·긍↔부0)과 대조.

config: base(추가0) / t1(+검증312) / full(+2024)
실행: python ab_retrain_corrected_260715.py --configs t1,full [--seed 45] [--epochs 4]
"""
import argparse
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from finetune_sentiment import (TRAIN_FILES, TEST_SETS, load, metrics,  # noqa: E402
                                LAB2ID, ID2LAB, DATASET_DIR, MODEL_PATH)

CORR = 'gold_corrected_260715.jsonl'
T1_SRC = {'human', 'user_agreed', 'rule_silver'}   # 검증 티어(사람/동의/규칙정제 중립)


def load_corrected(tier):
    """gold_corrected를 티어별로 (text,label_id,field) 반환. tier: 't1' | 'full'."""
    out = []
    for line in open(os.path.join(DATASET_DIR, 'eval', CORR), encoding='utf-8'):
        r = json.loads(line)
        hd = r.get('human_decision')
        if hd not in LAB2ID or not (r.get('text') or '').strip():
            continue
        if tier == 't1' and (r.get('decision_source') not in T1_SRC):
            continue
        out.append((r['text'].strip(), LAB2ID[hd], (r.get('field') or '').strip()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--configs', default='t1,full')
    ap.add_argument('--seed', type=int, default=45)
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--bs', type=int, default=16)
    ap.add_argument('--lr', type=float, default=2e-5)
    args = ap.parse_args()

    import torch
    from torch.utils.data import Dataset
    from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                              Trainer, TrainingArguments, set_seed)

    def apply_field(text, field):
        return f'{field} 평가: {text}' if field else text

    base_train = []
    for f in TRAIN_FILES:
        base_train += load(f)
    tests = {name: load(fn) for name, fn in TEST_SETS.items()}
    all_test = {t for ts in tests.values() for t, _, _ in ts}
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
        packs[name] = {'y': [yy for _, yy, _ in ts],
                       'mt': [apply_field(t, f) for t, _, f in ts]}

    report = {}
    for cfg in [c.strip() for c in args.configs.split(',') if c.strip()]:
        extra = [] if cfg == 'base' else load_corrected('t1' if cfg == 't1' else 'full')
        train = base_train + extra
        train = [(t, y, f) for t, y, f in train if t not in all_test]   # 누수가드
        print(f'\n{"="*64}\n[config={cfg}] base {len(base_train)} + 추가 {len(extra)} '
              f'→ train {len(train)} (누수제외 후)')
        print('  분포:', {ID2LAB[k]: v for k, v in Counter(l for _, l, _ in train).items()})

        set_seed(args.seed)
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_PATH, num_labels=3, ignore_mismatched_sizes=True, local_files_only=True,
            problem_type='single_label_classification')
        targs = TrainingArguments(
            output_dir=os.path.join(DATASET_DIR, 'model_ab_tmp'), num_train_epochs=args.epochs,
            per_device_train_batch_size=args.bs, learning_rate=args.lr,
            fp16=torch.cuda.is_available(), logging_steps=50, save_strategy='no',
            report_to=[], seed=args.seed)
        Trainer(model=model, args=targs, train_dataset=DS(train)).train()
        model.eval(); dev = model.device

        def pred(texts):
            out = []
            with torch.no_grad():
                for i in range(0, len(texts), 64):
                    enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                              return_tensors='pt').to(dev)
                    out += model(**enc).logits.argmax(-1).cpu().tolist()
            return out

        print(f'--- [config={cfg}] seed={args.seed} 측정 ---')
        report[cfg] = {'n_train': len(train), 'n_extra': len(extra), 'slices': {}}
        for name, pk in packs.items():
            r = metrics(f'{cfg}:{name}', pk['y'], pred(pk['mt']))
            report[cfg]['slices'][name] = {'acc': round(r['acc'], 4),
                                           'pos_neg_err': r['pos_neg_err'],
                                           'neg_recall': r['recall']['neg']}
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    out = os.path.join(DATASET_DIR, 'result', 'ab_retrain_corrected_260715.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(report, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n' + '=' * 64)
    print('GATE(긍↔부 baseline399·8c_hard = 0 필수) 요약:')
    for cfg, rr in report.items():
        g = {n: rr['slices'][n]['pos_neg_err'] for n in ('baseline399', '8c_hard')}
        acc = {n: rr['slices'][n]['acc'] for n in rr['slices']}
        ok = all(v == 0 for v in g.values())
        print(f'  [{cfg}] 긍↔부{g} {"PASS" if ok else "FAIL"} · acc {acc}')
    print(f'\n리포트 → {os.path.relpath(out, DATASET_DIR)}')


if __name__ == '__main__':
    main()
