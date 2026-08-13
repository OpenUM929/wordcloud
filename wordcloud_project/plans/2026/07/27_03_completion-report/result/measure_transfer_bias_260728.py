# -*- coding: utf-8 -*-
"""문장 이관 방식의 **편향계수 실측** — 2023년 추정치 보정용.

2023년은 칸(장점/단점) 정보가 배치 합본으로 소실돼, 타 연도 사전에서 같은 문장의 칸을
이관하는 방식으로만 대조할 수 있다. 이 방식은 **반복 상용구에 쏠려** 불일치율을 과대
계상한다. 그 과대 정도를 수치로 확정하기 위해, 칸이 확정된 2024·2025년에
**완전히 같은 절차**를 적용해 재현값을 구하고 전수 실측값과 비교한다.

  2024년: 사전=2025년(칸 확정) → 이관 재현값  vs  2024년 전수 실측값
  2025년: 사전=2024년(칸 확정) → 이관 재현값  vs  2025년 전수 실측값

편향계수 k = 재현값 / 전수값 (칸별·지표별). 2023년 확정분 실측치를 k 로 나눠 보정한다.
"""
import collections
import io
import json
import os
import sys
import time

DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/emotion/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")
MODEL = "D:/dev/wordcloud/model/hr_sentiment_finetuned"
FMAP = {"장점": "positive", "단점": "negative"}
ID2 = {0: "positive", 1: "negative", 2: "neutral"}
PURE = 0.95

B25 = {"batch_20260622_0": "장점", "batch_20260623_2": "장점",
       "batch_20260622_2": "단점", "batch_20260623_1": "단점", "batch_20260623_3": "단점"}
SRC = {
    "2024": (DS + "weak_export_260624.jsonl",
             lambda i: "장점" if "_1-" in i else ("단점" if "_0-" in i else None)),
    "2025": (DS + "weak_export_260623.jsonl", lambda i: B25.get(i.split("-")[0])),
}

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load(year):
    """occ[(칸, 문장)] → 건수."""
    path, fof = SRC[year]
    occ = collections.Counter()
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("is_clause"):
                continue
            fd = fof(r.get("id") or "")
            t = (r.get("text") or "").strip()
            if fd and t:
                occ[(fd, t)] += 1
    return occ


def make_pool(occ):
    pool = collections.defaultdict(collections.Counter)
    for (f, t), v in occ.items():
        pool[t][f] += v
    return pool


def resolve(t, pool):
    c = pool.get(t)
    if not c:
        return None
    s = c["장점"] + c["단점"]
    if c["장점"] / s >= PURE:
        return "장점"
    if c["단점"] / s >= PURE:
        return "단점"
    return None


t0 = time.perf_counter()
occ = {y: load(y) for y in SRC}
pool = {y: make_pool(occ[y]) for y in SRC}
for y in SRC:
    print(f"{y}: {sum(occ[y].values()):,}문장 / 고유 {len(occ[y]):,}")

import torch  # noqa: E402
from transformers import AutoTokenizer, AutoModelForSequenceClassification  # noqa: E402

dev = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
mdl = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True)
mdl.to(dev).eval()
print("device:", dev)
_cache = {}


def judge(keys):
    todo = [k for k in keys if k not in _cache]
    with torch.no_grad():
        for i in range(0, len(todo), 256):
            ch = todo[i:i + 256]
            enc = tok([f"{f} 평가: {t}" for f, t in ch], truncation=True,
                      padding=True, max_length=64, return_tensors="pt").to(dev)
            for k, j in zip(ch, mdl(**enc).logits.argmax(-1).cpu().tolist()):
                _cache[k] = ID2[j]
    return {k: _cache[k] for k in keys}


def stats(sub):
    """sub: Counter[(칸,문장)] → 지표."""
    pr = judge(list(sub))
    cell = collections.Counter()
    for k, v in sub.items():
        cell[(k[0], pr[k])] += v
    n = sum(sub.values())
    d = {"n": n, "fields": {}}
    m = fl = 0
    for f in ("장점", "단점"):
        c = FMAP[f]
        o = "negative" if c == "positive" else "positive"
        nf = sum(v for (ff, _), v in cell.items() if ff == f)
        if not nf:
            continue
        d["fields"][f] = dict(n=nf, match_pct=round(100 * cell[(f, c)] / nf, 2),
                              to_neutral_pct=round(100 * cell[(f, "neutral")] / nf, 2),
                              to_flip_pct=round(100 * cell[(f, o)] / nf, 2))
        m += cell[(f, c)]
        fl += cell[(f, o)]
    d["mismatch_pct"] = round(100 * (n - m) / n, 2)
    d["flip_pct"] = round(100 * fl / n, 2)
    return d


res = {"purity_threshold": PURE, "model": MODEL,
       "note": "재현 = 타 연도 사전으로 칸을 이관한 부분집합, 전수 = 해당 연도 칸 확정 전량",
       "years": {}}
for y, other in (("2024", "2025"), ("2025", "2024")):
    full = stats(occ[y])
    sub = collections.Counter()
    for (f, t), v in occ[y].items():
        if resolve(t, pool[other]) is not None:
            sub[(f, t)] += v          # 이관으로 걸러진 부분집합 (실제 칸 f 로 채점)
    rep = stats(sub)
    cov = round(100 * rep["n"] / full["n"], 2)
    res["years"][y] = {"full": full, "transfer_reproduced": rep, "coverage_pct": cov,
                       "bias_k": {
                           "mismatch": round(rep["mismatch_pct"] / full["mismatch_pct"], 4),
                           "flip": round(rep["flip_pct"] / full["flip_pct"], 4)}}
    print(f"\n[{y}] 전수 {full['n']:,} 불일치 {full['mismatch_pct']}% 정반대 {full['flip_pct']}%")
    print(f"     재현 {rep['n']:,} ({cov}%) 불일치 {rep['mismatch_pct']}% 정반대 {rep['flip_pct']}%"
          f"  → k(불일치) {res['years'][y]['bias_k']['mismatch']}")
    for f in ("장점", "단점"):
        a, b = full["fields"].get(f), rep["fields"].get(f)
        if a and b:
            print(f"     {f}: 라벨대로 전수 {a['match_pct']}% / 재현 {b['match_pct']}%")

km = [res["years"][y]["bias_k"]["mismatch"] for y in res["years"]]
kf = [res["years"][y]["bias_k"]["flip"] for y in res["years"]]
res["bias_k_mean"] = {"mismatch": round(sum(km) / len(km), 4),
                      "flip": round(sum(kf) / len(kf), 4)}
print("\n평균 편향계수:", res["bias_k_mean"])

json.dump(res, open(OUT + "transfer_bias_260728.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("저장:", OUT + "transfer_bias_260728.json", f"| 총 {time.perf_counter() - t0:.1f}초")
