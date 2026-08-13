# -*- coding: utf-8 -*-
"""정량적 정당성 지표 산출 — 정보이론 상한 · 유의성 검정 · 비용가중 오류.

배경: 기존 보고서는 정확도·건수 위주였고, "왜 이 설계가 정당한가"를 수식으로
     제시하는 부분이 없었다. 본 스크립트는 이미 산출된 원자료(JSON)만 재사용해
     추가 추론 없이 다음을 계산한다.

  ① 필드 단독 결정규칙의 정확도 상한 (Bayes ceiling)  — 전수 센서스 870,367
  ② 상호정보량 I(Y;F) / 조건부 엔트로피 H(Y|F)        — 전수 센서스 870,367
  ③ McNemar 대응표본 검정 (정확도·긍↔부 반전)         — 무작위 표본 400
  ④ Cohen's kappa 재계산                              — 무작위 표본 400
  ⑤ macro-F1                                          — 검증셋 761
  ⑥ 비용가중 오류율 E[C]                              — 검증셋 761 · 표본 400
  ⑦ 이항비율 신뢰구간 산식 검증                        — 표본 400

산출: result/formal_metrics_260728.json
"""
import collections
import json
import math
import os
import sys

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE = os.path.dirname(os.path.abspath(__file__))
LABS = ["positive", "negative", "neutral"]
J = lambda n: json.load(open(os.path.join(BASE, n), encoding="utf-8"))  # noqa: E731

census = J("field_census_260727.json")
sample = J("blind_sample_260727.json")
ba = J("before_after_metrics_260727.json")
judged = [json.loads(l) for l in open(os.path.join(BASE, "blind_judged_400.jsonl"), encoding="utf-8")]

out = {}

# ── ① 필드 단독 결정규칙의 정확도 상한 ───────────────────────────────────────
# 필드 f만 보는 임의의 결정규칙 g(f)의 정확도 = Σ_f P(f)·P(y=g(f)|f)
# 최대값은 g*(f) = argmax_y P(y|f) 일 때이며, 이것이 필드 단독 방식의 이론 상한.
fld = {}
for name, blk in census["fields"].items():
    n = blk["n"]
    # 센서스 정의: match=필드 라벨과 동일, to_neutral=실제 중립, to_flip=정반대
    if name == "장점":
        dist = {"positive": blk["match"], "neutral": blk["to_neutral"], "negative": blk["to_flip"]}
    else:
        dist = {"negative": blk["match"], "neutral": blk["to_neutral"], "positive": blk["to_flip"]}
    fld[name] = dict(n=n, dist=dist, best_label=max(dist, key=dist.get),
                     best_p=max(dist.values()) / n, s0_label=("positive" if name == "장점" else "negative"))
N = sum(v["n"] for v in fld.values())
ceiling = sum(max(v["dist"].values()) for v in fld.values()) / N
s0_acc = sum(v["dist"][v["s0_label"]] for v in fld.values()) / N
out["field_only_bound"] = dict(
    n=N, ceiling_pct=round(ceiling * 100, 2), s0_acc_pct=round(s0_acc * 100, 2),
    per_field={k: dict(n=v["n"], best_label=v["best_label"], best_pct=round(v["best_p"] * 100, 2),
                       s0_label=v["s0_label"], s0_pct=round(v["dist"][v["s0_label"]] / v["n"] * 100, 2))
               for k, v in fld.items()})

# ── ② 상호정보량 ─────────────────────────────────────────────────────────────
H = lambda ps: -sum(p * math.log2(p) for p in ps if p > 0)  # noqa: E731
marg = collections.Counter()
for v in fld.values():
    for k, c in v["dist"].items():
        marg[k] += c
h_y = H([marg[l] / N for l in LABS])
h_y_f = sum(v["n"] / N * H([v["dist"][l] / v["n"] for l in LABS]) for v in fld.values())
out["information"] = dict(H_Y=round(h_y, 4), H_Y_given_F=round(h_y_f, 4),
                          I_Y_F=round(h_y - h_y_f, 4),
                          explained_ratio_pct=round((h_y - h_y_f) / h_y * 100, 2),
                          residual_ratio_pct=round(h_y_f / h_y * 100, 2),
                          marginal={l: marg[l] for l in LABS})

# ── ③ McNemar (무작위 표본 400, 대응표본) ────────────────────────────────────
dis = {x["no"]: x["model"] for x in sample["disagreements"]}
tab = collections.Counter()
rev = collections.Counter()
for r in judged:
    h = r["claude_judgment"]
    s0 = "positive" if r["field"] == "장점" else "negative"
    m = dis.get(r["no"], h)          # 불일치 목록에 없으면 사람 판정과 동일
    tab[(s0 == h, m == h)] += 1
    rev[({h, s0} == {"positive", "negative"}, {h, m} == {"positive", "negative"})] += 1


def mcnemar(b, c):
    if b + c == 0:
        return None
    chi = (abs(b - c) - 1) ** 2 / (b + c)
    return dict(b=b, c=c, chi2=round(chi, 2), p=float("%.3g" % math.erfc(math.sqrt(chi / 2))))


out["mcnemar_400_accuracy"] = dict(
    both_correct=tab[(True, True)], only_s0=tab[(True, False)],
    only_current=tab[(False, True)], both_wrong=tab[(False, False)],
    **mcnemar(tab[(True, False)], tab[(False, True)]))
out["mcnemar_400_reversal"] = dict(
    only_s0_reversed=rev[(True, False)], only_current_reversed=rev[(False, True)],
    **mcnemar(rev[(True, False)], rev[(False, True)]))

# ── 검증셋 761: 대응 원자료가 없으므로 χ²의 하한만 계산(엄밀 부등식) ─────────
n761 = ba["overall"]["n"]
w_before = round(n761 * (1 - ba["overall"]["before_acc"] / 100))
w_after = round(n761 * (1 - ba["overall"]["after_acc"] / 100))
diff = w_before - w_after                      # = c - b
bc_max = w_after + w_before                    # b ≤ w_after, c ≤ w_before
chi_lo = (diff - 1) ** 2 / bc_max
out["mcnemar_761_bound"] = dict(n=n761, wrong_before=w_before, wrong_after=w_after,
                                c_minus_b=diff, chi2_lower_bound=round(chi_lo, 1),
                                p_upper_bound=float("%.3g" % math.erfc(math.sqrt(chi_lo / 2))))

# ── ④ Cohen's kappa (표본 400) ───────────────────────────────────────────────
def kappa(cm, n):
    po = sum(cm[(l, l)] for l in LABS) / n
    r = collections.Counter()
    c = collections.Counter()
    for (a, b), v in cm.items():
        r[a] += v
        c[b] += v
    pe = sum(r[l] * c[l] for l in LABS) / n ** 2
    return dict(po=round(po, 4), pe=round(pe, 4), kappa=round((po - pe) / (1 - pe), 4))


cm_cur = collections.Counter()
cm_s0 = collections.Counter()
for r in judged:
    h = r["claude_judgment"]
    s0 = "positive" if r["field"] == "장점" else "negative"
    cm_cur[(h, dis.get(r["no"], h))] += 1
    cm_s0[(h, s0)] += 1
out["kappa_400"] = dict(s0=kappa(cm_s0, 400), current=kappa(cm_cur, 400))

# ── ⑤ macro-F1 (검증셋 761) ──────────────────────────────────────────────────
mf = lambda blk: round(sum(blk[l]["f1"] for l in LABS) / 3, 4)  # noqa: E731
out["macro_f1_761"] = dict(before=mf(ba["overall"]["per_class_before"]),
                           after=mf(ba["overall"]["per_class"]))

# ── ⑥ 비용가중 오류율 ────────────────────────────────────────────────────────
# C(긍↔부)=1, C(극성↔중립)=w, C(정답)=0.  w를 흔들어 민감도까지 본다.
def expected_cost(cm, n, w):
    tot = 0.0
    for (a, b), v in cm.items():
        if a == b:
            continue
        tot += v * (1.0 if {a, b} == {"positive", "negative"} else w)
    return tot / n


cm761_b = collections.Counter({tuple(k.split("->")): v for k, v in ba["overall"]["confusion_before"].items()})
cm761_a = collections.Counter({tuple(k.split("->")): v for k, v in ba["overall"]["confusion_after"].items()})
out["expected_cost"] = {}
for w in (0.1, 0.25, 0.5):
    out["expected_cost"]["w=%.2f" % w] = dict(
        set761_before=round(expected_cost(cm761_b, 761, w), 4),
        set761_after=round(expected_cost(cm761_a, 761, w), 4),
        sample400_s0=round(expected_cost(cm_s0, 400, w), 4),
        sample400_current=round(expected_cost(cm_cur, 400, w), 4))

# ── ⑦ 이항비율 신뢰구간 산식 검증 ────────────────────────────────────────────
wald = lambda p, n: 1.96 * math.sqrt(p * (1 - p) / n) * 100  # noqa: E731
out["ci_check"] = dict(
    s0_acc=dict(p=63.25, reported=sample["cell"]["overall"]["acc_ci95"], recomputed=round(wald(0.6325, 400), 2)),
    cur_acc=dict(p=93.5, reported=sample["model"]["overall"]["acc_ci95"], recomputed=round(wald(0.935, 400), 2)),
    cur_rev=dict(p=1.0, reported=sample["model"]["overall"]["posneg_ci95"], recomputed=round(wald(0.01, 400), 2)))

p = os.path.join(BASE, "formal_metrics_260728.json")
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps(out, ensure_ascii=False, indent=2))
print("\n저장:", p)
