# -*- coding: utf-8 -*-
"""판독자 간 신뢰도(IRR) 측정 — 블라인드 400건 중 100건 이중 판독 · Cohen κ.

배경: §4-10 ⑩ 은 "산출된 κ 0.890 은 판독기준 대 모델 값이며 판독자 간 신뢰도는
      미측정"으로 부분 미비 판정을 받았음. 본 스크립트가 그 공백을 메운다.

절차 기록 (§10-4 제9조 자기적용):
  1. 표본  : blind_judged_400.jsonl 400건 중 seed=20260730 무작위 100건
             → irr_subset_260730.jsonl (no/field/text 3개 칸만. **1차 라벨 미포함**)
  2. 판독2 : 위 파일만 보고 독립 판정 → irr_reader2_260730.jsonl
  3. 판독 기준(양 판독에 동일 적용):
       - 명시적 역량·행위 칭찬            → positive
       - 개선요청 화행(필요/부족/아쉬움/요구/바람) → negative
       - 평가회피("보완점 없음"류)·무의미 문자열·무종결 단편 → neutral
       - 단점란의 칭찬 서술은 **칸이 아니라 문장 의미**로 판정
  4. 대조  : 본 스크립트 실행 (아래)
  ⚠️ 두 판독자는 동일 계열 모델임 — 독립 판독자가 아니므로 κ 는 **상한 추정**이다.
     사람 2인 재판독 시 이 값보다 낮게 나올 수 있다(조치 요청 4번).

출력: irr_kappa_260730.json
"""
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = ("positive", "negative", "neutral")

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return 100 * (c - h), 100 * (c + h)


r1 = {r["no"]: r["claude_judgment"]
      for r in map(json.loads, open(os.path.join(HERE, "blind_judged_400.jsonl"), encoding="utf-8"))}
r2rows = [json.loads(l) for l in open(os.path.join(HERE, "irr_reader2_260730.jsonl"), encoding="utf-8")]
r2 = {r["no"]: r["reader2_judgment"] for r in r2rows}
nos = sorted(r2)
n = len(nos)
print(f"이중 판독 대상 {n}건 (전체 400건의 {100*n/400:.0f}%)")

a = [r1[i] for i in nos]
b = [r2[i] for i in nos]
agree = sum(1 for x, y in zip(a, b) if x == y)
po = agree / n
pe = sum((a.count(L) / n) * (b.count(L) / n) for L in LABELS)
kappa = (po - pe) / (1 - pe)

# κ 표준오차(Fleiss 근사) — 등급 해석용 참고치
se = math.sqrt(po * (1 - po) / (n * (1 - pe) ** 2))
lo, hi = kappa - 1.96 * se, kappa + 1.96 * se

band = ("almost perfect (0.81~1.00)" if kappa >= .81 else
        "substantial (0.61~0.80)" if kappa >= .61 else
        "moderate (0.41~0.60)" if kappa >= .41 else "fair 이하")

wl, wh = wilson(agree, n)
print(f"\n[1] 단순 일치 {agree}/{n} = {100*po:.2f}% (Wilson 95% CI {wl:.2f}~{wh:.2f})")
print(f"[2] 우연 일치 기대값 Pe = {pe:.4f}")
print(f"[3] Cohen κ = {kappa:.3f}  (95% CI {lo:.3f}~{hi:.3f})  → Landis & Koch: {band}")

pn = [i for i in nos if {r1[i], r2[i]} == {"positive", "negative"}]
print(f"[4] 판독자 간 긍↔부 역전 = {len(pn)}건" + (f" {pn}" if pn else "  ← 제1원칙 지표"))

print("\n[5] 혼동표 (행=판독1 / 열=판독2)")
cm = collections.Counter(zip(a, b))
print("        " + "".join(f"{L:>10s}" for L in LABELS))
for x in LABELS:
    print(f"{x:>8s}" + "".join(f"{cm[(x, y)]:>10d}" for y in LABELS))

dis = [dict(no=i, field=next(r["field"] for r in r2rows if r["no"] == i),
            text=next(r["text"] for r in r2rows if r["no"] == i),
            reader1=r1[i], reader2=r2[i]) for i in nos if r1[i] != r2[i]]
print(f"\n[6] 불일치 {len(dis)}건")
for d in dis:
    print(f"   #{d['no']:>3d} [{d['field']}] 판독1={d['reader1']:8s} 판독2={d['reader2']:8s} | {d['text'][:46]}")

out = dict(n=n, agree=agree, po=round(po, 4), pe=round(pe, 4), kappa=round(kappa, 3),
           kappa_ci95=[round(lo, 3), round(hi, 3)], band=band,
           agree_pct=round(100 * po, 2), agree_wilson=[round(wl, 2), round(wh, 2)],
           posneg_reversal=len(pn), confusion={f"{x}->{y}": cm[(x, y)] for x in LABELS for y in LABELS},
           disagreements=dis,
           caveat="두 판독자는 동일 계열 모델이므로 독립이 아님 — κ 는 상한 추정치")
json.dump(out, open(os.path.join(HERE, "irr_kappa_260730.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n저장:", os.path.join(HERE, "irr_kappa_260730.json"))
