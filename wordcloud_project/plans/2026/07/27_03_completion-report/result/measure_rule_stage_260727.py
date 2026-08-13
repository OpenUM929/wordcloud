# -*- coding: utf-8 -*-
"""감정 분석 1세대(KoTE 원점수 + 규칙 엔진) 단계를 동일 검증셋 761건으로 측정."""
import json, os, sys, collections

sys.path.insert(0, "D:/dev/wordcloud/wordcloud_project")
os.chdir("D:/dev/wordcloud/wordcloud_project")

BASE = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/eval/"
SETS = [("baseline399", "baseline_eval_260624.jsonl"), ("8c_hard", "gold_8c_test_260706.jsonl"),
        ("c3_neu149", "gold_8c_test_c3neu_260707.jsonl"), ("sa_speech74", "gold_speechact_test_260707.jsonl")]
LAB = ["positive", "negative", "neutral"]

rows = []
for key, fn in SETS:
    for r in (json.loads(l) for l in open(BASE + fn, encoding="utf-8")):
        if r.get("human_decision") in LAB:
            rows.append(dict(slice=key, text=r.get("text") or "", field=r.get("field"),
                             gold=r["human_decision"]))
print("검증셋", len(rows))

from src.modules.sentence_emotion import compute_sentence_raw_scores
from src.services.perspective_service import sentence_sentiment_override

# ① KoTE 원점수(규칙 없음) ② KoTE + 규칙 엔진 — 두 단계 동시 산출
pred_kote, pred_rule = [], []
for i, r in enumerate(rows):
    cache = compute_sentence_raw_scores(r["text"])
    if not cache:
        pred_kote.append("neutral"); pred_rule.append("neutral"); continue
    e = cache[0]
    pos, neg, neu = e["pos"], e["neg"], e["neutral"]
    # ① 규칙 없는 KoTE 원점수 argmax
    pred_kote.append(("positive", "negative", "neutral")[max(range(3), key=lambda k: (pos, neg, neu)[k])])
    # ② 배포 규칙 엔진 (검증셋은 문장 단위 → is_last=True, total=1)
    s = sentence_sentiment_override(pos, neg, r["text"], True, 1, threshold=0.20, weight=2.0, neutral=neu)
    pred_rule.append("positive" if s > 0.01 else ("negative" if s < -0.01 else "neutral"))
    if (i + 1) % 200 == 0:
        print("  ...", i + 1)


def score(pred, subset=None):
    sel = [(r, p) for r, p in zip(rows, pred) if subset is None or r["slice"] == subset]
    n = len(sel)
    return dict(n=n, acc=round(100 * sum(1 for r, p in sel if r["gold"] == p) / n, 2),
                posneg=sum(1 for r, p in sel if {r["gold"], p} == {"positive", "negative"}),
                dist=dict(collections.Counter(p for _, p in sel)))


out = {}
for name, pred in [("KoTE 원점수(규칙 없음)", pred_kote), ("KoTE + 규칙 엔진", pred_rule)]:
    d = dict(overall=score(pred), slices={k: score(pred, k) for k, _ in SETS})
    out[name] = d
    print(f"[{name}] 전체 {d['overall']['acc']}% 긍↔부 {d['overall']['posneg']} | "
          + " ".join(f"{k}:{v['acc']}%/{v['posneg']}" for k, v in d["slices"].items()))

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rule_stage_260727.json")
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("저장:", OUT)
