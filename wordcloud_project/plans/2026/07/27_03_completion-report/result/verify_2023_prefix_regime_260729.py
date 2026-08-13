# -*- coding: utf-8 -*-
"""2023년 본배치(batch_20260713_0)가 **필드 프리픽스를 적용해 판정했는지** 문장 단위로 검정한다.

동기: 3개 연도 센서스 검산 중, 합본 산출물 `data/23.csv` 의 y 총계
      (p 579,252 / u 263,181 / n 183,201) 가 2026-07-29 칸별 재추출본에
      필드 프리픽스를 적용해 재추론한 총계와 **세 값 모두 정확히 일치**함을 발견했다.
      6자리 수 3개가 우연히 일치할 확률은 사실상 0이므로, 본배치도 프리픽스를
      적용했을 가능성이 높다. 이는 보고서 Ⅲ-1(연도별 전수 판정 분포)이
      **프리픽스 없이** 재추론한 값이라는 점과 충돌하므로 문장 단위로 확정한다.

방법: 재추출본에서 (칸, 문장) → ① 재추론 라벨(pred 캐시) ② 추출본 y(엔진) 를 만든 뒤,
      한쪽 칸에만 등장하는 문장(= 칸이 유일하게 결정되는 문장)에 한해
      `23.csv` 의 y 와 대조한다. 양쪽 칸에 다 나오는 문장(8,693 고유)은 제외한다.

산출: result/prefix_regime_2023_260729.json
"""
import collections
import json
import os
import sys

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE = os.path.dirname(os.path.abspath(__file__))
D = "D:/dev/wordcloud/data/"
SRC = {"장점": D + "23\ub144 \uc7a5\uc810.csv", "단점": D + "23\ub144 \ub2e8\uc810.csv"}
ALL = D + "23.csv"
CACHE = os.path.join(BASE, "field_census_2023_full_260729_pred.cache")
FMAP = {"장점": "positive", "단점": "negative"}
YMAP = {"p": "positive", "n": "negative", "u": "neutral"}

# ── 1. 재추출본 재로드 (센서스와 동일 순서로 keys 재현) ──────────────
occ = collections.Counter()
engy = collections.defaultdict(collections.Counter)   # (칸,문장) -> 엔진라벨 카운트
for f, path in SRC.items():
    for i, line in enumerate(open(path, encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if i == 0 and "#" in r:
            continue
        t = (r.get("x") or "").strip()
        ff = (r.get("f") or f).strip()
        if not t or ff not in FMAP:
            continue
        occ[(ff, t)] += 1
        engy[(ff, t)][YMAP.get(r.get("y"), "?")] += 1
keys = list(occ)

with open(CACHE, encoding="utf-8") as fh:
    n_hdr = fh.readline().strip()
    pred = fh.readline().strip().split(",")
assert n_hdr == str(len(keys)) and len(pred) == len(keys), "캐시가 현재 입력과 불일치 — 센서스를 다시 돌려라"
predmap = dict(zip(keys, pred))

# ── 2. 문장 → 칸 유일성 판정 ─────────────────────────────────────────
fields_of = collections.defaultdict(set)
for f, t in keys:
    fields_of[t].add(f)
uniq_field = {t: next(iter(fs)) for t, fs in fields_of.items() if len(fs) == 1}
print(f"고유 문장 {len(fields_of):,} | 칸 유일 {len(uniq_field):,} | 양쪽 칸 {len(fields_of) - len(uniq_field):,}")

# ── 3. 23.csv 와 대조 ────────────────────────────────────────────────
cmp_model = collections.Counter()      # (23.csv y, 재추론 라벨) -> 행수
cmp_engine = collections.Counter()     # (23.csv y, 재추출본 엔진 y) -> 행수
n_rows = n_cmp = n_skip = 0
seen = collections.Counter()
for i, line in enumerate(open(ALL, encoding="utf-8")):
    line = line.strip()
    if not line:
        continue
    r = json.loads(line)
    if i == 0 and "#" in r:
        continue
    n_rows += 1
    t = (r.get("x") or "").strip()
    f = uniq_field.get(t)
    if not t or not f:
        n_skip += 1
        continue
    y = YMAP.get(r.get("y"), "?")
    n_cmp += 1
    cmp_model[(y, predmap[(f, t)])] += 1
    # 엔진 라벨은 같은 (칸,문장)에 여러 값이 있을 수 있어 최빈값으로 대표
    cmp_engine[(y, engy[(f, t)].most_common(1)[0][0])] += 1
    seen[t] += 1

agree_m = sum(v for (a, b), v in cmp_model.items() if a == b)
agree_e = sum(v for (a, b), v in cmp_engine.items() if a == b)
print(f"23.csv {n_rows:,}행 | 대조 {n_cmp:,} | 제외(양쪽칸 문장) {n_skip:,}")
print(f"  vs 재추론(프리픽스 적용 모델): 일치 {agree_m:,} = {100 * agree_m / n_cmp:.4f}%")
print(f"  vs 재추출본 y(프리픽스 적용 엔진): 일치 {agree_e:,} = {100 * agree_e / n_cmp:.4f}%")

# 프리픽스를 쓰지 않았다면 특히 단점 칸에서 크게 어긋나야 한다 → 칸별로 쪼개 본다
per_field = collections.Counter()
for i, line in enumerate(open(ALL, encoding="utf-8")):
    line = line.strip()
    if not line:
        continue
    r = json.loads(line)
    if i == 0 and "#" in r:
        continue
    t = (r.get("x") or "").strip()
    f = uniq_field.get(t)
    if not t or not f:
        continue
    y = YMAP.get(r.get("y"), "?")
    per_field[(f, y == predmap[(f, t)])] += 1

res = dict(
    n_rows_23csv=n_rows, n_compared=n_cmp, n_excluded_both_fields=n_skip,
    vs_model_prefix=dict(agree=agree_m, agree_pct=round(100 * agree_m / n_cmp, 4),
                         confusion={f"{a}->{b}": v for (a, b), v in sorted(cmp_model.items())}),
    vs_engine_prefix=dict(agree=agree_e, agree_pct=round(100 * agree_e / n_cmp, 4),
                          confusion={f"{a}->{b}": v for (a, b), v in sorted(cmp_engine.items())}),
    per_field_agreement={f"{f}": dict(agree=per_field[(f, True)], disagree=per_field[(f, False)],
                                      agree_pct=round(100 * per_field[(f, True)] /
                                                      max(per_field[(f, True)] + per_field[(f, False)], 1), 4))
                         for f in ("장점", "단점")},
)
for f, v in res["per_field_agreement"].items():
    print(f"  [{f}] 일치 {v['agree']:,} / 불일치 {v['disagree']:,} = {v['agree_pct']}%")

p = os.path.join(BASE, "prefix_regime_2023_260729.json")
json.dump(res, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("저장:", p)
