# -*- coding: utf-8 -*-
"""2025년(최신) 평가 자료 전수 센서스 — 배포 모델 직접 판정.

배경(사용자 지적 260727-2차): 초판 센서스는 2024년 배치만 다루고 **최신 2025년 자료를
     전혀 취급하지 않았다**. 2025년은 사용자가 라벨을 부착해 반입한 최신 데이터
     (`data/25.csv`, batch_20260714_0)이므로 본 보고서가 반드시 다루어야 한다.

측정 한계(정직 고지): 2025년 배치에는 **장점/단점 필드가 보존되어 있지 않다**
     (weak_export_260714.jsonl 2,705,461행 전수 스캔 결과 field 보유 0건, 배치 id에도
     필드 규약 없음). 따라서 2025년에서는 S0("칸 = 라벨") 재현 채점이 **불가능**하다.
     S0 대비 개선폭은 필드가 보존된 2024년 배치에서만 측정 가능하며, 2025년에서는
     ① 전수 판정 분포 ② 약점부재 선언 규모 ③ 최다 반복 문장과 판정 점수
     ④ 규칙엔진 대비 모델 판정 차이 를 측정한다.

추론 조건: 실제 2025 배치가 필드 없이 실행되었으므로 **필드 프리픽스를 주입하지 않는다**
     (운영 조건 동일 재현). 2024 센서스는 필드 프리픽스를 주입했으므로 두 해의
     추론 조건이 다르다 — 정확도를 두 해 사이에 직접 비교하지 말 것.
"""
import collections
import json
import os
import re
import sys
import time

DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
SRC = DS + "emotion/weak_export_260714.jsonl"
MODEL = "D:/dev/wordcloud/model/hr_sentiment_finetuned"
BATCH = "batch_20260714_0"          # 2025년 자료(data/25.csv, 2026-07-14 반입)
ID2 = {0: "positive", 1: "negative", 2: "neutral"}
# 약점 부재·무기재 선언 — 2024 센서스와 동일 정의(30자 이하 + 부재 표지)
NOWEAK = re.compile(r"(없습니다|없음|없슴|없다|없으며|해당\s*없|미해당|특이사항)")

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

t0 = time.time()
occ = collections.Counter()          # text -> 출현 횟수 (필드 없음)
prod = collections.Counter()         # 규칙엔진(생산) 라벨 분포
prod_by_text = {}                    # text -> 규칙엔진 라벨(대표 1개)
n_raw = n_clause = 0
for line in open(SRC, encoding="utf-8"):
    r = json.loads(line)
    if not (r.get("id") or "").startswith(BATCH):
        continue
    n_raw += 1
    if r.get("is_clause"):
        n_clause += 1
        continue
    t = (r.get("text") or "").strip()
    if not t:
        continue
    occ[t] += 1
    prod[r.get("sentiment")] += 1
    prod_by_text.setdefault(t, r.get("sentiment"))

n_sent = sum(occ.values())
print(f"2025 배치 원본 {n_raw:,}행 | 절 제외 {n_clause:,} | 문장 {n_sent:,} | 고유 {len(occ):,}")
print(f"규칙엔진(생산) 라벨 분포: {dict(prod)}")

import torch  # noqa: E402
from transformers import AutoTokenizer, AutoModelForSequenceClassification  # noqa: E402

dev = "cuda" if torch.cuda.is_available() else "cpu"
tok = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
mdl = AutoModelForSequenceClassification.from_pretrained(MODEL, local_files_only=True)
mdl.to(dev).eval()
print(f"device: {dev} | 고유 문장 추론 시작 (필드 프리픽스 미주입 = 운영 조건 동일)")

uniq = list(occ)
pred, conf = [], []
BS = 256
t1 = time.time()
with torch.no_grad():
    for i in range(0, len(uniq), BS):
        chunk = uniq[i:i + BS]
        enc = tok(chunk, truncation=True, padding=True, max_length=64,
                  return_tensors="pt").to(dev)
        pr = torch.softmax(mdl(**enc).logits, dim=-1)
        top = pr.max(-1)
        pred.extend(ID2[j] for j in top.indices.cpu().tolist())
        conf.extend(round(v, 4) for v in top.values.cpu().tolist())
        if i % (BS * 200) == 0:
            el = time.time() - t1
            print(f"  {i + len(chunk):,}/{len(uniq):,} ({100*(i+len(chunk))/len(uniq):.1f}%) "
                  f"{(i+len(chunk))/max(el,1e-9):.0f}건/초")
print(f"추론 완료 {time.time()-t1:.1f}초")

m = dict(zip(uniq, pred))
c = dict(zip(uniq, conf))

# ── 전수 집계 ────────────────────────────────────────────────────────────────
model_dist = collections.Counter()
noweak_n = noweak_uniq = 0
noweak_model = collections.Counter()
agree = collections.Counter()        # (규칙엔진, 모델) 교차
for t, k in occ.items():
    model_dist[m[t]] += k
    agree[(prod_by_text[t], m[t])] += k
    if NOWEAK.search(t) and len(t) <= 30:
        noweak_n += k
        noweak_uniq += 1
        noweak_model[m[t]] += k

flip = sum(v for (a, b), v in agree.items() if {a, b} == {"positive", "negative"})
same = sum(v for (a, b), v in agree.items() if a == b)

res = dict(
    source=SRC, batch=BATCH, year=2025, model=MODEL, device=dev,
    field_available=False,
    n_rows_raw=n_raw, n_clause_excluded=n_clause, n_sentences=n_sent, n_unique=len(occ),
    infer_sec=round(time.time() - t1, 1),
    rule_engine_dist={k: v for k, v in prod.items()},
    model_dist=dict(model_dist),
    model_pct={k: round(100 * v / n_sent, 2) for k, v in model_dist.items()},
    no_weakness=dict(n=noweak_n, pct=round(100 * noweak_n / n_sent, 2),
                     unique=noweak_uniq, model_label=dict(noweak_model)),
    rule_vs_model=dict(agree=same, agree_pct=round(100 * same / n_sent, 2),
                       posneg=flip, posneg_pct=round(100 * flip / n_sent, 2),
                       matrix={f"{a}->{b}": v for (a, b), v in sorted(agree.items())}),
    top_repeated=[dict(n=k, pct=round(100 * k / n_sent, 3), text=t,
                       model=m[t], conf=c[t], rule=prod_by_text[t])
                  for t, k in occ.most_common(20)],
)

print(f"\n[2025 전수 {n_sent:,}문장 — 배포 모델 판정]")
for k in ("positive", "neutral", "negative"):
    print(f"  {k:9s} {model_dist[k]:>9,} = {100*model_dist[k]/n_sent:5.2f}%")
print(f"\n[약점 부재·무기재 선언] {noweak_n:,} = {100*noweak_n/n_sent:.2f}% "
      f"(고유 {noweak_uniq:,}) | 모델 판정 {dict(noweak_model)}")
print(f"\n[규칙엔진 vs 배포모델] 일치 {same:,} = {100*same/n_sent:.2f}% | "
      f"긍↔부 상충 {flip:,} = {100*flip/n_sent:.2f}%")
print(f"\n[최다 반복 문장 상위 10]")
for e in res["top_repeated"][:10]:
    print(f"  {e['n']:>6,} ({e['pct']:5.2f}%) [{e['model']}/{e['conf']:.2f}] {e['text'][:46]}")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prod25_census_260727.json")
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\n저장: {out} | 총 {time.time()-t0:.1f}초")
