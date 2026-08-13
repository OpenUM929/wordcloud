# -*- coding: utf-8 -*-
"""입력 칸(장점/단점) 라벨 대조 — 3개 연도 **동일 난이도 구간** 비교.

배경: 2023년은 라벨을 결합한 전수 사본이 로컬에 없다(4개 export 의 배치 ID 전수 확인).
      2023년에 대해 입력 칸 라벨이 남아 있는 유일한 자료는 판정 패킷이며,
      이는 **저마진 하드 케이스만 추출한 부분집합**이라 전수 대표성이 없다.

따라서 세 연도를 **같은 난이도 구간(저마진 gap ≤ 0.15)** 으로 잘라 비교한다.
  gap = |KoTE pos − KoTE neg|  (판정 패킷의 gap 정의와 동일)

  2023 → data/23년 판정패킷_judged.json  (hard == 'low_margin')
  2024 → emotion/weak_export_260624.jsonl (배치 id `_1-`=장점 / `_0-`=단점)
  2025 → emotion/weak_export_260623.jsonl (배치 5건, BATCH_FIELD 매핑)

판정 방식·프롬프트 결합 규약은 전수 센서스(measure_field_census_260727.py)와 동일하게 유지한다.
"""
import collections
import json
import os
import sys
import time

DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
PACKET = "D:/dev/wordcloud/data/23년 판정패킷_judged.json"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")
MODEL = "D:/dev/wordcloud/model/hr_sentiment_finetuned"
FMAP = {"장점": "positive", "단점": "negative"}
ID2 = {0: "positive", 1: "negative", 2: "neutral"}
GAP_MAX = 0.15

BATCH_FIELD_2025 = {          # RUNBOOK 2026-06-23행 + 약점부재 시그니처 5/5 일치
    "batch_20260622_0": "장점", "batch_20260623_2": "장점",
    "batch_20260622_2": "단점", "batch_20260623_1": "단점", "batch_20260623_3": "단점",
}

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_2023():
    """판정 패킷의 저마진 항목 → occ[(field, text)]."""
    o = json.load(open(PACKET, encoding="utf-8"))
    occ = collections.Counter()
    n_all = 0
    for it in o["items"]:
        n_all += 1
        if it.get("hard") != "low_margin":
            continue
        f, t = it.get("field"), (it.get("text") or "").strip()
        if f in FMAP and t:
            occ[(f, t)] += 1
    return occ, n_all


def load_export(path, field_of):
    """weak_export → 저마진(gap ≤ 0.15) 행만 occ[(field, text)]."""
    occ = collections.Counter()
    n_all = n_clause = 0
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        if r.get("is_clause"):
            n_clause += 1
            continue
        n_all += 1
        k = r.get("kote") or []
        if len(k) < 2 or abs(k[0] - k[1]) > GAP_MAX:
            continue
        f = field_of(r.get("id") or "")
        t = (r.get("text") or "").strip()
        if f in FMAP and t:
            occ[(f, t)] += 1
    return occ, n_all


t0 = time.perf_counter()
occ23, tot23 = load_2023()
occ24, tot24 = load_export(
    DS + "emotion/weak_export_260624.jsonl",
    lambda rid: "장점" if "_1-" in rid else ("단점" if "_0-" in rid else None))
occ25, tot25 = load_export(
    DS + "emotion/weak_export_260623.jsonl",
    lambda rid: BATCH_FIELD_2025.get(rid.split("-")[0]))

YEARS = [("2023", occ23, tot23), ("2024", occ24, tot24), ("2025", occ25, tot25)]
for y, occ, tot in YEARS:
    print(f"{y}: 저마진 {sum(occ.values()):,}건 (고유 {len(occ):,}) / 모집단 {tot:,}")

# ── 배포 모델 판정 (전수 센서스와 동일 규약) ─────────────────────────
import torch  # noqa: E402
from transformers import AutoTokenizer, AutoModelForSequenceClassification  # noqa: E402

dev = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
mdl = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True)
mdl.to(dev).eval()
print("device:", dev)

res = {"gap_max": GAP_MAX, "model": MODEL, "device": dev,
       "note": "gap = |KoTE pos - KoTE neg|. 2023은 판정패킷 저마진 항목, 2024·2025는 전수 export의 동일 gap 구간.",
       "years": {}}

for y, occ, tot in YEARS:
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
    cell = collections.Counter()
    for (f, t), p in zip(keys, pred):
        cell[(f, FMAP[f], p)] += occ[(f, t)]

    n = sum(occ.values())
    d = {"n": n, "n_unique": len(keys), "population": tot,
         "infer_sec": round(time.perf_counter() - t1, 1), "fields": {}}
    match_all = flip_all = 0
    for f in ("장점", "단점"):
        c = FMAP[f]
        fl = "negative" if c == "positive" else "positive"
        nf = sum(v for (ff, _, _), v in cell.items() if ff == f)
        if not nf:
            continue
        d["fields"][f] = dict(
            n=nf, match=cell[(f, c, c)], match_pct=round(100 * cell[(f, c, c)] / nf, 2),
            to_neutral=cell[(f, c, "neutral")],
            to_neutral_pct=round(100 * cell[(f, c, "neutral")] / nf, 2),
            to_flip=cell[(f, c, fl)], to_flip_pct=round(100 * cell[(f, c, fl)] / nf, 2))
        match_all += cell[(f, c, c)]
        flip_all += cell[(f, c, fl)]
    d["overall"] = dict(n=n, mismatch=n - match_all,
                        mismatch_pct=round(100 * (n - match_all) / n, 2),
                        flip=flip_all, flip_pct=round(100 * flip_all / n, 2))
    res["years"][y] = d
    print(f"\n[{y} 저마진 {n:,}건]  불일치 {n - match_all:,} = {d['overall']['mismatch_pct']}%"
          f" | 정반대 {flip_all:,} = {d['overall']['flip_pct']}%")
    for f, v in d["fields"].items():
        print(f"   {f} {v['n']:>8,}  라벨대로 {v['match_pct']:5.2f}%"
              f"  중립 {v['to_neutral_pct']:5.2f}%  정반대 {v['to_flip_pct']:5.2f}%")

json.dump(res, open(OUT + "field_census_hardband_260728.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n저장:", OUT + "field_census_hardband_260728.json",
      f"| 총 {time.perf_counter() - t0:.1f}초")
