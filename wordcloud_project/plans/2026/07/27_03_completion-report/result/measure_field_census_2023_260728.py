# -*- coding: utf-8 -*-
"""입력 칸(장점/단점) 라벨 대조 — **2023년**.

2023년 배치(batch_20260713_0)는 장점·단점을 **하나의 배치로 합쳐** 실행해,
export 레코드에 칸 정보가 남지 않았다. 다음 3개 가설을 모두 실측 기각했다.
  · export `f` 키          → 2023년분 0건
  · 레코드 순번 홀짝        → applied_rule 별 홀수비 49.3~52.2% (교대 아님)
  · 원본 db_id 홀짝        → 짝수 단점 75,367 / 홀수 74,969 (50:50)

따라서 **2024·2025년 161만 문장(칸 확정본)을 사전(pool)으로 삼아 동일 문장의 칸을 이관**한다.
  · 이관 기준: 같은 문장이 사전에서 한쪽 칸에 95% 이상 쏠릴 때만 그 칸으로 확정
  · 확정분만 배포 모델로 실측하고, 미확정분은 2024·2025년 층별 실측률로 층화 추정한다
판정 규약(프리픽스 결합·max_length·argmax)은 2024·2025년 센서스와 완전히 동일하다.
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

BATCH_FIELD_2025 = {          # RUNBOOK 2026-06-23행 + 약점부재 시그니처 5/5 일치
    "batch_20260622_0": "장점", "batch_20260623_2": "장점",
    "batch_20260622_2": "단점", "batch_20260623_1": "단점", "batch_20260623_3": "단점",
}

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def scan_pool(path, field_of, pool, freq):
    """칸 확정본 → pool[text][칸] 누적, freq[text] 총 등장수."""
    n = 0
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("is_clause"):
                continue
            fd = field_of(r.get("id") or "")
            if not fd:
                continue
            t = (r.get("text") or "").strip()
            if not t:
                continue
            pool[t][fd] += 1
            freq[t] += 1
            n += 1
    return n


t0 = time.perf_counter()
pool = collections.defaultdict(collections.Counter)
freq = collections.Counter()
n24 = scan_pool(DS + "weak_export_260624.jsonl",
                lambda i: "장점" if "_1-" in i else ("단점" if "_0-" in i else None),
                pool, freq)
n25 = scan_pool(DS + "weak_export_260623.jsonl",
                lambda i: BATCH_FIELD_2025.get(i.split("-")[0]), pool, freq)
print(f"칸 확정 사전: 2024 {n24:,} + 2025 {n25:,} = {n24 + n25:,} / 고유 {len(pool):,}")


def field_of_text(t):
    c = pool.get(t)
    if not c:
        return None
    s = c["장점"] + c["단점"]
    if c["장점"] / s >= PURE:
        return "장점"
    if c["단점"] / s >= PURE:
        return "단점"
    return None


# ── 2023년 적재 ──────────────────────────────────────────────────
occ = collections.Counter()      # (칸, 문장) → 건수  (확정분)
n23 = n_clause = n_unres = 0
with io.open(DS + "weak_export_260714.jsonl", encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        if not (r.get("id") or "").startswith("batch_20260713_0-"):
            continue
        if r.get("is_clause"):
            n_clause += 1
            continue
        n23 += 1
        t = (r.get("text") or "").strip()
        fd = field_of_text(t)
        if fd:
            occ[(fd, t)] += 1
        else:
            n_unres += 1
n_res = sum(occ.values())
print(f"2023 문장 {n23:,} (절 제외 {n_clause:,}) | 칸 확정 {n_res:,} "
      f"({100 * n_res / n23:.2f}%) 고유 {len(occ):,} | 미확정 {n_unres:,}")

# ── 배포 모델 판정 (2024·2025 센서스와 동일 규약) ───────────────────
import torch  # noqa: E402
from transformers import AutoTokenizer, AutoModelForSequenceClassification  # noqa: E402

dev = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
mdl = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True)
mdl.to(dev).eval()
print("device:", dev)

keys = list(occ)
pred = []
t1 = time.perf_counter()
with torch.no_grad():
    for i in range(0, len(keys), 256):
        chunk = keys[i:i + 256]
        txt = [f"{f} 평가: {t}" for f, t in chunk]
        enc = tok(txt, truncation=True, padding=True, max_length=64,
                  return_tensors="pt").to(dev)
        pred.extend(ID2[j] for j in mdl(**enc).logits.argmax(-1).cpu().tolist())
infer = round(time.perf_counter() - t1, 1)

cell = collections.Counter()
for (f, t), p in zip(keys, pred):
    cell[(f, FMAP[f], p)] += occ[(f, t)]

res = {"year": 2023, "model": MODEL, "device": dev, "purity_threshold": PURE,
       "method": "칸 확정본(2024·2025 161만)에서 동일 문장의 칸을 이관, 확정분만 실측",
       "n_sentences": n23, "n_clause_excluded": n_clause,
       "n_field_resolved": n_res, "n_field_unresolved": n_unres,
       "resolved_pct": round(100 * n_res / n23, 2),
       "n_unique": len(keys), "infer_sec": infer, "fields": {}}
match_all = flip_all = 0
for f in ("장점", "단점"):
    c = FMAP[f]
    fl = "negative" if c == "positive" else "positive"
    nf = sum(v for (ff, _, _), v in cell.items() if ff == f)
    if not nf:
        continue
    res["fields"][f] = dict(
        n=nf, match=cell[(f, c, c)], match_pct=round(100 * cell[(f, c, c)] / nf, 2),
        to_neutral=cell[(f, c, "neutral")],
        to_neutral_pct=round(100 * cell[(f, c, "neutral")] / nf, 2),
        to_flip=cell[(f, c, fl)], to_flip_pct=round(100 * cell[(f, c, fl)] / nf, 2))
    match_all += cell[(f, c, c)]
    flip_all += cell[(f, c, fl)]
res["overall"] = dict(n=n_res, mismatch=n_res - match_all,
                      mismatch_pct=round(100 * (n_res - match_all) / n_res, 2),
                      flip=flip_all, flip_pct=round(100 * flip_all / n_res, 2))

print(f"\n[2023 칸 확정 {n_res:,}건] 불일치 {n_res - match_all:,} "
      f"= {res['overall']['mismatch_pct']}% | 정반대 {flip_all:,} = {res['overall']['flip_pct']}%")
for f, v in res["fields"].items():
    print(f"   {f} {v['n']:>8,}  라벨대로 {v['match_pct']:5.2f}%"
          f"  중립 {v['to_neutral_pct']:5.2f}%  정반대 {v['to_flip_pct']:5.2f}%")

json.dump(res, open(OUT + "field_census_2023_260728.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n저장:", OUT + "field_census_2023_260728.json",
      f"| 총 {time.perf_counter() - t0:.1f}초")
