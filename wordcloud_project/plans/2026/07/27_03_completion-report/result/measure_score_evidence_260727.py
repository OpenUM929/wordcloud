# -*- coding: utf-8 -*-
"""판정 근거 점수(확률) 실측 — "왜 그렇게 봤는가"와 "얼마나 확신했는가"를 함께 낸다.

배경(사용자 요구 260727-6): 핵심 성과는 **긍↔부 반전의 최소화**다. 반전이 남아 있다면
그것이 *얼마나 약하게* 일어났는지를 점수로 보여야 성과가 정직하게 전달된다.

산출:
  [A] 전수 센서스 대표 반복 문장 — 입력 칸과 어긋난 문장 상위 N에 확률 3종 부착.
  [B] 무작위 400건 — 사람 판독 대비 잔여 오류의 확률 마진 분포(정답군과 대조).
  [C] 개발 검증셋 761건 — 긍↔부 반전 0건 확인 + 반전에 가장 근접한 상위 케이스 마진.
  [D] 반전 위험도 = 오답이 '강한 확신'이었는지 '경계선'이었는지 구간별 집계.

주의: 확률은 argmax를 바꾸지 않는 온도 보정 이전의 원시 softmax다(배포 판정과 동일 라벨).
"""
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
MODEL = "D:/dev/wordcloud/model/hr_sentiment_finetuned"
CENSUS = os.path.join(HERE, "field_census_260727.json")
SAMPLE = os.path.join(HERE, "blind_judged_400.jsonl")
ID2 = {0: "positive", 1: "negative", 2: "neutral"}
FMAP = {"장점": "positive", "단점": "negative"}
TEST_SETS = [("baseline399", "baseline_eval_260624.jsonl"),
             ("8c_hard", "gold_8c_test_260706.jsonl"),
             ("c3_neu149", "gold_8c_test_c3neu_260707.jsonl"),
             ("sa_speech74", "gold_speechact_test_260707.jsonl")]

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import torch  # noqa: E402
from transformers import AutoTokenizer, AutoModelForSequenceClassification  # noqa: E402

dev = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
mdl = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True)
mdl.to(dev).eval()


def infer(pairs):
    """[(field, text)] -> [{'label':.., 'p':{positive/negative/neutral: float}}]"""
    out = []
    txt = [f"{f} 평가: {t}" for f, t in pairs]
    with torch.no_grad():
        for i in range(0, len(txt), 64):
            enc = tok(txt[i:i + 64], truncation=True, padding=True, max_length=64,
                      return_tensors="pt").to(dev)
            pr = torch.softmax(mdl(**enc).logits, dim=-1).cpu().tolist()
            for row in pr:
                p = {ID2[j]: round(v, 4) for j, v in enumerate(row)}
                out.append({"label": max(p, key=p.get), "p": p})
    return out


def margin(rec):
    """1위 확률 - 2위 확률. 0에 가까울수록 경계선(=약하게 동작)."""
    v = sorted(rec["p"].values(), reverse=True)
    return round(v[0] - v[1], 4)


res = {"model": MODEL, "device": dev}

# ── [A] 전수 센서스 대표 반복 문장에 점수 부착 ────────────────────────────────
cen = json.load(open(CENSUS, encoding="utf-8"))
items, keys = [], []
for fld, blk in cen["fields"].items():
    for kind, lst in blk["top_mismatch"].items():
        for e in lst:
            items.append((fld, e["text"]))
            keys.append((fld, kind, e["n"], e["text"]))
sc = infer(items)
res["census_examples"] = [
    dict(field=f, verdict=k, occurrences=n, text=t,
         model=s["label"], p=s["p"], margin=margin(s))
    for (f, k, n, t), s in zip(keys, sc)]
print(f"[A] 센서스 대표 반복 문장 {len(res['census_examples'])}건 점수화")
for e in res["census_examples"][:3]:
    print(f"    {e['field']} {e['occurrences']:>6,}회 → {e['model']} "
          f"(pos {e['p']['positive']:.2f}/neg {e['p']['negative']:.2f}/neu "
          f"{e['p']['neutral']:.2f}) {e['text'][:34]}")

# ── [B] 무작위 400건 — 잔여 오류의 확률 마진 ─────────────────────────────────
rows = [json.loads(l) for l in open(SAMPLE, encoding="utf-8")]
sc = infer([(r["field"], r["text"]) for r in rows])
for r, s in zip(rows, sc):
    r["model"], r["p"], r["margin"] = s["label"], s["p"], margin(s)


def band(m):
    """확신 구간 — 반전이 '강한 확신'이었는지 '경계선'이었는지 가른다."""
    return "경계선(<0.20)" if m < 0.20 else ("보통(0.20~0.60)" if m < 0.60 else "강한확신(≥0.60)")


def summarize(sub, name):
    n = len(sub)
    if not n:
        return None
    ms = sorted(r["margin"] for r in sub)
    d = dict(n=n, margin_mean=round(sum(ms) / n, 4), margin_median=ms[n // 2],
             bands=dict(collections.Counter(band(r["margin"]) for r in sub)))
    print(f"    {name:22s} n={n:3d} 평균마진 {d['margin_mean']:.3f} "
          f"중앙값 {d['margin_median']:.3f} | {d['bands']}")
    return d


ok = [r for r in rows if r["claude_judgment"] == r["model"]]
ng = [r for r in rows if r["claude_judgment"] != r["model"]]
flip = [r for r in rows if {r["claude_judgment"], r["model"]} == {"positive", "negative"}]
soft = [r for r in ng if r not in flip]
print("\n[B] 무작위 400건 — 확률 마진(1위-2위) 분포")
res["sample_bands"] = dict(
    correct=summarize(ok, "일치(정답)"),
    wrong=summarize(ng, "불일치(전체)"),
    soft=summarize(soft, "불일치(중립 관련)"),
    flip=summarize(flip, "긍↔부 반전"))
res["sample_flip_detail"] = [
    dict(no=r["no"], field=r["field"], text=r["text"], human=r["claude_judgment"],
         model=r["model"], p=r["p"], margin=r["margin"]) for r in flip]
print("    ── 긍↔부 반전 전건 ──")
for r in flip:
    print(f"      #{r['no']} [{r['field']}] 사람 {r['claude_judgment']} / 모델 {r['model']} "
          f"마진 {r['margin']:.3f} | pos {r['p']['positive']:.2f} "
          f"neg {r['p']['negative']:.2f} neu {r['p']['neutral']:.2f}")
    print(f"        {r['text'][:60]}")

# 입력 칸 라벨 기준 반전과 대조(도입 이전 방식은 확률 개념 자체가 없음 → 전건 100% 확신)
cellflip = [r for r in rows if {r["claude_judgment"], FMAP[r["field"]]} == {"positive", "negative"}]
res["cell_flip_n"] = len(cellflip)
print(f"\n    (대조) 입력 칸 라벨 방식의 긍↔부 반전 {len(cellflip)}건 "
      f"— 칸=라벨이므로 전건이 확신도 100% 고정, 경계선 개념 없음")

# ── [C] 개발 검증셋 761건 — 반전 0건 + 근접 케이스 ──────────────────────────
print("\n[C] 개발 검증셋 — 긍↔부 반전 및 최근접 마진")
res["dev_sets"] = {}
for name, fn in TEST_SETS:
    ev = []
    for line in open(os.path.join(DS, "eval", fn), encoding="utf-8"):
        r = json.loads(line)
        hd = r.get("human_decision")
        if hd in ID2.values() and (r.get("text") or "").strip():
            ev.append((r.get("field") or "", r["text"].strip(), hd))
    s = infer([(f, t) for f, t, _ in ev])
    acc = sum(1 for (_, _, g), x in zip(ev, s) if g == x["label"])
    fl = [dict(field=f, text=t, human=g, model=x["label"], p=x["p"], margin=margin(x))
          for (f, t, g), x in zip(ev, s) if {g, x["label"]} == {"positive", "negative"}]
    # 극성 오답은 아니지만 반대극 확률이 가장 높았던(=반전에 근접한) 케이스
    near = sorted(({"text": t, "human": g, "model": x["label"],
                    "opp_p": x["p"]["negative"] if g == "positive" else x["p"]["positive"]}
                   for (f, t, g), x in zip(ev, s) if g in ("positive", "negative")),
                  key=lambda z: -z["opp_p"])[:3]
    res["dev_sets"][name] = dict(n=len(ev), correct=acc, acc=round(100 * acc / len(ev), 2),
                                 flip=len(fl), flip_detail=fl, nearest=near)
    print(f"    {name:12s} n={len(ev):3d} 정확도 {100*acc/len(ev):5.2f}% "
          f"긍↔부 {len(fl)}건 | 최근접 반대극 확률 {near[0]['opp_p']:.3f}")

tot_n = sum(v["n"] for v in res["dev_sets"].values())
tot_f = sum(v["flip"] for v in res["dev_sets"].values())
res["dev_total"] = dict(n=tot_n, flip=tot_f)
print(f"    합계 {tot_n}건 중 긍↔부 반전 {tot_f}건")

json.dump(res, open(os.path.join(HERE, "score_evidence_260727.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n저장:", os.path.join(HERE, "score_evidence_260727.json"))
