# -*- coding: utf-8 -*-
"""개선 레버 L1 — **라벨 일관성 감사**(confident-learning, 5-fold out-of-fold. plans/2026/0708_02 §L1).

가설: c5·c6·c7의 공통 실패 signature("gold 추가 → 중립경계 오류 재분배")는 학습셋 내부의
모순된 중립경계 라벨이 원인일 수 있다. 06-30 감사(gold_audit_260630)는 긍↔부 오염만 스크린
했고 라벨 일관성(특히 중립)은 미감사.

방법:
1. (GPU 0) 표면형 충돌 스캔: 동일 (정규화 텍스트, field)인데 라벨이 갈리는 행 병치.
2. (GPU 5런) TRAIN을 (text,field) 키 기준 5-fold 분할(중복행 동일 fold=자기누수 차단),
   각 fold를 나머지 4-fold 학습 모델로 oof 예측 → (gold≠oof)∧고확신 행을 의심 랭킹.
3. (GPU 0, model_out 재사용) 테스트 4슬라이스도 배포모델 예측 고확신 불일치 감사(측정 노이즈 축소용).
출력: eval/review/label_audit_queue_260708.jsonl (kind=surface_conflict|oof|test_slice)
      + result/label_audit_260708.json 요약.
정정 반영은 여기서 안 한다 — Claude per-row prefill → 사용자 확정 → promote_gold 리비전 append.
실행: python label_audit_cv_r13.py [--folds 5] [--conf 0.8]
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from finetune_sentiment import (TRAIN_FILES, TEST_SETS, load, LAB2ID, ID2LAB,  # noqa: E402
                                DATASET_DIR, MODEL_PATH)


def load_prov(fn):
    """finetune_sentiment.load와 동일 필터 + 출처(file·rec_id·행번호) 보존."""
    out = []
    with open(os.path.join(DATASET_DIR, 'eval', fn), encoding='utf-8') as f:
        for ln, line in enumerate(f, 1):
            r = json.loads(line)
            hd = r.get('human_decision')
            t = (r.get('text') or '').strip()
            if hd in LAB2ID and t:
                out.append({'file': fn, 'line': ln, 'rec_id': r.get('rec_id'),
                            'text': t, 'field': (r.get('field') or '').strip(),
                            'label': LAB2ID[hd], 'group': r.get('group')})
    return out


def norm_key(text, field):
    return (re.sub(r'\s+', '', text), field)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--folds', type=int, default=5)
    ap.add_argument('--conf', type=float, default=0.8, help='oof 의심행 최소 예측확신')
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--bs', type=int, default=16)
    ap.add_argument('--lr', type=float, default=2e-5)
    ap.add_argument('--skip-cv', action='store_true', help='GPU 없이 1·3단계만')
    args = ap.parse_args()

    rows = []
    for f in TRAIN_FILES:
        rows += load_prov(f)
    tests = {name: load(fn) for name, fn in TEST_SETS.items()}
    all_test = {t for ts in tests.values() for t, _, _ in ts}
    _b = len(rows)
    rows = [r for r in rows if r['text'] not in all_test]
    print(f'TRAIN {len(rows)}행 (누수가드 -{_b - len(rows)}) · 파일 {len(TRAIN_FILES)}종')
    print('  분포:', {ID2LAB[k]: v for k, v in Counter(r['label'] for r in rows).items()})

    queue = []

    # ── 1) 표면형 충돌(라벨 모순 직접 증거, GPU 0) ──
    by_key = defaultdict(list)
    for i, r in enumerate(rows):
        by_key[norm_key(r['text'], r['field'])].append(i)
    n_conf_groups = 0
    for key, idxs in sorted(by_key.items()):
        labs = {rows[i]['label'] for i in idxs}
        if len(labs) > 1:
            n_conf_groups += 1
            for i in idxs:
                r = rows[i]
                queue.append({'kind': 'surface_conflict', 'conflict_group': n_conf_groups,
                              'file': r['file'], 'line': r['line'], 'rec_id': r['rec_id'],
                              'text': r['text'], 'field': r['field'],
                              'gold': ID2LAB[r['label']],
                              'conflict_labels': sorted(ID2LAB[l] for l in labs)})
    print(f'\n[1] 표면형 충돌 그룹 {n_conf_groups}개 '
          f'({sum(1 for q in queue if q["kind"] == "surface_conflict")}행)')

    # ── 2) 5-fold oof (중복 표면형은 동일 fold 배정 → 자기누수 차단) ──
    oof_stats = {}
    if not args.skip_cv:
        import torch
        from torch.utils.data import Dataset
        from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                                  Trainer, TrainingArguments, set_seed)

        def apply_field(text, field):
            return f'{field} 평가: {text}' if field else text

        tok = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)

        class DS(Dataset):
            def __init__(self, rs):
                self.rs = rs
            def __len__(self):
                return len(self.rs)
            def __getitem__(self, i):
                r = self.rs[i]
                enc = tok(apply_field(r['text'], r['field']), truncation=True,
                          padding='max_length', max_length=64, return_tensors='pt')
                return {'input_ids': enc['input_ids'][0],
                        'attention_mask': enc['attention_mask'][0],
                        'labels': torch.tensor(r['label'])}

        # fold 배정: 유니크 키를 라벨 층화 라운드로빈(seed 42 셔플)
        import random
        keys = sorted(by_key.keys(), key=lambda k: (rows[by_key[k][0]]['label'], k))
        rng = random.Random(42)
        by_lab = defaultdict(list)
        for k in keys:
            by_lab[rows[by_key[k][0]]['label']].append(k)
        key_fold = {}
        for lab, ks in by_lab.items():
            rng.shuffle(ks)
            for j, k in enumerate(ks):
                key_fold[k] = j % args.folds
        fold_of = [key_fold[norm_key(r['text'], r['field'])] for r in rows]

        oof_pred = np.full(len(rows), -1)
        oof_conf = np.zeros(len(rows))
        for fold in range(args.folds):
            tr = [rows[i] for i in range(len(rows)) if fold_of[i] != fold]
            va_idx = [i for i in range(len(rows)) if fold_of[i] == fold]
            set_seed(42)
            model = AutoModelForSequenceClassification.from_pretrained(
                MODEL_PATH, num_labels=3, ignore_mismatched_sizes=True,
                local_files_only=True, problem_type='single_label_classification')
            targs = TrainingArguments(
                output_dir=os.path.join(DATASET_DIR, 'model_audit_tmp'),
                num_train_epochs=args.epochs, per_device_train_batch_size=args.bs,
                learning_rate=args.lr, fp16=torch.cuda.is_available(),
                logging_steps=80, save_strategy='no', report_to=[], seed=42)
            trainer = Trainer(model=model, args=targs, train_dataset=DS(tr))
            print(f'\n=== fold {fold + 1}/{args.folds} 학습(train {len(tr)} · oof {len(va_idx)}) ===')
            trainer.train()
            model.eval()
            dev = model.device
            texts = [apply_field(rows[i]['text'], rows[i]['field']) for i in va_idx]
            with torch.no_grad():
                for s in range(0, len(texts), 64):
                    enc = tok(texts[s:s + 64], truncation=True, padding=True, max_length=64,
                              return_tensors='pt').to(dev)
                    p = torch.softmax(model(**enc).logits, -1).cpu().numpy()
                    for off, pi in enumerate(p):
                        gi = va_idx[s + off]
                        oof_pred[gi] = int(pi.argmax())
                        oof_conf[gi] = float(pi.max())
            del model, trainer
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        gold = np.array([r['label'] for r in rows])
        dis = oof_pred != gold
        oof_acc = float((~dis).mean())
        sus = dis & (oof_conf >= args.conf)
        # 긍↔부 방향 의심(최우선)과 중립경계 의심 분리 집계
        pn = dis & (((gold == 0) & (oof_pred == 1)) | ((gold == 1) & (oof_pred == 0)))
        print(f'\n[2] oof 일치율 {oof_acc:.4f} · 불일치 {int(dis.sum())} · '
              f'고확신(≥{args.conf}) 의심 {int(sus.sum())} · 긍↔부 방향 {int(pn.sum())}')
        order = np.argsort(-oof_conf)
        rank = 0
        for i in order:
            if not sus[i]:
                continue
            rank += 1
            r = rows[i]
            queue.append({'kind': 'oof', 'rank': rank, 'file': r['file'], 'line': r['line'],
                          'rec_id': r['rec_id'], 'text': r['text'], 'field': r['field'],
                          'group': r.get('group'), 'gold': ID2LAB[r['label']],
                          'oof_pred': ID2LAB[int(oof_pred[i])],
                          'conf': round(float(oof_conf[i]), 4),
                          'pn_direction': bool(pn[i]), 'fold': int(fold_of[i])})
        oof_stats = {'oof_acc': round(oof_acc, 4), 'n_disagree': int(dis.sum()),
                     'n_suspect': int(sus.sum()), 'n_pn_direction': int(pn.sum()),
                     'conf_threshold': args.conf,
                     'disagree_by_gold': {ID2LAB[c]: int((dis & (gold == c)).sum())
                                          for c in (0, 1, 2)}}

    # ── 3) 테스트 슬라이스 감사(배포 seed45 model_out 재사용, 학습 0) ──
    mo = os.path.join(DATASET_DIR, 'model_out')
    if os.path.isdir(mo):
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        tok2 = AutoTokenizer.from_pretrained(mo, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(mo, local_files_only=True)
        if torch.cuda.is_available():
            model = model.cuda()
        model.eval()
        n_ts = 0
        for name, ts in tests.items():
            mt = [(f'{f} 평가: {t}' if f else t) for t, _, f in ts]
            preds, confs = [], []
            with torch.no_grad():
                for s in range(0, len(mt), 64):
                    enc = tok2(mt[s:s + 64], truncation=True, padding=True, max_length=64,
                               return_tensors='pt').to(model.device)
                    p = torch.softmax(model(**enc).logits, -1).cpu().numpy()
                    preds += p.argmax(-1).tolist()
                    confs += p.max(-1).tolist()
            for (t, y, f), pr, cf in zip(ts, preds, confs):
                if pr != y and cf >= args.conf:
                    n_ts += 1
                    queue.append({'kind': 'test_slice', 'slice': name, 'text': t, 'field': f,
                                  'gold': ID2LAB[y], 'model_pred': ID2LAB[pr],
                                  'conf': round(float(cf), 4),
                                  'pn_direction': (y, pr) in ((0, 1), (1, 0))})
        print(f'[3] 테스트 슬라이스 고확신 불일치 {n_ts}행 (배포 seed45 기준)')

    os.makedirs(os.path.join(DATASET_DIR, 'eval', 'review'), exist_ok=True)
    qpath = os.path.join(DATASET_DIR, 'eval', 'review', 'label_audit_queue_260708.jsonl')
    with open(qpath, 'w', encoding='utf-8') as f:
        for q in queue:
            f.write(json.dumps(q, ensure_ascii=False) + '\n')
    summary = {'n_train': len(rows), 'surface_conflict_groups': n_conf_groups,
               'queue_total': len(queue), 'oof': oof_stats,
               'queue_by_kind': dict(Counter(q['kind'] for q in queue))}
    spath = os.path.join(DATASET_DIR, 'result', 'label_audit_260708.json')
    json.dump(summary, open(spath, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n큐 {len(queue)}행 → {os.path.relpath(qpath, DATASET_DIR)}')
    print(f'요약 → {os.path.relpath(spath, DATASET_DIR)}')


if __name__ == '__main__':
    main()
