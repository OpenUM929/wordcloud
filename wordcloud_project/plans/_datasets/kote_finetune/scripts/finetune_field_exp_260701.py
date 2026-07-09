# -*- coding: utf-8 -*-
"""필드 프리픽스 효과 측정 — 일관 gold(정식 스트림) + 하드 held-out.

정식 스트림 emotion.jsonl(재정렬·하드샘플·감사정정 반영)에서 학습.
분할: test_base=baseline(대표) · test_hard=hard_failure 20%(다툼구역) held-out · train=나머지.
비교: 필드 프리픽스 無 vs 有([단점] 전문성 향상 모색). 지표: 정확도·긍↔부·★중립재현.
사용자 승인 하 GPU 학습. plans 배포제외.
"""
import json, os, random, sys
import numpy as np
HERE=os.path.dirname(__file__); PROOT=os.path.abspath(os.path.join(HERE,'..','..','..','..'))
DD=os.path.abspath(os.path.join(HERE,'..')); sys.path.insert(0,PROOT)
from src.config.settings import MODEL_PATH
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding='utf-8')
    except Exception: pass
LAB2ID={'positive':0,'negative':1,'neutral':2}; ID2LAB={v:k for k,v in LAB2ID.items()}

def load_split(seed=260701, hard_heldout=0.2):
    rows=[json.loads(l) for l in open(os.path.join(DD,'emotion','emotion.jsonl'),encoding='utf-8') if l.strip()]
    rows=[r for r in rows if r.get('sentiment_gold') in LAB2ID and (r.get('text') or '').strip()]
    base=[r for r in rows if r.get('source_file')=='baseline_eval_260624.jsonl']
    hard=[r for r in rows if r.get('source_file')=='hard_failure_review_260630.jsonl']
    rng=random.Random(seed); rng.shuffle(hard)
    k=int(len(hard)*hard_heldout)
    test_hard=hard[:k]; train_hard=hard[k:]
    test_ids={r['id'] for r in base}|{r['id'] for r in test_hard}
    test_txt={(r.get('text') or '').strip() for r in base}|{(r.get('text') or '').strip() for r in test_hard}
    train=[r for r in rows if r['id'] not in test_ids and (r.get('text') or '').strip() not in test_txt]
    return train, base, test_hard

def texts(rows, fp):
    def mk(r):
        t=(r['text'] or '').strip()
        return (f"[{r.get('field') or '?'}] {t}") if fp else t
    return [(mk(r), LAB2ID[r['sentiment_gold']]) for r in rows]

def metrics(tag, y, p):
    y,p=np.array(y),np.array(p); acc=(y==p).mean()
    pn=int(((y==1)&(p==0)).sum()); npp=int(((y==0)&(p==1)).sum())
    rec={nm:(round(float(((p==c)&(y==c)).sum()/max((y==c).sum(),1)),3)) for c,nm in ((0,'긍'),(1,'부'),(2,'중'))}
    print(f"    [{tag}] 정확도 {100*acc:.1f}% · 긍↔부 {pn+npp} · 재현 긍{rec['긍']}·부{rec['부']}·★중{rec['중']}")
    return acc, pn+npp, rec['중']

def run(fp, train, base, hard):
    import torch
    from torch.utils.data import Dataset
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
    tr=texts(train,fp); tb=texts(base,fp); th=texts(hard,fp)
    tok=AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)
    class DS(Dataset):
        def __init__(s,rows): s.r=rows
        def __len__(s): return len(s.r)
        def __getitem__(s,i):
            t,y=s.r[i]; e=tok(t,truncation=True,padding='max_length',max_length=72,return_tensors='pt')
            return {'input_ids':e['input_ids'][0],'attention_mask':e['attention_mask'][0],'labels':torch.tensor(y)}
    m=AutoModelForSequenceClassification.from_pretrained(MODEL_PATH,num_labels=3,ignore_mismatched_sizes=True,
        local_files_only=True,problem_type='single_label_classification')
    args=TrainingArguments(output_dir=os.path.join(DD,'model_out_fieldexp'),num_train_epochs=4,
        per_device_train_batch_size=16,learning_rate=2e-5,fp16=torch.cuda.is_available(),
        logging_steps=50,save_strategy='no',report_to=[],seed=42)
    Trainer(model=m,args=args,train_dataset=DS(tr)).train()
    m.eval(); dev=m.device
    def pred(rows):
        out=[]
        with torch.no_grad():
            for i in range(0,len(rows),64):
                ch=[t for t,_ in rows[i:i+64]]
                e=tok(ch,truncation=True,padding=True,max_length=72,return_tensors='pt').to(dev)
                out+=m(**e).logits.argmax(-1).cpu().tolist()
        return out
    print(f"  === 필드프리픽스 {'ON' if fp else 'OFF'} (train {len(tr)}) ===")
    rb=metrics('baseline',[y for _,y in tb],pred(tb))
    rh=metrics('hard-heldout',[y for _,y in th],pred(th))
    return rb, rh

def main():
    train, base, hard = load_split()
    from collections import Counter
    print(f"train {len(train)} · test_base {len(base)} · test_hard {len(hard)}")
    print("train 분포:", {ID2LAB[k]:v for k,v in Counter(LAB2ID[r['sentiment_gold']] for r in train).items()})
    print()
    off=run(False, train, base, hard)
    print()
    on=run(True, train, base, hard)
    print("\n=== 요약 (정확도 / 중립재현) ===")
    print(f"  baseline    : 필드無 {100*off[0][0]:.1f}%/{off[0][2]}  →  필드有 {100*on[0][0]:.1f}%/{on[0][2]}")
    print(f"  hard-heldout: 필드無 {100*off[1][0]:.1f}%/{off[1][2]}  →  필드有 {100*on[1][0]:.1f}%/{on[1][2]}")

if __name__=='__main__': main()
