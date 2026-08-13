# -*- coding: utf-8 -*-
"""사람 표기(decision_source=human*/user_agreed) 라벨만으로 배포 모델을 채점한다.
학습에 쓰이지 않은 것만 남겨 오염을 제거한다."""
import collections, glob, json, os, sys
DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
EVAL = os.path.join(DS, "eval")
LABELS = ("positive", "negative", "neutral")
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8")
    except Exception: pass
sys.path.insert(0, os.path.join(DS, "scripts"))
sys.path.insert(0, "D:/dev/wordcloud/wordcloud_project/src")
from finetune_sentiment import TRAIN_FILES, TEST_SETS

def is_human(ds): return ds.startswith("human") or ds == "user_agreed"

# 사람 표기가 붙은 키 수집 (라벨은 그 행의 human_decision)
human = {}
for pat in (os.path.join(EVAL, "*.jsonl"), os.path.join(EVAL, "review", "*.jsonl")):
    for p in sorted(glob.glob(pat)):
        if ".bak" in p or "backup" in p: continue
        for line in open(p, encoding="utf-8"):
            try: r = json.loads(line)
            except Exception: continue
            hd = r.get("human_decision"); t = (r.get("text") or "").strip()
            ds = (r.get("decision_source") or "")
            if hd in LABELS and t and is_human(ds):
                human[((r.get("field") or ""), t)] = hd

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

tr = keys_of(TRAIN_FILES)
clean = {k: v for k, v in human.items() if k not in tr}
print("사람 표기 키 총 %d / 학습 미포함(채점 가능) %d" % (len(human), len(clean)))
print("  라벨 분포:", dict(collections.Counter(clean.values())))
print("  칸 분포  :", dict(collections.Counter(k[0] or "(없음)" for k in clean)))

items = [(k[0], k[1], v) for k, v in clean.items()]
if not items:
    sys.exit("채점 가능 건 없음")

from modules.hr_sentiment import predict_sentiments
pred = predict_sentiments([t for _, t, _ in items], fields=[f for f, _, _ in items])
if pred is None:
    sys.exit("모델 로드 실패 — 규칙 폴백 상태")

n = len(items); ok = 0; flip = 0
cm = collections.defaultdict(collections.Counter)
for (f, t, gold), p in zip(items, pred):
    cm[gold][p] += 1
    if p == gold: ok += 1
    elif {p, gold} == {"positive", "negative"}: flip += 1
acc = 100.0 * ok / n
import math
se = math.sqrt(acc/100*(1-acc/100)/n) * 100
print("\n=== 사람 라벨 %d건 위 배포 모델 성적 ===" % n)
print("  정답률 %.2f%%  (95%% CI ±%.2f%%p)" % (acc, 1.96*se))
print("  긍↔부 뒤바뀜 %d (%.2f%%)" % (flip, 100.0*flip/n))
for g in LABELS:
    tot = sum(cm[g].values())
    if tot:
        print("    %-9s n=%4d  %s  recall %.1f%%"
              % (g, tot, dict(cm[g]), 100.0*cm[g][g]/tot))
