# -*- coding: utf-8 -*-
"""Before(입력칸=라벨) vs After(배포 7/8 모델) 전 지표 실측.

산출: q.txt 3장의 지표 (1)~(8)을 사람 gold 762건 검증셋에서 계산.
"""
import json, time, hashlib, os, sys, collections

BASE = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/eval/"
MODEL = "D:/dev/wordcloud/model/hr_sentiment_finetuned"
# 산출물은 이 스크립트와 같은 폴더(= 보고서 result/)에 기록한다.
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")

SETS = [
    ("baseline399", "baseline_eval_260624.jsonl", "human_decision", "일반 대표 문장셋"),
    ("8c_hard", "gold_8c_test_260706.jsonl", "human_decision", "혼합·고난도 문장셋"),
    ("c3_neu149", "gold_8c_test_c3neu_260707.jsonl", "human_decision", "중립 경계 문장셋"),
    ("sa_speech74", "gold_speechact_test_260707.jsonl", "human_decision", "개선요청·완곡표현 문장셋"),
]
FMAP = {"장점": "positive", "단점": "negative"}
LAB = ["positive", "negative", "neutral"]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 16), b""):
            h.update(c)
    return h.hexdigest()


def kappa(a, b):
    """Cohen's kappa between two label sequences."""
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe = sum((ca[l] / n) * (cb[l] / n) for l in set(a) | set(b))
    return (po - pe) / (1 - pe) if pe != 1 else 0.0


def prf(gold, pred, cls):
    tp = sum(1 for g, p in zip(gold, pred) if p == cls and g == cls)
    fp = sum(1 for g, p in zip(gold, pred) if p == cls and g != cls)
    fn = sum(1 for g, p in zip(gold, pred) if p != cls and g == cls)
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
    return dict(tp=tp, fp=fp, fn=fn, precision=round(pr, 4), recall=round(rc, 4), f1=round(f1, 4))


print("model sha256 =", sha256(os.path.join(MODEL, "model.safetensors")))
print("calibration  =", open(os.path.join(MODEL, "calibration.json"), encoding="utf-8").read().strip())

sys.path.insert(0, "D:/dev/wordcloud/wordcloud_project")
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
mdl = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True)
dev = "cuda" if torch.cuda.is_available() else "cpu"
mdl.to(dev).eval()
T = float(json.load(open(os.path.join(MODEL, "calibration.json"), encoding="utf-8")).get("temperature", 1.0))
ID2 = {0: "positive", 1: "negative", 2: "neutral"}
print("device =", dev, "T =", T)

rows_all = []
for key, fn, gk, ko in SETS:
    for r in (json.loads(l) for l in open(BASE + fn, encoding="utf-8")):
        g = r.get(gk)
        if g not in LAB:
            continue
        rows_all.append(dict(slice=key, ko=ko, text=r.get("text") or "",
                             field=r.get("field"), gold=g))

# ---- 추론 (배포와 동일 규약: "{field} 평가: {text}" 프리픽스, max_len 64, batch 64)
texts = [f"{r['field']} 평가: {r['text']}" if r["field"] else r["text"] for r in rows_all]
t0 = time.perf_counter()
preds, confs = [], []
with torch.no_grad():
    for i in range(0, len(texts), 64):
        enc = tok(texts[i:i + 64], truncation=True, padding=True, max_length=64,
                  return_tensors="pt").to(dev)
        pr = torch.softmax(mdl(**enc).logits / T, dim=-1).cpu().tolist()
        for p in pr:
            j = max(range(3), key=lambda k: p[k])
            preds.append(ID2[j])
            confs.append(p[j])
elapsed = time.perf_counter() - t0
for r, p, c in zip(rows_all, preds, confs):
    r["pred"] = p
    r["conf"] = c
    r["before"] = FMAP.get(r["field"])

res = {"model_sha256": sha256(os.path.join(MODEL, "model.safetensors")),
       "device": dev, "temperature": T, "n_total": len(rows_all),
       "elapsed_sec": round(elapsed, 3),
       "throughput_per_sec": round(len(rows_all) / elapsed, 1),
       "ms_per_sentence": round(elapsed / len(rows_all) * 1000, 2),
       "slices": {}, "overall": {}}


def block(rows):
    n = len(rows)
    gold = [r["gold"] for r in rows]
    pred = [r["pred"] for r in rows]
    bef = [r["before"] for r in rows]
    scored_b = [(g, b) for g, b in zip(gold, bef) if b]
    b_acc = sum(1 for g, b in scored_b if g == b) / len(scored_b)
    b_pn = sum(1 for g, b in scored_b if {g, b} == {"positive", "negative"})
    a_acc = sum(1 for g, p in zip(gold, pred) if g == p) / n
    a_pn = sum(1 for g, p in zip(gold, pred) if {g, p} == {"positive", "negative"})
    # 재분류 = 모델 판정이 입력칸 극성과 다른 건
    rec = [r for r in rows if r["before"] and r["pred"] != r["before"]]
    rec_ok = [r for r in rec if r["pred"] == r["gold"]]
    rec_bad = [r for r in rec if r["pred"] != r["gold"] and r["before"] == r["gold"]]
    kept = [r for r in rows if r["before"] and r["pred"] == r["before"]]
    kept_ok = [r for r in kept if r["pred"] == r["gold"]]
    lowc = [r for r in rows if r["conf"] < 0.6]
    d = dict(
        n=n,
        before_acc=round(100 * b_acc, 2), before_posneg_err=b_pn,
        before_posneg_rate=round(100 * b_pn / len(scored_b), 2),
        after_acc=round(100 * a_acc, 2), after_posneg_err=a_pn,
        after_posneg_rate=round(100 * a_pn / n, 2),
        acc_gain_pp=round(100 * (a_acc - b_acc), 2),
        reclass_n=len(rec), reclass_rate=round(100 * len(rec) / n, 2),
        reclass_correct=len(rec_ok),
        reclass_accuracy=round(100 * len(rec_ok) / len(rec), 2) if rec else None,
        reclass_harmful=len(rec_bad),
        kept_n=len(kept), kept_accuracy=round(100 * len(kept_ok) / len(kept), 2) if kept else None,
        direction_agreement=round(100 * (n - len(rec)) / n, 2),
        kappa_after=round(kappa(gold, pred), 4),
        kappa_before=round(kappa([g for g, b in scored_b], [b for g, b in scored_b]), 4),
        mean_confidence=round(sum(r["conf"] for r in rows) / n, 4),
        low_conf_n=len(lowc), low_conf_rate=round(100 * len(lowc) / n, 2),
        per_class={c: prf(gold, pred, c) for c in LAB},
        per_class_before={c: prf([g for g, b in scored_b], [b for g, b in scored_b], c) for c in LAB},
        confusion_after={f"{g}->{p}": v for (g, p), v in
                         sorted(collections.Counter(zip(gold, pred)).items())},
        confusion_before={f"{g}->{b}": v for (g, b), v in
                          sorted(collections.Counter(scored_b).items())},
        gold_dist=dict(collections.Counter(gold)),
        field_dist=dict(collections.Counter(r["field"] for r in rows)),
    )
    return d


for key, fn, gk, ko in SETS:
    rs = [r for r in rows_all if r["slice"] == key]
    res["slices"][key] = dict(korean=ko, **block(rs))
res["overall"] = block(rows_all)

json.dump(res, open(OUT + "before_after_metrics_260727.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

# 재분류 사례 덤프 (보고서 §4 정성 비교용)
cases = [dict(slice=r["slice"], field=r["field"], text=r["text"], before=r["before"],
              after=r["pred"], gold=r["gold"], conf=round(r["conf"], 3),
              verdict=("교정" if r["pred"] == r["gold"] else
                       ("악화" if r["before"] == r["gold"] else "둘다오답")))
         for r in rows_all if r["before"] and r["pred"] != r["before"]]
json.dump(cases, open(OUT + "reclass_cases_260727.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

o = res["overall"]
print(f"\n=== 전체 {o['n']}건 ===")
print(f"Before(입력칸=라벨) 정확도 {o['before_acc']}%  긍↔부 {o['before_posneg_err']}건")
print(f"After (배포 7/8 모델) 정확도 {o['after_acc']}%  긍↔부 {o['after_posneg_err']}건")
print(f"재분류율 {o['reclass_rate']}% ({o['reclass_n']}건) / 재해석 정확도 {o['reclass_accuracy']}% / 악화 {o['reclass_harmful']}건")
print(f"kappa before {o['kappa_before']} -> after {o['kappa_after']}")
print(f"평균 신뢰도 {o['mean_confidence']} / 저신뢰(<0.6) {o['low_conf_rate']}%")
print(f"처리 {o['elapsed_sec'] if 'elapsed_sec' in o else res['elapsed_sec']}s, {res['throughput_per_sec']}건/초, {res['ms_per_sentence']}ms/건")
for k, v in res["slices"].items():
    print(f"  [{k:12s}] n={v['n']:3d} before {v['before_acc']:5.1f}% (긍↔부{v['before_posneg_err']:3d}) "
          f"-> after {v['after_acc']:5.1f}% (긍↔부{v['after_posneg_err']:2d})  재분류 {v['reclass_rate']:5.1f}% 정확 {v['reclass_accuracy']}")
print("\n재분류 사례", len(cases), "건 저장")
