# -*- coding: utf-8 -*-
"""§1-5-1 용어 풀이에 싣는 예시 문장을 3개 단계에서 실제로 측정한다.

배경(사용자 지적 260728): §1-5 단계표의 "감정 분석 프로그램", "시중의 일반 감정
     분석 프로그램", "인사평가 전용 규칙"이 각각 무엇인지 설명이 없었다. 설명에
     예시를 실을 때 **측정 없이 예시를 지어내지 않는다**(계획서 수치 승계 금지 원칙).

측정 대상 3단계 (measure_rule_stage_260727.py / measure_stage_curve_260727.py와 동일 조건)
  S1 = KoTE 원점수 argmax (규칙 없음)      ← "시중의 일반 감정 분석 프로그램"
  S2 = KoTE + 배포 규칙 엔진                ← "인사평가 전용 규칙"
  S10 = 배포 파인튜닝 모델 (필드 프리픽스)  ← 현행 시스템
"""
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

MODEL = "D:/dev/wordcloud/model/hr_sentiment_finetuned"
ID2 = {0: "positive", 1: "negative", 2: "neutral"}

# (문장, 필드) — 인사평가에서 실제로 반복되는 문장 형태. 특정 개인 원문 아님.
CASES = [
    ("보완필요점 없습니다", "단점"),
    ("적극적인 자세가 요구됨", "단점"),
    ("고압적인 태도를 보이지 않음", "장점"),
    ("권위의식이 없음", "장점"),
    ("강압적이지 않음", "장점"),
    ("업무 난이도가 높은 일을 맡아 어려움 없이 처리함", "장점"),
]

from src.modules.sentence_emotion import compute_sentence_raw_scores  # noqa: E402
from src.services.perspective_service import sentence_sentiment_override  # noqa: E402

rows = []
for text, field in CASES:
    cache = compute_sentence_raw_scores(text)
    if not cache:
        rows.append(dict(text=text, field=field, s1=None, s2=None))
        continue
    e = cache[0]
    pos, neg, neu = e["pos"], e["neg"], e["neutral"]
    s1 = ("positive", "negative", "neutral")[max(range(3), key=lambda k: (pos, neg, neu)[k])]
    sc = sentence_sentiment_override(pos, neg, text, True, 1, threshold=0.20, weight=2.0, neutral=neu)
    s2 = "positive" if sc > 0.01 else ("negative" if sc < -0.01 else "neutral")
    rows.append(dict(text=text, field=field, kote_raw=dict(pos=round(pos, 4), neg=round(neg, 4),
                                                          neu=round(neu, 4)),
                     s1=s1, s2=s2, s2_score=round(sc, 4)))

import torch  # noqa: E402
from transformers import AutoTokenizer, AutoModelForSequenceClassification  # noqa: E402

tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
mdl = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True).eval()
texts = [f"{f} 평가: {t}" for t, f in CASES]          # 배포 조건과 동일(필드 프리픽스 주입)
with torch.no_grad():
    enc = tok(texts, truncation=True, padding=True, max_length=64, return_tensors="pt")
    pr = torch.softmax(mdl(**enc).logits, dim=-1)
for r, p in zip(rows, pr):
    v = p.tolist()
    r["s10"] = ID2[int(max(range(3), key=lambda k: v[k]))]
    r["s10_conf"] = round(max(v), 4)

print(f"{'문장':38s} {'필드':4s} {'S1(공개본)':10s} {'S2(규칙)':10s} {'S10(현행)':10s}")
for r in rows:
    print(f"{r['text'][:36]:38s} {r['field']:4s} {str(r['s1']):10s} {str(r['s2']):10s} "
          f"{r['s10']}/{r['s10_conf']:.2f}")

out = os.path.join("D:/dev/wordcloud/wordcloud_project/plans/2026/07/27_03_completion-report/result",
                   "example_stages_260728.json")
json.dump(rows, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("저장:", out)
