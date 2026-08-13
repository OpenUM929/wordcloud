import json,collections,math,os
R="D:/dev/wordcloud/wordcloud_project/plans/2026/07/27_03_completion-report/result"
z=1.959963985
def wilson(p,n):
    d=1+z*z/n; c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return (c-h)*100,(c+h)*100
def deff(rows,key):
    c=collections.Counter(key(r) for r in rows); n=len(rows)
    return sum(v*v for v in c.values())/n, len(c), n
k=lambda r:(r.get("field"),r.get("text"))
r400=[json.loads(l) for l in open(os.path.join(R,"blind_judged_400.jsonl"),encoding="utf-8") if l.strip()]
r1610=[json.loads(l) for l in open(os.path.join(R,"sample_round2s_1610_20260730.jsonl"),encoding="utf-8") if l.strip()]
d4,u4,n4=deff(r400,k); d16,u16,n16=deff(r1610,k)
print("400표본  deff=%.4f 고유 %d/%d  n_eff=%.1f" % (d4,u4,n4,n4/d4))
print("1610표본 deff=%.4f 고유 %d/%d  n_eff=%.1f" % (d16,u16,n16,n16/d16))
print()
print("[A] 400건 CI — 현행표기 vs deff 보정")
for lbl,p in [("현행 일치율 93.50%",0.9350),("현행 뒤바뀜 1.00%",0.0100),("종전 일치율 63.25%",0.6325),("종전 뒤바뀜 7.75%",0.0775)]:
    a=wilson(p,n4); b=wilson(p,n4/d4)
    print("  %-20s %.2f~%.2f  →  %.2f~%.2f  (반폭 %.2f→%.2f%%p)" % (lbl,a[0],a[1],b[0],b[1],(a[1]-a[0])/2,(b[1]-b[0])/2))
print()
print("[B] 1,610 표본 목표 달성 여부 (뒤바뀜 p=1.00%, 목표 반폭 <=0.5%p)")
for tag,ne in [("독립 가정",n16),("deff 보정",n16/d16)]:
    lo,hi=wilson(0.01,ne); print("  %-10s n_eff=%.0f → %.2f~%.2f  반폭 %.3f%%p  %s" % (tag,ne,lo,hi,(hi-lo)/2,"충족" if (hi-lo)/2<=0.5 else "미달"))
lo_,hi_=1,300000
while hi_-lo_>1:
    m=(lo_+hi_)//2; a,b=wilson(0.01,m)
    if (b-a)/2>0.5: lo_=m
    else: hi_=m
print("  필요 n_eff=%d → occurrence 가중(deff %.3f) 실표본 %d건 / unique 균등추출이면 %d건" % (hi_,d16,round(hi_*d16),hi_))
