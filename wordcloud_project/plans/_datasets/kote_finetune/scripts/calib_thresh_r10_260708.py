# -*- coding: utf-8 -*-
"""모델링 레버 C — **사후 캘리브레이션 + 임계값 튜닝**(MODELING_LEVERS_PLAN §C).

목표: 재학습 없이 **작동점(operating point) 명시 선택**. c5·c6·c7이 재학습으로 밀던
"중→부 vs 중→긍" 트레이드오프를 임계값으로 직접 제어. 긍↔부=0 하드제약 하 acc 최대.

방법(전부 사후, 학습된 모델 위):
1. train 일부(15%)를 dev로 홀드(테스트 누수 0). 나머지로 학습.
2. Temperature scaling: dev NLL 최소 T 1파라미터 그리드 적합.
3. 임계값: "부정=p_neg-p_neu>τneg, 긍정=p_pos-p_neu>τpos, 아니면 중립". dev에서
   **긍↔부=0 제약 하 acc 최대**인 (τneg,τpos) 그리드 탐색. (중립 방향 보수 = 중립→긍 허용 정렬)
4. 같은 모델의 test 로짓에 T·τ 적용 → argmax(대조) 대비 델타.

노이즈 통제: seed {42,43,44} 각각 자기 dev로 T·τ 적합 → 자기 test에 적용 → 델타 평균.
성공기준(§C): 긍↔부 0 유지하며 c3_neu149 acc ≥ argmax. ECE 개선. model_out 미덮어씀.
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

POS, NEG, NEU = 0, 1, 2


def softmax_np(z, T=1.0):
    z = z / T
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature(logits, y):
    """dev NLL 최소 T 그리드 적합."""
    best_T, best_nll = 1.0, 1e9
    for T in np.linspace(0.5, 5.0, 46):
        p = softmax_np(logits, T)
        nll = -np.log(p[np.arange(len(y)), y] + 1e-12).mean()
        if nll < best_nll:
            best_nll, best_T = nll, T
    return best_T, best_nll


def ece(probs, y, bins=10):
    conf = probs.max(1); pred = probs.argmax(1); correct = (pred == y).astype(float)
    e = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        m = (conf > lo) & (conf <= hi)
        if m.sum() > 0:
            e += m.mean() * abs(correct[m].mean() - conf[m].mean())
    return float(e)


def decide(probs, tneg, tpos):
    """3-way 임계결정: 극성은 중립대비 마진 초과해야 확정, 아니면 중립."""
    p_pos, p_neg, p_neu = probs[:, POS], probs[:, NEG], probs[:, NEU]
    mneg = p_neg - p_neu
    mpos = p_pos - p_neu
    out = np.full(len(probs), NEU)
    take_neg = mneg > tneg
    take_pos = mpos > tpos
    # 둘 다 넘으면 더 큰 마진 채택
    out[take_neg & (~take_pos | (mneg >= mpos))] = NEG
    out[take_pos & (~take_neg | (mpos > mneg))] = POS
    return out


def pn_err(y, pred):
    y, pred = np.array(y), np.array(pred)
    return int(((y == NEG) & (pred == POS)).sum() + ((y == POS) & (pred == NEG)).sum())


def tune_thresholds(dev_probs, dev_y):
    """dev에서 긍↔부=0(달성불가 시 최소) 제약 하 acc 최대 (τneg,τpos)."""
    grid = np.round(np.arange(-0.2, 0.61, 0.05), 2)
    best = None
    for tneg in grid:
        for tpos in grid:
            pred = decide(dev_probs, tneg, tpos)
            acc = (pred == dev_y).mean()
            pne = pn_err(dev_y, pred)
            key = (pne, -acc)   # 긍↔부 최소 우선, 그다음 acc 최대
            if best is None or key < best[0]:
                best = (key, tneg, tpos, acc, pne)
    return best[1], best[2], best[3], best[4]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', default='42,43,44')
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--bs', type=int, default=16)
    ap.add_argument('--lr', type=float, default=2e-5)
    ap.add_argument('--dev-frac', type=float, default=0.15)
    ap.add_argument('--field-token', choices=['on', 'off'], default='on')
    args = ap.parse_args()
    seeds = [int(s) for s in args.seeds.split(',') if s.strip()]

    import random
    import torch
    from torch.utils.data import Dataset
    from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                              Trainer, TrainingArguments, set_seed)

    def apply_field(text, field):
        return f'{field} 평가: {text}' if (args.field_token == 'on' and field) else text

    train_all = []
    for f in TRAIN_FILES:
        train_all += load(f)
    tests = {name: load(fn) for name, fn in TEST_SETS.items()}
    all_test = {t for ts in tests.values() for t, _, _ in ts}
    train_all = [(t, y, fld) for t, y, fld in train_all if t not in all_test]
    print(f'train_all {len(train_all)} · dev_frac {args.dev_frac} · seeds {seeds}')

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
        y = [yy for _, yy, _ in ts]
        mt = [apply_field(t, f) for t, _, f in ts]
        packs[name] = {'y': np.array(y), 'mt': mt}

    def get_logits(model, texts):
        model.eval(); dev = model.device; out = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                          return_tensors='pt').to(dev)
                out.append(model(**enc).logits.cpu().numpy())
        return np.concatenate(out, 0)

    summary = {'field_token': args.field_token, 'seeds': seeds, 'per_seed': [],
               'dev_frac': args.dev_frac}
    # 슬라이스별: argmax vs calibrated 지표를 seed별로 모아 평균
    agg = {name: {'argmax': [], 'calib': []} for name in tests}

    for seed in seeds:
        rng = random.Random(seed)
        idx = list(range(len(train_all)))
        rng.shuffle(idx)
        ndev = int(round(len(idx) * args.dev_frac))
        dev_rows = [train_all[i] for i in idx[:ndev]]
        tr_rows = [train_all[i] for i in idx[ndev:]]
        set_seed(seed)
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_PATH, num_labels=3, ignore_mismatched_sizes=True, local_files_only=True,
            problem_type='single_label_classification')
        targs = TrainingArguments(
            output_dir=os.path.join(DATASET_DIR, 'model_calib_tmp'), num_train_epochs=args.epochs,
            per_device_train_batch_size=args.bs, learning_rate=args.lr,
            fp16=torch.cuda.is_available(), logging_steps=60, save_strategy='no',
            report_to=[], seed=seed)
        trainer = Trainer(model=model, args=targs, train_dataset=DS(tr_rows))
        print(f'\n=== seed={seed} 학습(train {len(tr_rows)}, dev {len(dev_rows)}) ===')
        trainer.train()

        # dev 로짓 → T 적합 → τ 튜닝
        dev_logits = get_logits(model, [apply_field(t, f) for t, _, f in dev_rows])
        dev_y = np.array([y for _, y, _ in dev_rows])
        T, nll = fit_temperature(dev_logits, dev_y)
        dev_probs_T = softmax_np(dev_logits, T)
        tneg, tpos, dev_acc, dev_pne = tune_thresholds(dev_probs_T, dev_y)
        ece_raw = ece(softmax_np(dev_logits, 1.0), dev_y)
        ece_T = ece(dev_probs_T, dev_y)
        print(f'  T={T:.2f} (dev NLL {nll:.3f}) · τneg={tneg} τpos={tpos} '
              f'(dev acc {dev_acc:.3f} 긍↔부 {dev_pne}) · ECE {ece_raw:.3f}→{ece_T:.3f}')
        summary['per_seed'].append({'seed': seed, 'T': round(float(T), 3),
                                    'tneg': float(tneg), 'tpos': float(tpos),
                                    'dev_acc': round(float(dev_acc), 4), 'dev_pne': int(dev_pne),
                                    'ece_raw': round(ece_raw, 4), 'ece_T': round(ece_T, 4)})

        print(f'--- seed={seed} test (argmax 대조 vs 캘리브+임계) ---')
        for name, pk in packs.items():
            lg = get_logits(model, pk['mt'])
            am = lg.argmax(1)
            cal = decide(softmax_np(lg, T), tneg, tpos)
            r_am = metrics(f'{name} argmax s{seed}', pk['y'], am.tolist())
            r_cal = metrics(f'{name} calib  s{seed}', pk['y'], cal.tolist())
            agg[name]['argmax'].append(r_am)
            agg[name]['calib'].append(r_cal)
        del model, trainer
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # ── 집계(argmax vs calib 다중런 평균) ──
    print('\n' + '=' * 60)
    print('=== argmax(대조) vs 캘리브+임계 (seed 평균) ===')
    summary['agg'] = {}
    for name in tests:
        am_acc = [r['acc'] for r in agg[name]['argmax']]
        ca_acc = [r['acc'] for r in agg[name]['calib']]
        am_pne = [r['pos_neg_err'] for r in agg[name]['argmax']]
        ca_pne = [r['pos_neg_err'] for r in agg[name]['calib']]
        am_neg = [r['recall']['neg'] for r in agg[name]['argmax'] if r['recall']['neg'] is not None]
        ca_neg = [r['recall']['neg'] for r in agg[name]['calib'] if r['recall']['neg'] is not None]
        d = np.mean(ca_acc) - np.mean(am_acc)
        print(f'\n[{name}]')
        print(f'  argmax  acc {np.mean(am_acc):.4f}±{np.std(am_acc):.4f} · 긍↔부 {am_pne} · 부recall {np.mean(am_neg):.3f}')
        print(f'  calib   acc {np.mean(ca_acc):.4f}±{np.std(ca_acc):.4f} · 긍↔부 {ca_pne} · 부recall {np.mean(ca_neg):.3f} · Δacc {d:+.4f}')
        summary['agg'][name] = {
            'argmax_acc_mean': round(float(np.mean(am_acc)), 4), 'calib_acc_mean': round(float(np.mean(ca_acc)), 4),
            'argmax_pne': am_pne, 'calib_pne': ca_pne, 'delta_acc': round(float(d), 4),
            'argmax_neg_mean': round(float(np.mean(am_neg)), 3), 'calib_neg_mean': round(float(np.mean(ca_neg)), 3)}

    out = os.path.join(DATASET_DIR, 'result', 'calib_thresh_260708.json')
    json.dump(summary, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n리포트 → {os.path.relpath(out, DATASET_DIR)}')


if __name__ == '__main__':
    main()
