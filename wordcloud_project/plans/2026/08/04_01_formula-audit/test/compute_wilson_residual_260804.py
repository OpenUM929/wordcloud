# -*- coding: utf-8 -*-
"""결함 4 — 정규근사가 정본 CI 로 잔존한 3곳의 Wilson 대체값 산출.

대상
  [1] 구축완료보고서_260727.md:237  전수 vs 표본 교차검증표(불일치율 3종)
  [2] 구축완료보고서_260727.md:505  채점 결과표(일치율 6종, 현재 ± 정규근사)
  [3] MODEL_CARD_260730.md:94       입력 칸별 표(일치율 2종, 이 표의 유일한 CI)

원자료는 blind_sample_260727.json(집계 산출물)이며, z·산식은
compute_wilson_ci_260730.py(§4-7 정본 도구)와 동일하게 z=1.96 을 쓴다.
"""
import io
import json
import math
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

R = "D:/dev/wordcloud/wordcloud_project/plans/2026/07/27_03_completion-report/result"
d = json.load(open(os.path.join(R, "blind_sample_260727.json"), encoding="utf-8"))


def wilson(k, n, z=1.96):
    p = k / n
    dd = 1 + z * z / n
    c = (p + z * z / (2 * n)) / dd
    h = z / dd * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return 100 * (c - h), 100 * (c + h)


def normal(k, n, z=1.96):
    p = k / n
    return 100 * z * math.sqrt(p * (1 - p) / n)


print("[1] 구축완료:237 — 전수 vs 표본 교차검증(불일치율)")
cen = json.load(open(os.path.join(R, "field_census_260727.json"), encoding="utf-8"))
for nm, key, census in [("전체", "overall", cen["overall"]["mismatch_pct"]),
                        ("장점란", "장점", cen["fields"]["장점"]["mismatch_pct"]),
                        ("단점란", "단점", cen["fields"]["단점"]["mismatch_pct"])]:
    c = d["cell"][key]
    lo, hi = wilson(c["mismatch"], c["n"])
    nh = normal(c["mismatch"], c["n"])
    print("  %-5s 센서스 %6.2f%% | 표본 %6.2f%% (%d/%d)  정규근사 %5.2f~%5.2f  →  Wilson %5.2f~%5.2f  %s"
          % (nm, census, c["mismatch_pct"], c["mismatch"], c["n"],
             c["mismatch_pct"] - nh, c["mismatch_pct"] + nh, lo, hi,
             "구간 안" if lo <= census <= hi else "구간 밖 🔴"))

print()
print("[2] 구축완료:505 채점 결과표 · [3] MODEL_CARD:94 칸별표 — 일치율")
for grp, tag in [("cell", "기존(라벨=극성)"), ("model", "현행(7/8 배포본)")]:
    for key, nm in [("overall", "전체"), ("장점", "장점란"), ("단점", "단점란")]:
        c = d[grp][key]
        lo, hi = wilson(c["correct"], c["n"])
        print("  %-16s %-4s n=%3d  %6.2f%%  ± %.2f(정규근사)  →  Wilson %6.2f ~ %6.2f (반폭 %.2f%%p)"
              % (tag, nm, c["n"], c["acc"], c["acc_ci95"], lo, hi, (hi - lo) / 2))

print()
print("[참고] 긍↔부 뒤바뀜 Wilson (표에 병기하지 않으나 대조용)")
for grp, tag in [("cell", "기존"), ("model", "현행")]:
    for key, nm in [("overall", "전체"), ("장점", "장점란"), ("단점", "단점란")]:
        c = d[grp][key]
        lo, hi = wilson(c["posneg"], c["n"])
        print("  %-4s %-4s %d/%d = %5.2f%%  Wilson %5.2f ~ %5.2f" % (tag, nm, c["posneg"], c["n"], c["posneg_pct"], lo, hi))
