# -*- coding: utf-8 -*-
"""검토큐 재편 — 우선순위 부여 · 중복/기결정 제거 · 폐기분 분리 · 근거 대장 산출.

사용자 지시(2026-08-06)
  B 문서·모델 활용 우선순위가 높은 쪽을 정본으로 남기고 나머지 중복은 제거
  C P1·P2 로 나누고 P3 부터는 필요성 재검토
  D 문서·모델에 필요 없는 것은 제거
  「불필요 자료는 삭제하되, 향후 문서·모델 활용 시 근거자료로 남을 수 있게 이력 관리」

따라서 제거 = 큐에서 뺀다는 뜻이고 소멸이 아니다. 제거되는 모든 행은
`_archive/_ledger_260806.jsonl` 에 제거 사유·원 파일·대체 위치와 함께 1행씩 남긴다.
파일 단위 이동분은 `_archive/` 아래에 원본 그대로 보관한다(git 추적 중).

우선순위 (게시판이 파일명 알파벳순으로 나열하므로 접두어가 곧 순서다)
  P1 긍↔부 뒤바뀜 후보 — 핵심 가치(칭찬↔불만 오분류) 직결. 사람 눈이 반드시 필요.
  P2 극성↔중립 경계·양가·화행 — 모델 약점 구간. 규칙 프리필 후 잔여만.
  P3 대량 유니크 풀 — 티어링된 전수 판정 대상. 양이 크고 개별 가치는 낮으나
     모델 과부정 패턴의 발굴원이라 폐기하지 않는다(필요성 재검토 결과 = 유지).
"""
import io
import json
import os
import re
import shutil
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REVIEW = os.path.join(ROOT, "eval", "review")
ARCH = os.path.join(REVIEW, "_archive")
SILVER = os.path.join(ARCH, "silver")
LEDGER = os.path.join(ARCH, "_ledger_260806.jsonl")
DATE = "260806"

for d in (ARCH, SILVER):
    os.makedirs(d, exist_ok=True)


def norm(t):
    return re.sub(r"\s+", "", (t or "")).strip()


# ── 파일 분류 ──────────────────────────────────────────────────────────
def classify(nm):
    """파일명 → (등급, 사유). 등급 None 이면 큐에서 뺀다."""
    if nm.startswith("prod25_flip_"):
        return "P1", "긍↔부 뒤바뀜 후보 — 핵심 가치 직결"
    if "silver" in nm:
        return None, "silver = 규칙·모델 합의 자동분. 사람 판정 대상이 아니며 학습 silver 로만 쓴다"
    if nm.startswith("packet_audit_"):
        return None, "260714 블라인드 감사 산출물(표본·불일치 기록). 판정 대상이 아니라 감사 증적"
    if nm.startswith("packet_") and "pool" in nm:
        return "P3", "대량 유니크 풀 — 티어링 전수 판정 대상. 모델 과부정 패턴 발굴원"
    return "P2", "극성↔중립 경계·양가·화행 잔여"


# ── 적재 ───────────────────────────────────────────────────────────────
files = {}
for nm in sorted(os.listdir(REVIEW)):
    p = os.path.join(REVIEW, nm)
    if not os.path.isfile(p) or not nm.endswith(".jsonl"):
        continue
    recs = []
    for line in io.open(p, encoding="utf-8"):
        if not line.strip():
            continue
        try:
            recs.append(json.loads(line))
        except ValueError:
            pass
    files[nm] = recs

# ── 패킷 풀 스키마 정규화 (게시판 계약: text·cur_rule_label·ai_reference) ──
FULL = {"p": "positive", "n": "negative", "u": "neutral",
        "positive": "positive", "negative": "negative", "neutral": "neutral"}


def normalize_packet(nm, recs):
    """packet 풀은 model=라벨 문자열, kote=[긍,부,중] 확률, tier=문자열 티어명."""
    out = []
    for i, r in enumerate(recs, 1):
        m = FULL.get(r.get("model"))
        s = r.get("kote") if isinstance(r.get("kote"), list) else [0, 0, 0]
        k = ["positive", "negative", "neutral"][max(range(3), key=lambda j: s[j])]
        out.append({
            "rec_id": r.get("i") if r.get("i") is not None else "%s_%05d" % (nm.split("_")[1], i),
            "text": r.get("text"), "field": r.get("field"),
            "group": r.get("tier"),
            "cur_rule_label": m,
            "ai_reference": {"polarity": m, "confidence": r.get("conf"),
                             "reason": "배포모델=%s(확신 %s) · KoTE=%s(긍%.2f/부%.2f/중%.2f) · 티어 %s "
                                       "· 동일문장 %s회 · 신호스택 %s"
                                       % (m, r.get("conf"), k, s[0], s[1], s[2],
                                          r.get("tier"), r.get("dup_n"), r.get("stack"))},
            "claude_judgment": None, "human_decision": None, "decision_source": None,
            "tier": r.get("tier"), "conf": r.get("conf"), "dup_n": r.get("dup_n"),
            "model": r.get("model"), "kote": r.get("kote"), "stack": r.get("stack"),
            "bucket": r.get("bucket"),
        })
    return out


for nm in list(files):
    if nm.startswith("packet_") and "pool" in nm:
        files[nm] = normalize_packet(nm, files[nm])

# ── 등급 부여 ──────────────────────────────────────────────────────────
grade = {nm: classify(nm) for nm in files}
RANK = {"P1": 1, "P2": 2, "P3": 3}

ledger = []


def log(reason, r, src, keep=None, extra=None):
    e = {"date": DATE, "reason": reason, "text": r.get("text"), "field": r.get("field"),
         "from_file": src, "kept_in": keep,
         "cur_rule_label": r.get("cur_rule_label"),
         "claude_judgment": r.get("claude_judgment"),
         "human_decision": r.get("human_decision")}
    if extra:
        e.update(extra)
    ledger.append(e)


# ── 1) 폐기 파일 → 아카이브 (행 단위로 대장에 남긴다) ──────────────────
disposed = []
for nm, recs in list(files.items()):
    g, why = grade[nm]
    if g is not None:
        continue
    dst = SILVER if "silver" in nm else ARCH
    for r in recs:
        if r.get("human_decision") is None and r.get("gold") is None:
            log("큐에서 제외(%s)" % why, r, nm,
                keep=os.path.join(os.path.basename(dst), nm) if dst is SILVER else "_archive/" + nm)
    shutil.move(os.path.join(REVIEW, nm), os.path.join(dst, nm))
    disposed.append((nm, len(recs), why))
    del files[nm]

# ── 2) 이미 gold 가 있는 문장 제거 ─────────────────────────────────────
gold = {}
gp = os.path.join(ROOT, "emotion", "emotion.jsonl")
for line in io.open(gp, encoding="utf-8"):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    t = norm(r.get("text"))
    if t:
        gold[t] = r.get("label") or r.get("y")

removed_gold = 0
for nm, recs in files.items():
    keep = []
    for r in recs:
        t = norm(r.get("text"))
        if (r.get("human_decision") is None and r.get("gold") is None and t in gold):
            log("정식 gold 에 이미 확정 라벨이 있음 — 재판정 불요", r, nm,
                keep="emotion/emotion.jsonl", extra={"gold_label": gold[t]})
            removed_gold += 1
            continue
        keep.append(r)
    files[nm] = keep

# ── 3) 파일 간 중복 제거 — 우선순위 높은 파일을 정본으로 ───────────────
def score(nm, r):
    """작을수록 정본. 등급 → 근거 유무 → 반복수(클수록 가치) 순."""
    g = grade[nm][0]
    has_ev = 0 if (r.get("ai_reference") or r.get("claude_judgment")) else 1
    rep = -(r.get("freq") or r.get("dup_n") or 0)
    return (RANK[g], has_ev, rep, nm)


occur = collections.defaultdict(list)
for nm, recs in files.items():
    for idx, r in enumerate(recs):
        if r.get("human_decision") is None and r.get("gold") is None:
            t = norm(r.get("text"))
            if t:
                occur[t].append((score(nm, r), nm, idx))

drop = collections.defaultdict(set)
removed_dup = 0
for t, lst in occur.items():
    if len(lst) < 2:
        continue
    lst.sort()
    canon = lst[0][1]
    for _, nm, idx in lst[1:]:
        drop[nm].add(idx)
        log("중복 — 우선순위 높은 파일을 정본으로 채택", files[nm][idx], nm, keep=canon)
        removed_dup += 1

for nm, idxs in drop.items():
    files[nm] = [r for i, r in enumerate(files[nm]) if i not in idxs]

# ── 4) P 접두어로 재발행 (게시판 알파벳 정렬 = 우선순위) ───────────────
renames = []
for nm, recs in sorted(files.items()):
    g, _ = grade[nm]
    new = "%s_%s" % (g, nm)
    with io.open(os.path.join(REVIEW, new), "w", encoding="utf-8", newline="\n") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.remove(os.path.join(REVIEW, nm))
    renames.append((nm, new, g, len(recs),
                    sum(1 for r in recs if r.get("human_decision") is None and r.get("gold") is None)))

with io.open(LEDGER, "a", encoding="utf-8", newline="\n") as f:
    for e in ledger:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")

rep = io.open(os.path.join(HERE, "_reorg_report.txt"), "w", encoding="utf-8")
rep.write("폐기(큐 제외) 파일 %d개\n" % len(disposed))
for nm, n, why in disposed:
    rep.write("  %-50s %5d행  %s\n" % (nm, n, why))
rep.write("\ngold 기확정 제거 %d행 · 중복 제거 %d행 · 대장 기록 %d행\n"
          % (removed_gold, removed_dup, len(ledger)))
rep.write("\n재발행 %d파일\n" % len(renames))
for old, new, g, n, u in sorted(renames, key=lambda t: t[1]):
    rep.write("  %-3s %-54s %6d행 미판정 %6d\n" % (g, new, n, u))
rep.write("\n미판정 합계 %d\n" % sum(t[4] for t in renames))
rep.close()
print("done")
