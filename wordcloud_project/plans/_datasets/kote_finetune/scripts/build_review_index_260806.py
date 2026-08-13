# -*- coding: utf-8 -*-
"""검토큐 지도·근거 대장 문서를 현재 파일 상태에서 생성한다(멱등, 재실행 가능).

산출: result/review_queue_index_260806.md
왜: 260703 지도(group_files_index)가 29파일 기준이라 낡았고, 파일별 출처가
    파일 안에도 문서에도 없어 "이 큐가 어디서 왔는가"를 추적할 수 없었다.
    향후 문서·모델에 이 판정을 인용할 때 근거로 쓸 수 있게 남긴다.
"""
import io
import json
import os
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REVIEW = os.path.join(ROOT, "eval", "review")
ARCH = os.path.join(REVIEW, "_archive")
OUT = os.path.join(ROOT, "result", "review_queue_index_260806.md")

ORIGIN = {
    "prod25_flip_neg2pos": ("2025 실배치 감사(260716)", "audit_screen_prod_260716 → audit_stratify_prod_260716 → audit_extract_queue_260716 (시드 20260716)", "batch_20260714_0 / data/25.csv 758,880"),
    "prod25_flip_pos2neg": ("2025 실배치 감사(260716)", "동상", "동상"),
    "prod25_ambivalent": ("2025 실배치 감사(260716)", "동상", "동상"),
    "8a_other_pos": ("검토큐 그룹재편(260703)", "split_by_group_260703.py", "validation_candidates_260624 계열"),
    "8b_other_neg": ("검토큐 그룹재편(260703)", "split_by_group_260703.py", "validation_candidates_260624 계열"),
    "8c_other_neu": ("검토큐 그룹재편(260703)", "split_by_group_260703.py", "validation_candidates_260624 계열"),
    "hard_queue": ("하드샘플 마이닝", "mine_hard_samples 계열", "저마진·중립경계"),
    "hard_prefilled": ("하드샘플 프리필", "prefill_hard_queue.py", "저마진·중립경계"),
    "hard_escalate": ("하드샘플 escalation", "prefill_hard_queue.py", "규칙-모델 불일치분"),
    "bareNP_r": ("맨명사구 라운드", "mine_bareNP_r4_260707.py", "8c 계열"),
    "speechact_r6": ("화행 라운드", "mine_speechact_r6_260707.py", "8c 계열"),
    "pattern_D_traitpos": ("패턴 D 마이닝(260715)", "build_pattern_gold_260715.py", "trait positive 후보"),
    "packet_review_pool": ("대량 판정 패킷 유니크 풀(260714)", "judge_packet_260714.py", "티어링 전수 유니크"),
    "packet_b346_pool": ("대량 판정 패킷 버킷 풀(260714)", "judge_packet_260714.py", "버킷 3·4·6"),
}
GRADE_DESC = {
    "P1": "긍↔부 뒤바뀜 후보 — 핵심 가치 직결. 규칙 자동 처리 금지, 전건 사람 판정.",
    "P2": "극성↔중립 경계·양가·화행 — 규칙 프리필 후 잔여.",
    "P3": "대량 유니크 풀 — 티어링 전수 판정 대상. 개별 가치는 낮으나 모델 과부정 패턴의 발굴원.",
}


def origin_of(nm):
    for k, v in ORIGIN.items():
        if k in nm:
            return v
    return ("미기재", "미기재", "미기재")


def scan(d):
    rows = []
    for nm in sorted(os.listdir(d)):
        p = os.path.join(d, nm)
        if not os.path.isfile(p) or not nm.endswith(".jsonl"):
            continue
        n = u = pre = 0
        for line in io.open(p, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            n += 1
            if r.get("human_decision") is None and r.get("gold") is None:
                u += 1
            if r.get("claude_judgment"):
                pre += 1
        rows.append((nm, n, u, pre))
    return rows


cur = scan(REVIEW)
arc = scan(ARCH)
sil = scan(os.path.join(ARCH, "silver")) if os.path.isdir(os.path.join(ARCH, "silver")) else []

led = []
lp = os.path.join(ARCH, "_ledger_260806.jsonl")
if os.path.isfile(lp):
    led = [json.loads(l) for l in io.open(lp, encoding="utf-8") if l.strip()]
byreason = collections.Counter(e["reason"] for e in led)

f = io.open(OUT, "w", encoding="utf-8", newline="\n")
f.write("# 검토큐 지도·근거 대장 (2026-08-06 재편)\n\n")
f.write("> 게시판 `/group-review` 는 `eval/review/` **최상위 `.jsonl` 만** 파일명 알파벳순으로 나열한다.\n"
        "> 따라서 접두어 `P1_ < P2_ < P3_` 가 곧 검토 우선순위다. 하위 폴더(`_archive/`)는 노출되지 않는다.\n"
        "> 이 문서는 `scripts/build_review_index_260806.py` 로 현재 파일에서 재생성한다(멱등).\n\n")
f.write("## 1. 우선순위 정의\n\n| 등급 | 정의 |\n|---|---|\n")
for g, d in GRADE_DESC.items():
    f.write("| **%s** | %s |\n" % (g, d))
f.write("\n## 2. 현재 판정 대상 (게시판 노출)\n\n")
f.write("| 파일 | 전체 | **미판정** | 프리필 | 출처 | 산출 스크립트 |\n|---|---:|---:|---:|---|---|\n")
for nm, n, u, pre in cur:
    o = origin_of(nm)
    f.write("| `%s` | %d | **%d** | %d | %s | `%s` |\n" % (nm, n, u, pre, o[0], o[1]))
f.write("| **합계** | **%d** | **%d** | **%d** | | |\n"
        % (sum(r[1] for r in cur), sum(r[2] for r in cur), sum(r[3] for r in cur)))

f.write("\n## 3. 큐에서 제외한 것 — 사유별 (삭제 아님, 근거로 보존)\n\n")
f.write("| 사유 | 행수 |\n|---|---:|\n")
for k, v in byreason.most_common():
    f.write("| %s | %d |\n" % (k, v))
f.write("| **합계** | **%d** |\n\n" % len(led))
f.write("행 단위 원본은 `eval/review/_archive/_ledger_260806.jsonl` 에 있다 — "
        "`text · from_file · kept_in · reason · gold_label · cur_rule_label · claude_judgment` 로 1행씩. "
        "**어떤 문장이 왜 큐에서 빠졌고 대신 어디에 있는지**를 이 파일 하나로 되짚을 수 있다.\n")

f.write("\n## 4. 보관 위치\n\n")
f.write("| 위치 | 파일 | 행 | 성격 |\n|---|---:|---:|---|\n")
f.write("| `_archive/` | %d | %d | 판정 완료분·감사 증적·재편 전 원본 |\n"
        % (len(arc), sum(r[1] for r in arc)))
f.write("| `_archive/silver/` | %d | %d | 규칙·모델 합의 자동분. 학습 silver 로만 사용, **gold 아님** |\n"
        % (len(sil), sum(r[1] for r in sil)))
f.write("| `_gold_backup/pre_queue_split_260806/` | 1 | 5,597 | 260716 원본 큐 스냅샷 |\n")

f.write("\n## 5. 인용 규약 (문서·모델에 이 판정을 쓸 때)\n\n")
f.write("- `decision_source` 로만 출처를 판별한다. `human`=사람 확정 / "
        "`claude_rule_prefill_260806`=**규칙 발동 결과이지 문장 개별 판독이 아님** / "
        "`auto_rule_wellbeing_260806`=건강·개인안녕 중립화 자동분.\n")
f.write("- 프리필·silver 는 **gold 로 승격하지 않는다.** 승격은 사람 확정 후 `promote_gold.py` 로만 한다 "
        "(AUDIT_STANDARD §4, 대량 확정=escalation).\n")
f.write("- 보고서에 건수를 인용할 때는 이 문서의 **재생성 시점**을 함께 적는다(큐는 판정에 따라 변한다).\n")

f.write("\n## 6. 알려진 제약\n\n")
f.write("- `prod25_*` 3파일은 원 배치에 평가 칸(장점/단점)이 없어 `field` 가 전부 `null` 이다"
        "(`batch_20260714_0` 에서 필드 0/758,880). 칸 신호 없이 문장만으로 판정해야 한다.\n")
f.write("- 260806 이전 이름을 **문자열로 박아 둔 과거 스크립트**가 있다"
        "(`build_hard_labeling_queue_260715` · `judge_packet_260714` · `audit_extract_queue_260716` 등). "
        "재실행하면 `FileNotFoundError` 로 **소리내어 실패**한다. glob 사용처는 접두 허용 패턴으로 이미 고쳤다"
        "(조용히 0건이 되는 쪽이 위험하므로).\n")
f.write("- 낡은 지도 `result/group_files_index_260703.md`(29파일)·`result/review_todo_260703.md` 는 "
        "**이 문서로 대체**된다.\n")
f.close()
print("wrote", OUT)
