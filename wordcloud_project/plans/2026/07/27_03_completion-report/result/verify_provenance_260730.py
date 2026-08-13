# -*- coding: utf-8 -*-
"""판정 출처 검증 (재현용 정본). 12,924건이 누구의 판정인지 decision_source 로 분류한다.

분류 규칙:
  - 같은 (field,text) 키가 여러 파일에 있으면 '사람 표식'이 하나라도 있으면 사람으로 센다(사람에게 관대).
  - 사람 표식 = decision_source 가 'human' 으로 시작하거나 == 'user_agreed'
  - 기계 표식 = packet23_judge / claude_delegated / pattern_* / rule_silver / group 이 active_silver_*
  - 어느 표식도 없으면 '표기없음'(판별 불가)
"""
import collections, glob, json, os, sys
DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
EVAL = os.path.join(DS, "eval")
LABELS = ("positive", "negative", "neutral")
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8")
    except Exception: pass
sys.path.insert(0, os.path.join(DS, "scripts"))
from finetune_sentiment import TRAIN_FILES, TEST_SETS

def is_human(ds):  return ds.startswith("human") or ds == "user_agreed"
def is_mach(ds, grp):
    d = ds.lower()
    return (d.startswith("packet23_judge") or d.startswith("claude") or d.startswith("pattern")
            or d.startswith("rule_") or "silver" in d or grp.lower().startswith("active_silver"))

recs = collections.defaultdict(list)   # key -> [(파일, decision_source, group, review폴더여부)]
for sub, pat in (("eval", os.path.join(EVAL, "*.jsonl")),
                 ("review", os.path.join(EVAL, "review", "*.jsonl"))):
    for p in sorted(glob.glob(pat)):
        if ".bak" in p or "backup" in p: continue
        for line in open(p, encoding="utf-8"):
            try: r = json.loads(line)
            except Exception: continue
            hd = r.get("human_decision"); t = (r.get("text") or "").strip()
            if hd not in LABELS or not t: continue
            ds = (r.get("decision_source") or "")
            if ds == "auto_fragment": continue
            recs[((r.get("field") or ""), t)].append(
                (os.path.basename(p), ds, (r.get("group") or ""), sub == "review"))

print("[검산] 합집합 =", len(recs), "(보고서 기재 12,924)")

cat = {}
for k, lst in recs.items():
    if any(is_human(ds) for _, ds, _, _ in lst):        cat[k] = "사람"
    elif any(is_mach(ds, g) for _, ds, g, _ in lst):    cat[k] = "기계(AI·규칙)"
    else:                                               cat[k] = "표기없음"
cc = collections.Counter(cat.values())
print("\n[출처 분류]")
for v, n in cc.most_common(): print("   %6d  %5.1f%%  %s" % (n, 100*n/len(recs), v))

# 표기없음 좁히기: 검토게시판(eval/review/) 경유 여부
noflag = [k for k, v in cat.items() if v == "표기없음"]
via_board = sum(1 for k in noflag if any(isrev for _, _, _, isrev in recs[k]))
print("\n[표기없음 %d건 세부]" % len(noflag))
print("   검토게시판(eval/review/) 경유 = %d" % via_board)
print("   eval/ 직속에만 존재         = %d" % (len(noflag) - via_board))
print("   최초 소재 파일 상위:")
for f, n in collections.Counter(recs[k][0][0] for k in noflag).most_common(8):
    print("      %6d  %s" % (n, f))

# 구간별
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
print("\n[구간별 출처]")
for name, S in (("학습", tr), ("검증(학습제외)", te - tr), ("미승격", set(recs) - tr - te)):
    c = collections.Counter(cat[k] for k in S if k in cat)
    print("   %-14s n=%5d  %s" % (name, len(S), dict(c)))

lo = cc["사람"]; hi = cc["사람"] + cc["표기없음"]
print("\n[결론] 사람 판독 확정 하한 = %d / 상한 = %d (표기없음을 전부 사람으로 볼 때)" % (lo, hi))
print("        기계 판정 확정 = %d" % cc["기계(AI·규칙)"])

# 블라인드 400 정답 칸
p400 = ("D:/dev/wordcloud/wordcloud_project/plans/2026/07/27_03_completion-report/"
        "result/blind_judged_400.jsonl")
rs = [json.loads(l) for l in open(p400, encoding="utf-8") if l.strip()]
print("\n[블라인드 400] 행 %d / 정답 칸 필드명 = %s"
      % (len(rs), [k for k in rs[0] if k.endswith("judgment") or k in ("gold", "human_decision")]))
