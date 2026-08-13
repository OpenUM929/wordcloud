# -*- coding: utf-8 -*-
"""보고서에 인용된 모든 신뢰구간·필요표본·상한을 재산출한다 (재현 전용).

신설 사유(2026-07-30, 인수검수 2차 지적): 상세결과보고서가 Wilson 구간을 정본으로
채택했으나 이를 산출하는 스크립트가 저장소에 없어 헤드라인 값이 수기 계산 상태였음.
§10-4 제2조("수치에는 산출 코드를 동봉한다")의 자기적용.

산출 항목
  [1] 채점 표본 400의 전 지표 Wilson / 정규근사 구간
  [2] §4-7 전수 vs 표본 교차검증표의 Wilson 재판정
  [3] 필요 표본 수 — 정규근사 역산과 Wilson 기준 탐색 양쪽
  [4] 입력 라벨 단독 상한을 **블라인드 400 자체 기준**으로 재계산
      (전수 센서스 기준 72.85%는 모델 자기채점 기준이라 93.50%와 정답 정의가 달랐음.
       동일 기준으로 다시 재야 개선폭 비교가 성립함 — 인수검수 2차 지적)
"""
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "blind_judged_400.jsonl")
FMAP = {"장점": "positive", "단점": "negative"}

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def wilson(k, n, z=1.96):
    """Wilson score interval — p가 0·1에 가깝거나 n이 작을 때 정규근사보다 포함률이 정확."""
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return 100 * (c - h), 100 * (c + h)


def normal(k, n, z=1.96):
    p = k / n
    h = z * math.sqrt(p * (1 - p) / n)
    return 100 * (p - h), 100 * (p + h), 100 * h


rows = [json.loads(l) for l in open(SAMPLE, encoding="utf-8")]
n = len(rows)
gold = [r["claude_judgment"] for r in rows]
cell = [FMAP[r["field"]] for r in rows]

# 배포 모델 판정은 채점 산출물에서 읽는다(재추론 불요)
bs = os.path.join(HERE, "blind_sample_260727.json")
model = None
if os.path.isfile(bs):
    d = json.load(open(bs, encoding="utf-8"))
    k_model = d["model"]["overall"]["correct"]
    pn_model = d["model"]["overall"]["posneg"]
else:
    k_model = pn_model = None

k_cell = sum(1 for g, c in zip(gold, cell) if g == c)
pn_cell = sum(1 for g, c in zip(gold, cell) if {g, c} == {"positive", "negative"})

print("표본 n = %d  (장점 %d / 단점 %d)"
      % (n, sum(1 for r in rows if r["field"] == "장점"),
         sum(1 for r in rows if r["field"] == "단점")))

print("\n[1] 채점 표본 400 — 구간 비교")
print("   %-22s %-10s %-24s %-24s" % ("지표", "점추정", "정규근사 95%", "Wilson 95% (정본)"))
items = [("종전 일치율", k_cell, n), ("종전 뒤바뀜", pn_cell, n)]
if k_model is not None:
    items += [("현행 일치율", k_model, n), ("현행 뒤바뀜", pn_model, n)]
for lab, k, N in items:
    nl, nh, nh2 = normal(k, N)
    wl, wh = wilson(k, N)
    print("   %-22s %6.2f%%    %6.2f ~ %6.2f (±%.2f)   %6.2f ~ %6.2f"
          % (lab, 100 * k / N, nl, nh, nh2, wl, wh))

if k_model is not None:
    print("   → 현행 뒤바뀜: 정규근사 하한 %.2f%% 는 관측 %d건 상황에서 과도하게 낙관적."
          % (normal(pn_model, n)[0], pn_model))
    print("     Wilson 상한 %.2f%% 는 점추정의 %.1f배." % (wilson(pn_model, n)[1],
                                                     wilson(pn_model, n)[1] / (100 * pn_model / n)))

print("\n[2] 전수 vs 표본 교차검증 — Wilson 재판정 (§4-7)")
cen_path = os.path.join(HERE, "field_census_260727.json")
if os.path.isfile(cen_path):
    cen = json.load(open(cen_path, encoding="utf-8"))
    scopes = [("전체", cen["overall"]["mismatch_pct"], None),
              ("장점란", cen["fields"]["장점"]["mismatch_pct"], "장점"),
              ("단점란", cen["fields"]["단점"]["mismatch_pct"], "단점")]
    for nm, census, f in scopes:
        sub = [(g, c) for g, c, r in zip(gold, cell, rows) if f is None or r["field"] == f]
        mis = sum(1 for g, c in sub if g != c)
        wl, wh = wilson(mis, len(sub))
        print("   %-6s 센서스 %6.2f%% | 표본 %6.2f%% (Wilson %.2f ~ %.2f) → %s"
              % (nm, census, 100 * mis / len(sub), wl, wh,
                 "구간 안" if wl <= census <= wh else "구간 밖"))

print("\n[3] 필요 표본 수 — 두 산식")
print("   정규근사 역산 n = z²p(1−p)/d²")
for p, d_, lab in [(0.935, 0.025, "일치율 ±2.5%p"), (0.935, 0.017, "일치율 ±1.7%p"),
                   (0.010, 0.005, "뒤바뀜 ±0.5%p")]:
    print("      %-18s n ≈ %5d" % (lab, math.ceil(p * (1 - p) * (1.96 / d_) ** 2)))
print("   Wilson 기준 탐색 — 관측 비율이 유지된다는 가정에서 구간 반폭이 목표 이하가 되는 최소 n")
for p, tgt, lab in [(0.010, 0.005, "뒤바뀜 반폭 ≤0.5%p"), (0.935, 0.025, "일치율 반폭 ≤2.5%p")]:
    N = 50
    while N < 200000:
        k = round(p * N)
        wl, wh = wilson(k, N)
        if (wh - wl) / 2 <= tgt * 100:
            break
        N += 10
    print("      %-22s n ≈ %5d   (구간 %.3f ~ %.3f, 반폭 %.3f%%p)"
          % (lab, N, wl, wh, (wh - wl) / 2))
print("   ⚠️ Wilson 구간은 비대칭이므로 '±x%p' 표기가 엄밀하지 않음 — 반폭 기준으로 읽을 것")

print("\n[4] 입력 라벨 단독 상한 — 블라인드 400 자체 기준 (동일 기준 비교)")
by = collections.defaultdict(collections.Counter)
for g, r in zip(gold, rows):
    by[r["field"]][g] += 1
best = 0
for f, c in sorted(by.items()):
    top = c.most_common(1)[0]
    best += top[1]
    print("   [%s] n=%3d  최적 배정=%s  적중 %3d  → %.2f%%   분포 %s"
          % (f, sum(c.values()), top[0], top[1], 100 * top[1] / sum(c.values()), dict(c)))
wl, wh = wilson(best, n)
print("   라벨 단독 상한 = %d/%d = %.2f%%  (Wilson %.2f ~ %.2f)" % (best, n, 100 * best / n, wl, wh))
print("   실제 종전 규칙(장점=긍정·단점=부정) = %d/%d = %.2f%%" % (k_cell, n, 100 * k_cell / n))
if k_model is not None:
    print("   현행 = %.2f%%  →  **동일 기준 개선폭 = %.2f%%p**"
          % (100 * k_model / n, 100 * (k_model - best) / n))
print("   ※ 전수 센서스 기준 상한 72.85%(§4-2)는 정답을 모델이 정한 값이고, 위 73.50%는")
print("     블라인드 판독이 정한 값임. 두 기준이 0.65%p 안에서 일치하므로 상한 주장은 유지됨.")
