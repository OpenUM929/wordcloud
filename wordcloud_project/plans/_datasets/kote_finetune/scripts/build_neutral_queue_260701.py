# -*- coding: utf-8 -*-
"""중립 화행 gold 확충 큐 — 모델 최약 클래스(중립 재현 ~0.71) 보강. 사람 판정용.

필드·silver·양 다 중립 인식을 못 뚫음(2026-07-01 측정). 중립은 극성이 아니라 **화행**이라 사람 gold 필요.
중립 가능성 높은 화행을 코퍼스에서 발굴하되 **규칙이 극성으로 오판한 것 우선**(=모델이 못 배운 중립):
  wellwish     기원/안녕(건강·행복·계셔) — 비평가적
  noweak_abs   약점부재(보완점 없음·특이사항 없음)
  dev_request  발전지향 요청(하면 좋겠·바람직) — 비난 아닌 제언
  fragment     무종결 단편(맨 명사구)
gold/기존큐 텍스트 중복제외. ai_reference=HL힌트, human_decision=null. 0624_05 UI 판정 → promote → 재학습.
"""
import argparse, json, os, random, re, sys
HERE=os.path.dirname(__file__); DD=os.path.abspath(os.path.join(HERE,'..'))
EVAL=os.path.join(DD,'eval'); OUT=os.path.join(EVAL,'neutral_gold_review_260701.jsonl')
sys.path.insert(0,HERE); import human_label as HL
for s in (sys.stdout,sys.stderr):
    try: s.reconfigure(encoding='utf-8')
    except Exception: pass

RE_WELLWISH=re.compile(r'건강|행복|건승|쾌차|무탈|평안|계셔|늘 함께|오래.{0,4}함께|바랍니다$|기원')
RE_NOWEAK=re.compile(r'(보완|단점|개선점|개선 ?사항|특이 ?사항|문제점|미흡한 ?점|지적|보완 ?필요점|결점).{0,7}(없|않|아니|딱히|못)')
RE_DEVREQ=re.compile(r'하면 좋|하면 더|바람직|권장|하시면|였으면|었으면|면 더 좋|기를 바|해보|해 보')

def field_of(rid): return '장점' if '_1-' in rid else ('단점' if '_0-' in rid else '?')
def norm(t): return re.sub(r'\s+',' ',(t or '').strip())

def categorize(t):
    if RE_NOWEAK.search(t): return 'noweak_abs'
    if RE_WELLWISH.search(t): return 'wellwish'
    if RE_DEVREQ.search(t): return 'dev_request'
    if not HL._END.search(t) and len(t)<=22: return 'fragment'
    return None

def exclude_texts():
    ex=set()
    for r in (json.loads(l) for l in open(os.path.join(DD,'emotion','emotion.jsonl'),encoding='utf-8') if l.strip()):
        ex.add(norm(r.get('text','')))
    for fn in os.listdir(EVAL):
        if fn.endswith('.jsonl'):
            for line in open(os.path.join(EVAL,fn),encoding='utf-8'):
                line=line.strip()
                if line:
                    try: ex.add(norm(json.loads(line).get('text','')))
                    except Exception: pass
    return ex

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--caps', default='noweak_abs:120,wellwish:60,dev_request:140,fragment:200')
    ap.add_argument('--seed', type=int, default=2607011)
    args=ap.parse_args()
    caps=dict((k,int(v)) for k,v in (x.split(':') for x in args.caps.split(',')))
    ex=exclude_texts()
    buckets={k:{} for k in caps}
    for line in open(os.path.join(DD,'emotion','weak_export_260624.jsonl'),encoding='utf-8'):
        r=json.loads(line)
        if str(r.get('is_clause'))=='True': continue
        t=r.get('text') or ''; nt=norm(t)
        if not nt or nt in ex: continue
        cat=categorize(t)
        if not cat or cat not in buckets or nt in buckets[cat]: continue
        buckets[cat][nt]={'rec_id':r.get('id'),'text':t,'field':field_of(r.get('id','')),
            'cur_rule_label':r.get('sentiment'),
            'ai_reference':json.dumps({'polarity':HL.label(t)[0],'confidence':HL.label(t)[1],'reason':HL.reason(t)},ensure_ascii=False),
            'human_decision':None,'note':f"{cat} 규칙={r.get('sentiment')}"}
    rnd=random.Random(args.seed); picked=[]
    from collections import Counter
    print('=== 중립 화행 gold 확충 큐 ===')
    for cat in caps:
        rows=list(buckets[cat].values())
        # 규칙이 극성으로 본 것 우선(=모델 오판=고가치), 부족분은 나머지로 채움
        polar=[r for r in rows if r['cur_rule_label']!='neutral']; neu=[r for r in rows if r['cur_rule_label']=='neutral']
        rnd.shuffle(polar); rnd.shuffle(neu)
        take=(polar+neu)[:caps[cat]]
        picked.extend(take)
        dist=Counter(r['cur_rule_label'] for r in rows)
        print(f"  {cat:12s}: 풀 {len(rows):5d} → 채택 {len(take):3d}  규칙분포={dict(dist)}")
    rnd.shuffle(picked)
    with open(OUT,'w',encoding='utf-8') as f:
        for r in picked: f.write(json.dumps(r,ensure_ascii=False)+'\n')
    print(f"\n총 {len(picked)}행 → {os.path.basename(OUT)} (0624_05 UI 판정)")
    print("규칙이 극성으로 본 화행 우선 채택 = 모델이 못 배운 중립 후보.")

if __name__=='__main__': main()
