# -*- coding: utf-8 -*-
"""3개 연도(2023·2024·2025) 칸 라벨 대조 — 합계 재집계 + 정보이론 상한 재산출.

배경: 2026-07-28까지 2023년은 칸 정보가 없어 27.95% 구간 실측 + 편향보정 **추정치**였다.
     2026-07-29 칸별 재추출본으로 전수 확정값을 얻었으므로, 여기서
     ① 3개 연도 합계를 재집계하고
     ② 필드 단독 결정규칙의 정확도 상한(Bayes ceiling)·상호정보량을 3개 연도로 확장하고
     ③ 종전 추정치(32.1% / 4.4%)가 실제와 얼마나 어긋났는지 검증한다.

입력(모두 기존 산출물, 추가 추론 없음):
  field_census_260727.json        2024년 전수 (870,367)
  field_census_2025_260728.json   2025년 전수 (739,918)
  field_census_2023_full_260729.json  2023년 전수 (1,025,634)  ← 신규
  field_census_2023_260728.json   2023년 종전 추정의 실측 구간(286,062) — 검증용

산출: result/field_census_3y_260729.json
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
S0 = {"장점": "positive", "단점": "negative"}
FLIP = {"장점": "negative", "단점": "positive"}
J = lambda n: json.load(open(os.path.join(BASE, n), encoding="utf-8"))  # noqa: E731

SRC = {
    "2023": "field_census_2023_full_260729.json",
    "2024": "field_census_260727.json",
    "2025": "field_census_2025_260728.json",
}


def dist_of(field, blk):
    """센서스 블록 → 라벨 분포. match=칸라벨 그대로, to_neutral=중립, to_flip=정반대."""
    return {S0[field]: blk["match"], "neutral": blk["to_neutral"], FLIP[field]: blk["to_flip"]}


# ── 1. 연도별 로드 + 검산 ─────────────────────────────────────────────
years = {}
for y, fn in SRC.items():
    d = J(fn)
    fields = {}
    for f in ("장점", "단점"):
        blk = d["fields"][f]
        dd = dist_of(f, blk)
        assert sum(dd.values()) == blk["n"], (y, f, "칸 내부 합 불일치")
        fields[f] = dict(n=blk["n"], dist=dd)
    n = sum(v["n"] for v in fields.values())
    assert n == d["n_sentences"], (y, "칸 합 != 문장 수", n, d["n_sentences"])
    years[y] = dict(n=n, fields=fields)
    print(f"{y}: 문장 {n:,} (장점 {fields['장점']['n']:,} / 단점 {fields['단점']['n']:,}) — 검산 통과")

# ── 2. 3개 연도 합계 ─────────────────────────────────────────────────
comb = {f: collections.Counter() for f in ("장점", "단점")}
for y in years:
    for f in comb:
        comb[f].update(years[y]["fields"][f]["dist"])
years["3y"] = dict(n=sum(sum(c.values()) for c in comb.values()),
                   fields={f: dict(n=sum(c.values()), dist=dict(c)) for f, c in comb.items()})


def summarize(blk):
    """칸 라벨을 그대로 극성으로 쓰는 종전 방식(S0)의 성적 + 필드단독 상한 + 정보량."""
    N = blk["n"]
    row = {"n": N, "per_field": {}}
    match = flip = to_neu_weak = 0
    for f, v in blk["fields"].items():
        d, nf = v["dist"], v["n"]
        row["per_field"][f] = dict(
            n=nf,
            match=d[S0[f]], match_pct=round(100 * d[S0[f]] / nf, 2),
            to_neutral=d["neutral"], to_neutral_pct=round(100 * d["neutral"] / nf, 2),
            to_flip=d[FLIP[f]], to_flip_pct=round(100 * d[FLIP[f]] / nf, 2),
            best_label=max(d, key=d.get), best_pct=round(100 * max(d.values()) / nf, 2),
        )
        match += d[S0[f]]
        flip += d[FLIP[f]]
        if f == "단점":
            to_neu_weak = d["neutral"]
    row["s0"] = dict(
        correct=match, accuracy_pct=round(100 * match / N, 2),
        mismatch=N - match, mismatch_pct=round(100 * (N - match) / N, 2),
        flip=flip, flip_pct=round(100 * flip / N, 2),
        # 실제로는 중립인데 종전 방식이 '불만'으로 계산한 건수 = 단점 칸의 중립
        neutral_counted_as_negative=to_neu_weak,
        neutral_counted_as_negative_pct=round(100 * to_neu_weak / N, 2),
    )
    # 필드 단독 결정규칙의 정확도 상한 (Bayes ceiling)
    ceiling = sum(max(v["dist"].values()) for v in blk["fields"].values()) / N
    row["field_only_ceiling_pct"] = round(100 * ceiling, 2)
    row["s0_gap_to_ceiling_pp"] = round(100 * (ceiling - match / N), 2)
    # 상호정보량
    H = lambda ps: -sum(p * math.log2(p) for p in ps if p > 0)  # noqa: E731
    marg = collections.Counter()
    for v in blk["fields"].values():
        marg.update(v["dist"])
    h_y = H([marg[l] / N for l in LABS])
    h_y_f = sum(v["n"] / N * H([v["dist"][l] / v["n"] for l in LABS]) for v in blk["fields"].values())
    row["information"] = dict(
        H_Y=round(h_y, 4), H_Y_given_F=round(h_y_f, 4), I_Y_F=round(h_y - h_y_f, 4),
        explained_ratio_pct=round(100 * (h_y - h_y_f) / h_y, 2),
        residual_ratio_pct=round(100 * h_y_f / h_y, 2),
        marginal={l: marg[l] for l in LABS},
    )
    return row


out = {"note": "칸 라벨(장점=긍정/단점=부정) 대비 배포 모델(2026-07-08 seed45) 판정. 전수·추정 없음.",
       "sources": SRC, "years": {y: summarize(blk) for y, blk in years.items()}}

for y in ("2023", "2024", "2025", "3y"):
    r = out["years"][y]
    s = r["s0"]
    print(f"\n=== {y} | 대조 {r['n']:,}건")
    print(f"  종전방식 정답률 {s['accuracy_pct']}% | 불일치 {s['mismatch']:,} ({s['mismatch_pct']}%)"
          f" | 뒤바뀜 {s['flip']:,} ({s['flip_pct']}%)")
    print(f"  실제 중립인데 불만으로 계산 {s['neutral_counted_as_negative']:,}"
          f" ({s['neutral_counted_as_negative_pct']}%)")
    print(f"  필드단독 상한 {r['field_only_ceiling_pct']}% | 정보량 H(Y)={r['information']['H_Y']}"
          f" I={r['information']['I_Y_F']} ({r['information']['explained_ratio_pct']}%)")
    for f, v in r["per_field"].items():
        print(f"    [{f}] {v['n']:,} | 칸대로 {v['match_pct']}% | 중립 {v['to_neutral_pct']}%"
              f" | 정반대 {v['to_flip_pct']}%")

# ── 3. 종전 추정치 검증 ───────────────────────────────────────────────
est = J("field_census_2023_260728.json")
bias = J("transfer_bias_260728.json") if os.path.exists(os.path.join(BASE, "transfer_bias_260728.json")) else {}
act = out["years"]["2023"]["s0"]
out["estimate_check_2023"] = dict(
    method="2024·2025 확정본에서 동일 문장 칸 이관(커버 27.95%) + 편향계수 보정",
    resolved_n=est["n_field_resolved"], resolved_mismatch_pct=est["overall"]["mismatch_pct"],
    resolved_flip_pct=est["overall"]["flip_pct"],
    estimated_mismatch_pct=32.1, actual_mismatch_pct=act["mismatch_pct"],
    mismatch_error_pp=round(act["mismatch_pct"] - 32.1, 2),
    estimated_flip_pct=4.4, actual_flip_pct=act["flip_pct"],
    flip_error_pp=round(act["flip_pct"] - 4.4, 2),
    flip_estimate_ratio=round(4.4 / act["flip_pct"], 3),
    bias_coefficients=bias.get("coefficients") or bias,
    verdict=("불일치율은 근사했으나(오차 %.2f%%p) 뒤바뀜은 실제의 %.0f%% 수준으로 크게 과소추정. "
             "이관 구간이 반복 상용구(중립)에 몰려 뒤바뀜 편향계수가 어긋난 것이 원인."
             % (act["mismatch_pct"] - 32.1, 100 * 4.4 / act["flip_pct"])),
)
print("\n=== 종전 추정 검증 ===")
print(f"  불일치: 추정 32.1% → 실제 {act['mismatch_pct']}% (오차 {act['mismatch_pct'] - 32.1:+.2f}%p)")
print(f"  뒤바뀜: 추정 4.4% → 실제 {act['flip_pct']}% (실제의 {100 * 4.4 / act['flip_pct']:.0f}% 수준)")

p = os.path.join(BASE, "field_census_3y_260729.json")
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n저장:", p)
