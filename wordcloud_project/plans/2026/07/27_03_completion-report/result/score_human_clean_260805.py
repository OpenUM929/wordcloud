# -*- coding: utf-8 -*-
"""사람 표기 라벨 위 배포 모델 채점 — 학습 제외분(249)과 학습+검증 제외분(88)을 함께 낸다.

신설 사유(2026-08-05, 조치 8번)
  기존 `score_human_only_260730.py` 는 `TEST_SETS` 를 import 하고도(13행) 제외 집합에
  넣지 않아(43행 `if k not in tr`) 249건 안에 개발용 검증셋 161건이 그대로 남았다.
  겹친 161건은 학습이 아니라 **모델 선택(시드·체크포인트)** 에 쓰인 자료이므로 성적을
  높이는 쪽으로 작용한다 — 즉 65.86%는 "한 번도 보지 않은 문장의 성적"이 아니다.

  구 스크립트는 65.86% 의 재현 근거이므로 수정하지 않고 보존한다(무결성). 본 스크립트가
  구 값(249)을 같은 코드로 재현하면서 순수 미노출분(88)을 추가로 산출한다.

산출
  [A] 학습만 제외 = 249건 (구 스크립트 재현 — 값이 일치해야 한다)
  [B] 학습 + 검증셋 4종 모두 제외 = 순수 미노출 (정본)
  [C] 겹침 161건만 — 낙관 편향의 크기를 직접 보이기 위한 대조군
  구간은 Wilson(보고서 정본 규약, compute_wilson_ci_260730.py 와 동일 산식).
"""
import collections
import glob
import json
import math
import os
import sys

DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
EVAL = os.path.join(DS, "eval")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "score_human_clean_260805.json")
LABELS = ("positive", "negative", "neutral")

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.join(DS, "scripts"))
sys.path.insert(0, "D:/dev/wordcloud/wordcloud_project/src")
from finetune_sentiment import TRAIN_FILES, TEST_SETS  # noqa: E402


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z / d * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return 100 * (c - h), 100 * (c + h)


def is_human(ds):
    return ds.startswith("human") or ds == "user_agreed"


# 사람 표기가 붙은 키 수집 (구 스크립트와 동일 규약 — 넓은 정의)
human = {}
for pat in (os.path.join(EVAL, "*.jsonl"), os.path.join(EVAL, "review", "*.jsonl")):
    for p in sorted(glob.glob(pat)):
        if ".bak" in p or "backup" in p:
            continue
        for line in open(p, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            hd = r.get("human_decision")
            t = (r.get("text") or "").strip()
            ds = r.get("decision_source") or ""
            if hd in LABELS and t and is_human(ds):
                human[((r.get("field") or ""), t)] = hd


def keys_of(files):
    out = set()
    for fn in files:
        p = os.path.join(EVAL, fn)
        if not os.path.isfile(p):
            continue
        for line in open(p, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("human_decision") in LABELS and (r.get("text") or "").strip():
                out.add(((r.get("field") or ""), (r.get("text") or "").strip()))
    return out


tr = keys_of(TRAIN_FILES)
te = keys_of(list(TEST_SETS.values()))

setA = {k: v for k, v in human.items() if k not in tr}                 # 학습만 제외 = 249
setB = {k: v for k, v in setA.items() if k not in te}                  # 순수 미노출 = 88
setC = {k: v for k, v in setA.items() if k in te}                      # 겹침 = 161

print("사람 표기 키 총 %d" % len(human))
print("  [A] 학습만 제외          : %d" % len(setA))
print("  [B] 학습+검증 모두 제외  : %d" % len(setB))
print("  [C] 검증셋 겹침(대조군)  : %d" % len(setC))
assert len(setB) + len(setC) == len(setA), "A = B + C 가 성립해야 함"

# 세 집합을 한 번에 추론(중복 텍스트 없음 — 키가 (field, text))
items = [(k[0], k[1], v) for k, v in setA.items()]
from modules.hr_sentiment import predict_sentiments  # noqa: E402

pred = predict_sentiments([t for _, t, _ in items], fields=[f for f, _, _ in items])
if pred is None:
    sys.exit("모델 로드 실패 — 규칙 폴백 상태(채점 무효)")
pmap = {(f, t): p for (f, t, _), p in zip(items, pred)}


def score(name, subset):
    n = len(subset)
    if n == 0:
        return None
    ok = flip = 0
    cm = collections.defaultdict(collections.Counter)
    for k, gold in subset.items():
        p = pmap[k]
        cm[gold][p] += 1
        if p == gold:
            ok += 1
        elif {p, gold} == {"positive", "negative"}:
            flip += 1
    acc = 100.0 * ok / n
    alo, ahi = wilson(ok, n)
    flo, fhi = wilson(flip, n)
    rec = {}
    for g in LABELS:
        tot = sum(cm[g].values())
        if tot:
            rec[g] = {"n": tot, "correct": cm[g][g], "recall": round(100.0 * cm[g][g] / tot, 2),
                      "pred": dict(cm[g])}
    print("\n=== %s (n=%d) ===" % (name, n))
    print("  정답률 %.2f%%  (95%% CI Wilson %.2f~%.2f)" % (acc, alo, ahi))
    print("  긍↔부 뒤바뀜 %d (%.2f%% · CI %.2f~%.2f)" % (flip, 100.0 * flip / n, flo, fhi))
    for g, d in rec.items():
        print("    %-9s n=%4d  %s  recall %.1f%%" % (g, d["n"], d["pred"], d["recall"]))
    return {"n": n, "correct": ok, "acc": round(acc, 2), "acc_ci": [round(alo, 2), round(ahi, 2)],
            "posneg_flip": flip, "flip_pct": round(100.0 * flip / n, 2),
            "flip_ci": [round(flo, 2), round(fhi, 2)],
            "label_dist": dict(collections.Counter(subset.values())),
            "field_dist": dict(collections.Counter(k[0] or "(없음)" for k in subset)),
            "per_class": rec}


res = {
    "measured_at": "2026-08-05",
    "note": "A=학습만 제외(구 score_human_only_260730.py 재현) · B=학습+검증 모두 제외(정본) · C=검증셋 겹침 대조군",
    "train_files": len(TRAIN_FILES), "test_sets": list(TEST_SETS.values()),
    "human_keys_total": len(human),
    "A_train_excluded_only": score("[A] 학습만 제외", setA),
    "B_clean_holdout": score("[B] 순수 미노출(학습+검증 제외) — 정본", setB),
    "C_testset_overlap": score("[C] 검증셋 겹침(낙관 편향 대조군)", setC),
}
# [D] 88건 층화 분해 — 무작위 표본이 아닌 '잔여' 집합이므로 교란 요인을 분리한다.
#     ① 칸(장점/단점) 유무: 칸이 없으면 학습·추론 규약인 필드 프리픽스가 빠진 채로 추론된다.
#     ② decision_source: 'human*' (사람이 직접 표기) vs 'user_agreed' (제시안 동의)
srcmap = {}
for pat in (os.path.join(EVAL, "*.jsonl"), os.path.join(EVAL, "review", "*.jsonl")):
    for p in sorted(glob.glob(pat)):
        if ".bak" in p or "backup" in p:
            continue
        for line in open(p, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            t = (r.get("text") or "").strip()
            ds = r.get("decision_source") or ""
            if r.get("human_decision") in LABELS and t and is_human(ds):
                srcmap[((r.get("field") or ""), t)] = ds

# 출처 파일 역추적 — 보고서가 88건을 '260715 교정 묶음 62 + 그 외 26'으로 서술하므로,
# 그 구분이 산출물 안에서 검증되도록 건별 출처를 함께 기록한다(인수검수 2차 지적).
filemap = collections.defaultdict(set)
for pat in (os.path.join(EVAL, "*.jsonl"), os.path.join(EVAL, "review", "*.jsonl")):
    for p in sorted(glob.glob(pat)):
        if ".bak" in p or "backup" in p:
            continue
        base = os.path.basename(p)
        for line in open(p, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            k = ((r.get("field") or ""), (r.get("text") or "").strip())
            if k in setB and is_human(r.get("decision_source") or ""):
                filemap[k].add(base)

def is_715(k):
    return any("260715" in f for f in filemap.get(k, ()))

strata = {
    "260715 교정 묶음(회수분)": {k: v for k, v in setB.items() if is_715(k)},
    "그 외": {k: v for k, v in setB.items() if not is_715(k)},
    "칸 있음(프리픽스 적용)": {k: v for k, v in setB.items() if k[0]},
    "칸 없음(프리픽스 없음)": {k: v for k, v in setB.items() if not k[0]},
    "decision_source=human*": {k: v for k, v in setB.items() if srcmap.get(k, "").startswith("human")},
    "decision_source=user_agreed": {k: v for k, v in setB.items() if srcmap.get(k) == "user_agreed"},
}
res["D_strata_of_B"] = {name: score("[D] " + name, s) for name, s in strata.items()}
res["B_decision_source_dist"] = dict(collections.Counter(srcmap.get(k, "(미상)") for k in setB))
res["B_src_file_dist"] = dict(collections.Counter(
    f for k in setB for f in sorted(filemap.get(k, {"(미상)"}))))

# 원자료 동봉 — 이후 재추론 없이 재검증할 수 있게 건별 기록을 남긴다(가명 텍스트만).
with open(os.path.join(HERE, "score_human_clean_260805.jsonl"), "w", encoding="utf-8") as fh:
    for k, v in setB.items():
        fh.write(json.dumps({"field": k[0], "text": k[1], "human_decision": v,
                             "model_pred": pmap[k], "decision_source": srcmap.get(k, ""),
                             "src_files": sorted(filemap.get(k, [])),
                             "stratum": "260715_withdrawn" if is_715(k) else "other",
                             "correct": pmap[k] == v}, ensure_ascii=False) + "\n")

a, b, c = res["A_train_excluded_only"], res["B_clean_holdout"], res["C_testset_overlap"]
res["optimism_gap_pp"] = round(c["acc"] - b["acc"], 2)
res["A_minus_B_pp"] = round(a["acc"] - b["acc"], 2)
print("\n낙관 편향 크기: 겹침(C) %.2f%% − 미노출(B) %.2f%% = %+.2f%%p" % (c["acc"], b["acc"], res["optimism_gap_pp"]))
print("구 보고값(A) %.2f%% → 정본(B) %.2f%% = %+.2f%%p" % (a["acc"], b["acc"], -res["A_minus_B_pp"]))
json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n저장: %s" % OUT)
