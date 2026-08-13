# -*- coding: utf-8 -*-
"""누출 배제 후 재계산 — 채점 표본 400건에서 학습 노출분을 제거하고 지표를 다시 낸다.

배경: §4-10 ④ 은 "400건 중 8건이 학습 자료와 중복(누출)"으로 부분 미비 판정을 받았음.
      누출 통제의 요건은 '누출 0'이 아니라 **검출·정량화·배제 후 재보고**이므로
      본 스크립트가 배제본을 산출해 정본 표기에 병기한다.

입력:
  - blind_judged_400.jsonl        판독 기준(정답 칸 claude_judgment)
  - blind_sample_260727.json      배포 모델 채점 결과(불일치 목록으로 행별 예측 복원)
  - 학습 파일 목록                finetune_sentiment.TRAIN_FILES (배제 대상 판정용)

출력: leakage_free_260730.json
"""
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
EVAL = os.path.join(DS, "eval")
LABELS = ("positive", "negative", "neutral")
FMAP = {"장점": "positive", "단점": "negative"}

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass
sys.path.insert(0, os.path.join(DS, "scripts"))
from finetune_sentiment import TRAIN_FILES  # noqa: E402


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return 100 * (c - h), 100 * (c + h)


rows = [json.loads(l) for l in open(os.path.join(HERE, "blind_judged_400.jsonl"), encoding="utf-8")]
res = json.load(open(os.path.join(HERE, "blind_sample_260727.json"), encoding="utf-8"))

# 행별 모델 예측 복원 — 불일치 목록에 없는 행은 판독 기준과 같음
mis = {d["no"]: d["model"] for d in res["disagreements"]}
for r in rows:
    r["model"] = mis.get(r["no"], r["claude_judgment"])
assert sum(1 for r in rows if r["model"] != r["claude_judgment"]) == len(mis)

# 학습 노출 키 수집
train = set()
for fn in TRAIN_FILES:
    p = os.path.join(EVAL, fn)
    if not os.path.isfile(p):
        continue
    for line in open(p, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("human_decision") in LABELS and (r.get("text") or "").strip():
            train.add(((r.get("field") or ""), (r.get("text") or "").strip()))

for r in rows:
    r["leaked"] = ((r["field"], r["text"].strip()) in train)
leaked = [r for r in rows if r["leaked"]]
clean = [r for r in rows if not r["leaked"]]
print(f"전체 {len(rows)}건 / 학습 노출 {len(leaked)}건 배제 → 누출 배제본 {len(clean)}건")
for r in leaked:
    print(f"   배제 #{r['no']:>3d} [{r['field']}] 기준={r['claude_judgment']:8s} "
          f"모델={r['model']:8s} | {r['text'][:40]}")


def score(name, subset, key):
    n = len(subset)
    got = [FMAP[r["field"]] if key == "cell" else r[key] for r in subset]
    ok = sum(1 for r, g in zip(subset, got) if r["claude_judgment"] == g)
    pn = sum(1 for r, g in zip(subset, got) if {r["claude_judgment"], g} == {"positive", "negative"})
    lo, hi = wilson(ok, n)
    plo, phi = wilson(pn, n)
    print(f"   {name:22s} n={n:3d}  일치 {100*ok/n:6.2f}% (Wilson {lo:.2f}~{hi:.2f})  "
          f"긍↔부 {pn}건 {100*pn/n:.2f}% (Wilson {plo:.2f}~{phi:.2f})")
    return dict(n=n, correct=ok, acc=round(100 * ok / n, 2), acc_wilson=[round(lo, 2), round(hi, 2)],
                posneg=pn, posneg_pct=round(100 * pn / n, 2),
                posneg_wilson=[round(plo, 2), round(phi, 2)])


out = {"n_all": len(rows), "n_leaked": len(leaked), "n_clean": len(clean),
       "leaked_rows": [dict(no=r["no"], field=r["field"], text=r["text"],
                            ref=r["claude_judgment"], model=r["model"]) for r in leaked]}

print("\n[A] 배포 모델 (현행)")
out["model_all"] = score("전체 400건", rows, "model")
out["model_clean"] = score("누출 배제 392건", clean, "model")
print("\n[B] 입력 칸 라벨 (도입 이전 방식)")
out["cell_all"] = score("전체 400건", rows, "cell")
out["cell_clean"] = score("누출 배제 392건", clean, "cell")

d_all = out["model_all"]["acc"] - out["cell_all"]["acc"]
d_cln = out["model_clean"]["acc"] - out["cell_clean"]["acc"]
out["gain_all"] = round(d_all, 2)
out["gain_clean"] = round(d_cln, 2)
print(f"\n[C] 동일 기준 개선폭   전체 {d_all:+.2f}%p / 누출 배제 {d_cln:+.2f}%p "
      f"(차이 {abs(d_all-d_cln):.2f}%p)")

# 누출 8건이 모델에 유리하게 작용했는지 방향 확인
lk_ok = sum(1 for r in leaked if r["model"] == r["claude_judgment"])
print(f"[D] 배제된 {len(leaked)}건에서 모델 일치 = {lk_ok}/{len(leaked)} "
      f"→ 누출은 성능을 {'과대' if lk_ok/len(leaked) > out['model_clean']['acc']/100 else '과소'}평가 방향")
out["leaked_model_correct"] = lk_ok

json.dump(out, open(os.path.join(HERE, "leakage_free_260730.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n저장:", os.path.join(HERE, "leakage_free_260730.json"))
