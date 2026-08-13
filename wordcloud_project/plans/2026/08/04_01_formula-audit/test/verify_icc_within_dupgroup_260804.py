"""§8 검증 1 — 반증 실험: 중복 문장 그룹 내부에서 판정이 엇갈리는가.

전 그룹에서 판정이 동일하면 급내상관 rho=1 이 성립하고 deff=Sum(m^2)/n 이 유효하다.
엇갈리면 rho<1 이므로 deff 는 과대추정이고 결함 1 의 보정폭이 줄어든다.
"""
import json, os, collections

R = "D:/dev/wordcloud/wordcloud_project/plans/2026/07/27_03_completion-report/result"


def load(p):
    return [json.loads(l) for l in open(os.path.join(R, p), encoding="utf-8") if l.strip()]


def report(name, rows, judge_keys):
    key = lambda r: (r.get("field"), r.get("text"))
    groups = collections.defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    dup = {k: v for k, v in groups.items() if len(v) > 1}
    n = len(rows)
    deff = sum(len(v) ** 2 for v in groups.values()) / n
    print("[%s] n=%d 고유=%d 중복그룹=%d 중복소속행=%d 초과행=%d deff(rho=1)=%.4f"
          % (name, n, len(groups), len(dup), sum(len(v) for v in dup.values()),
             sum(len(v) - 1 for v in dup.values()), deff))
    for jk in judge_keys:
        present = sum(1 for r in rows if r.get(jk) is not None)
        if not present:
            print("   - %-18s 필드 없음(스킵)" % jk)
            continue
        split = [(k, collections.Counter(r.get(jk) for r in v))
                 for k, v in dup.items() if len({r.get(jk) for r in v}) > 1]
        print("   - %-18s 값보유 %d행 / 그룹내 불일치 그룹 %d개" % (jk, present, len(split)))
        for k, c in split:
            print("       엇갈림: %s | %s -> %s" % (k[0], str(k[1])[:40], dict(c)))
    # 그룹 목록
    for k, v in sorted(dup.items(), key=lambda x: -len(x[1])):
        vals = {jk: sorted({str(r.get(jk)) for r in v}) for jk in judge_keys if any(r.get(jk) is not None for r in v)}
        print("       m=%d %s | %s :: %s" % (len(v), k[0], str(k[1])[:36], vals))


rows400 = load("blind_judged_400.jsonl")
print("blind_judged_400 keys:", list(rows400[0].keys()))
report("400 채점표본", rows400, ["claude_judgment", "model_judgment", "rule_judgment", "human_judgment"])

print()
rows1610 = load("sample_round2s_1610_20260730.jsonl")
print("sample_round2s_1610 keys:", list(rows1610[0].keys()))
report("1610 증량표본", rows1610, ["claude_judgment", "model_judgment", "rule_judgment", "pred", "current", "prev"])
