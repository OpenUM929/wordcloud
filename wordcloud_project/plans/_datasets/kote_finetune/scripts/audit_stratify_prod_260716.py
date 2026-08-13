# -*- coding: utf-8 -*-
"""실배치 감사 표준 절차 — 단계 2: 중복제거 + 티어링 + 층화표본.

입력 CSV를 고유 문장으로 접고(freq 보존) 각 고유문장에 티어를 부여한 뒤,
티어별 고정시드(20260716) 무작위 표본을 뽑아 판독 파일로 낸다. CLEAN 표본은
스크린이 놓친 오류(누락) 확인용. 티어 모집단(고유수·인스턴스수)도 기록(가중 추정용).
표준 절차 정본: ../AUDIT_STANDARD.md §2 단계2.

사용:  python audit_stratify_prod_260716.py [입력csv]
"""
import io, os, sys, json, random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.join('D:', os.sep, 'dev', 'wordcloud', 'wordcloud_project')
sys.path.insert(0, ROOT)
from src.services import perspective_service as P
IN = sys.argv[1] if len(sys.argv) > 1 else os.path.join('D:', os.sep, 'dev', 'wordcloud', 'data', '25.csv')
OUT = os.path.join(ROOT, 'plans', '_datasets', 'kote_finetune', 'eval', 'review', 'audit_work_260716')
os.makedirs(OUT, exist_ok=True)
SEED = 20260716

def argmax3(pos, neg, neu):
    m = max(pos, neg, neu); return 'p' if m==pos else ('n' if m==neg else 'u')

# 1) dedup
uniq = {}
with open(IN, encoding='utf-8') as f:
    for line in f:
        line=line.strip()
        if not line: continue
        r=json.loads(line)
        if '#' in r: continue
        x=r.get('x'); y=r.get('y'); s=r.get('s')
        if not x or y not in ('p','n','u') or not s or len(s)<3: continue
        if x not in uniq:
            uniq[x]={'x':x,'y':y,'s':[float(s[0]),float(s[1]),float(s[2])],
                     'e':r.get('e'),'freq':0}
        uniq[x]['freq']+=1
print('고유 문장 %d개 (인스턴스 %d)' % (len(uniq), sum(u['freq'] for u in uniq.values())))

# 2) tier
def tier(u):
    pos,neg,neu=u['s']; my=u['y']; x=u['x']
    ky=argmax3(pos,neg,neu)
    try:
        sc,_=P._sentence_sentiment_override_explain(pos,neg,x,True,1,neutral=neu)
        ry='p' if sc>1e-6 else ('n' if sc<-1e-6 else 'u')
    except: ry='u'
    if {my,ry}=={'p','n'} and {my,ky}=={'p','n'}:
        return 'T0_A' if my=='p' else 'T0_C'   # 삼각 긍↔부 충돌
    if {my,ry}=={'p','n'} or {my,ky}=={'p','n'}:
        return 'T0_single'
    if ('u' in (my,ry)) and my!=ry: return 'T1_pol_neu'
    if abs(pos-neg)<0.05: return 'T2_margin'
    etop=u['e'][0][0] if u['e'] and isinstance(u['e'][0],list) else None
    if my in ('p','n') and (etop=='없음' or len(x.strip())<=4): return 'T3_none_frag'
    return 'CLEAN'

from collections import defaultdict
by=defaultdict(list)
for u in uniq.values():
    by[tier(u)].append(u)
print('\n티어별 (고유수 / 인스턴스수):')
inst_tot=sum(u['freq'] for u in uniq.values())
tierpop={}
for t in sorted(by):
    uc=len(by[t]); ic=sum(u['freq'] for u in by[t])
    tierpop[t]={'uniq':uc,'inst':ic}
    print('  %-12s %7d / %8d (%.1f%% inst)'%(t,uc,ic,100*ic/inst_tot))
json.dump(tierpop, open(os.path.join(OUT,'tier_pop.json'),'w',encoding='utf-8'), ensure_ascii=False, indent=1)

# 3) stratified samples (표본 계획 정본 — AUDIT_STANDARD.md §5)
plan={'CLEAN':60,'T0_A':40,'T0_C':50,'T0_single':30,'T1_pol_neu':45,'T2_margin':35,'T3_none_frag':35}
rng=random.Random(SEED)
samples={}
for t,n in plan.items():
    pool=by.get(t,[])
    rng.shuffle(pool)
    samples[t]=pool[:min(n,len(pool))]
json.dump(samples, open(os.path.join(OUT,'samples.json'),'w',encoding='utf-8'), ensure_ascii=False)
print('\n표본 저장: samples.json (seed=%d)'%SEED)
for t in plan: print('  %-12s 표본 %d'%(t,len(samples.get(t,[]))))
