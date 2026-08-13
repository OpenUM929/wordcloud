# -*- coding: utf-8 -*-
"""무작위 400 표본의 적격성 역검정 — 추출 주장(모집단 일치·빈도가중·학습 미노출)을 데이터로 검사."""
import collections, glob, json, math, os, sys
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8")
    except Exception: pass
R = "D:/dev/wordcloud/wordcloud_project/plans/2026/07/27_03_completion-report/result/"
DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
EVAL = os.path.join(DS, "eval")
LABELS = ("positive", "negative", "neutral")
sys.path.insert(0, os.path.join(DS, "scripts"))
from finetune_sentiment import TRAIN_FILES, TEST_SETS

rows = [json.loads(l) for l in open(R + "blind_judged_400.jsonl", encoding="utf-8")]
print("표본 행 =", len(rows))

# --- 1) 칸 구성이 모집단과 일치하는가 (빈도가중 무작위라면 일치해야 함) ---
cen = json.load(open(R + "field_census_260727.json", encoding="utf-8"))
print("\n[1] 칸 구성 대조")
pop = {}
for f, d in cen.get("fields", {}).items():
    pop[f] = d.get("n") or d.get("total") or d.get("rows")
print("   센서스 키:", list(cen.keys())[:8])
print("   모집단 칸별:", pop)
sc = collections.Counter(r["field"] for r in rows)
print("   표본 칸별  :", dict(sc))
tot = sum(v for v in pop.values() if v)
if tot:
    for f in sc:
        exp = 400 * pop.get(f, 0) / tot
        se = math.sqrt(400 * (pop.get(f, 0)/tot) * (1 - pop.get(f, 0)/tot))
        z = (sc[f] - exp) / se if se else float('nan')
        print("     %s: 관측 %d / 기대 %.1f  (z=%+.2f)" % (f, sc[f], exp, z))

# --- 2) 빈도가중이면 중복 문장이 표본에 나타나야 한다 ---
print("\n[2] 표본 내 중복 구조 (빈도가중 여부의 지문)")
ct = collections.Counter((r["field"], r["text"].strip()) for r in rows)
dup = {k: v for k, v in ct.items() if v > 1}
print("   고유 (칸,문장) = %d / 중복 키 = %d / 초과 행 = %d"
      % (len(ct), len(dup), sum(v-1 for v in dup.values())))
for k, v in sorted(dup.items(), key=lambda x: -x[1])[:5]:
    print("      x%d  [%s] %s" % (v, k[0], k[1][:50]))
print("   고유 rec_id = %d" % len(set(r.get("rec_id") for r in rows)))

# --- 3) 학습·검증 오염 ---
def keys_of(files):
    out = set()
    for fn in files:
        p = os.path.join(EVAL, fn)
        if not os.path.isfile(p): continue
        for line in open(p, encoding="utf-8"):
            try: r = json.loads(line)
            except Exception: continue
            if r.get("human_decision") in LABELS and (r.get("text") or "").strip():
                out.add(((r.get("field") or ""), (r.get("text") or "").strip()))
    return out
tr = keys_of(TRAIN_FILES); te = keys_of(list(TEST_SETS.values()))
k400 = set(ct)
t400 = {t for _, t in k400}
print("\n[3] 오염 검사")
print("   400 ∩ 학습 (칸,문장) = %d | 문장만 = %d" % (len(k400 & tr), len(t400 & {t for _, t in tr})))
print("   400 ∩ 검증 (칸,문장) = %d | 문장만 = %d" % (len(k400 & te), len(t400 & {t for _, t in te})))
for k in sorted(k400 & tr)[:10]: print("      학습겹침:", k[0], k[1][:50])

# --- 4) 정밀도 한계: n에 따른 95% CI ---
print("\n[4] 표본 크기별 95% 신뢰구간 (정규근사)")
def ci(p, n): return 1.96 * math.sqrt(p*(1-p)/n) * 100
print("   %-8s %-22s %-22s" % ("n", "정확도 p=0.935", "뒤바뀜 p=0.010"))
for n in (150, 250, 400, 800, 1500, 3000):
    print("   %-8d ±%-21.2f ±%-21.2f" % (n, ci(0.935, n), ci(0.010, n)))
print("   → 뒤바뀜 1%%를 ±0.5%%p 로 좁히려면 n≈%d" % math.ceil(0.01*0.99*(1.96/0.005)**2))

# --- 5) 판정 난이도: 표본 라벨 분포 vs 칸 라벨 ---
print("\n[5] 판정 난이도 지표")
FMAP = {"장점": "positive", "단점": "negative"}
agree = sum(1 for r in rows if r["claude_judgment"] == FMAP.get(r["field"]))
print("   칸 라벨과 판정이 다른 문장 = %d / 400 (%.1f%%)" % (400-agree, 100*(400-agree)/400))
print("   판정 라벨 분포:", dict(collections.Counter(r["claude_judgment"] for r in rows)))
print("   문장 길이 중앙값 = %d자, 최장 %d자"
      % (sorted(len(r["text"]) for r in rows)[200], max(len(r["text"]) for r in rows)))
