# -*- coding: utf-8 -*-
"""88건 중 칸(field) 값이 비어 있는 26건에 대해, 데이터셋 안에서 칸을 복원할 수 있는지 전수 확인한다.

신설 사유(2026-08-05, 인수검수 지적): 상세 §6-4-1 (2)·조치 10번이 "복원 가능한 것은 26건 중
5건뿐"이라고 적었으나 산출 스크립트가 동봉되지 않아 검수자가 판정 불가([미확인]) 상태였음.
§10-4 제2조("수치에는 산출 코드를 동봉한다")의 자기적용.

방법: 26건의 text 를 키로, 데이터셋 하위 전 .jsonl 을 훑어 같은 text 를 가진 행 중
      field 값이 비어 있지 않은 것이 하나라도 있으면 '복원 가능'으로 센다.
      대형 파일(weak_export 계열)도 제외하지 않는다 — 부재 결론을 파생본 하나로 내지 않기 위함.
"""
import collections
import glob
import json
import os
import sys

DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune/"
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "score_human_clean_260805.jsonl")
OUT = os.path.join(HERE, "verify_field_recovery_260805.json")

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass

targets = {}
for line in open(SRC, encoding="utf-8"):
    r = json.loads(line)
    if not r["field"]:
        targets[r["text"]] = r["human_decision"]
print("칸 없는 대상: %d건" % len(targets))

found = collections.defaultdict(collections.Counter)   # text -> {field: n}
seen_in = collections.defaultdict(set)                 # text -> {file}
scanned = 0
for p in sorted(glob.glob(os.path.join(DS, "**", "*.jsonl"), recursive=True)):
    if ".bak" in p or "backup" in p:
        continue
    scanned += 1
    base = os.path.relpath(p, DS).replace("\\", "/")
    try:
        for line in open(p, encoding="utf-8"):
            if '"text"' not in line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            t = (r.get("text") or "").strip()
            if t in targets:
                seen_in[t].add(base)
                f = r.get("field")
                if f:
                    found[t][f] += 1
    except Exception as e:
        print("  ! 읽기 실패 %s: %s" % (base, e))

recoverable = {t: dict(c) for t, c in found.items() if c}
ambiguous = {t: c for t, c in recoverable.items() if len(c) > 1}
print("스캔한 파일: %d" % scanned)
print("어딘가에서 발견된 대상: %d / %d" % (len(seen_in), len(targets)))
print("칸이 복원되는 대상: %d" % len(recoverable))
print("복원되나 칸이 상충(장점·단점 양쪽 출현): %d" % len(ambiguous))
for t, c in recoverable.items():
    print("  %-8s ← %s | %s" % (list(c)[0] if len(c) == 1 else "충돌", c, t[:44]))

json.dump({
    "measured_at": "2026-08-05",
    "targets": len(targets),
    "files_scanned": scanned,
    "found_anywhere": len(seen_in),
    "recoverable": len(recoverable),
    "ambiguous": len(ambiguous),
    "detail": {t: {"fields": c, "files": sorted(seen_in[t])} for t, c in recoverable.items()},
}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("저장: %s" % OUT)
