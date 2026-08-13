# -*- coding: utf-8 -*-
"""단계별 개선 추이 — 보존된 체크포인트 전부를 **동일 검증셋 761건**으로 재측정.

목적: "기존 → 최종"의 2점 비교가 아니라, 각 개선 단계가 같은 눈금에서 얼마나 올랐는지 보인다.
각 체크포인트의 필드 프리픽스 사용 여부는 **그 체크포인트가 학습된 규약**과 일치시킨다(공정 비교).
"""
import json, os, sys, time, collections

DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
BASE = DS + "eval/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")

SETS = [
    ("baseline399", "baseline_eval_260624.jsonl", "일반 대표 문장셋"),
    ("8c_hard", "gold_8c_test_260706.jsonl", "혼합·고난도 문장셋"),
    ("c3_neu149", "gold_8c_test_c3neu_260707.jsonl", "중립 경계 문장셋"),
    ("sa_speech74", "gold_speechact_test_260707.jsonl", "개선요청·완곡표현 문장셋"),
]
# (표시명, 경로, 필드프리픽스 사용, 시점, 설명)
STAGES = [
    ("S1 초기 파인튜닝(대조군)", DS + "model_out_ctrl", False, "2026-06-30", "사람 gold 1,579 학습"),
    ("S2 하드샘플 1차 추가", DS + "model_out_round1", False, "2026-06-30", "gold 2,123"),
    ("S3 전 gold 통합", DS + "model_out_final", False, "2026-07-01", "정식 gold 3,040"),
    ("S4 하드클래스(8c) 학습", DS + "model_out_8c", False, "2026-07-07", "8c 하드 gold 추가"),
    ("S5 필드신호 미적용(A/B 대조)", DS + "model_out_ft_off", False, "2026-07-07", "train 3,328, 필드 OFF"),
    ("S6 필드신호 적용(A/B 처리)", DS + "model_out_ft_on", True, "2026-07-07", "train 3,328, 필드 ON"),
    ("S7 능동학습 누적", DS + "model_out_backup_c4_260708", True, "2026-07-08", "c4 시점 체크포인트"),
    ("S8 배포 확정본(seed45)", "D:/dev/wordcloud/model/hr_sentiment_finetuned", True, "2026-07-08", "현 운영 모델"),
]
FMAP = {"장점": "positive", "단점": "negative"}
LAB = ["positive", "negative", "neutral"]

rows = []
for key, fn, ko in SETS:
    for r in (json.loads(l) for l in open(BASE + fn, encoding="utf-8")):
        g = r.get("human_decision")
        if g not in LAB:
            continue
        rows.append(dict(slice=key, text=r.get("text") or "", field=r.get("field"), gold=g))
print("검증셋 로드:", len(rows), "건", dict(collections.Counter(r["slice"] for r in rows)))

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

ID2 = {0: "positive", 1: "negative", 2: "neutral"}
dev = "cuda" if torch.cuda.is_available() else "cpu"


def run(path, use_field):
    tok = AutoTokenizer.from_pretrained(path, local_files_only=True)
    mdl = AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True)
    mdl.to(dev).eval()
    cfg = getattr(mdl.config, "id2label", None)
    txt = [f"{r['field']} 평가: {r['text']}" if (use_field and r["field"]) else r["text"] for r in rows]
    out = []
    with torch.no_grad():
        for i in range(0, len(txt), 64):
            enc = tok(txt[i:i + 64], truncation=True, padding=True, max_length=64,
                      return_tensors="pt").to(dev)
            out.extend(ID2[j] for j in mdl(**enc).logits.argmax(-1).cpu().tolist())
    del mdl
    if dev == "cuda":
        torch.cuda.empty_cache()
    return out, cfg


def score(pred, subset=None):
    sel = [(r, p) for r, p in zip(rows, pred) if subset is None or r["slice"] == subset]
    n = len(sel)
    acc = sum(1 for r, p in sel if r["gold"] == p) / n
    pn = sum(1 for r, p in sel if {r["gold"], p} == {"positive", "negative"})
    return dict(n=n, acc=round(100 * acc, 2), posneg=pn)


res = {"n_total": len(rows), "device": dev, "stages": []}

# S0 — 감정 분석 도입 이전: 입력 칸이 곧 라벨
pred0 = [FMAP.get(r["field"]) for r in rows]
sel = [(r, p) for r, p in zip(rows, pred0) if p]
s0 = dict(stage="S0 감정 분석 미도입(입력 칸 = 라벨)", date="도입 이전", note="문장을 읽지 않음",
          field_prefix=False, overall=dict(n=len(sel),
          acc=round(100 * sum(1 for r, p in sel if r["gold"] == p) / len(sel), 2),
          posneg=sum(1 for r, p in sel if {r["gold"], p} == {"positive", "negative"})),
          slices={k: dict(n=sum(1 for r, p in zip(rows, pred0) if r["slice"] == k and p),
                          acc=round(100 * sum(1 for r, p in zip(rows, pred0)
                                              if r["slice"] == k and p and r["gold"] == p)
                                    / sum(1 for r, p in zip(rows, pred0) if r["slice"] == k and p), 2),
                          posneg=sum(1 for r, p in zip(rows, pred0)
                                     if r["slice"] == k and p and {r["gold"], p} == {"positive", "negative"}))
                  for k, _, _ in SETS})
res["stages"].append(s0)
print(f"[S0] 전체 {s0['overall']['acc']}% 긍↔부 {s0['overall']['posneg']}")

for name, path, use_field, date, note in STAGES:
    if not os.path.isfile(os.path.join(path, "model.safetensors")):
        print(f"[SKIP] {name} — 가중치 없음: {path}")
        continue
    t0 = time.perf_counter()
    pred, cfg = run(path, use_field)
    d = dict(stage=name, date=date, note=note, path=path, field_prefix=use_field,
             id2label=cfg, elapsed=round(time.perf_counter() - t0, 2),
             overall=score(pred), slices={k: score(pred, k) for k, _, _ in SETS})
    res["stages"].append(d)
    print(f"[{name}] 전체 {d['overall']['acc']}% 긍↔부 {d['overall']['posneg']} | "
          + " ".join(f"{k}:{v['acc']}%/{v['posneg']}" for k, v in d["slices"].items()))

json.dump(res, open(OUT + "stage_curve_260727.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n저장:", OUT + "stage_curve_260727.json")
