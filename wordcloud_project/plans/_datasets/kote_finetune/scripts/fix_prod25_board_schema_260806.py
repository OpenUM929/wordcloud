# -*- coding: utf-8 -*-
"""prod25 분리본 3파일을 게시판(/group-review) 로드 계약에 맞춘다.

왜 필요한가 (사고)
  260716 원본 검토큐는 본문 키가 `x` 였다. 게시판 로드는 `r.get('text')` 를 읽으므로
  이 파일을 열면 **본문이 빈칸으로 보인다** — 판정이 물리적으로 불가능하다.
  260806 분리에서 이 스키마를 그대로 물려받아 3파일에 실어 보냈다. 여기서 교정한다.
  (원본이 3주간 손대지 않은 채 남아 있던 이유일 가능성이 높다.)

게시판 계약 (perspective_routes.api_group_review_load)
  rec_id · text · field · group · cur_rule_label · ai_reference · claude_judgment
  · human_decision · decision_source · suggested_source · memo · memo_tags
  ai_reference 는 {'polarity','confidence','reason'} dict 규약.

헤더 행도 제거한다 — 로드가 전 행을 세므로 헤더가 빈 행 1개로 보인다.
출처·이력은 파일 안이 아니라 result/review_queue_index_260806.md 에 둔다.
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW = os.path.join(os.path.dirname(HERE), "eval", "review")

FULL = {"p": "positive", "n": "negative", "u": "neutral"}
GROUP = {
    "E5_clearflip_n": "E5_명백뒤집힘(부→긍)",
    "E2_bareNP_neg": "E2_맨명사구 칭찬(부→긍)",
    "E5_clearflip_p": "E5_명백뒤집힘(긍→부)",
    "E1_harm_pos": "E1_해악표지(긍→부)",
    "E1_ambi_neg": "E1_양가 업무태도",
}
FILES = ["prod25_flip_neg2pos_260806.jsonl",
         "prod25_flip_pos2neg_260806.jsonl",
         "prod25_ambivalent_260806.jsonl"]


def reason(r):
    """감사가 왜 이 행을 뽑았는지 한 줄로. 사람이 판정할 때 보는 근거."""
    s = r.get("s") or [0, 0, 0]
    parts = [
        "감사유형 %s" % GROUP.get(r.get("error_type"), r.get("error_type")),
        "배포모델=%s" % FULL.get(r.get("model_y"), "?"),
        "규칙=%s" % FULL.get(r.get("rule_y"), "?"),
        "KoTE=%s(긍%.2f/부%.2f/중%.2f)" % (FULL.get(r.get("kote_y"), "?"), s[0], s[1], s[2]),
        "감사추천=%s" % FULL.get(r.get("suggested"), "?"),
        "이 문장 반복 %d회" % (r.get("freq") or 0),
    ]
    if r.get("rule_note"):
        parts.append("⚠ " + r["rule_note"])
    return " · ".join(parts)


for fn in FILES:
    path = os.path.join(REVIEW, fn)
    lines = [l for l in io.open(path, encoding="utf-8") if l.strip()]
    recs = [json.loads(l) for l in lines]
    if "x" not in recs[0] and "text" not in recs[0]:
        recs = recs[1:]                                   # 헤더 행 제거
    out = []
    for i, r in enumerate(recs, 1):
        out.append({
            "rec_id": "prod25_%s_%05d" % (r.get("error_type", "na"), i),
            "text": r.get("x") or r.get("text"),
            "field": None,          # 원 배치(batch_20260714_0)에 필드 0/758,880 — 부재가 사실
            "group": GROUP.get(r.get("error_type"), r.get("error_type")),
            "cur_rule_label": FULL.get(r.get("model_y")),   # 현 판정 = 배포 모델 출력
            "ai_reference": {
                "polarity": FULL.get(r.get("suggested")),
                "confidence": r.get("confidence"),
                "reason": reason(r),
            },
            "claude_judgment": None,        # 아직 per-row 프리필 전 — 다음 단계
            "human_decision": None,
            "decision_source": None,
            # 원 감사 필드 보존(추적용)
            "error_type": r.get("error_type"), "freq": r.get("freq"), "s": r.get("s"),
            "model_y": r.get("model_y"), "rule_y": r.get("rule_y"), "kote_y": r.get("kote_y"),
            "suggested": r.get("suggested"), "confidence": r.get("confidence"),
            "src": r.get("src"), "split_from": r.get("split_from"), "split_date": r.get("split_date"),
            "rule_note": r.get("rule_note"),
        })
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print("%-38s %5d행 (헤더 제거, text 키 정규화)" % (fn, len(out)))
