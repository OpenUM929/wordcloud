# -*- coding: utf-8 -*-
"""검토큐 규칙 프리필 + silver 분리 (사용자 지시 E, 2026-08-06).

무엇을 하는가
  확립된 라벨링 규칙을 코드로 명시해 미판정 행에 `claude_judgment` 를 채우고,
  배포 모델 판정(`cur_rule_label`)과 **합의하면 silver 로 큐에서 빼고**,
  **불일치하거나 규칙이 발동하지 않으면 사용자 판정 대상으로 남긴다.**

정직 고지
  이 프리필은 **문장을 한 건씩 읽어 내린 판단이 아니라 규칙 발동 결과**다.
  그래서 `decision_source='claude_rule_prefill_260806'` 로 사람 판정과 구분하고,
  `claude_judgment.rule` 에 어떤 규칙이 걸렸는지 남긴다. gold 로 쓰지 않는다.

안전 규칙 (긍↔부 오분류 방지 최우선)
  · P1(긍↔부 뒤바뀜 후보)은 프리필만 하고 **silver 로 빼지 않는다** — 사람 눈이 목적인 큐다.
  · 규칙이 발동하지 않은 행은 건드리지 않는다(빈 판정을 지어내지 않는다).

규칙 (RUNBOOK §2-5 · 라벨링 원칙 · 사용자 확정 사항)
  R1 무결점·약점부재 선언 → 중립 (명시 강긍정 동반 시 긍정)
  R2 건강·개인안녕·평가유보 → 중립
  R3 개선요청 화행(~필요/키워야/보완해야) → 부정
  R4 양가 업무태도(꼼꼼·철저·원칙·신중·소신·객관) → 긍정, 명시 해악표지 동반 시 부정
  (R5 사생활→중립 은 표본 검증에서 개선요청 문장을 삼켜 폐기했다)
  적용 순서는 위와 같다(R1 이 R3 보다 앞서야 "보완필요점 없음" 이 부정으로 새지 않는다).
"""
import io
import json
import os
import re
import sys
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REVIEW = os.path.join(ROOT, "eval", "review")
SILVER = os.path.join(REVIEW, "_archive", "silver")
DATE = "260806"

# ⚠ 표본 검증(260806)에서 걸러낸 오발동을 반영한 형태다. 아래 주석을 지우지 말 것.
#   · 맨끝 `없습니다$|없음$` 를 무결점으로 보면 "일과삶의 균형, 없습니다"·"너무 자리에 없습니다"
#     같은 **지적 문장이 중립으로 뒤집힌다**(부→중). 반드시 보완/개선/약점류 표지와 함께여야 한다.
#   · "X 외 없습니다" 는 X 를 지적한 문장이므로 무결점이 아니다 → NO_WEAK_BLOCK 으로 뺀다.
NO_WEAK = re.compile(r"(보완|개선|지적|미흡|단점|약점|부족|아쉬|고칠|나무랄)[^.]{0,12}?"
                     r"(없|미발견|모르겠)")
NO_WEAK_BLOCK = re.compile(r"(외|말고|빼고|이외|제외)\s*(딱히\s*)?없")
STRONG_POS = re.compile(r"완벽|탁월|뛰어남|뛰어난|훌륭|최고|모범")
WELLBEING = re.compile(r"건강|건겅|몸이|병가|치료|입원|체력|가정사|개인사"
                       r"|평가하기\s*어렵|판단하기\s*어렵|잘\s*모르겠|함께\s*일한\s*기간|파악하기\s*어렵"
                       r"|접점이\s*없|경험이\s*없")
IMPROVE = re.compile(r"(필요하|필요함|필요합니다|필요해|필요가\s*있|요구된|요구됨|키워야|길러야"
                     r"|보완해야|개선해야|노력해야|향상시켜야|바랍니다|바람직|요망)")
IMPROVE_BLOCK = re.compile(r"없|잘\s*확인|잘\s*파악|충분")
AMBI = re.compile(r"꼼꼼|철저|원칙|신중|소신|객관|엄격|정확성|성실|열정|책임감")
AMBI_DEGREE = re.compile(r"너무|지나치|과도|다소|때로")
# ⚠ "무시" 를 그대로 넣으면 "업무시간"·"업무시" 에 substring 매칭돼 칭찬이 부정으로 뒤집힌다
#   (260716 감사에서 같은 함정으로 E1 오추출이 났다). 활용형으로만 잡는다.
HARM = re.compile(r"고압적|강압|독선|편향|기복|위압|폭언|따돌|차별|불친절|비협조|무시(하|한|함|해|당)")
# R5(사생활→중립)는 폐기했다. 표본에서 "흡연을 줄여야"·"결혼생활을 잘 챙겨야" 같은
# **개선요청이 섞인 문장까지 중립으로 만들어** 부→중 오류를 냈다. 사용자 판정으로 넘긴다.


def judge(text):
    """규칙 발동 시 (라벨, 규칙명) 반환. 아니면 (None, None)."""
    t = text or ""
    if NO_WEAK.search(t) and not NO_WEAK_BLOCK.search(t):
        if STRONG_POS.search(t):
            return "positive", "R1b 무결점+명시강긍정→긍정"
        return "neutral", "R1 무결점·약점부재 선언→중립"
    if WELLBEING.search(t):
        return "neutral", "R2 건강·개인안녕·평가유보→중립"
    if AMBI.search(t) and AMBI_DEGREE.search(t):
        if HARM.search(t):
            return "negative", "R4b 양가태도+명시해악표지→부정"
        return "positive", "R4 양가 업무태도(기업 관점)→긍정"
    if IMPROVE.search(t) and not IMPROVE_BLOCK.search(t):
        return "negative", "R3 개선요청 화행→부정"
    return None, None


DRY = "--apply" not in sys.argv
files = sorted(f for f in os.listdir(REVIEW) if f.endswith(".jsonl"))
stat = collections.Counter()
samples = collections.defaultdict(list)
moved = collections.Counter()

for nm in files:
    p = os.path.join(REVIEW, nm)
    recs = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
    keep, silver = [], []
    for r in recs:
        if r.get("human_decision") is not None or r.get("gold") is not None:
            keep.append(r)
            continue
        lab, rule = judge(r.get("text"))
        if lab:
            r["claude_judgment"] = {"polarity": lab, "rule": rule,
                                    "reason": "규칙 프리필(문장 개별 판독 아님) — " + rule}
            r["decision_source"] = "claude_rule_prefill_%s" % DATE
            stat[rule] += 1
            if len(samples[rule]) < 4:
                samples[rule].append((r.get("text"), r.get("cur_rule_label")))
        # 합의라도 **부정 라벨은 큐에 남긴다** — 확립 원칙이 「중립·긍정만 자동, 부정은 잔여」다.
        # 부정으로 자동 확정했다가 실제로 칭찬이면 긍↔부 오분류가 누락으로 실현된다.
        agree = (lab is not None and lab == r.get("cur_rule_label") and lab != "negative")
        if agree and not nm.startswith("P1_"):
            stat["silver(모델과 합의)"] += 1
            moved[nm] += 1
            silver.append(r)
        else:
            if lab and not agree:
                stat["escalation(모델과 불일치)"] += 1
            elif not lab:
                stat["규칙 미발동(사용자 판정)"] += 1
            keep.append(r)
    if not DRY:
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            for r in keep:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if silver:
            with io.open(os.path.join(SILVER, "rule_silver_%s__%s" % (DATE, nm)),
                         "w", encoding="utf-8", newline="\n") as f:
                for r in silver:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")

out = io.open(os.path.join(HERE, "_prefill_report.txt"), "w", encoding="utf-8")
out.write("모드: %s\n\n규칙별 발동\n" % ("DRY(미적용)" if DRY else "APPLY(적용)"))
for k, v in stat.most_common():
    out.write("  %-34s %6d\n" % (k, v))
out.write("\n규칙별 표본 (문장 / 현재 모델 판정)\n")
for rule, ss in samples.items():
    out.write("\n[%s]\n" % rule)
    for t, cur in ss:
        out.write("   %-58s  모델=%s\n" % ((t or "")[:58], cur))
if not DRY:
    out.write("\nsilver 이동 파일별\n")
    for k, v in moved.most_common(20):
        out.write("  %-56s %5d\n" % (k, v))
out.close()
print("done")
