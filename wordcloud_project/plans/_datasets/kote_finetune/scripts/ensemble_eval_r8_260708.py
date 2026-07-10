# -*- coding: utf-8 -*-
"""모델링 레버 A — **앙상블(seed 소프트보팅)** 실측(MODELING_LEVERS_PLAN §A).

배경: c3_neu149 부recall은 런당 0.48~0.69로 단일런 point가 노이즈. 후속 레버(B 비대칭손실·
C 캘리브레이션)의 +1~2pp를 노이즈와 구분하려면 **측정 분산부터 죽여야** 한다.

방법: c4 라인(TRAIN_FILES 불변, 단일헤드) 을 seed {42..46}로 K회 학습 → 슬라이스별 **softmax
확률** 수집 → 평균 → argmax → metrics. 개별 K런 지표도 출력(acc·부recall의 평균·std로 분산 정량화).
model_out(c4 배포모델) **미덮어씀**(save 안 함, 임시 output_dir).

성공기준(§A): 앙상블 c3_neu149 acc > 단일런 평균+1std(분산 넘는 실이득) · baseline·8c_hard
긍↔부 0 · acc std 축소(측정 정밀화 입증).
실행: python ensemble_eval_r8_260708.py [--seeds 42,43,44,45,46] [--epochs 4] [--field-token on]
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from finetune_sentiment import (TRAIN_FILES, TEST_SETS, load, metrics, rule_before,  # noqa: E402
                                LAB2ID, ID2LAB, DATASET_DIR, MODEL_PATH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', default='42,43,44,45,46')
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--bs', type=int, default=16)
    ap.add_argument('--lr', type=float, default=2e-5)
    ap.add_argument('--field-token', choices=['on', 'off'], default='on')
    ap.add_argument('--skip-before', action='store_true', default=True)
    ap.add_argument('--save-seed', type=int, default=None,
                    help='지정 시 5런 루프 대신 이 seed 하나만 학습·저장(best-seed 배포용). 앙상블 루프와 동일 코드경로로 재현.')
    ap.add_argument('--save-dir', default=None, help='--save-seed 저장 경로(예: model_out)')
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(',') if s.strip()]

    import torch
    from torch.utils.data import Dataset
    from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                              Trainer, TrainingArguments, set_seed)

    def apply_field(text, field):
        return f'{field} 평가: {text}' if (args.field_token == 'on' and field) else text

    # ── 데이터(누수가드는 finetune_sentiment와 동일 규약) ──
    train = []
    for f in TRAIN_FILES:
        train += load(f)
    tests = {name: load(fn) for name, fn in TEST_SETS.items()}
    all_test = {t for ts in tests.values() for t, _, _ in ts}
    train = [(t, y, fld) for t, y, fld in train if t not in all_test]
    from collections import Counter
    print(f'train {len(train)} · field-token={args.field_token} · seeds={seeds}')
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

    # 슬라이스별 텍스트/정답/프리픽스 사전계산
    packs = {}
    for name, ts in tests.items():
        texts = [t for t, _, _ in ts]; y = [yy for _, yy, _ in ts]; fields = [fld for _, _, fld in ts]
        mt = [apply_field(t, f) for t, f in zip(texts, fields)]
        packs[name] = {'y': y, 'mt': mt, 'prob_sum': None}

    # ── best-seed 저장 모드(배포): 지정 seed 하나만 앙상블과 동일 경로로 학습·저장 ──
    if args.save_seed is not None:
        assert args.save_dir, '--save-dir 필요'
        set_seed(args.save_seed)
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_PATH, num_labels=3, ignore_mismatched_sizes=True, local_files_only=True,
            problem_type='single_label_classification')
        targs = TrainingArguments(
            output_dir=os.path.join(DATASET_DIR, 'model_ens_tmp'), num_train_epochs=args.epochs,
            per_device_train_batch_size=args.bs, learning_rate=args.lr,
            fp16=torch.cuda.is_available(), logging_steps=40, save_strategy='no',
            report_to=[], seed=args.save_seed)
        trainer = Trainer(model=model, args=targs, train_dataset=DS(train))
        print(f'\n=== best-seed 저장 학습 seed={args.save_seed} → {args.save_dir} ===')
        trainer.train()
        model.eval(); dev = model.device

        def _pred(texts):
            out = []
            with torch.no_grad():
                for i in range(0, len(texts), 64):
                    enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                              return_tensors='pt').to(dev)
                    out += model(**enc).logits.argmax(-1).cpu().tolist()
            return out
        print(f'--- 저장 전 재현 확인(seed={args.save_seed}) ---')
        for name, pk in packs.items():
            metrics(f'{name} save-seed{args.save_seed}', pk['y'], _pred(pk['mt']))
        model.save_pretrained(args.save_dir); tok.save_pretrained(args.save_dir)
        print(f'\n저장 완료 → {args.save_dir} (field-token=on 규약으로 학습됨)')
        return

    per_seed = {name: [] for name in tests}   # 개별런 지표(분산 정량화)

    for si, seed in enumerate(seeds):
        set_seed(seed)
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_PATH, num_labels=3, ignore_mismatched_sizes=True, local_files_only=True,
            problem_type='single_label_classification')
        targs = TrainingArguments(
            output_dir=os.path.join(DATASET_DIR, 'model_ens_tmp'), num_train_epochs=args.epochs,
            per_device_train_batch_size=args.bs, learning_rate=args.lr,
            fp16=torch.cuda.is_available(), logging_steps=40, save_strategy='no',
            report_to=[], seed=seed)
        trainer = Trainer(model=model, args=targs, train_dataset=DS(train))
        print(f'\n=== [{si+1}/{len(seeds)}] seed={seed} 학습 ===')
        trainer.train()
        model.eval(); dev = model.device

        def probs(texts):
            out = []
            with torch.no_grad():
                for i in range(0, len(texts), 64):
                    enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                              return_tensors='pt').to(dev)
                    p = torch.softmax(model(**enc).logits, dim=-1).cpu().numpy()
                    out.append(p)
            return np.concatenate(out, axis=0)

        print(f'--- seed={seed} 개별런 ---')
        for name, pk in packs.items():
            p = probs(pk['mt'])
            pk['prob_sum'] = p if pk['prob_sum'] is None else pk['prob_sum'] + p
            r = metrics(f'{name} s{seed}', pk['y'], p.argmax(-1).tolist())
            per_seed[name].append(r)
        del model, trainer
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # ── 앙상블(확률평균) + 분산요약 ──
    print('\n' + '=' * 60)
    print(f'=== 앙상블(softmax 평균, K={len(seeds)}) vs 단일런 분산 ===')
    summary = {'seeds': seeds, 'field_token': args.field_token, 'n_train': len(train), 'slices': {}}
    for name, pk in packs.items():
        ens_pred = (pk['prob_sum'] / len(seeds)).argmax(-1).tolist()
        print(f'\n--- [{name}] ---')
        ens = metrics(f'{name} ENSEMBLE', pk['y'], ens_pred)
        accs = [r['acc'] for r in per_seed[name]]
        negs = [r['recall']['neg'] for r in per_seed[name] if r['recall']['neg'] is not None]
        pnerrs = [r['pos_neg_err'] for r in per_seed[name]]
        acc_mean, acc_std = float(np.mean(accs)), float(np.std(accs))
        neg_mean = float(np.mean(negs)) if negs else None
        neg_std = float(np.std(negs)) if negs else None
        print(f'  단일런 acc {acc_mean:.4f}±{acc_std:.4f} (min {min(accs):.4f} max {max(accs):.4f}) '
              f'· 부recall {neg_mean}±{neg_std} · 긍↔부 {pnerrs}')
        gain = ens['acc'] - acc_mean
        beats = ens['acc'] > acc_mean + acc_std
        print(f'  ▶ 앙상블 acc {ens["acc"]:.4f} = 평균 {"+" if gain>=0 else ""}{gain:.4f} '
              f'({"평균+1std 초과 ✔실이득" if beats else "분산내 ✘노이즈"})')
        summary['slices'][name] = {
            'ensemble': ens, 'single_acc_mean': round(acc_mean, 4), 'single_acc_std': round(acc_std, 4),
            'single_acc_min': round(min(accs), 4), 'single_acc_max': round(max(accs), 4),
            'single_neg_mean': neg_mean, 'single_neg_std': neg_std,
            'single_pos_neg_errs': pnerrs, 'ens_beats_mean_plus_std': bool(beats),
            'ens_acc_gain_vs_mean': round(gain, 4)}

    out = os.path.join(DATASET_DIR, 'result', 'ensemble_eval_260708.json')
    json.dump(summary, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n리포트 → {os.path.relpath(out, DATASET_DIR)}')


if __name__ == '__main__':
    main()
