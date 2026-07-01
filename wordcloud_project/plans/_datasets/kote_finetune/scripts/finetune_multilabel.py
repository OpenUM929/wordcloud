# -*- coding: utf-8 -*-
"""신규 그룹 멀티라벨 헤드 — KoTE 44감정 + HR신규 3그룹(G1/G2/G4) 통합 모델.

ROADMAP 택소노미(KoTE44 + ≤3) 구현. 타깃:
  · 44감정 = 베이스 KoTE 자기예측(sigmoid>0.3) 증류(soft 지식 보존)
  · G1 약점부재 / G2 개선요청 / G4 자기개발 = 선별기(is_no_weakness/has_improvement_request/is_growth)
멀티라벨(47) BCE. 베이스 KoTE 인코더 → 47 헤드.

⚠️ 정직: 신규 3그룹은 결정적 선별기의 증류라 '새 지식'은 아니다. 목적은 감정+HR그룹을
   단일 모델로 통합(추론 1회). 감정 극성 정확화는 별도 3분류 파인튜닝(finetune_sentiment)이 담당.
"""
import argparse
import json
import os
import random
import sys

import numpy as np

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, HERE)
from src.config.settings import MODEL_PATH, EMOTION_NAMES  # noqa: E402
from src.services.perspective_service import (  # noqa: E402
    is_no_weakness_declaration, has_improvement_request)
from g4_extract import is_growth  # noqa: E402

NEW_GROUPS = ['hr_no_weakness_declaration', 'hr_improvement_request', 'hr_growth_orientation']
ALL_LABELS = list(EMOTION_NAMES) + NEW_GROUPS
N_EMO = len(EMOTION_NAMES)
N_ALL = len(ALL_LABELS)


def sample_texts(n):
    path = os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl')
    rows = []
    for line in open(path, encoding='utf-8'):
        r = json.loads(line)
        if r.get('is_clause'):
            continue
        t = (r.get('text') or '').strip()
        s = r.get('sentiment')
        if t:
            rows.append((t, s))
    rng = random.Random(42)
    rng.shuffle(rows)
    return rows[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=12000)
    ap.add_argument('--epochs', type=int, default=3)
    ap.add_argument('--bs', type=int, default=32)
    ap.add_argument('--thr', type=float, default=0.3)
    ap.add_argument('--out', default=os.path.join(DATASET_DIR, 'model_out_multilabel'))
    args = ap.parse_args()

    import torch
    from torch.utils.data import Dataset
    from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                              Trainer, TrainingArguments)

    texts = sample_texts(args.n)
    print(f'표본 {len(texts)}건 · 라벨 {N_ALL}(감정 {N_EMO} + 신규 {len(NEW_GROUPS)})')
    tok = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)
    base = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH, local_files_only=True)
    dev = 'cuda' if torch.cuda.is_available() else 'cpu'
    base.to(dev).eval()

    # 44감정 타깃 = 베이스 KoTE sigmoid>thr / 신규 3그룹 = 선별기
    print('[1/3] 타깃 생성(KoTE 추론 + 선별기)...')
    Y = np.zeros((len(texts), N_ALL), dtype=np.float32)
    only = [t for t, _ in texts]
    with torch.no_grad():
        for i in range(0, len(only), 128):
            chunk = only[i:i + 128]
            enc = tok(chunk, truncation=True, padding=True, max_length=64, return_tensors='pt').to(dev)
            probs = torch.sigmoid(base(**enc).logits).cpu().numpy()
            Y[i:i + len(chunk), :N_EMO] = (probs > args.thr).astype(np.float32)
    for j, (t, _) in enumerate(texts):
        Y[j, N_EMO + 0] = 1.0 if is_no_weakness_declaration(t) else 0.0
        Y[j, N_EMO + 1] = 1.0 if has_improvement_request(t) else 0.0
        Y[j, N_EMO + 2] = 1.0 if is_growth(t, None) or is_growth(t, 'positive') else 0.0
    print('  신규그룹 양성:', {NEW_GROUPS[k]: int(Y[:, N_EMO + k].sum()) for k in range(3)})

    n_test = max(500, len(texts) // 6)
    tr_idx, te_idx = list(range(len(texts)))[n_test:], list(range(len(texts)))[:n_test]
    # 희소 신규그룹(G2/G4) 양성 오버샘플링 — 불균형으로 F1 0 방지.
    rare = [i for i in tr_idx if Y[i, N_EMO + 1] or Y[i, N_EMO + 2]]
    tr_idx = tr_idx + rare * 9
    random.Random(1).shuffle(tr_idx)
    print(f'  train {len(tr_idx)}(희소 오버샘플 +{len(rare)*9}) · test {len(te_idx)}')

    class DS(Dataset):
        def __init__(self, idx):
            self.idx = idx
        def __len__(self):
            return len(self.idx)
        def __getitem__(self, k):
            i = self.idx[k]
            enc = tok(texts[i][0], truncation=True, padding='max_length', max_length=64, return_tensors='pt')
            return {'input_ids': enc['input_ids'][0], 'attention_mask': enc['attention_mask'][0],
                    'labels': torch.tensor(Y[i])}

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_PATH, num_labels=N_ALL, ignore_mismatched_sizes=True, local_files_only=True,
        problem_type='multi_label_classification')

    targs = TrainingArguments(output_dir=args.out, num_train_epochs=args.epochs,
                              per_device_train_batch_size=args.bs, learning_rate=2e-5,
                              fp16=torch.cuda.is_available(), logging_steps=50, save_strategy='no',
                              report_to=[], seed=42)
    print('[2/3] 멀티라벨 파인튜닝...')
    Trainer(model=model, args=targs, train_dataset=DS(tr_idx)).train()

    # 평가: 신규 3그룹 F1 + 44감정 retention(베이스 대비 일치)
    print('[3/3] 평가(test)...')
    model.eval()
    P = np.zeros((len(te_idx), N_ALL), dtype=np.float32)
    with torch.no_grad():
        for a in range(0, len(te_idx), 128):
            chunk = [texts[te_idx[b]][0] for b in range(a, min(a + 128, len(te_idx)))]
            enc = tok(chunk, truncation=True, padding=True, max_length=64, return_tensors='pt').to(model.device)
            P[a:a + len(chunk)] = (torch.sigmoid(model(**enc).logits).cpu().numpy() > 0.3)
    Yte = Y[te_idx]

    def f1(col):
        tp = float(((P[:, col] == 1) & (Yte[:, col] == 1)).sum())
        fp = float(((P[:, col] == 1) & (Yte[:, col] == 0)).sum())
        fn = float(((P[:, col] == 0) & (Yte[:, col] == 1)).sum())
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        return (2 * pr * rc / (pr + rc)) if pr + rc else 0.0, pr, rc

    print('\n=== 신규 그룹 예측 성능(test) ===')
    rep = {'n': len(texts), 'labels': N_ALL, 'new_groups': {}}
    for k in range(3):
        f, pr, rc = f1(N_EMO + k)
        print(f'  {NEW_GROUPS[k]:28s} F1 {f:.3f} (P {pr:.3f}·R {rc:.3f})')
        rep['new_groups'][NEW_GROUPS[k]] = {'f1': round(f, 3), 'p': round(pr, 3), 'r': round(rc, 3)}
    emo_f1 = np.mean([f1(c)[0] for c in range(N_EMO)])
    print(f'  44감정 macro-F1 retention(베이스 타깃 대비): {emo_f1:.3f}')
    rep['emotion_macro_f1'] = round(float(emo_f1), 3)

    json.dump(rep, open(os.path.join(DATASET_DIR, 'result', 'finetune_multilabel_260624.json'),
                        'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    model.save_pretrained(args.out); tok.save_pretrained(args.out)
    json.dump(ALL_LABELS, open(os.path.join(args.out, 'labels.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    print(f'\n모델 → {args.out} · 리포트 → result/finetune_multilabel_260624.json')


if __name__ == '__main__':
    main()
