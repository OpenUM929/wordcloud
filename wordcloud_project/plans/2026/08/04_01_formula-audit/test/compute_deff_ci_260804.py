# -*- coding: utf-8 -*-
"""결함 1 A안 — 설계효과 보정 Wilson 구간 산출(보고서 삽입값 정본).

z 는 §4-7 정본 도구 compute_wilson_ci_260730.py 와 동일하게 1.96 을 쓴다.
deff 는 실측(measure_design_effect_260804.py)이며, 급내상관 rho=1 은
verify_icc_within_dupgroup_260804.py 로 확정했다(중복 6그룹 전건 판정 동일).
"""
import collections
import io
import json
import math
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

R = "D:/dev/wordcloud/wordcloud_project/plans/2026/07/27_03_completion-report/result"
Z = 1.96


def wilson(p, n, z=Z):
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return 100 * (c - h), 100 * (c + h)


rows = [json.loads(l) for l in open(os.path.join(R, "blind_judged_400.jsonl"), encoding="utf-8") if l.strip()]
cnt = collections.Counter((r.get("field"), r.get("text")) for r in rows)
n = len(rows)
deff = sum(v * v for v in cnt.values()) / n
neff = n / deff
print("n=%d 고유=%d deff=%.4f n_eff=%.2f" % (n, len(cnt), deff, neff))
print()
print("| 추정 대상 | p̂ | Wilson(n=400) | Wilson(n_eff=%.0f, 보정) | 반폭 변화 |" % neff)
for lbl, k in [("종전 일치율", 253), ("현행 일치율", 374), ("종전 뒤바뀜률", 31), ("현행 뒤바뀜률", 4)]:
    p = k / n
    a = wilson(p, n)
    b = wilson(p, neff)
    print("| %s | %.2f%% | %.2f ~ %.2f | **%.2f ~ %.2f** | %.2f → %.2f%%p |"
          % (lbl, 100 * p, a[0], a[1], b[0], b[1], (a[1] - a[0]) / 2, (b[1] - b[0]) / 2))
print()
lo = wilson(374 / n, neff)[0]
cap = wilson(294 / n, n)  # 라벨 단독 상한 73.50%
print("현행 일치율 보정 하한 %.2f%% vs 라벨 단독 상한 73.50%% → 초과폭 %.2f%%p" % (lo, lo - 73.50))
print("라벨 단독 상한 Wilson(n=400) %.2f ~ %.2f / 보정 %.2f ~ %.2f"
      % (cap[0], cap[1], *wilson(294 / n, neff)))
