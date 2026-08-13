# -*- coding: utf-8 -*-
"""채점 표본 400건의 **클래스별** 지표(특히 중립)를 낸다.

왜: 원페이퍼·상세보고서가 전체 정확도 93.5% 와 칸(장점/단점)별 값만 싣고
    **중립의 재현율·정밀도를 싣지 않았다.** 중립은 본 사업이 신설한 분류이자
    가장 어려운 클래스이므로, 빠뜨리면 유리한 지표만 고른 것이 된다.

예측 복원: leakage_free_metric_260730.py 와 동일 방식
          (blind_sample_260727.json 의 disagreements 에 없는 행 = 판독 기준과 일치)

출력: per_class_400_260806.json
"""
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = ("positive", "neutral", "negative")
FMAP = {"장점": "positive", "단점": "negative"}

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round(100 * (c - h), 2), round(100 * (c + h), 2)


rows = [json.loads(l) for l in open(os.path.join(HERE, "blind_judged_400.jsonl"), encoding="utf-8") if l.strip()]
res = json.load(open(os.path.join(HERE, "blind_sample_260727.json"), encoding="utf-8"))
mis = {d["no"]: d["model"] for d in res["disagreements"]}
for r in rows:
    r["model"] = mis.get(r["no"], r["claude_judgment"])
    r["cell"] = FMAP.get(r.get("field"))  # 종전 방식: 칸 라벨을 그대로 결과로


def per_class(pred_key):
    out = {}
    for lab in LABELS:
        tp = sum(1 for r in rows if r["claude_judgment"] == lab and r[pred_key] == lab)
        fn = sum(1 for r in rows if r["claude_judgment"] == lab and r[pred_key] != lab)
        fp = sum(1 for r in rows if r["claude_judgment"] != lab and r[pred_key] == lab)
        n = tp + fn
        rec = tp / n if n else 0.0
        pre = tp / (tp + fp) if (tp + fp) else 0.0
        f1 = 2 * pre * rec / (pre + rec) if (pre + rec) else 0.0
        out[lab] = {
            "n_gold": n, "tp": tp, "fn": fn, "fp": fp,
            "recall_pct": round(100 * rec, 2), "recall_ci": wilson(tp, n) if n else None,
            "precision_pct": round(100 * pre, 2), "f1": round(f1, 4),
            "pred_dist": dict(collections.Counter(r[pred_key] for r in rows if r["claude_judgment"] == lab)),
        }
    macro = sum(out[l]["f1"] for l in LABELS) / len(LABELS)
    return {"per_class": out, "macro_f1": round(macro, 4)}


doc = {
    "measured_at": "2026-08-06",
    "n": len(rows),
    "gold_dist": dict(collections.Counter(r["claude_judgment"] for r in rows)),
    "note": ("정답(claude_judgment)은 AI 판독. 'cell'=종전 방식(장점칸→칭찬/단점칸→불만) 복원. "
             "칸이 없는 행은 종전 방식에서 예측 불가로 오답 처리됨."),
    "current_model": per_class("model"),
    "cell_baseline": per_class("cell"),
}
out = os.path.join(HERE, "per_class_400_260806.json")
json.dump(doc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

for name in ("current_model", "cell_baseline"):
    print("==", name, "macroF1", doc[name]["macro_f1"])
    for lab in LABELS:
        d = doc[name]["per_class"][lab]
        print("  %-9s gold %3d  recall %6.2f%%  precision %6.2f%%  F1 %.3f  pred %s"
              % (lab, d["n_gold"], d["recall_pct"], d["precision_pct"], d["f1"], d["pred_dist"]))
print("wrote", out)
