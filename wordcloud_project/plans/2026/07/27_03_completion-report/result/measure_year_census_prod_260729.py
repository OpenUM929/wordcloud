# -*- coding: utf-8 -*-
"""연도별 전수 판정 분포 — **실제 배치 산출물 그대로** 재집계 (2023·2024·2025).

정정 배경: 종전 `measure_year_census_260727.py` 는 `weak_export_260714.jsonl` 의 문장을
  **필드 프리픽스 없이 재추론**해 분포를 냈다("실제 배치가 필드 없이 실행되었다"는 전제,
  같은 파일 :15 주석). 2026-07-29 검정에서 이 전제가 **거짓**임이 확정됐다 —
  `verify_2023_prefix_regime_260729.py` 결과 `data/23.csv` 의 y 가 필드 프리픽스를
  적용한 재추론과 **769,406행 100.0000% 일치**(칸별로도 불일치 0)했다.
  24·25년 산출물의 분포(칭찬 56.38% / 56.58%)도 프리픽스 적용 결과와 일치하고
  프리픽스 없는 재추론값(51.94% / 52.50%)과는 4%p 이상 어긋난다.

따라서 "시스템이 실제로 무엇을 출력했는가"는 재추론이 아니라 **배치 산출물 자체**로
집계해야 한다. 본 스크립트는 `data/{23,24,25}.csv` 의 y 를 그대로 세며 추론하지 않는다.

산출: result/yearcensus_prod_260729.json
"""
import collections
import json
import os
import re
import sys

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE = os.path.dirname(os.path.abspath(__file__))
D = "D:/dev/wordcloud/data/"
FILES = {"2023": D + "23.csv", "2024": D + "24.csv", "2025": D + "25.csv"}
YMAP = {"p": "positive", "n": "negative", "u": "neutral"}
LABS = ["positive", "neutral", "negative"]
# 종전 스크립트와 **동일한** 판정식을 쓴다(비교 가능성 유지) — measure_year_census_260727.py:33,104
NOWEAK = re.compile(r"(없습니다|없음|없슴|없다|없으며|해당\s*없|미해당|특이사항)")

out = {"note": "배치 산출물(data/*.csv)의 y 를 그대로 집계. 추론 없음. y = 배포 엔진이 실제로 낸 라벨.",
       "noweak_rule": "정규식 (없습니다|없음|없슴|없다|없으며|해당\\s*없|미해당|특이사항) AND 길이<=30 — 종전 스크립트와 동일",
       "years": {}}
grand = collections.Counter()
grand_nw = collections.Counter()
grand_n = 0

for y, path in FILES.items():
    batch = None
    lab = collections.Counter()
    occ = collections.Counter()
    nw_n = 0
    nw_lab = collections.Counter()
    nw_uniq = set()
    for i, line in enumerate(open(path, encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if i == 0 and "#" in r:
            batch = r.get("batch")
            continue
        t = (r.get("x") or "").strip()
        if not t:
            continue
        l = YMAP.get(r.get("y"), "?")
        lab[l] += 1
        occ[t] += 1
        if len(t) <= 30 and NOWEAK.search(t):
            nw_n += 1
            nw_lab[l] += 1
            nw_uniq.add(t)
    n = sum(lab.values())
    blk = dict(
        source=path, batch=batch, n_sentences=n, n_unique=len(occ),
        dist={l: lab[l] for l in LABS},
        pct={l: round(100 * lab[l] / n, 2) for l in LABS},
        no_weakness=dict(n=nw_n, pct=round(100 * nw_n / n, 2), unique=len(nw_uniq),
                         label={l: nw_lab[l] for l in LABS},
                         neutral_pct=round(100 * nw_lab["neutral"] / max(nw_n, 1), 2)),
        top_repeated=[dict(n=c, pct=round(100 * c / n, 3), text=t) for t, c in occ.most_common(10)],
    )
    out["years"][y] = blk
    grand.update(lab)
    grand_nw.update(nw_lab)
    grand_n += n
    print(f"=== {y} ({batch}) 문장 {n:,} / 고유 {len(occ):,}")
    print("    " + " | ".join(f"{l} {lab[l]:,} ({blk['pct'][l]}%)" for l in LABS))
    print(f"    '보완할 점 없음'류 {nw_n:,} ({blk['no_weakness']['pct']}%, 고유 {len(nw_uniq):,})"
          f" → 중립 분리 {blk['no_weakness']['neutral_pct']}%")
    print(f"    최다 반복 1위: {occ.most_common(1)[0][1]:,}회")

nwt = sum(grand_nw.values())
out["total"] = dict(
    n_sentences=grand_n, dist={l: grand[l] for l in LABS},
    pct={l: round(100 * grand[l] / grand_n, 2) for l in LABS},
    no_weakness=dict(n=nwt, pct=round(100 * nwt / grand_n, 2),
                     label={l: grand_nw[l] for l in LABS},
                     neutral_pct=round(100 * grand_nw["neutral"] / max(nwt, 1), 2)),
)
print(f"\n=== 3개 연도 합계 문장 {grand_n:,}")
print("    " + " | ".join(f"{l} {grand[l]:,} ({out['total']['pct'][l]}%)" for l in LABS))
print(f"    '보완할 점 없음'류 {nwt:,} ({out['total']['no_weakness']['pct']}%)"
      f" → 중립 분리 {out['total']['no_weakness']['neutral_pct']}%")

p = os.path.join(BASE, "yearcensus_prod_260729.json")
json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n저장:", p)
