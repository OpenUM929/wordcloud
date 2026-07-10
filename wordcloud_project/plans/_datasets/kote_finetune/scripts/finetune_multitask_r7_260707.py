# -*- coding: utf-8 -*-
"""능동학습 7차 — **화행 멀티태스크** 프로토타입(극성 + 화행 보조헤드).

배경(전략감사 2026-07-07, IMPROVEMENT_HISTORY): gold는 ~99% 일관(라벨/데이터 문제 아님).
남은 병목 = **화행 붕괴** — 같은 표지(노력/보완/필요/좋겠)가 요청형(→부)·실현형(→긍)·서술
(→field)·축원/안녕(→중)의 다른 화행을 인코딩하는데 3분류가 한 상자에 뭉갠다. 화행 purity 감사:
요청형 80% 부정(깨끗)이나 서술기타(1681행) 37%로 혼돈. → **가설: 화행을 보조과제로 주면
인코더가 요청↔실현↔서술을 분리 표현 → 극성(특히 c3_neu149 부recall) 개선.**

설계: 공유 인코더(KoTE base) + [극성헤드 3분류 + 화행헤드 6분류]. loss = CE(극성) + λ·CE(화행).
- λ=0 : 순수 극성(대조군, 커스텀 CLS풀링 아키텍처 자체효과 통제).
- λ>0 : 멀티태스크(처치군). λ=0 대비 개선분이 화행보조 순효과.
평가: 극성헤드만, 기존 4슬라이스·metrics 재사용. **model_out(c4 라인) 미덮어씀**(저장 안 함).
검증절차: λ=0/λ=0.3/0.5를 seed 2개씩 → 다중런 평균으로 노이즈 제압(test 손라벨 확대 前 프록시).
"""
import argparse
import os
import sys

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
import re
from finetune_sentiment import (TRAIN_FILES, TEST_SETS, load, metrics, rule_before,  # noqa: E402
                                LAB2ID, ID2LAB, DATASET_DIR, MODEL_PATH)
from transformers import AutoTokenizer, AutoModel, Trainer, TrainingArguments  # noqa: E402

# ── 화행 6분류 휴리스틱(보조라벨 — 노이즈 허용, 인코더 정규화 목적) ──
SA = {'개인안녕': 0, '약점부재': 1, '축원': 2, '실현형': 3, '요청형': 4, '서술기타': 5}


def speech_act(t):
    if any(w in t for w in ['건강', '체력', '휴식', '건강관리', '건강챙', '아프']) and \
       any(w in t for w in ['챙기', '유의', '관리', '보충', '계셔', '바랍', '필요', '좋겠', '하시']):
        return SA['개인안녕']
    if any(z in t for z in ['없', '엇ㅂ', '않을만큼', '않을 만큼', '필요치 않', '필요하지 않',
                            '떠오르지', '찾기가 어', '확인되지', '보이지 않', '보이지않']):
        return SA['약점부재']
    if any(w in t for w in ['되길', '되시길', '바랍니다', '화이팅', '승승장구', '되시기 바', '기원', '응원']):
        return SA['축원']
    # 요청형 우선(결여지적) — 실현어와 공존해도 요청표지 있으면 요청
    if re.search(r'(필요|보완|미흡|부족|자제|과도|좋겠|해주|해야|모르겠|개선|키워|줄이|바람직|아쉽|보완사항)', t):
        return SA['요청형']
    if re.search(r'(했|함|하심|하십|합니다|하고 있|해옴|해왔|보유|뛰어남|뛰어나|우수|훌륭|잘함|열의|충실|성실)', t):
        return SA['실현형']
    return SA['서술기타']


class MTModel(nn.Module):
    def __init__(self, lam):
        super().__init__()
        self.base = AutoModel.from_pretrained(MODEL_PATH, local_files_only=True)
        h = self.base.config.hidden_size
        self.drop = nn.Dropout(0.1)
        self.pol = nn.Linear(h, 3)
        self.sa = nn.Linear(h, 6)
        self.lam = lam
        self.ce = nn.CrossEntropyLoss()

    def forward(self, input_ids=None, attention_mask=None, labels=None, sa_labels=None):
        out = self.base(input_ids=input_ids, attention_mask=attention_mask)
        cls = self.drop(out.last_hidden_state[:, 0])
        pol_logits = self.pol(cls)
        loss = None
        if labels is not None:
            loss = self.ce(pol_logits, labels)
            if self.lam > 0 and sa_labels is not None:
                loss = loss + self.lam * self.ce(self.sa(cls), sa_labels)
        return {'loss': loss, 'logits': pol_logits}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--lam', type=float, default=0.3, help='화행 보조 loss 가중(0=대조군)')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--bs', type=int, default=16)
    ap.add_argument('--lr', type=float, default=2e-5)
    ap.add_argument('--field-token', choices=['on', 'off'], default='on')
    ap.add_argument('--tag', default='')
    args = ap.parse_args()

    def apply_field(text, field):
        return f'{field} 평가: {text}' if (args.field_token == 'on' and field) else text

    tok = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)

    train = []
    for f in TRAIN_FILES:
        train += load(f)
    tests = {name: load(fn) for name, fn in TEST_SETS.items()}
    all_test = {t for ts in tests.values() for t, _, _ in ts}
    train = [(t, y, fld) for t, y, fld in train if t not in all_test]
    from collections import Counter
    print(f'train {len(train)} · λ={args.lam} · seed={args.seed} · field-token={args.field_token}')
    print('  화행 분포:', {k: v for k, v in sorted(Counter(speech_act(t) for t, _, _ in train).items())})

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
                    'labels': torch.tensor(y), 'sa_labels': torch.tensor(speech_act(t))}

    def collate(b):
        return {k: torch.stack([x[k] for x in b]) for k in b[0]}

    model = MTModel(args.lam)
    targs = TrainingArguments(
        output_dir=os.path.join(DATASET_DIR, 'model_mt_tmp'), num_train_epochs=args.epochs,
        per_device_train_batch_size=args.bs, learning_rate=args.lr,
        fp16=torch.cuda.is_available(), logging_steps=40, save_strategy='no', report_to=[],
        seed=args.seed, remove_unused_columns=False)
    trainer = Trainer(model=model, args=targs, train_dataset=DS(train), data_collator=collate)
    trainer.train()

    model.eval()
    dev = model.base.device

    def predict(texts):
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                          return_tensors='pt').to(dev)
                out += model(input_ids=enc['input_ids'],
                             attention_mask=enc['attention_mask'])['logits'].argmax(-1).cpu().tolist()
        return out

    print(f'\n=== 화행 멀티태스크 λ={args.lam} seed={args.seed} (극성헤드 평가) ===')
    rep = {}
    for name, ts in tests.items():
        texts = [t for t, _, _ in ts]; y = [yy for _, yy, _ in ts]; fields = [fld for _, _, fld in ts]
        mt = [apply_field(t, f) for t, f in zip(texts, fields)]
        r = metrics(f'{name} λ{args.lam}s{args.seed}', y, predict(mt))
        rep[name] = r
    # 간단 요약행
    print('\nSUMMARY', args.tag or f'lam{args.lam}_s{args.seed}',
          {n: (r['acc'], r['pos_neg_err'], r['recall']['neg']) for n, r in rep.items()})


if __name__ == '__main__':
    main()
