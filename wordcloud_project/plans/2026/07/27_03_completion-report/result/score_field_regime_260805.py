# -*- coding: utf-8 -*-
"""칸(장점/단점) 규약 기준으로 D-8·D-9 를 판정하기 위한 측정.

배경(2026-08-05 사용자 확인)
  운영 규약상 '라벨'은 **그 문장이 장점 칸에 적혔는지 단점 칸에 적혔는지**를 가리키는
  칸 표기이며, 2023~2025년 전수 데이터는 **모두 칸이 있는 자료**다(field_census_3y_260729.json:
  2023 521,817+503,817=1,025,634 / 2024 443,637+426,730=870,367 — 칸 없는 행 0).
  학습·추론 규약도 `"{장점|단점} 평가: {문장}"` 프리픽스를 강제한다.

  그렇다면 88건 중
    · 칸 없는 26건 → 운영에서 발생하지 않는 조건(프리픽스 결락)에서 채점된 것 (D-9)
    · 260715 교정 62건 → 칸은 있으나, 사람 표기가 그 칸과 어긋나는지 여부가 쟁점 (D-8)

산출
  [D-9] 26건을 ① 칸 없음(현행) ② 복원된 칸 적용 ③ 전량 '장점' 가정 세 조건으로 재추론.
        조건 간 차이 = 프리픽스 결락이 만든 인공 오차의 크기.
  [D-8] 62건의 사람 표기가 자기 칸과 모순되는 건수(칸 무시 라벨링의 규모).
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
OUT = os.path.join(HERE, "score_field_regime_260805.json")

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, "D:/dev/wordcloud/wordcloud_project")      # utils 패키지
sys.path.insert(0, "D:/dev/wordcloud/wordcloud_project/src")  # modules 패키지
from modules.hr_sentiment import predict_sentiments  # noqa: E402

rows = [json.loads(l) for l in open(os.path.join(HERE, "score_human_clean_260805.jsonl"),
                                    encoding="utf-8")]
recov = json.load(open(os.path.join(HERE, "verify_field_recovery_260805.json"), encoding="utf-8"))

# 복원 칸: 다수결이 단일할 때만 채택(충돌 1건은 미채택 — verify_field_recovery 와 동일 규약)
rec_field = {}
for t, d in recov["detail"].items():
    f = d["fields"]
    if len(f) == 1:
        rec_field[t] = next(iter(f))

res = {"measured_at": "2026-08-05", "recoverable_single": len(rec_field)}

# ── D-9 : 칸 없는 26건 ────────────────────────────────────────────────────────
nof = [r for r in rows if r["stratum"] == "other"]
assert all(not r["field"] for r in nof), "other 층은 전량 칸 없음이어야 함"
texts = [r["text"] for r in nof]

conds = {
    "① 칸 없음(현행 채점)": [""] * len(nof),
    "② 복원된 칸 적용":     [rec_field.get(t, "") for t in texts],
    "③ 전량 장점 가정":     ["장점"] * len(nof),
}
res["D9_fieldless_26"] = {}
for name, fields in conds.items():
    pred = predict_sentiments(texts, fields=fields)
    if pred is None:
        sys.exit("모델 로드 실패 — 규칙 폴백 상태(채점 무효)")
    ok = sum(1 for r, p in zip(nof, pred) if p == r["human_decision"])
    flip = sum(1 for r, p in zip(nof, pred)
               if {p, r["human_decision"]} == {"positive", "negative"})
    dist = dict(collections.Counter(pred))
    print("\n=== [D-9] %s (n=%d) ===" % (name, len(nof)))
    print("  정답률 %.2f%% (%d/%d) · 긍↔부 %d · 예측분포 %s"
          % (100.0 * ok / len(nof), ok, len(nof), flip, dist))
    res["D9_fieldless_26"][name] = {"n": len(nof), "correct": ok,
                                    "acc": round(100.0 * ok / len(nof), 2),
                                    "posneg_flip": flip, "pred_dist": dist,
                                    "n_field_applied": sum(1 for f in fields if f)}
    if name == "③ 전량 장점 가정":
        for r, p in zip(nof, pred):
            if p != r["human_decision"]:
                print("    남는 오답: %s → %s | %s" % (r["human_decision"], p, r["text"][:50]))

# ── D-8 : 260715 교정 62건이 자기 칸과 모순되는가 ─────────────────────────────
w = [r for r in rows if r["stratum"] == "260715_withdrawn"]
EXPECT = {"장점": "positive", "단점": "negative"}          # 칸이 시사하는 극성
contra = [r for r in w                                      # 칸과 정반대(긍↔부)로 표기된 건
          if {r["human_decision"], EXPECT[r["field"]]} == {"positive", "negative"}]
agree = [r for r in w if r["human_decision"] == EXPECT[r["field"]]]
neu = [r for r in w if r["human_decision"] == "neutral"]

print("\n=== [D-8] 260715 교정 62건 · 사람 표기 vs 자기 칸 ===")
print("  칸과 일치      : %d" % len(agree))
print("  칸과 정반대    : %d   ← 칸 규약을 따르지 않은 표기" % len(contra))
print("  중립 표기      : %d" % len(neu))
for r in contra:
    print("    [%s 칸] human=%s / model=%s | %s"
          % (r["field"], r["human_decision"], r["model_pred"], r["text"][:50]))

# 모델이 긍↔부로 어긋난 13건이 '칸과 정반대 표기' 안에 들어있는지
flip13 = [r for r in w if {r["model_pred"], r["human_decision"]} == {"positive", "negative"}]
in_contra = sum(1 for r in flip13 if r in contra)
model_matches_field = sum(1 for r in flip13 if r["model_pred"] == EXPECT[r["field"]])
print("\n  긍↔부 13건 중 '칸과 정반대 표기'에 해당: %d / %d" % (in_contra, len(flip13)))
print("  긍↔부 13건 중 모델 예측이 칸과 일치     : %d / %d" % (model_matches_field, len(flip13)))

res["D8_withdrawn_62"] = {
    "n": len(w), "human_matches_field": len(agree), "human_contradicts_field": len(contra),
    "human_neutral": len(neu), "posneg_flip": len(flip13),
    "flip_in_contradiction": in_contra, "flip_model_matches_field": model_matches_field,
    "contradiction_rows": [{"field": r["field"], "human": r["human_decision"],
                            "model": r["model_pred"], "text": r["text"]} for r in contra],
}

json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n저장: %s" % OUT)
