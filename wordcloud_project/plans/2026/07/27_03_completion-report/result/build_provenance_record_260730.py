# -*- coding: utf-8 -*-
"""라벨 출처 대장(provenance record) 생성 — ISO/IEC 25012 추적성 공백을 메우는 산출물.

배경: §4-10 ⑤ 는 "학습 파일 13종 내부에 판정 주체가 기록된 행이 38/4,016(99.05% 미기록)"
      으로 ❌미비 판정을 받았음. 원본 파일을 소급 수정하는 것은 append-only 원칙 위반이므로,
      **별도 대장(sidecar)** 을 생성해 행별 출처를 확정 기록한다.
      추적성 요건은 '모든 행의 출처를 아는 것'이 아니라 **'모든 행의 출처 상태가 기록되는 것'**
      이므로, 판별 불가분은 unknown 으로 확정 기록한다.

각 행에 기록하는 것:
  key_sha1        (칸+문장)의 SHA-1 앞 16자 — 원문 대신 조인 키만 실음(개인정보 노출 최소화)
  field           장점/단점
  label           human_decision
  origin          human | machine | unknown   ← 확정 기록
  origin_basis    direct(해당 행에 표기 있음) | cross_file(다른 파일 표기로 귀속) | none
  origin_rule     귀속에 사용한 규칙 문자열
  decision_sources 관측된 decision_source 원문 전체(중복 제거)
  files           출현한 파일 전부
  split           train | eval_only | not_promoted
  in_deployed_train 배포 모델(2026-07-08) 학습 파일 목록에 포함되었는가

출력: training_provenance_260730.jsonl  +  provenance_summary_260730.json
"""
import collections
import glob
import hashlib
import json
import os
import sys

DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
EVAL = os.path.join(DS, "eval")
HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = ("positive", "negative", "neutral")

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass
sys.path.insert(0, os.path.join(DS, "scripts"))
from finetune_sentiment import TRAIN_FILES, TEST_SETS  # noqa: E402

HUMAN_RULE = "decision_source 가 'human' 으로 시작하거나 == 'user_agreed'"
MACH_RULE = ("decision_source 가 packet23_judge/claude*/pattern*/rule_* 로 시작하거나 "
             "'silver' 포함, 또는 group 이 active_silver* 로 시작")


def is_human(ds):
    return ds.startswith("human") or ds == "user_agreed"


def is_mach(ds, grp):
    d = ds.lower()
    return (d.startswith("packet23_judge") or d.startswith("claude") or d.startswith("pattern")
            or d.startswith("rule_") or "silver" in d or grp.lower().startswith("active_silver"))


recs = collections.defaultdict(list)
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
            if hd not in LABELS or not t:
                continue
            ds = r.get("decision_source") or ""
            if ds == "auto_fragment":
                continue
            recs[((r.get("field") or ""), t)].append(
                dict(file=os.path.basename(p), ds=ds, grp=r.get("group") or "", label=hd))

print(f"[1] 누적 풀 합집합 = {len(recs)}건 (보고서 기재 12,924)")


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
print(f"[2] 학습 고유 = {len(tr)} / 검증(학습 제외) = {len(te - tr)} / 미승격 = {len(set(recs)-tr-te)}")

n_direct = n_cross = 0
cnt = collections.Counter()
split_cnt = collections.defaultdict(collections.Counter)
outp = os.path.join(HERE, "training_provenance_260730.jsonl")
with open(outp, "w", encoding="utf-8") as f:
    for (field, text), lst in sorted(recs.items()):
        sources = sorted({e["ds"] for e in lst if e["ds"]})
        files = sorted({e["file"] for e in lst})
        h = [e for e in lst if is_human(e["ds"])]
        m = [e for e in lst if is_mach(e["ds"], e["grp"])]
        if h:
            origin, rule = "human", HUMAN_RULE
        elif m:
            origin, rule = "machine", MACH_RULE
        else:
            origin, rule = "unknown", "어느 표식도 관측되지 않음"
        # 귀속 근거: 표식이 '해당 행 자체'에 있으면 direct, 여러 파일 중 일부에만 있으면 cross_file
        if origin == "unknown":
            basis = "none"
        elif len(files) == 1:
            basis = "direct"
            n_direct += 1
        else:
            marked = {e["file"] for e in (h or m)}
            basis = "direct" if marked == set(files) else "cross_file"
            n_direct += (basis == "direct")
            n_cross += (basis == "cross_file")
        key = (field, text)
        split = "train" if key in tr else ("eval_only" if key in te else "not_promoted")
        cnt[origin] += 1
        split_cnt[split][origin] += 1
        f.write(json.dumps(dict(
            key_sha1=hashlib.sha1((field + "\x00" + text).encode("utf-8")).hexdigest()[:16],
            field=field, label=lst[0]["label"], origin=origin, origin_basis=basis,
            origin_rule=rule, decision_sources=sources, files=files, split=split,
            in_deployed_train=(key in tr)), ensure_ascii=False) + "\n")

print(f"\n[3] 출처 확정 기록 {sum(cnt.values())}건 — 미기록 0건 (판별 불가분은 unknown 으로 확정)")
for k, v in cnt.most_common():
    print(f"    {v:6d}  {100*v/sum(cnt.values()):5.1f}%  {k}")
print(f"\n[4] 귀속 근거   direct(자체 표기) = {n_direct} / cross_file(타 파일 귀속) = {n_cross}")
print("\n[5] 구간별 출처")
for sp in ("train", "eval_only", "not_promoted"):
    c = split_cnt[sp]
    print(f"    {sp:14s} n={sum(c.values()):5d}  {dict(c)}")

summary = dict(total=sum(cnt.values()), origin=dict(cnt),
               basis=dict(direct=n_direct, cross_file=n_cross),
               by_split={k: dict(v) for k, v in split_cnt.items()},
               human_rule=HUMAN_RULE, machine_rule=MACH_RULE,
               note=("원본 코퍼스는 append-only 이므로 소급 수정하지 않고 별도 대장으로 기록함. "
                     "unknown 은 '기록 누락'이 아니라 '판별 불가로 확정 기록'된 상태임. "
                     "cross_file 귀속은 사람에게 관대한 방향이므로 human 수는 상한 추정치."),
               record_file=os.path.basename(outp))
json.dump(summary, open(os.path.join(HERE, "provenance_summary_260730.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("\n저장:", outp)
print("저장:", os.path.join(HERE, "provenance_summary_260730.json"))
