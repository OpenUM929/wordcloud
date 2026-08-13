# -*- coding: utf-8 -*-
"""prod25 검토큐(260716, 5,596) 를 「사용자 판정 대상」과 「규칙 자동확정분」으로 분리한다.

왜 나누는가
  게시판(/group-review)은 eval/review/ 최상위의 *.jsonl 만 나열한다(하위 폴더 미노출).
  따라서 규칙이 이미 정하는 행이 그 폴더에 남아 있으면 사용자가 "판정할 것"과 섞인다.
  확립 규칙을 먼저 적용하고 **진짜 잔여만** review/ 에 남긴다.

분리 기준 (긍↔부 최우선 원칙)
  [자동] E4_wellbeing_neg — 건강·개인안녕·평가유보 → 중립. 부→중 이므로 긍↔부 위반 없음.
         conf=high 이고 per-row 탐지기(is_personal_wellbeing_neutral) 산출분.
         human_decision 은 건드리지 않는다(자동 gold 금지). auto_label 로만 표시한다.
  [사용자] 나머지 전부 — 방향이 긍↔부이거나(E5/E2/E1_harm), 확립 규칙과 감사 제안이
         어긋나는 것(E1_ambi: 감사는 중립 제안이나 확립 규칙은 「양가 업무태도=긍정」).

원본은 옮기기만 하고 지우지 않는다(_archive/ + _gold_backup/).
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REVIEW = os.path.join(ROOT, "eval", "review")
ARCHIVE = os.path.join(REVIEW, "_archive")
SRC = os.path.join(REVIEW, "prod25_audit_queue_260716.jsonl")
DATE = "260806"

# 사용자 판정 파일 — (파일명, 헤더설명, 담을 error_type)
USER_FILES = [
    ("prod25_flip_neg2pos_260806.jsonl",
     "prod25 감사 잔여 — 부정 판정이나 실제 칭찬 의심(부→긍). 긍↔부 방향이라 전건 사람 판정.",
     ("E5_clearflip_n", "E2_bareNP_neg")),
    ("prod25_flip_pos2neg_260806.jsonl",
     "prod25 감사 잔여 — 긍정 판정이나 실제 불만 의심(긍→부). 긍↔부 방향이라 전건 사람 판정.",
     ("E5_clearflip_p", "E1_harm_pos")),
    ("prod25_ambivalent_260806.jsonl",
     "prod25 감사 잔여 — 양가 업무태도(너무 철저/과도한 열의류). 감사 제안은 중립이나 "
     "확립 규칙은 「양가 업무태도=긍정, 명시 해악표지 있을 때만 부정」이라 어긋난다. rule_note 참조.",
     ("E1_ambi_neg",)),
]
AUTO_TYPES = ("E4_wellbeing_neg",)

AMBI_NOTE = ("확립 규칙: 꼼꼼·철저·객관·소신 등 양가 업무태도는 기업 관점에서 긍정, "
             "명시적 해악표지(고압적/편향/기복)가 붙을 때만 부정, 사생활·성격은 중립. "
             "suggested=u 는 감사 자동추출값이며 이 규칙과 어긋난다. "
             "추출 단계에서 substring 오검출 이력 있음(IMPROVEMENT_HISTORY 260716).")

lines = list(io.open(SRC, encoding="utf-8"))
header = json.loads(lines[0])
rows = [json.loads(l) for l in lines[1:]]
print("원본 레코드", len(rows))

buckets = {fn: [] for fn, _, _ in USER_FILES}
auto = []
for r in rows:
    et = r.get("error_type")
    if et in AUTO_TYPES:
        r = dict(r)
        r["auto_label"] = r.get("suggested")
        r["decision_source"] = "auto_rule_wellbeing_%s" % DATE
        r["human_decision"] = None          # 자동 gold 금지 — 표시만 한다
        auto.append(r)
        continue
    for fn, _, types in USER_FILES:
        if et in types:
            r = dict(r)
            r["split_from"] = os.path.basename(SRC)
            r["split_date"] = DATE
            if et == "E1_ambi_neg":
                r["rule_note"] = AMBI_NOTE
            buckets[fn].append(r)
            break
    else:
        raise SystemExit("미분류 error_type: %s" % et)


def dump(path, desc, recs):
    """freq 내림차순(반복 많은 문장부터 = 교정 효과 큰 순)으로 기록한다."""
    recs = sorted(recs, key=lambda r: -(r.get("freq") or 0))
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"#": desc, "date": DATE, "src": header.get("#")},
                           ensure_ascii=False) + "\n")
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("%-42s %5d행 (반복포함 %d)" % (os.path.basename(path), len(recs),
                                        sum(r.get("freq") or 0 for r in recs)))


for fn, desc, _ in USER_FILES:
    dump(os.path.join(REVIEW, fn), desc, buckets[fn])

dump(os.path.join(ARCHIVE, "prod25_auto_wellbeing_neutral_260716.jsonl"),
     "prod25 감사 — 건강·개인안녕·평가유보 부→중 규칙 자동확정분. 게시판 미노출(사용자 판정 불요). "
     "human_decision 은 null 유지(자동 gold 금지), auto_label 만 부여.", auto)

# 원본은 아카이브로 이동(삭제 금지). 게시판에서만 빠진다.
dst = os.path.join(ARCHIVE, os.path.basename(SRC))
os.replace(SRC, dst)
print("원본 이동 ->", os.path.relpath(dst, ROOT))
print("합계 검산:", sum(len(v) for v in buckets.values()) + len(auto), "==", len(rows))
