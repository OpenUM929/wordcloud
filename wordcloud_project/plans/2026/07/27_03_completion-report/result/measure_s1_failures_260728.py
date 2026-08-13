# -*- coding: utf-8 -*-
"""공개 KoTE 원본(S1)이 실제로 무엇을 틀렸는지 검증셋 761건에서 유형별로 추출.

배경: §1-5-1 ②("시중의 일반 감정 분석 프로그램이란?")에 실을 예시를 **지어내지 않고**
     실측에서 뽑기 위함. measure_example_stages_260728.py에서 확인했듯 추측 예시는
     실제 측정과 어긋났다(예: "보완필요점 없습니다"는 공개본도 중립으로 맞힌다).

산출: S1이 틀리고 S10(배포본)이 맞힌 사례를, 긍↔부 뒤바뀜 여부로 나누어 저장.
"""
import collections
import json
import os
import sys

sys.path.insert(0, "D:/dev/wordcloud/wordcloud_project")
os.chdir("D:/dev/wordcloud/wordcloud_project")
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/eval/"
SETS = [("baseline399", "baseline_eval_260624.jsonl"), ("8c_hard", "gold_8c_test_260706.jsonl"),
        ("c3_neu149", "gold_8c_test_c3neu_260707.jsonl"), ("sa_speech74", "gold_speechact_test_260707.jsonl")]
MODEL = "D:/dev/wordcloud/model/hr_sentiment_finetuned"
LAB = ["positive", "negative", "neutral"]
ID2 = {0: "positive", 1: "negative", 2: "neutral"}

rows = []
for key, fn in SETS:
    for r in (json.loads(l) for l in open(BASE + fn, encoding="utf-8")):
        if r.get("human_decision") in LAB and (r.get("text") or "").strip():
            rows.append(dict(slice=key, text=r["text"].strip(),
                             field=(r.get("field") or "").strip(), gold=r["human_decision"]))
print("검증셋", len(rows))

from src.modules.sentence_emotion import compute_sentence_raw_scores  # noqa: E402
from src.services.perspective_service import sentence_sentiment_override  # noqa: E402

for i, r in enumerate(rows):
    cache = compute_sentence_raw_scores(r["text"])
    if not cache:
        r["s1"] = r["s2"] = "neutral"
        continue
    e = cache[0]
    pos, neg, neu = e["pos"], e["neg"], e["neutral"]
    r["s1"] = ("positive", "negative", "neutral")[max(range(3), key=lambda k: (pos, neg, neu)[k])]
    sc = sentence_sentiment_override(pos, neg, r["text"], True, 1, threshold=0.20, weight=2.0, neutral=neu)
    r["s2"] = "positive" if sc > 0.01 else ("negative" if sc < -0.01 else "neutral")
    if (i + 1) % 200 == 0:
        print("  ...", i + 1)

import torch  # noqa: E402
from transformers import AutoTokenizer, AutoModelForSequenceClassification  # noqa: E402

dev = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
mdl = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True).to(dev).eval()
texts = [f"{r['field']} 평가: {r['text']}" if r["field"] else r["text"] for r in rows]
with torch.no_grad():
    for i in range(0, len(texts), 128):
        enc = tok(texts[i:i + 128], truncation=True, padding=True, max_length=64,
                  return_tensors="pt").to(dev)
        pr = torch.softmax(mdl(**enc).logits, dim=-1)
        for r, p in zip(rows[i:i + 128], pr.cpu().tolist()):
            r["s10"] = ID2[int(max(range(3), key=lambda k: p[k]))]
            r["s10_conf"] = round(max(p), 4)

# ── 유형별 집계 ───────────────────────────────────────────────────────────────
conf = collections.Counter((r["gold"], r["s1"]) for r in rows)
fixed = [r for r in rows if r["s1"] != r["gold"] and r["s10"] == r["gold"]]
flip_fixed = [r for r in fixed if {r["s1"], r["gold"]} == {"positive", "negative"}]
s2_fixed = [r for r in flip_fixed if r["s2"] == r["gold"]]

print(f"\nS1 오답 {sum(1 for r in rows if r['s1']!=r['gold']):,} / S10이 교정 {len(fixed):,}")
print(f"그중 긍↔부 뒤바뀜 교정 {len(flip_fixed):,} (규칙 엔진 S2 단계에서 이미 교정된 것 {len(s2_fixed):,})")
print("\nS1 혼동(정답→S1판정) 상위:")
for (g, p), n in conf.most_common(9):
    if g != p:
        print(f"  {g:9s} → {p:9s} {n:4d}")

print("\n[긍↔부 뒤바뀜 교정 사례]")
for r in flip_fixed[:14]:
    print(f"  [{r['field'] or '?'}] {r['text'][:44]:46s} 사람:{r['gold']:9s} "
          f"공개본:{r['s1']:9s} 규칙:{r['s2']:9s} 현행:{r['s10']}/{r['s10_conf']:.2f}")

out = dict(n=len(rows),
           s1_wrong=sum(1 for r in rows if r["s1"] != r["gold"]),
           s10_fixed=len(fixed), flip_fixed=len(flip_fixed), flip_fixed_by_rule=len(s2_fixed),
           confusion={f"{g}->{p}": n for (g, p), n in sorted(conf.items())},
           examples=[{k: r[k] for k in ("slice", "field", "text", "gold", "s1", "s2", "s10", "s10_conf")}
                     for r in flip_fixed])
p = os.path.join("D:/dev/wordcloud/wordcloud_project/plans/2026/07/27_03_completion-report/result",
                 "s1_failures_260728.json")
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n저장:", p)
