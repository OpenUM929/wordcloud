# -*- coding: utf-8 -*-
"""라벨 마스터 빌더 — 흩어진 라벨 파일을 출처 태그가 붙은 단일 스트림으로 통합한다.

신설 사유(2026-08-04, `plans/2026/08/04_02_human-holdout`): 라벨이 117개 파일에 흩어져 있고
**필드명이 출처를 뜻하지 않는다**(`human_decision` 에 Claude 판정·규칙 산출이 섞여 있음).
그래서 "사람이 만든 라벨이 무엇인가"에 답하려면 매번 전수 스캔이 필요했다. 이 스크립트는
그 답을 **한 파일**로 고정한다.

출력
  eval/label_master_260804.jsonl   — 고유 (칸,문장) 1행. 티어·출처·충돌 여부 포함
  result/label_master_260804.md    — 현황 요약(사람이 읽는 쪽)

티어 규약 (decision_source 실측 기반)
  A_human   : decision_source == "human"                → 사람 확정. 주장 근거로 쓸 수 있음
  B_unknown : decision_source 미기재                     → 출처 불명. **주장 근거 금지**
  C_auto    : claude/packet/pattern/rule/auto 계열       → AI·규칙 산출

용도 표시
  in_train / in_test : finetune_sentiment.py 의 TRAIN_FILES·TEST_SETS 에 포함 여부
  → 홀드아웃 후보 = A_human 이면서 in_train·in_test 모두 False

멱등: 매 실행마다 전체 재생성(append 아님). 원본 파일은 건드리지 않는다.
게이트: 입력>0 인데 출력 0행이면 FAIL.
"""
import io
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from finetune_sentiment import TRAIN_FILES, TEST_SETS  # noqa: E402

OUT_JSONL = os.path.join(DS, "eval", "label_master_260804.jsonl")
OUT_MD = os.path.join(DS, "result", "label_master_260804.md")

LABEL_FIELDS = ["human_decision", "prev_human_decision", "sentiment_gold", "gold",
                "claude_judgment", "human_judgment", "y_human", "verdict"]
TEXT_KEYS = ["text", "sentence", "s", "content"]
FIELD_KEYS = ["field", "f", "칸"]
VALID = {"positive", "negative", "neutral"}
NORM = {"pos": "positive", "neg": "negative", "neu": "neutral",
        "긍정": "positive", "부정": "negative", "중립": "neutral"}
SKIP = ("_gold_backup", "model_", "logs", "result", "scripts", "tmp")
MAX_BYTES = 50 * 1024 * 1024


def tier_of(src):
    if src == "human":
        return "A_human"
    if not src:
        return "B_unknown"
    return "C_auto"


def pick(d, keys):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def keyset(fn):
    for sub in ("eval", "emotion", ""):
        p = os.path.join(DS, sub, fn) if sub else os.path.join(DS, fn)
        if os.path.isfile(p):
            ks = set()
            for line in open(p, encoding="utf-8"):
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                t, f = pick(d, TEXT_KEYS), pick(d, FIELD_KEYS)
                if t and f:
                    ks.add((str(f).strip(), str(t).strip()))
            return ks
    return set()


train_keys = set().union(*[keyset(f) for f in TRAIN_FILES]) if TRAIN_FILES else set()
test_keys = set().union(*[keyset(f) for f in TEST_SETS.values()]) if TEST_SETS else set()

# ── 수집 ──
recs = defaultdict(list)
n_in = n_files = 0
for root, dirs, files in os.walk(DS):
    dirs[:] = [d for d in dirs if not any(d.startswith(s) for s in SKIP)]
    for fn in files:
        if not fn.endswith(".jsonl"):
            continue
        p = os.path.join(root, fn)
        rel = os.path.relpath(p, DS).replace("\\", "/")
        if any("/" + s in "/" + rel for s in SKIP) or ".bak" in rel or ".pre_" in rel:
            continue
        if os.path.getsize(p) > MAX_BYTES:
            continue
        hit = False
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            n_in += 1
            try:
                d = json.loads(line)
            except Exception:
                continue
            t, f = pick(d, TEXT_KEYS), pick(d, FIELD_KEYS)
            if not t or not f:
                continue
            f, t = str(f).strip(), str(t).strip()
            if f not in ("장점", "단점"):
                continue
            for lf in LABEL_FIELDS:
                v = d.get(lf)
                if v in (None, ""):
                    continue
                v = NORM.get(str(v).strip(), str(v).strip())
                if v not in VALID:
                    continue
                recs[(f, t)].append(dict(label=v, label_field=lf,
                                         decision_source=d.get("decision_source") or "",
                                         src_file=rel))
                hit = True
        n_files += hit

if not recs:
    print("FAIL — 입력 %d행인데 수집 0건" % n_in)
    sys.exit(1)

# ── 병합: 키당 1행. 티어 우선순위 A > B > C, 동일 티어 내 라벨 충돌은 표시만 하고 판정하지 않는다 ──
PRIO = {"A_human": 0, "B_unknown": 1, "C_auto": 2}
out = []
for (f, t), lst in recs.items():
    for r in lst:
        r["tier"] = tier_of(r["decision_source"])
    lst.sort(key=lambda r: PRIO[r["tier"]])
    best = lst[0]
    same_tier = [r for r in lst if r["tier"] == best["tier"]]
    labels = {r["label"] for r in same_tier}
    out.append(dict(
        field=f, text=t, label=best["label"], tier=best["tier"],
        decision_source=best["decision_source"] or None,
        label_field=best["label_field"], src_file=best["src_file"],
        n_sources=len(lst),
        conflict=sorted(labels) if len(labels) > 1 else None,
        posneg_conflict=bool({"positive", "negative"} <= labels),
        in_train=(f, t) in train_keys, in_test=(f, t) in test_keys,
        holdout_candidate=(best["tier"] == "A_human"
                           and (f, t) not in train_keys and (f, t) not in test_keys)))

out.sort(key=lambda r: (PRIO[r["tier"]], r["field"], r["text"]))
os.makedirs(os.path.dirname(OUT_JSONL), exist_ok=True)
with open(OUT_JSONL, "w", encoding="utf-8") as fo:
    for r in out:
        fo.write(json.dumps(r, ensure_ascii=False) + "\n")

# ── 요약 ──
tc = Counter(r["tier"] for r in out)
conf = [r for r in out if r["conflict"]]
pn = [r for r in out if r["posneg_conflict"]]
hold = [r for r in out if r["holdout_candidate"]]


def row(t):
    s = [r for r in out if r["tier"] == t]
    return (len(s), sum(r["in_train"] for r in s), sum(r["in_test"] for r in s),
            sum(1 for r in s if not r["in_train"] and not r["in_test"]),
            sum(1 for r in s if r["conflict"]))


md = ["# 라벨 마스터 — 현황 (2026-08-04)", "",
      "> 생성: `scripts/build_label_master_260804.py` · 정본: `eval/label_master_260804.jsonl`",
      "> 멱등 — 재실행하면 전체 재생성된다. 원본 라벨 파일은 수정하지 않는다.", "",
      "## 왜 만들었나", "",
      "라벨이 파일 수십 개에 흩어져 있고 **필드명이 출처를 뜻하지 않는다**. "
      "`human_decision` 이라는 이름의 필드에 Claude 판정·규칙 산출이 섞여 있어, "
      "\"사람이 만든 라벨이 무엇인가\"에 답하려면 매번 전수 스캔이 필요했다. 그 답을 한 파일로 고정한 것이다.", "",
      "**출처 판별은 필드명이 아니라 `decision_source` 로만 한다.**", "",
      "## 현황", "",
      "| 티어 | 정의 | 고유 (칸,문장) | 학습 포함 | 테스트 포함 | 미사용 | 라벨 충돌 |",
      "|---|---|---:|---:|---:|---:|---:|"]
for t, d in [("A_human", "사람 확정 — **주장 근거로 쓸 수 있음**"),
             ("B_unknown", "출처 미기재 — **주장 근거 금지**"),
             ("C_auto", "AI·규칙 산출")]:
    n, tr, te, un, cf = row(t)
    md.append("| `%s` | %s | %s | %s | %s | %s | %s |"
              % (t, d, f"{n:,}", f"{tr:,}", f"{te:,}", f"{un:,}", f"{cf:,}"))
md += ["", "- 전체 고유 (칸,문장) **%s개** (원본 %s행 / 라벨 보유 파일 %d개)"
       % (f"{len(out):,}", f"{n_in:,}", n_files),
       "- 라벨이 엇갈리는 키 **%s개**, 그중 **긍↔부 정면 충돌 %s개**"
       % (f"{len(conf):,}", f"{len(pn):,}"),
       "- **홀드아웃 후보(A_human 이면서 학습·테스트 미포함): %s개**" % f"{len(hold):,}",
       "", "## 쓰는 법", "",
       "```python", "import json",
       "rows = [json.loads(l) for l in open('eval/label_master_260804.jsonl', encoding='utf-8')]",
       "human = [r for r in rows if r['tier'] == 'A_human']          # 사람 확정만",
       "holdout = [r for r in rows if r['holdout_candidate']]        # 채점에 쓸 수 있는 것",
       "risky = [r for r in rows if r['posneg_conflict']]            # 긍↔부 충돌 — 우선 검토",
       "```", "",
       "## 주의", "",
       "- `B_unknown` 은 수량이 많지만 **사람인지 AI인지 모른다.** 사람 정답이라 부르면 근거 없는 주장이 된다",
       "- `conflict` 가 붙은 키는 **같은 문장에 다른 라벨**이 달린 것이다. 이 스크립트는 표시만 하고 **판정하지 않는다** — 사람이 정할 몫이다",
       "- `posneg_conflict` 는 긍↔부 정면 충돌이라 **최우선 검토 대상**이다(사업 제1원칙)",
       "- 라벨 신규 적재 시 **`decision_source` 를 반드시 기록**할 것. 없으면 `B_unknown` 으로 떨어져 쓸 수 없게 된다"]
os.makedirs(os.path.dirname(OUT_MD), exist_ok=True)
open(OUT_MD, "w", encoding="utf-8").write("\n".join(md) + "\n")

print("원본 %s행 / 라벨보유 %d파일 → 고유 (칸,문장) %s"
      % (f"{n_in:,}", n_files, f"{len(out):,}"))
print("%-11s %8s %9s %9s %8s %8s" % ("티어", "고유", "학습", "테스트", "미사용", "충돌"))
for t in ("A_human", "B_unknown", "C_auto"):
    n, tr, te, un, cf = row(t)
    print("%-11s %8s %9s %9s %8s %8s" % (t, f"{n:,}", f"{tr:,}", f"{te:,}", f"{un:,}", f"{cf:,}"))
print("\n라벨 충돌 %s개 (긍↔부 정면충돌 %s개) / 홀드아웃 후보 %s개"
      % (f"{len(conf):,}", f"{len(pn):,}", f"{len(hold):,}"))
print("→ %s\n→ %s" % (os.path.relpath(OUT_JSONL, DS), os.path.relpath(OUT_MD, DS)))
