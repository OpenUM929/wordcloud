# -*- coding: utf-8 -*-
"""1·2·3차 정확도 추이 측정 — 내 직접 판정(gold) 대비 버전별 override 정확도.

버전 재현(monkeypatch):
  V0_KoTE : 규칙 없음 = KoTE argmax(pos/neg/neu)
  Vbase   : override(positive_rescue 등) 단, 1차 가드 OFF (pmdn=False, husn=plain, 결함/필요 OFF)
  V1(1차) : + positive-negation 가드(pmdn) + euphemistic negation(husn)   [결함/필요 OFF]
  V2(2차) : + 소홀 결함가드 + has_constructive_need                       [현재 코드]
  V3(3차) : V2와 동일(안전 추가 없음 — substring 한계, 핵심가치 보호)
"""
import json, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))
import src.services.perspective_service as ps

# 입력: 손판정 벤치마크(eval/accuracy_benchmark_<date>.jsonl). 최신 파일 자동 선택.
import glob
_EVAL = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'eval'))
_bench = sorted(glob.glob(os.path.join(_EVAL, 'accuracy_benchmark_*.jsonl')))[-1]
_ROWS = [json.loads(l) for l in open(_bench, encoding='utf-8') if l.strip()]
SAMPLE = [{'text': r['text'], 'kote': r['kote'], 'stratum': r.get('stratum', '')} for r in _ROWS]
GOLD = {i: r['gold'] for i, r in enumerate(_ROWS)}   # 손판정(p/n/u), 긍↔부 경계 집중

LAB = {'positive':'p','negative':'n','neutral':'u'}
_orig = {k: getattr(ps, k) for k in
         ('positive_marker_directly_negated','has_unnegated_strong_negative',
          'has_unnegated_deficiency','has_constructive_need')}


def restore():
    for k,v in _orig.items(): setattr(ps,k,v)


def kote_argmax(p,n,u):
    m=max(p,n,u)
    return 'p' if m==p else ('n' if m==n else 'u')


def predict(p,n,u,text):
    sc,_=ps._sentence_sentiment_override_explain(p,n,text,True,1,neutral=u)
    return 'p' if sc>0 else ('n' if sc<0 else 'u')


def set_version(v):
    restore()
    if v=='Vbase':
        ps.positive_marker_directly_negated=lambda s:False
        ps.has_unnegated_strong_negative=lambda s:any(ph in s for ph in ps.STRONG_NEGATIVE_PHRASES)
        ps.has_unnegated_deficiency=lambda s:False
        ps.has_constructive_need=lambda s:False
    elif v=='V1':
        ps.has_unnegated_deficiency=lambda s:False
        ps.has_constructive_need=lambda s:False
    # V2 = 현재(restore 그대로), V3 = V2


def score(version):
    if version!='V0': set_version(version if version!='V3' else 'V2')
    exact=polerr=0; errs=[]
    for i,row in enumerate(SAMPLE):
        g=GOLD[i]; p,n,u=row['kote']
        pred = kote_argmax(p,n,u) if version=='V0' else predict(p,n,u,row['text'])
        if pred==g: exact+=1
        if {pred,g}=={'p','n'}:
            polerr+=1; errs.append((g,pred,row['text'][:50]))
    restore()
    return exact, polerr, errs


N=len(SAMPLE)
gp=sum(1 for v in GOLD.values() if v=='p'); gn=sum(1 for v in GOLD.values() if v=='n'); gu=sum(1 for v in GOLD.values() if v=='u')
print('표본 %d개 (gold: 긍%d 부%d 중%d)\n' % (N,gp,gn,gu))
print('%-22s %10s %10s' % ('버전','정확일치','긍↔부오류'))
print('-'*46)
labels=[('V0','V0_KoTE(규칙없음)'),('Vbase','override(가드前)'),('V1','1차(긍부negation가드)'),('V2','2차(소홀+필요가드)'),('V3','3차(안전추가없음)')]
last_errs=None
for v,name in labels:
    ex,pe,errs=score(v)
    print('%-22s %4d/%d (%2d%%) %8d' % (name,ex,N,100*ex//N,pe))
    if v=='V2': last_errs=errs
print()
print('=== V2(현재) 잔여 긍↔부 오류 ===')
for g,pred,t in (last_errs or []): print(f'  gold={g} pred={pred} | {t}')
