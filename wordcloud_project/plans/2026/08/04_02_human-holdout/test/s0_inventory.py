# -*- coding: utf-8 -*-
"""S0 — 사람 라벨 후보 파일 인벤토리 (원자료를 컨텍스트에 올리지 않기 위한 1단계).

목적: eval/ 아래 라벨 후보 파일이 ① 몇 행인지 ② 어떤 키를 갖는지 ③ 사람 판정 필드가
      있는지를 **파일당 요약 1줄**로 만든다. 다음 단계(S1 누출검사)는 이 요약만 보고
      대상 파일을 고르므로, 2.3GB 코퍼스는 여기서 건드리지 않는다.

설계 제약(세션 중단 대비)
  - stdout 은 요약만. 전량은 result/s0_inventory.json 으로 나간다.
  - .bak / _gold_backup / 임시 폴더는 제외 — 정본만 센다.
  - 무동작 게이트: 스캔 대상 0건이면 FAIL 로 끝낸다.
"""
import io
import json
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

DS = "D:/dev/wordcloud/wordcloud_project/plans/_datasets/kote_finetune"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "result", "s0_inventory.json")

# 사람 판정을 담을 법한 필드명 후보 (실측으로 확인하기 위한 탐침)
HUMAN_KEYS = ["human_decision", "human_judgment", "human", "decision", "final",
              "gold", "label_final", "reviewer", "judgment", "verdict", "y_human"]
SKIP_DIR = ("_gold_backup", "model_", "logs", "result", "scripts", "tmp")


def is_skip(path):
    p = path.replace("\\", "/")
    if ".bak" in p or ".backup" in p or ".pre_" in p:
        return True
    return any("/" + d in p for d in SKIP_DIR)


targets = []
for root, dirs, files in os.walk(DS):
    dirs[:] = [d for d in dirs if not any(d.startswith(s) for s in SKIP_DIR)]
    for fn in files:
        if fn.endswith(".jsonl"):
            p = os.path.join(root, fn)
            if not is_skip(p):
                targets.append(p)

if not targets:
    print("FAIL — 스캔 대상 0건. 경로를 확인할 것:", DS)
    sys.exit(1)

rows = []
for p in sorted(targets):
    size = os.path.getsize(p)
    rec = dict(path=os.path.relpath(p, DS).replace("\\", "/"), bytes=size)
    # 2GB 급 파일은 행수 전수 대신 표본만 — S0 에서 시간을 쓰지 않는다
    heavy = size > 50 * 1024 * 1024
    keys = Counter()
    n = 0
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                n += 1
                if n <= 200:
                    try:
                        keys.update(json.loads(line).keys())
                    except Exception:
                        pass
                if heavy and n >= 200:
                    break
    except Exception as e:
        rec["error"] = str(e)[:120]
        rows.append(rec)
        continue
    rec["rows"] = n
    rec["rows_exact"] = not heavy
    rec["keys"] = sorted(keys)
    rec["human_like_keys"] = [k for k in keys if any(h in k.lower() for h in HUMAN_KEYS)]
    rows.append(rec)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(dict(scanned=len(rows), root=DS, files=rows),
          open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

cand = [r for r in rows if r.get("human_like_keys") and r.get("rows_exact")]
cand.sort(key=lambda r: -r.get("rows", 0))
print("스캔 %d개 파일 → %s" % (len(rows), os.path.relpath(OUT)))
print("사람판정 후보 필드를 가진 정본 파일 상위 15개 (행수 내림차순)")
print("%-56s %8s  %s" % ("파일", "행수", "후보 필드"))
for r in cand[:15]:
    print("%-56s %8d  %s" % (r["path"][:56], r["rows"], ",".join(r["human_like_keys"])[:60]))
print("... 후보 총 %d개 파일 / 합계 %d행" % (len(cand), sum(r["rows"] for r in cand)))
