# -*- coding: utf-8 -*-
"""T1 — 사람 판독용 눈가림 패키지 생성.

만드는 것
  A. 조치요청 4번 — 기존 400건 재판독
     A-1 판독자1: 400건 전건            reading/A1_판독자1_400건.csv/.jsonl
     A-2 판독자2: 그중 100건(κ 대조용)   reading/A2_판독자2_100건.csv/.jsonl
         ※ 100건은 2026-07-30 κ 산출에 쓴 `irr_subset_260730.jsonl` 과 **동일 표본**을 쓴다.
            그래야 사람-사람 κ 를 기존 AI-AI κ 0.967 과 같은 자리에서 비교할 수 있다.
  B. 조치요청 5번 — 뒤바뀜 정밀화 1,610건  reading/B_뒤바뀜정밀화_1610건.csv/.jsonl

눈가림 규약(어기면 자료가 무효가 된다)
  - `claude_judgment`(기존 AI 판독) · 모델 예측 · 규칙 판정을 **출력에 넣지 않는다**
  - 판독자에게 주는 열은 `no · 칸 · 문장 · 판정(빈칸)` 뿐이다
  - `rec_id` 는 회수 후 대사에만 쓰므로 CSV 에서 제외하고 JSONL 매핑에만 남긴다

CSV 는 Excel 한글 깨짐 방지를 위해 utf-8-sig(BOM) 로 쓴다.
게이트: 입력>0 인데 출력 0행이면 FAIL.
"""
import csv
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "reading")
SRC = "D:/dev/wordcloud/wordcloud_project/plans/2026/07/27_03_completion-report/result"

BLIND_DROP = ("claude_judgment", "model_judgment", "rule_judgment", "pred",
              "human_decision", "gold", "label", "sentiment_gold")


def load(fn):
    p = os.path.join(SRC, fn)
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def emit(rows, base, title):
    """CSV(사람용·눈가림) + JSONL(기계 대사용·rec_id 포함) 동시 생성."""
    os.makedirs(OUT, exist_ok=True)
    leaked = sorted({k for r in rows for k in r if k in BLIND_DROP})
    csv_p = os.path.join(OUT, base + ".csv")
    with open(csv_p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["no", "칸", "문장", "판정(positive/negative/neutral)", "메모"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r.get("field", ""), r.get("text", ""), "", ""])
    jsonl_p = os.path.join(OUT, base + ".map.jsonl")
    with open(jsonl_p, "w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            f.write(json.dumps(dict(no=i, rec_id=r.get("rec_id"), field=r.get("field"),
                                    text=r.get("text")), ensure_ascii=False) + "\n")
    print("  %-30s %5d행  (제거한 정답열: %s)"
          % (base, len(rows), ",".join(leaked) if leaked else "없음"))
    return len(rows)


print("[판독 패키지 생성]")
r400 = load("blind_judged_400.jsonl")
irr = load("irr_subset_260730.jsonl")
irr_nos = {r["no"] for r in irr}
r100 = [r for r in r400 if r["no"] in irr_nos]
r1610 = load("sample_round2u_1610_20260804.jsonl")

if not (r400 and r1610):
    print("FAIL — 원본 표본을 읽지 못했다")
    sys.exit(1)
if len(r100) != len(irr_nos):
    print("FAIL — κ 대조 100건 매칭 실패: %d/%d" % (len(r100), len(irr_nos)))
    sys.exit(1)

n = 0
n += emit(r400, "A1_판독자1_400건", "조치4 전건")
n += emit(r100, "A2_판독자2_100건", "조치4 κ대조")
n += emit(r1610, "B_뒤바뀜정밀화_1610건", "조치5")

if n == 0:
    print("FAIL — 출력 0행")
    sys.exit(1)

# 눈가림 자기검사 — 생성된 CSV 어디에도 정답 문자열이 없어야 한다
bad = []
for fn in os.listdir(OUT):
    if not fn.endswith(".csv"):
        continue
    head = open(os.path.join(OUT, fn), encoding="utf-8-sig").readline()
    if any(k in head for k in ("judgment", "판정결과", "정답", "예측")):
        bad.append(fn)
print("\n눈가림 자기검사: %s" % ("FAIL — " + ",".join(bad) if bad else "통과 (CSV 헤더에 정답·예측 열 없음)"))
print("총 %d행 / 출력 %s" % (n, os.path.relpath(OUT)))
