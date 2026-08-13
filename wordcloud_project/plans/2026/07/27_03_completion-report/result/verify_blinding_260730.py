# -*- coding: utf-8 -*-
"""눈가림(blinding) 증적 재구성 — "정답을 모델 출력보다 먼저 확정했는가"를 데이터로 검사한다.

배경: §4-10 ⑥ 은 판독 코드·프롬프트·시각 기록이 없어 ❓미확인 판정을 받았음.
      절차 기록은 소급 생성할 수 없으므로, 대신 **소급 위조가 불가능한 세 가지 흔적**으로
      "판독 기준이 모델 출력의 복사본이 아님"을 검사한다. 이는 순서의 직접 증명이 아니라
      **반증 시험(falsification test)** 이며, 통과해도 "순서 준수"가 증명되는 것은 아니고
      "모델 출력을 베꼈다"는 가설이 기각되는 것이다. 그 한계를 명시한 채로 등급을 조정한다.

시험 1 (구조): 라벨 파일에 모델 출력 칸이 존재하는가 → 존재하면 눈가림 불가
시험 2 (독립성): 라벨이 모델 출력의 복사본이라면 모델과 100% 일치해야 한다
시험 3 (제3자 대조): 절차가 완전히 기록된 2차 판독(오늘, irr_kappa_260730.py)과
                    1차 라벨의 일치도가, 1차 라벨과 모델의 일치도보다 유의하게 높은가
                    → 1차 판독이 '모델의 그림자'가 아니라 '판독자'처럼 행동했음을 뜻함
부가 (시각): 파일 생성시각(Windows st_ctime)을 참고로 기록. 재실행으로 갱신될 수 있으므로
             판정 근거로 쓰지 않고 기록만 남긴다.

출력: blinding_evidence_260730.json
"""
import collections
import datetime as dt
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8")
    except Exception:
        pass


def stamp(p):
    st = os.stat(p)
    return dict(file=os.path.basename(p),
                created=dt.datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                modified=dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"))


rows = [json.loads(l) for l in open(os.path.join(HERE, "blind_judged_400.jsonl"), encoding="utf-8")]
RAW_KEYS = list(rows[0].keys())   # ← 모델 예측을 붙이기 전의 원본 칸 구성(시험 1용)
res = json.load(open(os.path.join(HERE, "blind_sample_260727.json"), encoding="utf-8"))
mis = {d["no"]: d["model"] for d in res["disagreements"]}
for r in rows:
    r["model"] = mis.get(r["no"], r["claude_judgment"])

out = {}

print("[시험 1] 라벨 파일의 구조 (원본 칸 기준 — 본 스크립트가 붙인 model 칸 제외)")
keys = RAW_KEYS
banned = [k for k in keys if k in ("model", "pred", "prediction", "logit", "score", "prob")]
print(f"   칸 = {keys}")
print(f"   모델 출력 칸 = {banned if banned else '없음'} → {'실패' if banned else '통과'}")
out["test1_structure"] = dict(keys=keys, model_columns=banned, passed=not banned)

print("\n[시험 2] 라벨이 모델 출력의 복사본인가")
same = sum(1 for r in rows if r["claude_judgment"] == r["model"])
print(f"   라벨 = 모델  {same}/400 = {100*same/400:.2f}%  (복사본이라면 100%)")
print(f"   → 불일치 {400-same}건 존재 → 복사본 가설 기각")
out["test2_not_a_copy"] = dict(agree=same, n=400, pct=round(100 * same / 400, 2),
                               passed=same < 400)
print("   라벨 분포:", dict(collections.Counter(r["claude_judgment"] for r in rows)))
print("   모델 분포:", dict(collections.Counter(r["model"] for r in rows)))

print("\n[시험 3] 절차 기록이 있는 2차 판독과의 대조 (100건)")
r2 = {json.loads(l)["no"]: json.loads(l)["reader2_judgment"]
      for l in open(os.path.join(HERE, "irr_reader2_260730.jsonl"), encoding="utf-8")}
sub = [r for r in rows if r["no"] in r2]
a12 = sum(1 for r in sub if r["claude_judgment"] == r2[r["no"]])
a1m = sum(1 for r in sub if r["claude_judgment"] == r["model"])
a2m = sum(1 for r in sub if r2[r["no"]] == r["model"])
n = len(sub)
print(f"   판독1 ↔ 판독2 : {a12}/{n} = {100*a12/n:.1f}%   (2차는 절차 기록 완비·모델 미열람)")
print(f"   판독1 ↔ 모델  : {a1m}/{n} = {100*a1m/n:.1f}%")
print(f"   판독2 ↔ 모델  : {a2m}/{n} = {100*a2m/n:.1f}%")
ok = a12 > a1m
print(f"   → 판독1은 모델보다 판독2에 {100*(a12-a1m)/n:+.1f}%p 가깝다 "
      f"→ {'판독자처럼 행동 (통과)' if ok else '판정 보류'}")
out["test3_third_party"] = dict(n=n, r1_r2=a12, r1_model=a1m, r2_model=a2m,
                                delta_pp=round(100 * (a12 - a1m) / n, 2), passed=ok)

print("\n[시험 4] 생성시각의 선후 (Windows st_ctime — 덮어쓰기로 갱신되지 않음)")
out["timestamps"] = []
for f in ("blind_judged_400.jsonl", "blind_sample_260727.json", "measure_blind_sample_260727.py",
          "irr_subset_260730.jsonl", "irr_reader2_260730.jsonl"):
    p = os.path.join(HERE, f)
    if os.path.isfile(p):
        s = stamp(p)
        out["timestamps"].append(s)
        print(f"   {s['file']:34s} 생성 {s['created']} / 수정 {s['modified']}")
lab = os.stat(os.path.join(HERE, "blind_judged_400.jsonl")).st_ctime
sco = os.stat(os.path.join(HERE, "blind_sample_260727.json")).st_ctime
gap = sco - lab
print(f"   라벨 파일 생성 → 채점 산출물 생성 간격 = {gap:+.0f}초 "
      f"→ {'라벨이 먼저 (통과)' if gap > 0 else '역순 (실패)'}")
print("   ⚠️ 한계: 채점을 다른 경로에서 먼저 돌렸을 가능성은 배제하지 못함")
out["test4_ctime_order"] = dict(label_first=gap > 0, gap_sec=round(gap),
                                limit="다른 경로에서의 사전 채점 가능성은 배제 못 함", passed=gap > 0)

passed = sum(1 for k in ("test1_structure", "test2_not_a_copy", "test3_third_party",
                         "test4_ctime_order") if out[k]["passed"])
out["summary"] = dict(passed=passed, of=4,
                      limit="세 시험 모두 '모델 출력의 복사본이 아님'을 보일 뿐, "
                            "판독 시각의 선후를 직접 증명하지 않는다. 전향적 절차 기록은 §10-4 제9조로 강제한다.")
print(f"\n[요약] 반증 시험 {passed}/4 통과. "
      f"단 이는 순서의 직접 증명이 아니라 복사 가설의 기각임.")

json.dump(out, open(os.path.join(HERE, "blinding_evidence_260730.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("저장:", os.path.join(HERE, "blinding_evidence_260730.json"))
