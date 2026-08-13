# -*- coding: utf-8 -*-
"""S2 — 누출 검사. **이 작업의 분기점.**

사람 라벨이 있어도 학습에 들어갔으면 홀드아웃이 아니다(자기채점이 된다).
`finetune_sentiment.py` 의 TRAIN_FILES / TEST_SETS 를 **코드에서 그대로 읽어** 키 집합을
만들고, S1 수집분 중 어디에도 없는 행만 홀드아웃으로 남긴다.

티어 구분 — `decision_source` 실측에 근거한다(필드명 `human_decision` 은 사람을 뜻하지 않음).
  A: decision_source == "human"   → 확정 사람 판정
  B: "(미기재)"                    → 출처 불명. 사람일 수도 AI 일 수도 있어 **주장 근거로 못 씀**
  C: 나머지(claude/packet/pattern/rule/auto) → AI·규칙. 제외

보수적으로 TRAIN ∪ TEST 양쪽 모두에서 빠진 것만 홀드아웃으로 인정한다.
출력: result/s2_holdout.jsonl · result/s2_summary.json
게이트: 입력>0 인데 티어 A 집계 0건이면 FAIL.
"""
import io
import json
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "result")
DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune"
SCR = os.path.join(DS, "scripts")

sys.path.insert(0, SCR)
from finetune_sentiment import TRAIN_FILES, TEST_SETS  # noqa: E402

TEXT_KEYS = ["text", "sentence", "s", "content"]
FIELD_KEYS = ["field", "f", "칸"]


def find(fn):
    for sub in ("eval", "emotion", ""):
        p = os.path.join(DS, sub, fn) if sub else os.path.join(DS, fn)
        if os.path.isfile(p):
            return p
    return None


def keys_of(fn):
    """(칸, 문장) 키 집합. 파일이 없으면 None 을 돌려 '누락'을 드러낸다."""
    p = find(fn)
    if not p:
        return None
    ks = set()
    for line in open(p, encoding="utf-8"):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = next((d[k] for k in TEXT_KEYS if d.get(k)), None)
        f = next((d[k] for k in FIELD_KEYS if d.get(k)), None)
        if t and f:
            ks.add((str(f).strip(), str(t).strip()))
    return ks


train_keys, test_keys, missing = set(), set(), []
for fn in TRAIN_FILES:
    ks = keys_of(fn)
    (missing.append(("TRAIN", fn)) if ks is None else train_keys.update(ks))
for name, fn in TEST_SETS.items():
    ks = keys_of(fn)
    (missing.append(("TEST", fn)) if ks is None else test_keys.update(ks))

# S1 수집분 → 티어별 고유키
tier_keys = {"A": {}, "B": {}, "C": {}}
n_in = 0
for line in open(os.path.join(RES, "s1_human_labels.jsonl"), encoding="utf-8"):
    if not line.strip():
        continue
    n_in += 1
    d = json.loads(line)
    src = d.get("decision_source")
    t = "A" if src == "human" else ("B" if src == "(미기재)" else "C")
    tier_keys[t][(d["field"], d["text"])] = d

if not tier_keys["A"]:
    print("FAIL — 입력 %d행인데 티어 A(확정 사람) 0건" % n_in)
    sys.exit(1)


def split(keys):
    tr = {k for k in keys if k in train_keys}
    te = {k for k in keys if k in test_keys and k not in tr}
    ho = {k for k in keys if k not in train_keys and k not in test_keys}
    return tr, te, ho


rep = {}
for t in ("A", "B", "C"):
    tr, te, ho = split(tier_keys[t])
    rep[t] = dict(unique=len(tier_keys[t]), in_train=len(tr), in_test=len(te), holdout=len(ho))

hoA = [v for k, v in tier_keys["A"].items() if k not in train_keys and k not in test_keys]
with open(os.path.join(RES, "s2_holdout.jsonl"), "w", encoding="utf-8") as fo:
    for v in hoA:
        fo.write(json.dumps(v, ensure_ascii=False) + "\n")

summary = dict(train_files=len(TRAIN_FILES), test_sets=len(TEST_SETS),
               train_keys=len(train_keys), test_keys=len(test_keys),
               missing_files=missing, s1_rows=n_in, tiers=rep,
               holdout_A_label_dist=dict(Counter(v["label"] for v in hoA)),
               holdout_A_field_dist=dict(Counter(v["field"] for v in hoA)),
               holdout_A_src_files=dict(Counter(v["src_file"] for v in hoA).most_common(10)))
json.dump(summary, open(os.path.join(RES, "s2_summary.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

print("TRAIN %d파일 → 키 %s / TEST %d셋 → 키 %s%s"
      % (len(TRAIN_FILES), format(len(train_keys), ","), len(TEST_SETS),
         format(len(test_keys), ","),
         ("  ⚠️ 파일 누락 %d건" % len(missing)) if missing else ""))
print("\n%-4s %-28s %8s %9s %8s %9s" % ("티어", "정의", "고유키", "학습포함", "테스트", "**홀드아웃**"))
for t, d in [("A", "확정 사람(source=human)"), ("B", "출처 미기재 — 주장근거 불가"),
             ("C", "AI·규칙 — 제외")]:
    r = rep[t]
    print("%-4s %-28s %8s %9s %8s %9s"
          % (t, d, format(r["unique"], ","), format(r["in_train"], ","),
             format(r["in_test"], ","), format(r["holdout"], ",")))
print("\n[티어 A 홀드아웃] 라벨분포 %s / 칸분포 %s"
      % (summary["holdout_A_label_dist"], summary["holdout_A_field_dist"]))
if missing:
    print("⚠️ 누락 파일:", missing[:6])
