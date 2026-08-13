# -*- coding: utf-8 -*-
"""실배치 감사 표준 절차 — 단계 1: 전수 삼각 스크리닝.

배포 모델 산출 결과(예: data/25.csv)의 모든 문장을 3방식으로 판정해
어긋나는 의심건을 티어별로 추출한다. 표준 절차 정본: ../AUDIT_STANDARD.md §2 단계1.
  model_y = 패킷 y (배포 모델 + R1)
  rule_y  = 규칙엔진 _sentence_sentiment_override_explain (폴백 경로)
  kote_y  = KoTE 원점수 s argmax
티어: T0_pn(긍↔부 정면충돌 ★) · T1_pol_neu · T2_margin(|pos-neg|<0.05) · T3_none_frag

사용:  python audit_screen_prod_260716.py [입력csv]
"""
import io, os, sys, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.join('D:', os.sep, 'dev', 'wordcloud', 'wordcloud_project')
sys.path.insert(0, ROOT)
from src.services import perspective_service as P  # noqa

IN = sys.argv[1] if len(sys.argv) > 1 else os.path.join('D:', os.sep, 'dev', 'wordcloud', 'data', '25.csv')
OUTDIR = os.path.join(ROOT, 'plans', '_datasets', 'kote_finetune', 'eval', 'review', 'audit_work_260716', 'suspects')
os.makedirs(OUTDIR, exist_ok=True)

def argmax3(pos, neg, neu):
    m = max(pos, neg, neu)
    if m == pos: return 'p'
    if m == neg: return 'n'
    return 'u'

def rule_label(pos, neg, neu, x):
    try:
        score, tag = P._sentence_sentiment_override_explain(pos, neg, x, True, 1, neutral=neu)
    except Exception as e:
        return 'u', 'ERR:%s' % type(e).__name__
    y = 'p' if score > 1e-6 else ('n' if score < -1e-6 else 'u')
    return y, tag

tiers = ['T0_pn', 'T1_pol_neu', 'T2_margin', 'T3_none_frag']
fh = {t: open(os.path.join(OUTDIR, t + '.jsonl'), 'w', encoding='utf-8') for t in tiers}
cnt = {t: 0 for t in tiers}
sub = {}
def bump(k): sub[k] = sub.get(k, 0) + 1

total = 0
dist_model = {'p':0,'n':0,'u':0}
t0 = time.time()
with open(IN, encoding='utf-8') as f:
    for i, line in enumerate(f):
        line = line.strip()
        if not line: continue
        try: r = json.loads(line)
        except: continue
        if '#' in r:  # 헤더
            continue
        x = r.get('x') or ''
        my = r.get('y')
        s = r.get('s') or [0,0,0]
        if my not in ('p','n','u') or len(s) < 3:
            continue
        total += 1
        dist_model[my] += 1
        pos, neg, neu = float(s[0]), float(s[1]), float(s[2])
        ky = argmax3(pos, neg, neu)
        ry, rtag = rule_label(pos, neg, neu, x)
        e = r.get('e') or []
        etop = e[0][0] if e and isinstance(e[0], list) else None
        rec = {'x': x, 'my': my, 'ry': ry, 'ky': ky, 's': [round(pos,3),round(neg,3),round(neu,3)],
               'rtag': rtag, 'etop': etop}
        placed = False
        pn_pairs = []
        if {my, ry} == {'p','n'}: pn_pairs.append('model_vs_rule')
        if {my, ky} == {'p','n'}: pn_pairs.append('model_vs_kote')
        if pn_pairs:
            rec['pn'] = pn_pairs
            fh['T0_pn'].write(json.dumps(rec, ensure_ascii=False)+'\n'); cnt['T0_pn']+=1
            for k in pn_pairs: bump('T0:'+k)
            bump('T0:%s->%s(rule)' % (my, ry) if 'model_vs_rule' in pn_pairs else 'T0:%s->%s(kote)'%(my,ky))
            placed = True
        elif ('u' in (my, ry)) and my != ry and (my in ('p','n') or ry in ('p','n')):
            fh['T1_pol_neu'].write(json.dumps(rec, ensure_ascii=False)+'\n'); cnt['T1_pol_neu']+=1
            bump('T1:m%s_r%s' % (my, ry)); placed = True
        if not placed and abs(pos-neg) < 0.05:
            fh['T2_margin'].write(json.dumps(rec, ensure_ascii=False)+'\n'); cnt['T2_margin']+=1
            bump('T2:model_%s' % my); placed = True
        if not placed and my in ('p','n') and (etop == '없음' or len(x.strip()) <= 4):
            fh['T3_none_frag'].write(json.dumps(rec, ensure_ascii=False)+'\n'); cnt['T3_none_frag']+=1
            bump('T3:%s_%s' % (my, 'none' if etop=='없음' else 'short')); placed = True
        if total % 100000 == 0:
            print('  ...%d건 처리 (%.0fs)' % (total, time.time()-t0), flush=True)

for t in fh.values(): t.close()
print('\n=== 전수 스크리닝 완료: 총 %d건 (%.0fs) ===' % (total, time.time()-t0))
print('모델 라벨 분포: 긍 %d(%.1f%%) 부 %d(%.1f%%) 중 %d(%.1f%%)' % (
    dist_model['p'],100*dist_model['p']/total, dist_model['n'],100*dist_model['n']/total,
    dist_model['u'],100*dist_model['u']/total))
print('\n의심건 티어별:')
for t in tiers:
    print('  %-14s %7d (%.2f%%)' % (t, cnt[t], 100*cnt[t]/total))
tot_susp = sum(cnt.values())
print('  %-14s %7d (%.2f%%)' % ('의심 합계', tot_susp, 100*tot_susp/total))
print('\n세부:')
for k in sorted(sub, key=lambda k:-sub[k]):
    print('  %-28s %7d' % (k, sub[k]))
