import math

print("=== 1) Acc_max / Acc(S0) ===")
n_pro, n_con, N = 1333323, 1302596, 2635919
accmax = (n_pro*0.9577 + n_con*0.4938)/N
accs0  = (n_pro*0.9577 + n_con*0.3509)/N
print("Acc_max=%.6f  Acc(S0)=%.6f  (report 0.7285 / 0.6579)" % (accmax, accs0))
print("N check:", n_pro+n_con, "vs", N)

print()
print("=== 2) Entropy / MI ===")
# P(f)
pf = [n_pro/N, n_con/N]
cond = [[0.9577,0.0330,0.0092],[0.1553,0.4938,0.3509]]
py=[0,0,0]
for i,p in enumerate(pf):
    for y in range(3): py[y]+= p*cond[i][y]
HY = -sum(q*math.log2(q) for q in py if q>0)
HYF = 0
for i,p in enumerate(pf):
    HYF += p*(-sum(q*math.log2(q) for q in cond[i] if q>0))
print("P(Y)=", [round(q,6) for q in py])
print("H(Y)=%.4f (report 1.4167)  H(Y|F)=%.4f (report 0.8606)  I=%.4f (report 0.5561)" % (HY,HYF,HY-HYF))
print("I/H=%.4f%% (report 39.26)   H(Y|F)/H(Y)=%.4f%% (report 60.74)" % (100*(HY-HYF)/HY, 100*HYF/HY))
print("row sums:", [round(sum(r),4) for r in cond])

print()
print("=== 3) McNemar ===")
def mcnemar_cc(b,c):
    chi=(abs(b-c)-1)**2/(b+c); return chi
def chi2_sf_df1(x):
    return math.erfc(math.sqrt(x/2))
for lbl,b,c in [("acc400",4,125),("flip400",28,1)]:
    x=mcnemar_cc(b,c); print("%s chi2=%.2f p=%.3e" % (lbl,x,chi2_sf_df1(x)))
x=(141-1)**2/279; print("761 lower bound chi2=%.2f p=%.3e" % (x, chi2_sf_df1(x)))
# exact binomial two-sided
def exact(b,c):
    n=b+c; k=min(b,c)
    s=sum(math.comb(n,i) for i in range(0,k+1))
    return min(1.0, 2*s/2**n)
print("exact acc400 p=%.3e   exact flip400 p=%.3e" % (exact(4,125), exact(28,1)))

print()
print("=== 4) Wilson vs Wald ===")
z=1.959963985
def wald(k,n):
    p=k/n; se=math.sqrt(p*(1-p)/n); return (p-z*se)*100,(p+z*se)*100
def wilson(k,n):
    p=k/n; d=1+z*z/n
    c=(p+z*z/(2*n))/d
    h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return (c-h)*100,(c+h)*100
for lbl,k,n,rep in [("종전일치 63.25",253,400,"58.42~67.83"),("현행일치 93.50",374,400,"90.65~95.53"),
                    ("종전뒤바뀜 7.75",31,400,"5.51~10.79"),("현행뒤바뀜 1.00",4,400,"0.39~2.54"),
                    ("상한 73.50",294,400,"68.97~77.59"),("누출배제 93.88",368,392,"91.05~95.85")]:
    print("%-18s wald %.2f~%.2f | wilson %.2f~%.2f | report %s" % (lbl,*wald(k,n),*wilson(k,n),rep))

print()
print("=== 5) Clopper-Pearson (참고) ===")
from math import lgamma
def betainv_bisect(a,b,t):
    lo,hi=0.0,1.0
    for _ in range(200):
        m=(lo+hi)/2
        # regularized incomplete beta via series-free numeric integration
        n=20000; s=0.0; 
        # use simple Simpson on [0,m]
        if m<=0: I=0.0
        else:
            h=m/n; tot=0.0
            for i in range(n+1):
                x=i*h
                if x<=0 or x>=1:
                    f=0.0 if (a>1 and x<=0) or (b>1 and x>=1) else (0.0)
                else:
                    f=math.exp((a-1)*math.log(x)+(b-1)*math.log(1-x))
                w=1 if i in (0,n) else (4 if i%2 else 2)
                tot+=w*f
            I=tot*h/3
        B=math.exp(lgamma(a)+lgamma(b)-lgamma(a+b))
        val=I/B
        if val<t: lo=m
        else: hi=m
    return (lo+hi)/2
for lbl,k,n in [("현행뒤바뀜",4,400),("현행일치",374,400)]:
    lo = 0.0 if k==0 else betainv_bisect(k,n-k+1,0.025)
    hi = 1.0 if k==n else betainv_bisect(k+1,n-k,0.975)
    print("%s Clopper-Pearson %.2f~%.2f" % (lbl,lo*100,hi*100))
