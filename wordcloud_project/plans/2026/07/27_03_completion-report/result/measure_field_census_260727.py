# -*- coding: utf-8 -*-
"""입력 칸(장점/단점) 라벨이 실제 문장 내용과 얼마나 어긋나는가 — 원데이터 전수 센서스.

대상: `plans/_datasets/kote_finetune/emotion/weak_export_260624.jsonl`
      → 필드가 살아있는 유일한 전수 배치(장점 배치 `_1`, 단점 배치 `_0`).
        절(is_clause) 행은 문장 중복이므로 제외 → 870,367 문장.

측정: ① 입력 칸 라벨(장점=긍정, 단점=부정) — 감정 분석 도입 이전 방식(S0)
      ② 배포 모델(2026-07-08 seed45) 판정 — 현행 방식
      ①≠② 인 건수를 전수·고유 양쪽으로 집계한다.

주: 고유 (필드, 문장) 조합만 추론하고 출현 횟수로 되매핑한다(결과 동일, 연산 1/2.2).
"""
import collections
import json
import os
import sys
import time

DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
SRC = DS + "emotion/weak_export_260624.jsonl"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "")
MODEL = "D:/dev/wordcloud/model/hr_sentiment_finetuned"
FMAP = {"장점": "positive", "단점": "negative"}
ID2 = {0: "positive", 1: "negative", 2: "neutral"}

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def field_of(rid):
    """배치 id 규약: `_1-`=장점란, `_0-`=단점란 (scripts/field_conflict_review.py:field_of)."""
    return "장점" if "_1-" in rid else ("단점" if "_0-" in rid else None)


# ── 1. 전수 로드 + 고유화 ─────────────────────────────────────────────
t0 = time.perf_counter()
occ = collections.Counter()   # (field, text) -> 출현 횟수
n_row = n_clause = n_skip = 0
for line in open(SRC, encoding="utf-8"):
    r = json.loads(line)
    n_row += 1
    if r.get("is_clause"):
        n_clause += 1
        continue
    f = field_of(r.get("id") or "")
    t = (r.get("text") or "").strip()
    if not f or not t:
        n_skip += 1
        continue
    occ[(f, t)] += 1
n_sent = sum(occ.values())
keys = list(occ)
print(f"원본 {n_row:,}행 | 절 제외 {n_clause:,} | 무효 {n_skip:,} | 문장 {n_sent:,} | 고유 {len(keys):,}")

# ── 2. 배포 모델 전수 판정 ────────────────────────────────────────────
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
                  f"{done / max(time.perf_counter() - t1, 1e-9):,.0f}건/초")
infer_sec = time.perf_counter() - t1
print(f"추론 완료 {infer_sec:.1f}초, {len(keys) / infer_sec:,.0f} 고유건/초")

# ── 3. 집계 (전수 = 출현 횟수 가중, 고유 = 조합 단위) ─────────────────
cell = collections.Counter()     # (field, cell_label, model_label) -> 전수
cellu = collections.Counter()    # 동일, 고유 단위
examples = collections.defaultdict(list)
for (f, t), p in zip(keys, pred):
    c = FMAP[f]
    n = occ[(f, t)]
    cell[(f, c, p)] += n
    cellu[(f, c, p)] += 1
    if c != p:
        examples[(f, p)].append((n, t))

res = {
    "source": SRC,
    "model": MODEL,
    "device": dev,
    "n_rows_raw": n_row, "n_clause_excluded": n_clause, "n_invalid": n_skip,
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
        n=tot, n_unique=totu,
        cell_label=c,
        match=match, match_pct=round(100 * match / tot, 2),
        mismatch=tot - match, mismatch_pct=round(100 * (tot - match) / tot, 2),
        match_unique=matchu, mismatch_unique=totu - matchu,
        mismatch_unique_pct=round(100 * (totu - matchu) / totu, 2),
        to_neutral=cell[(f, c, "neutral")],
        to_neutral_pct=round(100 * cell[(f, c, "neutral")] / tot, 2),
        to_flip=cell[(f, c, flip)],
        to_flip_pct=round(100 * cell[(f, c, flip)] / tot, 2),
    )
    # 반복이 많은 불일치 문장 상위 = 대표 사례(개인 식별 정보 없는 상용구 위주로 상위가 뽑힘)
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

tot_all = sum(v for v in cell.values())
mis_all = tot_all - cell[("장점", "positive", "positive")] - cell[("단점", "negative", "negative")]
flip_all = cell[("장점", "positive", "negative")] + cell[("단점", "negative", "positive")]
res["overall"] = dict(n=tot_all, mismatch=mis_all,
                      mismatch_pct=round(100 * mis_all / tot_all, 2),
                      flip=flip_all, flip_pct=round(100 * flip_all / tot_all, 2))
print(f"\n[전체] {tot_all:,}건 중 입력칸 라벨과 불일치 {mis_all:,} = {res['overall']['mismatch_pct']}%"
      f" | 정반대(뒤집힘) {flip_all:,} = {res['overall']['flip_pct']}%")

json.dump(res, open(OUT + "field_census_260727.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("저장:", OUT + "field_census_260727.json", f"| 총 {time.perf_counter() - t0:.1f}초")
