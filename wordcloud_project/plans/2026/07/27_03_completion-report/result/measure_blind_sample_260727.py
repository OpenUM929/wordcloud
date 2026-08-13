# -*- coding: utf-8 -*-
"""무작위 표본 400건 — 블라인드 판독 기준으로 ① 입력 칸 라벨 ② 배포 모델을 각각 채점.

⚠️ 판독 주체는 사람이 아니다(정답 칸 `claude_judgment`). 상세결과보고서 §6-4-1 참조.
   신뢰구간은 아래에서 정규근사로 계산하나 **정본은 Wilson** 이다 —
   `compute_wilson_ci_260730.py` 로 산출한다(§4-7).

목적: 전수 센서스(`measure_field_census_260727.py`)는 **모델이 판정한 값**이므로 그 자체로는
      "모델이 스스로를 채점한" 것이다. 이 스크립트는 동일 모집단(870,367 문장)에서
      **고정 시드 무작위 400건**을 뽑아 별도 블라인드 판독 라벨과 대조해,
      센서스 수치가 외부 기준과 어긋나지 않음을 확인한다.

표본: seed=20260727, `random.sample(모집단, 400)` — 출현 빈도 가중(=운영 실제 구성).
      ⚠️ 이 추출을 수행한 코드는 저장소에 없다(재현 불가). 사후 적격성 검정은
      `verify_sample_400_260730.py` 참조.
라벨: `blind_judged_400.jsonl`의 `claude_judgment`.
      ⚠️ **사람 판정이 아니다.** 모델 출력을 보지 않은 상태의 선판정이라는 점만 보장된다.
      판정 주체·적격성·한계는 상세결과보고서 §6-4-1.
"""
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "blind_judged_400.jsonl")
MODEL = "D:/dev/wordcloud/model/hr_sentiment_finetuned"
FMAP = {"장점": "positive", "단점": "negative"}
ID2 = {0: "positive", 1: "negative", 2: "neutral"}

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

rows = [json.loads(l) for l in open(SAMPLE, encoding="utf-8")]
print("표본", len(rows), "건", dict(collections.Counter(r["field"] for r in rows)))

import torch  # noqa: E402
from transformers import AutoTokenizer, AutoModelForSequenceClassification  # noqa: E402

dev = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
mdl = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True)
mdl.to(dev).eval()
txt = [f"{r['field']} 평가: {r['text']}" for r in rows]
pred = []
with torch.no_grad():
    for i in range(0, len(txt), 64):
        enc = tok(txt[i:i + 64], truncation=True, padding=True, max_length=64,
                  return_tensors="pt").to(dev)
        pred.extend(ID2[j] for j in mdl(**enc).logits.argmax(-1).cpu().tolist())
for r, p in zip(rows, pred):
    r["model"] = p


def ci(k, n):
    """이항비율 95% 신뢰구간(정규근사) — %p."""
    p = k / n
    return round(100 * 1.96 * math.sqrt(p * (1 - p) / n), 2)


def score(name, key, sel=None):
    sub = [r for r in rows if sel is None or r["field"] == sel]
    n = len(sub)
    if key == "cell":
        got = [FMAP[r["field"]] for r in sub]
    else:
        got = [r[key] for r in sub]
    ok = sum(1 for r, g in zip(sub, got) if r["claude_judgment"] == g)
    pn = sum(1 for r, g in zip(sub, got)
             if {r["claude_judgment"], g} == {"positive", "negative"})
    d = dict(n=n, correct=ok, acc=round(100 * ok / n, 2), acc_ci95=ci(ok, n),
             mismatch=n - ok, mismatch_pct=round(100 * (n - ok) / n, 2),
             mismatch_ci95=ci(n - ok, n), posneg=pn,
             posneg_pct=round(100 * pn / n, 2), posneg_ci95=ci(pn, n))
    tag = f"{name}({sel})" if sel else name
    print(f"  {tag:28s} n={n:3d} 일치 {d['acc']}%±{d['acc_ci95']} | "
          f"불일치 {d['mismatch_pct']}%±{d['mismatch_ci95']} | 긍↔부 {pn} ({d['posneg_pct']}%)")
    return d


res = {"n": len(rows), "seed": 20260727, "device": dev,
       "label_dist": dict(collections.Counter(r["claude_judgment"] for r in rows))}
print("\n블라인드 판독 기준 채점 (기준 = claude_judgment — 사람 판정 아님, §6-4-1)")
print("[A] 입력 칸 라벨 = 감정 분석 도입 이전 방식")
res["cell"] = dict(overall=score("입력칸 라벨", "cell"),
                   **{f: score("입력칸 라벨", "cell", f) for f in ("장점", "단점")})
print("[B] 배포 모델(2026-07-08 seed45) = 현행")
res["model"] = dict(overall=score("배포 모델", "model"),
                    **{f: score("배포 모델", "model", f) for f in ("장점", "단점")})

# 센서스와의 대조 — 센서스(모델 판정 전수)가 사람 기준 표본 구간 안에 드는가
cen_path = os.path.join(HERE, "field_census_260727.json")
if os.path.isfile(cen_path):
    cen = json.load(open(cen_path, encoding="utf-8"))
    print("\n[C] 전수 센서스 vs 무작위 표본(사람 판독) — 불일치율 대조")
    pairs = [("전체", cen["overall"]["mismatch_pct"], res["cell"]["overall"]),
             ("장점란", cen["fields"]["장점"]["mismatch_pct"], res["cell"]["장점"]),
             ("단점란", cen["fields"]["단점"]["mismatch_pct"], res["cell"]["단점"])]
    res["census_vs_sample"] = []
    for nm, c, s in pairs:
        lo, hi = s["mismatch_pct"] - s["mismatch_ci95"], s["mismatch_pct"] + s["mismatch_ci95"]
        inside = lo <= c <= hi
        res["census_vs_sample"].append(dict(scope=nm, census_pct=c, sample_pct=s["mismatch_pct"],
                                            ci_lo=round(lo, 2), ci_hi=round(hi, 2), inside=inside))
        print(f"  {nm:5s} 센서스 {c:5.2f}% | 표본 {s['mismatch_pct']:5.2f}% "
              f"(95% CI {lo:.2f}~{hi:.2f}) → {'구간 안' if inside else '구간 밖'}")

# 사람 vs 모델 일치(무작위 표본에서의 실제 성능)
agree = sum(1 for r in rows if r["claude_judgment"] == r["model"])
pn = sum(1 for r in rows if {r["claude_judgment"], r["model"]} == {"positive", "negative"})
res["human_model_agreement"] = dict(n=len(rows), agree=agree,
                                    pct=round(100 * agree / len(rows), 2),
                                    ci95=ci(agree, len(rows)), posneg=pn)
print(f"\n[D] 무작위 표본에서 블라인드 판독 vs 배포 모델 일치 "
      f"{agree}/{len(rows)} = {res['human_model_agreement']['pct']}%"
      f"±{res['human_model_agreement']['ci95']} | 긍↔부 {pn}건")

cm = collections.Counter((r["claude_judgment"], r["model"]) for r in rows)
res["confusion_human_model"] = {f"{a}->{b}": v for (a, b), v in sorted(cm.items())}
res["disagreements"] = [dict(no=r["no"], field=r["field"], text=r["text"],
                             human=r["claude_judgment"], model=r["model"])
                        for r in rows if r["claude_judgment"] != r["model"]]

json.dump(res, open(os.path.join(HERE, "blind_sample_260727.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("저장:", os.path.join(HERE, "blind_sample_260727.json"))
