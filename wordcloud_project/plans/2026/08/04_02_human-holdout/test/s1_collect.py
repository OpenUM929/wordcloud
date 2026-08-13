# -*- coding: utf-8 -*-
"""S1 — 사람 판정 실체 확정.

설계 원칙: **무엇이 사람 판정인지 여기서 단정하지 않는다.**
라벨을 담은 필드명(`label_field`)과 출처(`decision_source`)를 그대로 보존해 수집하고,
분포를 요약으로 내놓는다. 사람분 확정은 그 분포를 보고 S2 에서 한다.
(사전라벨을 정답으로 신뢰하지 않는다 — `claude_judgment` 는 AI 판독이라 사람이 아니다.)

입력: result/s0_inventory.json (S0 산출)
출력: result/s1_human_labels.jsonl (전량) · result/s1_summary.json (요약)
게이트: 대상 파일>0 인데 수집 0건이면 FAIL.
"""
import io
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "result")
DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune"

INV = json.load(open(os.path.join(RES, "s0_inventory.json"), encoding="utf-8"))

# 라벨을 담을 수 있는 필드 — 사람/AI 를 가리지 않고 모은 뒤 태그로 구분한다
LABEL_FIELDS = ["human_decision", "prev_human_decision", "sentiment_gold", "gold",
                "claude_judgment", "human_judgment", "y_human", "verdict"]
TEXT_KEYS = ["text", "sentence", "s", "content"]
FIELD_KEYS = ["field", "f", "칸"]
VALID = {"positive", "negative", "neutral"}
NORM = {"pos": "positive", "neg": "negative", "neu": "neutral", "중립": "neutral",
        "긍정": "positive", "부정": "negative"}

MAX_BYTES = 50 * 1024 * 1024  # 대용량 코퍼스는 사람 라벨 파일이 아님 — 제외하고 기록


def pick(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return k, d[k]
    return None, None


targets, skipped_big = [], []
for r in INV["files"]:
    if r.get("error") or not r.get("human_like_keys"):
        continue
    if any(k in r["keys"] for k in LABEL_FIELDS):
        (skipped_big if r["bytes"] > MAX_BYTES else targets).append(r)

if not targets:
    print("FAIL — 대상 파일 0건")
    sys.exit(1)

out_path = os.path.join(RES, "s1_human_labels.jsonl")
n_in = n_out = 0
by_field = Counter()
by_source = Counter()
by_field_source = Counter()
files_hit = Counter()
seen = {}
conflicts = defaultdict(set)

with open(out_path, "w", encoding="utf-8") as fo:
    for r in targets:
        p = os.path.join(DS, r["path"])
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            n_in += 1
            try:
                d = json.loads(line)
            except Exception:
                continue
            tk, text = pick(d, TEXT_KEYS)
            fk, field = pick(d, FIELD_KEYS)
            if not text or not field:
                continue
            text = str(text).strip()
            field = str(field).strip()
            if field not in ("장점", "단점"):
                continue
            for lf in LABEL_FIELDS:
                v = d.get(lf)
                if v in (None, ""):
                    continue
                v = NORM.get(str(v).strip(), str(v).strip())
                if v not in VALID:
                    continue
                src = d.get("decision_source") or "(미기재)"
                rec = dict(field=field, text=text, label=v, label_field=lf,
                           decision_source=src, src_file=r["path"])
                fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_out += 1
                by_field[lf] += 1
                by_source[src] += 1
                by_field_source[(lf, src)] += 1
                files_hit[r["path"]] += 1
                key = (field, text)
                if key in seen and seen[key] != v:
                    conflicts[key].add(seen[key])
                    conflicts[key].add(v)
                seen[key] = v

if n_out == 0:
    print("FAIL — 입력 %d행인데 수집 0건. 키 별칭·라벨값 정규화를 확인할 것" % n_in)
    sys.exit(1)

summary = dict(
    files_scanned=len(targets), files_with_labels=len(files_hit),
    files_skipped_big=[dict(path=r["path"], bytes=r["bytes"]) for r in skipped_big],
    rows_read=n_in, labels_collected=n_out,
    unique_field_text=len(seen), conflicting_keys=len(conflicts),
    by_label_field=dict(by_field.most_common()),
    by_decision_source=dict(by_source.most_common(30)),
    by_label_field_and_source={"%s | %s" % k: v for k, v in by_field_source.most_common(40)})
json.dump(summary, open(os.path.join(RES, "s1_summary.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

print("대상 %d파일(대용량 제외 %d) → 읽은 행 %s / 수집 라벨 %s / 고유(칸,문장) %s / 충돌키 %s"
      % (len(targets), len(skipped_big), format(n_in, ","), format(n_out, ","),
         format(len(seen), ","), format(len(conflicts), ",")))
print("\n[라벨 필드별]")
for k, v in by_field.most_common():
    print("  %-22s %s" % (k, format(v, ",")))
print("\n[decision_source 별 상위 12]")
for k, v in by_source.most_common(12):
    print("  %-34s %s" % (str(k)[:34], format(v, ",")))
