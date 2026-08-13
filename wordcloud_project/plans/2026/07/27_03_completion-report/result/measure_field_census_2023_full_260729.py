# -*- coding: utf-8 -*-
"""입력 칸(장점/단점) 라벨이 실제 문장 내용과 얼마나 어긋나는가 — 2023년분 **전수 확정 측정**.

배경: 종전(2026-07-28)에는 2023년 자료에 칸 정보가 없어 27.95% 구간 실측 + 편향보정 추정치
      (약 32.1%)를 보고서에 실었다. 2026-07-29 사용자가 칸별로 분리 재추출해 주어
      **추정 없이 전수 확정값**을 산출할 수 있게 되었다.

대상: `D:/dev/wordcloud/data/23년 장점.csv` (batch_20260729_0, 521,817행)
      `D:/dev/wordcloud/data/23년 단점.csv` (batch_20260729_1, 503,817행)
      두 파일의 합 = `23.csv`(합본, 1,025,634행)와 문장 집합·행수 100% 일치(검증 완료).
      두 파일에는 `f`(입력칸) 키가 실려 있다 — export 12종 중 최초.

측정: ① 입력 칸 라벨(장점=긍정, 단점=부정) — 감정 분석 도입 이전 방식(S0)
      ② 배포 모델(2026-07-08 seed45) 판정 — 2024·2025 센서스와 **동일 규약**으로 재추론
         (`f"{field} 평가: {text}"`, max_length=64, argmax)
      ③ 참고: 추출본의 `y`(규칙+모델 전체 엔진 출력)와 ②의 일치도

주: 고유 (칸, 문장) 조합만 추론하고 출현 횟수로 되매핑한다(결과 동일).
"""
import collections
import json
import os
import sys
import time

D = "D:/dev/wordcloud/data/"
SRC = {"장점": D + "23\ub144 \uc7a5\uc810.csv", "단점": D + "23\ub144 \ub2e8\uc810.csv"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")
MODEL = "D:/dev/wordcloud/model/hr_sentiment_finetuned"
FMAP = {"장점": "positive", "단점": "negative"}
ID2 = {0: "positive", 1: "negative", 2: "neutral"}
YMAP = {"p": "positive", "n": "negative", "u": "neutral"}

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ── 1. 전수 로드 + 고유화 ─────────────────────────────────────────────
t0 = time.perf_counter()
occ = collections.Counter()               # (칸, 문장) -> 출현 횟수
eng = collections.Counter()               # (칸, 문장, 엔진라벨) -> 횟수
batches = {}
n_row = n_skip = 0
for f, path in SRC.items():
    for i, line in enumerate(open(path, encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if i == 0 and "#" in r:
            batches[f] = r.get("batch")
            continue
        n_row += 1
        t = (r.get("x") or "").strip()
        if not t:
            n_skip += 1
            continue
        # 파일이 주장하는 칸과 실제 f 키가 어긋나면 f 키를 정본으로 쓴다
        ff = (r.get("f") or f).strip()
        if ff not in FMAP:
            n_skip += 1
            continue
        occ[(ff, t)] += 1
        eng[(ff, t, YMAP.get(r.get("y"), "?"))] += 1

n_sent = sum(occ.values())
keys = list(occ)
print(f"원본 {n_row:,}행 | 무효 {n_skip:,} | 문장 {n_sent:,} | 고유(칸,문장) {len(keys):,}")
print("배치:", batches)

# ── 2. 배포 모델 전수 판정 (2024·2025와 동일 규약) ────────────────────
# 추론이 21분 걸리므로 (칸, 문장) 순서대로 예측 라벨을 캐시해 재집계를 무료로 만든다.
CACHE = OUT + "field_census_2023_full_260729_pred.cache"
pred, dev, infer_sec = None, "cache", 0.0
if os.path.exists(CACHE):
    with open(CACHE, encoding="utf-8") as fh:
        head = fh.readline().strip()
        cached = fh.readline().strip().split(",")
    if head == str(len(keys)) and len(cached) == len(keys):
        pred = cached
        print(f"예측 캐시 재사용: {CACHE} ({len(pred):,}건)")
    else:
        print("캐시가 현재 입력과 불일치 — 재추론한다")

if pred is None:
    import torch  # noqa: E402
    from transformers import AutoTokenizer, AutoModelForSequenceClassification  # noqa: E402

    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    mdl = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True)
    mdl.to(dev).eval()
    print("device:", dev, "| 고유 문장 추론 시작")

    BS = 256
    pred = []
    t1 = time.perf_counter()
    with torch.no_grad():
        for i in range(0, len(keys), BS):
            chunk = keys[i:i + BS]
            txt = [f"{f} 평가: {t}" for f, t in chunk]
            enc = tok(txt, truncation=True, padding=True, max_length=64, return_tensors="pt").to(dev)
            pred.extend(ID2[j] for j in mdl(**enc).logits.argmax(-1).cpu().tolist())
            if (i // BS) % 200 == 0:
                done = min(i + BS, len(keys))
                print(f"  {done:,}/{len(keys):,} ({100 * done / len(keys):.1f}%) "
                      f"{done / max(time.perf_counter() - t1, 1e-9):,.0f}건/초", flush=True)
    infer_sec = time.perf_counter() - t1
    print(f"추론 완료 {infer_sec:.1f}초, {len(keys) / infer_sec:,.0f} 고유건/초")
    with open(CACHE, "w", encoding="utf-8") as fh:
        fh.write(f"{len(keys)}\n" + ",".join(pred) + "\n")
    print("예측 캐시 저장:", CACHE)

# ── 3. 집계 ───────────────────────────────────────────────────────────
cell = collections.Counter()     # (칸, 칸라벨, 모델라벨) -> 전수
cellu = collections.Counter()    # 동일, 고유 단위
agree = collections.Counter()    # "same"/"diff" 전수
conf = collections.Counter()     # (엔진라벨, 모델라벨) -> 전수
examples = collections.defaultdict(list)
for (f, t), p in zip(keys, pred):
    c = FMAP[f]
    n = occ[(f, t)]
    cell[(f, c, p)] += n
    cellu[(f, c, p)] += 1
    if c != p:
        examples[(f, p)].append((n, t))
    for lab in ("positive", "negative", "neutral", "?"):
        k = eng.get((f, t, lab))
        if k:
            agree["same" if lab == p else "diff"] += k
            conf[(lab, p)] += k

res = {
    "source": {k: v for k, v in SRC.items()},
    "batches": batches,
    "model": MODEL, "device": dev,
    "n_rows_raw": n_row, "n_invalid": n_skip,
    "n_sentences": n_sent, "n_unique": len(keys),
    "infer_sec": round(infer_sec, 1),
    "fields": {},
}
for f in ("장점", "단점"):
    c = FMAP[f]
    tot = sum(v for (ff, _, _), v in cell.items() if ff == f)
    totu = sum(v for (ff, _, _), v in cellu.items() if ff == f)
    match = cell[(f, c, c)]
    matchu = cellu[(f, c, c)]
    flip = "negative" if c == "positive" else "positive"
    d = dict(
        n=tot, n_unique=totu, cell_label=c,
        match=match, match_pct=round(100 * match / tot, 2),
        mismatch=tot - match, mismatch_pct=round(100 * (tot - match) / tot, 2),
        match_unique=matchu, mismatch_unique=totu - matchu,
        mismatch_unique_pct=round(100 * (totu - matchu) / totu, 2),
        to_neutral=cell[(f, c, "neutral")],
        to_neutral_pct=round(100 * cell[(f, c, "neutral")] / tot, 2),
        to_flip=cell[(f, c, flip)],
        to_flip_pct=round(100 * cell[(f, c, flip)] / tot, 2),
    )
    d["top_mismatch"] = {
        lab: [dict(n=n, text=t) for n, t in sorted(examples[(f, lab)], reverse=True)[:15]]
        for lab in ("neutral", flip)
    }
    res["fields"][f] = d
    print(f"\n[{f}란] 전수 {tot:,}건 (고유 {totu:,})")
    print(f"  입력칸대로({c}) {match:,} = {d['match_pct']}%")
    print(f"  불일치 {tot - match:,} = {d['mismatch_pct']}%  (고유 기준 {d['mismatch_unique_pct']}%)")
    print(f"    → 실제 중립: {d['to_neutral']:,} ({d['to_neutral_pct']}%)")
    print(f"    → 실제 {flip}(정반대): {d['to_flip']:,} ({d['to_flip_pct']}%)")

tot_all = sum(cell.values())
mis_all = tot_all - cell[("장점", "positive", "positive")] - cell[("단점", "negative", "negative")]
flip_all = cell[("장점", "positive", "negative")] + cell[("단점", "negative", "positive")]
res["overall"] = dict(n=tot_all, mismatch=mis_all,
                      mismatch_pct=round(100 * mis_all / tot_all, 2),
                      flip=flip_all, flip_pct=round(100 * flip_all / tot_all, 2),
                      s0_accuracy_pct=round(100 * (tot_all - mis_all) / tot_all, 2))
print(f"\n[전체] {tot_all:,}건 중 입력칸 라벨과 불일치 {mis_all:,} = {res['overall']['mismatch_pct']}%"
      f" | 정반대(뒤집힘) {flip_all:,} = {res['overall']['flip_pct']}%"
      f" | 종전방식 정답률 {res['overall']['s0_accuracy_pct']}%")

# 모델 재추론 vs 추출본 y(전체 엔진) 일치도 — 규약 검증용
same, diff = agree.get("same", 0), agree.get("diff", 0)
res["engine_vs_model"] = dict(
    same=same, diff=diff,
    same_pct=round(100 * same / max(same + diff, 1), 2),
    confusion={f"{a}->{b}": v for (a, b), v in sorted(conf.items())},
)
print(f"\n[규약 검증] 추출본 y(엔진) vs 재추론(모델): 일치 {same:,} / 불일치 {diff:,}"
      f" = {res['engine_vs_model']['same_pct']}% 일치")

json.dump(res, open(OUT + "field_census_2023_full_260729.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("저장:", OUT + "field_census_2023_full_260729.json", f"| 총 {time.perf_counter() - t0:.1f}초")
