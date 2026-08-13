import json,os,math,collections
R="D:/dev/wordcloud/wordcloud_project/plans/2026/07/27_03_completion-report/result"
z=1.959963985
def wilson(k,n):
    p=k/n; d=1+z*z/n; c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return (c-h)*100,(c+h)*100
rows=[json.loads(l) for l in open(os.path.join(R,"blind_judged_400.jsonl"),encoding="utf-8") if l.strip()]
bs=json.load(open(os.path.join(R,"blind_sample_260727.json"),encoding="utf-8"))
dis={d["no"]:d for d in bs["disagreements"]}
print("보고서 일치 374/400? agree=",bs["human_model_agreement"]["agree"],"불일치 원자료",len(dis))
for r in rows:
    r["model"]= dis[r["no"]]["model"] if r["no"] in dis else r["claude_judgment"]
    r["s0"]= "positive" if r["field"]=="장점" else "negative"
def score(rs,tag):
    n=len(rs)
    a=sum(1 for r in rs if r["claude_judgment"]==r["model"])
    f=sum(1 for r in rs if {r["claude_judgment"],r["model"]}=={"positive","negative"})
    a0=sum(1 for r in rs if r["claude_judgment"]==r["s0"])
    f0=sum(1 for r in rs if {r["claude_judgment"],r["s0"]}=={"positive","negative"})
    print("\n[%s] n=%d" % (tag,n))
    for lbl,k in [("현행 일치",a),("현행 뒤바뀜",f),("종전 일치",a0),("종전 뒤바뀜",f0)]:
        lo,hi=wilson(k,n); print("  %-12s %3d/%d = %6.2f%%  Wilson %.2f~%.2f (반폭 %.2f%%p)" % (lbl,k,n,100*k/n,lo,hi,(hi-lo)/2))
    # 라벨 단독 상한
    best=0
    for f_ in ("장점","단점"):
        sub=[r for r in rs if r["field"]==f_]
        c=collections.Counter(r["claude_judgment"] for r in sub)
        best+= c.most_common(1)[0][1]
    lo,hi=wilson(best,n); print("  %-12s %3d/%d = %6.2f%%  Wilson %.2f~%.2f" % ("라벨단독 상한",best,n,100*best/n,lo,hi))
score(rows,"현행 400건 (출현빈도 가중, deff 1.175)")
seen=set(); ded=[]
for r in rows:
    k=(r["field"],r["text"])
    if k in seen: continue
    seen.add(k); ded.append(r)
score(ded,"중복 제거 386건 (고유문장, deff 1.000)")
