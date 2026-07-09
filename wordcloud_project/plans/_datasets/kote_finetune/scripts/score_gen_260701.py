# -*- coding: utf-8 -*-
"""일반화 검증 — 2023 배치 held-out에서 규칙(before) vs 최종모델 채점.

gen_holdout_260701(2023, gold 미사용)의 사람 라벨 대비 정확도·긍↔부·클래스별 재현.
"""
import json, os, sys
import numpy as np
HERE=os.path.dirname(__file__); PROOT=os.path.abspath(os.path.join(HERE,'..','..','..','..')); DD=os.path.abspath(os.path.join(HERE,'..'))
sys.path.insert(0,PROOT)
from src.config.settings import MODEL_PATH
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding='utf-8')
    except Exception: pass
LAB2ID={'positive':0,'negative':1,'neutral':2}; ID2LAB={v:k for k,v in LAB2ID.items()}

test=[]
for l in open(os.path.join(DD,'eval','gen_holdout_260701.jsonl'),encoding='utf-8'):
    r=json.loads(l); hd=r.get('human_decision')
    if hd in LAB2ID and (r.get('text') or '').strip(): test.append((r['text'].strip(), LAB2ID[hd]))
y=[c for _,c in test]; texts=[t for t,_ in test]

def metrics(tag, pred):
    yt,p=np.array(y),np.array(pred); acc=(yt==p).mean()
    pn=int(((yt==1)&(p==0)).sum()); npp=int(((yt==0)&(p==1)).sum())
    rec={nm:(round(float(((p==c)&(yt==c)).sum()/max((yt==c).sum(),1)),3)) for c,nm in ((0,'긍'),(1,'부'),(2,'중'))}
    print(f"  [{tag}] 정확도 {100*acc:.1f}% · ★긍↔부 {pn+npp}(긍→부 {npp}·부→긍 {pn}) · 재현 긍{rec['긍']}·부{rec['부']}·중{rec['중']}")

# 규칙 before
from src.modules.emotion_analysis import analyze_emotion_batch
from src.services.perspective_service import _sentence_sentiment_override_explain as ov
pred_rule=[]
for i in range(0,len(texts),64):
    ch=texts[i:i+64]; res=analyze_emotion_batch(ch)
    for t,r in zip(ch,res):
        br=(r.get('analysis') or {}).get('base_result') or {}; sc=br.get('scores') or br
        pos=float(sc.get('positive',0)); neg=float(sc.get('negative',0)); neu=float(sc.get('neutral',0))
        s,_=ov(pos,neg,t,True,1,neutral=neu); pred_rule.append(0 if s>1e-6 else (1 if s<-1e-6 else 2))

# 최종 모델
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
md=os.path.join(DD,'model_out_final')
tok=AutoTokenizer.from_pretrained(md,local_files_only=True)
m=AutoModelForSequenceClassification.from_pretrained(md,local_files_only=True).eval().cuda()
pred_m=[]
with torch.no_grad():
    for i in range(0,len(texts),64):
        e=tok(texts[i:i+64],truncation=True,padding=True,max_length=72,return_tensors='pt').to('cuda')
        pred_m+=m(**e).logits.argmax(-1).cpu().tolist()

from collections import Counter
print(f"일반화셋(2023) n={len(test)} · gold분포 {dict(Counter(ID2LAB[c] for c in y))}")
metrics('규칙(before)', pred_rule)
metrics('최종모델', pred_m)
# 예시 문장 최종모델 판정
ex='개인의 목표보다는 조직의 목표를 중요시함'
with torch.no_grad():
    e=tok([ex],truncation=True,padding=True,max_length=72,return_tensors='pt').to('cuda')
    print(f"\n예시 「{ex}」 최종모델={ID2LAB[m(**e).logits.argmax(-1).item()]}")
