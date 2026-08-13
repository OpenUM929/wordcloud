# -*- coding: utf-8 -*-
"""중립 경계 149건 — 배포 가중치 재판정으로 칭찬↔불만 뒤바뀜 건수 확정.

배경: 배포 가중치 실측(before_after_metrics_260727.json)은 0, 데이터셋 개발 기록
(status_260715.md §1-1 · ensemble_BASELINE_noT1_260715.json seed45)은 3으로 어긋난다.
정확도는 양쪽 76.5%로 같아 예측이 같아 보이는데 오류 분포만 다르다.

추론 규약은 measure_before_after_260727.py 와 동일하게 맞춘다
("{field} 평가: {text}" 프리픽스 · max_len 64 · batch 64 · calibration.json 온도).
산출: verify_c3neu_flip_260812.json (요약) · .jsonl (건별, 가명 텍스트만)
"""
import json, time, hashlib, os, collections

EVAL = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/eval/gold_8c_test_c3neu_260707.jsonl"
MODEL = "D:/dev/wordcloud/model/hr_sentiment_finetuned"
OUT = os.path.dirname(os.path.abspath(__file__))
LAB = ["positive", "negative", "neutral"]
ID2 = {0: "positive", 1: "negative", 2: "neutral"}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


msha = sha256(os.path.join(MODEL, "model.safetensors"))
print("model sha256 =", msha)

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
mdl = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True)
dev = "cuda" if torch.cuda.is_available() else "cpu"
mdl.to(dev).eval()
T = float(json.load(open(os.path.join(MODEL, "calibration.json"), encoding="utf-8")).get("temperature", 1.0))
print("device =", dev, "T =", T)

rows = []
n_file = 0
for line in open(EVAL, encoding="utf-8"):
    if not line.strip():
        continue
    n_file += 1
    r = json.loads(line)
    g = r.get("human_decision")
    if g not in LAB:
        continue
    rows.append(dict(rec_id=r.get("rec_id"), text=r.get("text") or "",
                     field=r.get("field"), gold=g))
print("파일 %d행 · 채점 대상 %d건" % (n_file, len(rows)))

texts = [("%s 평가: %s" % (r["field"], r["text"])) if r["field"] else r["text"] for r in rows]
t0 = time.perf_counter()
preds, probs = [], []
with torch.no_grad():
    for i in range(0, len(texts), 64):
        enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                  return_tensors="pt").to(dev)
        pr = torch.softmax(mdl(**enc).logits / T, dim=-1).cpu().tolist()
        for p in pr:
            j = max(range(3), key=lambda k: p[k])
            preds.append(ID2[j])
            probs.append({ID2[k]: round(p[k], 4) for k in range(3)})
elapsed = time.perf_counter() - t0

cm = collections.Counter()
flips = []
for r, p, pb in zip(rows, preds, probs):
    r["pred"] = p
    r["p"] = pb
    cm[(r["gold"], p)] += 1
    if {r["gold"], p} == {"positive", "negative"}:
        flips.append(r)

acc = sum(1 for r in rows if r["gold"] == r["pred"]) / len(rows)
res = {
    "model_sha256": msha, "device": dev, "temperature": T,
    "eval_file": os.path.basename(EVAL), "n_file_rows": n_file, "n_scored": len(rows),
    "elapsed_sec": round(elapsed, 3),
    "accuracy_pct": round(acc * 100, 2),
    "pos_neg_flip": len(flips),
    "flip_pos_to_neg": sum(1 for r in flips if r["gold"] == "positive"),
    "flip_neg_to_pos": sum(1 for r in flips if r["gold"] == "negative"),
    "confusion": {"%s->%s" % k: v for k, v in sorted(cm.items())},
    "gold_dist": dict(collections.Counter(r["gold"] for r in rows)),
    "pred_dist": dict(collections.Counter(r["pred"] for r in rows)),
}
json.dump(res, open(os.path.join(OUT, "verify_c3neu_flip_260812.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
with open(os.path.join(OUT, "verify_c3neu_flip_260812.jsonl"), "w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(json.dumps({k: v for k, v in res.items() if k != "confusion"}, ensure_ascii=False, indent=2))
print("confusion:", res["confusion"])
print("FLIPS =", len(flips))
