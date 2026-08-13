# -*- coding: utf-8 -*-
"""사람 판정 누적 총량 집계 — "표본이 400건뿐인가"에 대한 실측 답변(§4-3-0).

배경: 본 사업의 사람 판정은 400건이 아니라 누적 1만여 건이다. 그러나 그 누적분은
      하드케이스·필드충돌·모델 오답을 표적 수집한 **적대 표본**이라 모집단을 대표하지
      않는다. 따라서 성능 일반화의 자로는 쓸 수 없고, 별도 무작위 표본이 필요하다.
      이 스크립트는 (a) 누적 총량 (b) 그 분포 편중 (c) 적대 표본 위에서 S0를 재면
      전수 센서스와 어떻게 어긋나는지를 수치로 보인다.

집계 규칙:
  - `human_decision` ∈ {positive, negative, neutral} 인 행만 사람 판정으로 센다.
  - `decision_source == "auto_fragment"`(규칙 자동 판정)는 제외한다.
  - 중복은 (field, text) 키로 제거한다(같은 문장이 여러 큐에 실려 있음).
  - `.bak`/`backup` 파일은 제외한다.
"""
import collections
import glob
import json
import os
import sys

DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
EVAL = os.path.join(DS, "eval")
SCRIPTS = os.path.join(DS, "scripts")
LABELS = ("positive", "negative", "neutral")
FMAP = {"장점": "positive", "단점": "negative"}

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, SCRIPTS)
from finetune_sentiment import TRAIN_FILES, TEST_SETS  # noqa: E402


def count(path):
    """(전체 행, 사람 판정 행, 라벨 분포)"""
    if not os.path.isfile(path):
        return None
    n = h = 0
    dist = collections.Counter()
    for line in open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
        except Exception:
            continue
        n += 1
        hd = r.get("human_decision")
        if hd in LABELS and (r.get("text") or "").strip():
            h += 1
            dist[hd] += 1
    return n, h, dist


res = {}

print("=== 검증 held-out (TEST_SETS) ===")
tot_test = 0
res["test_sets"] = {}
for k, fn in TEST_SETS.items():
    n, h, d = count(os.path.join(EVAL, fn))
    tot_test += h
    res["test_sets"][k] = dict(file=fn, rows=n, labeled=h, dist=dict(d))
    print(f"  {k:12s} {fn:34s} 행{n:6d} 사람라벨{h:6d}")
print(f"  합계 {tot_test}")

print("\n=== 학습 투입 (TRAIN_FILES) ===")
tot_train = 0
res["train_files"] = {}
for fn in TRAIN_FILES:
    r = count(os.path.join(EVAL, fn))
    if r is None:
        continue
    n, h, d = r
    tot_train += h
    res["train_files"][fn] = dict(rows=n, labeled=h, dist=dict(d))
    print(f"  {fn:44s} 행{n:6d} 사람라벨{h:6d}")
print(f"  합계 {tot_train}")


def scan(pattern):
    """(field, text) -> human_decision. 자동판정·백업 제외."""
    seen = {}
    for p in sorted(glob.glob(pattern)):
        if ".bak" in p or "backup" in p:
            continue
        for line in open(p, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            hd = r.get("human_decision")
            t = (r.get("text") or "").strip()
            if hd not in LABELS or not t:
                continue
            if (r.get("decision_source") or "") == "auto_fragment":
                continue
            seen[((r.get("field") or ""), t)] = hd
    return seen


a = scan(os.path.join(EVAL, "*.jsonl"))
b = scan(os.path.join(EVAL, "review", "*.jsonl"))
union = dict(a)
union.update(b)
res["union"] = dict(
    eval_direct=len(a), review_board=len(b), total=len(union),
    label_dist=dict(collections.Counter(union.values())),
    field_dist=dict(collections.Counter(k[0] or "(미상)" for k in union)))
print(f"\n=== 중복 제외 합집합 ===")
print(f"  eval/ 직속 {len(a):,} | eval/review/ {len(b):,} | 합집합 {len(union):,}")
print(f"  라벨 {res['union']['label_dist']}")
print(f"  필드 {res['union']['field_dist']}")

# 적대 표본 위에서 S0(입력 칸 = 라벨)를 재면 어떻게 어긋나는가
print("\n=== 적대 표본 위의 S0 정확도 (모집단 대표성 없음을 보이는 대조) ===")
res["adversarial_s0"] = {}
for f in ("장점", "단점"):
    sub = [(k, v) for k, v in union.items() if k[0] == f]
    ok = sum(1 for _, v in sub if v == FMAP[f])
    pn = sum(1 for _, v in sub if {v, FMAP[f]} == {"positive", "negative"})
    res["adversarial_s0"][f] = dict(n=len(sub), match=ok, acc=round(100 * ok / len(sub), 2),
                                    posneg=pn, posneg_pct=round(100 * pn / len(sub), 2))
    print(f"  {f}: n={len(sub):,} 칸라벨 일치 {100*ok/len(sub):.1f}% | 긍↔부 {pn:,} "
          f"({100*pn/len(sub):.1f}%)")
withf = [(k, v) for k, v in union.items() if k[0] in FMAP]
ok = sum(1 for k, v in withf if v == FMAP[k[0]])
res["adversarial_s0"]["overall"] = dict(n=len(withf), acc=round(100 * ok / len(withf), 2))
print(f"  전체(칸 보유 {len(withf):,}): {100*ok/len(withf):.1f}%")
print("  → 전수 센서스(장점 95.63% / 단점 35.77%)와 양방향으로 어긋난다."
      " 적대 표본은 일반화 근거가 될 수 없다.")

res["summary"] = dict(train=tot_train, test=tot_test,
                      other=len(union) - tot_train - tot_test, union=len(union))
print(f"\n요약: 학습 {tot_train} · 검증 {tot_test} · 기타(미승격) "
      f"{len(union)-tot_train-tot_test} = 합집합 {len(union)}")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "human_labels_260727.json")
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("저장:", out)
