# -*- coding: utf-8 -*-
"""표본 추출기(정본) — 추출을 재현 가능하게 만들고, 추출물이 눈가림을 구조적으로 강제하게 한다.

배경: §4-10 ⑫ 는 "400건을 뽑은 코드가 저장소에 없어 추출 재현 불가"로 부분 미비 판정을 받았음.
      과거 추출은 소급 재현할 수 없으므로, **이후 모든 추출을 이 스크립트로만 하도록** 정본을 둔다.
      §10-4 제2조(재현 스크립트)·제9조(판독 절차 기록)의 집행 수단이다.

설계 원칙
  1. 모집단 지문을 남긴다 — 원본 파일 크기·행 수·고유 키 수·SHA-256 을 매니페스트에 기록
  2. 출력 파일에 정답·모델 예측 칸을 **넣지 않는다** — 눈가림을 구조로 강제
  3. 시드·추출시각·파라미터를 매니페스트에 기록 — 동일 시드면 동일 표본이 재현됨
  4. 빈도 가중(운영 실제 구성)과 고유 가중(문장 다양성) 중 선택 가능

사용:
  python sample_frame_260730.py --n 1610 --seed 20260730 --weight occurrence --tag round2
출력:
  sample_<tag>_<n>_<seed>.jsonl        no/rec_id/field/text 만
  sample_<tag>_<n>_<seed>.manifest.json 모집단 지문 + 파라미터 + 구성 검정
"""
import argparse
import collections
import hashlib
import json
import os
import random
import sys
import time

DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
SRC = DS + "emotion/weak_export_260624.jsonl"
HERE = os.path.dirname(os.path.abspath(__file__))

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def field_of(rid):
    """배치 id 규약: `_1-`=장점란, `_0-`=단점란 (scripts/field_conflict_review.py:field_of)."""
    return "장점" if "_1-" in rid else ("단점" if "_0-" in rid else None)


ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=1610)
ap.add_argument("--seed", type=int, default=20260730)
ap.add_argument("--weight", choices=("occurrence", "unique"), default="occurrence",
                help="occurrence=출현 빈도 가중(운영 구성 재현) / unique=고유 문장 균등")
ap.add_argument("--tag", default="round2")
ap.add_argument("--stratify", action="store_true",
                help="칸(장점/단점) 비례배분 층화추출 — 칸 구성 변동을 제거한다")
a = ap.parse_args()

t0 = time.perf_counter()
print(f"[1] 모집단 로드 — {SRC}")
h = hashlib.sha256()
rows = []
n_row = n_clause = n_skip = 0
with open(SRC, "rb") as fb:
    for chunk in iter(lambda: fb.read(1 << 20), b""):
        h.update(chunk)
for line in open(SRC, encoding="utf-8"):
    r = json.loads(line)
    n_row += 1
    if r.get("is_clause"):
        n_clause += 1
        continue
    rid = r.get("id") or r.get("rec_id") or ""
    f = field_of(rid)
    t = (r.get("text") or "").strip()
    if not f or not t:
        n_skip += 1
        continue
    rows.append((rid, f, t))
print(f"    원행 {n_row:,} / 절 제외 {n_clause:,} / 칸·본문 결측 제외 {n_skip:,} "
      f"→ 모집단 문장 {len(rows):,}")
uniq = collections.Counter((f, t) for _, f, t in rows)
print(f"    고유 (칸,문장) = {len(uniq):,}   SHA-256(원본) = {h.hexdigest()[:16]}…")

print(f"\n[2] 추출 — n={a.n} seed={a.seed} weight={a.weight}")
rnd = random.Random(a.seed)
if a.stratify:
    # 칸 비례배분 층화 — 층별 표본수를 모집단 비율로 고정하고, 잔여는 큰 소수부 순으로 배분
    by = collections.defaultdict(list)
    for e in rows:
        by[e[1]].append(e)
    tot_all = len(rows)
    quota = {f: a.n * len(v) / tot_all for f, v in by.items()}
    alloc = {f: int(q) for f, q in quota.items()}
    for f in sorted(quota, key=lambda x: -(quota[x] - alloc[x]))[:a.n - sum(alloc.values())]:
        alloc[f] += 1
    pick = [e for f in sorted(by) for e in rnd.sample(by[f], alloc[f])]
    rnd.shuffle(pick)
    print("    층화 배분:", alloc)
elif a.weight == "occurrence":
    pick = rnd.sample(rows, a.n)
else:
    keys = rnd.sample(sorted(uniq), a.n)
    first = {}
    for rid, f, t in rows:
        first.setdefault((f, t), rid)
    pick = [(first[k], k[0], k[1]) for k in keys]

out = [dict(no=i + 1, rec_id=rid, field=f, text=t) for i, (rid, f, t) in enumerate(pick)]
base = f"sample_{a.tag}_{a.n}_{a.seed}"
p_jsonl = os.path.join(HERE, base + ".jsonl")
with open(p_jsonl, "w", encoding="utf-8") as fo:
    for o in out:
        fo.write(json.dumps(o, ensure_ascii=False) + "\n")

# 구성 검정 — 표본 칸 구성이 모집단과 일치하는가(z)
pop = collections.Counter(f for _, f, _ in rows)
smp = collections.Counter(o["field"] for o in out)
tot = sum(pop.values())
checks = []
print("\n[3] 구성 검정 (칸)")
for f in sorted(pop):
    p = pop[f] / tot
    exp = a.n * p
    se = (a.n * p * (1 - p)) ** .5
    z = (smp[f] - exp) / se if se else 0.0
    checks.append(dict(field=f, observed=smp[f], expected=round(exp, 1), z=round(z, 2)))
    print(f"    {f}: 관측 {smp[f]:5d} / 기대 {exp:7.1f}  (z={z:+.2f})")

man = dict(
    tool=os.path.basename(__file__), created=time.strftime("%Y-%m-%d %H:%M:%S"),
    params=dict(n=a.n, seed=a.seed, weight=a.weight, tag=a.tag, stratify=a.stratify),
    population=dict(path=SRC, sha256=h.hexdigest(), bytes=os.path.getsize(SRC),
                    raw_rows=n_row, clause_excluded=n_clause, skipped=n_skip,
                    sentences=len(rows), unique_keys=len(uniq)),
    output=dict(file=os.path.basename(p_jsonl), n=len(out),
                columns=list(out[0].keys()),
                blinding="정답·모델 예측 칸 없음 — 판독 시 모델 출력 열람 불가"),
    field_check=checks,
    elapsed_sec=round(time.perf_counter() - t0, 1))
p_man = os.path.join(HERE, base + ".manifest.json")
json.dump(man, open(p_man, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n저장: {p_jsonl}\n저장: {p_man}  ({man['elapsed_sec']}초)")
print("\n⚠️ 2026-07-27 추출 400건은 본 스크립트 이전에 수행되어 재현 불가함(§4-10 ⑫). "
      "이후 추출은 본 스크립트로만 수행한다.")
