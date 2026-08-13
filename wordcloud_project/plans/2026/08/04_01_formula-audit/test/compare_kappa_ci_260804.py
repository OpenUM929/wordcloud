import json,os,math,collections,random
R="D:/dev/wordcloud/wordcloud_project/plans/2026/07/27_03_completion-report/result"
z=1.959963985
def wilson(p,n):
    d=1+z*z/n; c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return (c-h)*100,(c+h)*100
print("=== A) 설계효과 보정 Wilson (동일문장 클러스터) ===")
for lbl,p,n,deff in [("현행 일치율 93.50%",0.9350,400,1.180),("현행 뒤바뀜 1.00%",0.0100,400,1.180),
                     ("종전 일치율 63.25%",0.6325,400,1.180)]:
    a=wilson(p,n); b=wilson(p,n/deff)
    print("%-20s 현행표기 %.2f~%.2f  →  deff보정 %.2f~%.2f (반폭 %.2f→%.2f%%p)" %
          (lbl,a[0],a[1],b[0],b[1],(a[1]-a[0])/2,(b[1]-b[0])/2))

print()
print("=== B) 1,610 표본이 목표(뒤바뀜 반폭 ≤0.5%p)를 달성하는가 ===")
p=0.01
for n,deff,tag in [(1610,1.0,"독립 가정(보고서 전제)"),(1610,1.784,"실측 deff 보정")]:
    lo,hi=wilson(p,n/deff); print("  n=%d %-22s → %.2f~%.2f  반폭 %.2f%%p" % (n,tag,lo,hi,(hi-lo)/2))
# 필요한 n_eff
def halfwidth(neff):
    lo,hi=wilson(p,neff); return (hi-lo)/2
lo_,hi_=1,200000
while hi_-lo_>1:
    m=(lo_+hi_)//2
    if halfwidth(m)>0.5: lo_=m
    else: hi_=m
print("  반폭 0.5%%p 달성에 필요한 유효표본 n_eff ~ %d  → deff 1.784 환산 실표본 ~ %d" % (hi_, round(hi_*1.784)))

print()
print("=== C) Cohen κ 신뢰구간 산식 비교 (n=100, 판독자 간) ===")
rows1={json.loads(l)["no"]:json.loads(l) for l in open(os.path.join(R,"irr_subset_260730.jsonl"),encoding="utf-8") if l.strip()}
r2=[json.loads(l) for l in open(os.path.join(R,"irr_reader2_260730.jsonl"),encoding="utf-8") if l.strip()]
print("  reader2 keys:", list(r2[0].keys()))
j400={json.loads(l)["no"]:json.loads(l) for l in open(os.path.join(R,"blind_judged_400.jsonl"),encoding="utf-8") if l.strip()}
pairs=[]
for r in r2:
    no=r["no"]
    a=j400[no].get("claude_judgment"); b=r.get("reader2_judgment")
    pairs.append((a,b))
print("  쌍 수:", len(pairs), " 예:", pairs[:3])
labs=sorted({x for p_ in pairs for x in p_})
n=len(pairs)
po=sum(1 for a,b in pairs if a==b)/n
pa=collections.Counter(a for a,_ in pairs); pb=collections.Counter(b for _,b in pairs)
pe=sum(pa[l]/n*pb[l]/n for l in labs)
k=(po-pe)/(1-pe)
se_simple=math.sqrt(po*(1-po)/(n*(1-pe)**2))
print("  po=%.4f pe=%.4f kappa=%.4f" % (po,pe,k))
print("  [보고서 산식] 단순 SE=%.4f → CI %.3f ~ %.3f  (상한 %s)" % (se_simple,k-z*se_simple,k+z*se_simple,"1을 넘음" if k+z*se_simple>1 else "OK"))
# Fleiss-Cohen-Everitt 점근분산
pij={}
for a,b in pairs: pij[(a,b)]=pij.get((a,b),0)+1/n
pi_=lambda l: pa[l]/n
p_j=lambda l: pb[l]/n
A=sum(pij.get((l,l),0)*(1-(pi_(l)+p_j(l))*(1-k))**2 for l in labs)
B=(1-k)**2*sum(pij.get((a,b),0)*(p_j(a)+pi_(b))**2 for a in labs for b in labs if a!=b)
C=(k-pe*(1-k))**2
var=(A+B-C)/(n*(1-pe)**2)
se_fce=math.sqrt(max(var,0))
print("  [Fleiss-Cohen-Everitt] SE=%.4f → CI %.3f ~ %.3f" % (se_fce,k-z*se_fce,k+z*se_fce))
# bootstrap
rnd=random.Random(20260804); bs=[]
for _ in range(20000):
    s=[pairs[rnd.randrange(n)] for _ in range(n)]
    po_=sum(1 for a,b in s if a==b)/n
    ca=collections.Counter(a for a,_ in s); cb=collections.Counter(b for _,b in s)
    pe_=sum(ca[l]/n*cb[l]/n for l in set(list(ca)+list(cb)))
    if pe_<1: bs.append((po_-pe_)/(1-pe_))
bs.sort()
print("  [부트스트랩 percentile 20,000] CI %.3f ~ %.3f" % (bs[int(.025*len(bs))],bs[int(.975*len(bs))]))
