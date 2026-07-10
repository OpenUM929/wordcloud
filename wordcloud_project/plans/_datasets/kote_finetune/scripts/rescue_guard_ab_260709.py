# -*- coding: utf-8 -*-
"""요청표지 가드(0709) 신·구 규칙 A/B — 양방향 적대검증 (q.txt ②).

구(스냅샷) vs 신(현재) 규칙을 868k 전량에 적용해:
 1) 내부망 y별 (구라벨→신라벨) 플립 행렬 — 특히 y=p에서 새로 생기는 긍→부(핵심가치 위반 후보) 전수.
 2) y=n 부→긍 축(어제 16,031)의 잔존/차단 수.
 3) 새 긍→부 표본 덤프(블라인드 판정용).

실행: 프로젝트 루트에서  python plans/_datasets/kote_finetune/scripts/rescue_guard_ab_260709.py <구스냅샷.py>
출력: result/rescue_guard_ab_260709.md
"""
import importlib.util
import io
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
REPO = os.path.abspath(os.path.join(ROOT, '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'src'))
from services.perspective_service import _sentence_sentiment_override_explain as ov_new  # noqa: E402

OLD_PATH = sys.argv[1]
spec = importlib.util.spec_from_file_location('ps_old', OLD_PATH)
ps_old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps_old)
ov_old = ps_old._sentence_sentiment_override_explain

BATCH = os.path.join(REPO, 'data', 'batch_20260708_0.csv')
OUT_MD = os.path.join(HERE, '..', 'result', 'rescue_guard_ab_260709.md')

Y2L = {'p': '긍', 'n': '부', 'u': '중'}


def lab(s):
    return '긍' if s > 1e-6 else ('부' if s < -1e-6 else '중')


def main():
    flip = defaultdict(Counter)          # y → (old,new) 쌍
    conf_new = Counter()                 # (y, new)
    p2neg_rows = []                      # y=p 에서 새로 긍→부 된 행 전수
    n_fixed_samp = defaultdict(list)     # y=n 부→긍 이 새로 부/중이 된 행 표본(신규칙 rule별)
    n = 0
    for line in open(BATCH, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        t = r.get('x', '') or ''
        y = r.get('y')
        s3 = r.get('s')
        if not t or y not in Y2L or not s3:
            continue
        p, ng, u = s3
        try:
            so, ro = ov_old(p, ng, t, True, 1, neutral=u)
            sn, rn = ov_new(p, ng, t, True, 1, neutral=u)
        except Exception:
            continue
        n += 1
        L, O, N = Y2L[y], lab(so), lab(sn)
        flip[L][(O, N)] += 1
        conf_new[(L, N)] += 1
        if L == '긍' and O != '부' and N == '부':
            if len(p2neg_rows) < 400:
                p2neg_rows.append((rn, round(p, 2), round(ng, 2), t[:90]))
        if L == '부' and O == '긍' and N != '긍':
            key = '%s(%s)' % (N, rn)
            if len(n_fixed_samp[key]) < 6:
                n_fixed_samp[key].append(t[:80])

    with open(OUT_MD, 'w', encoding='utf-8') as f:
        def out(s=''):
            print(s)
            f.write(s + '\n')
        out('# 요청표지 가드 신·구 A/B — 260709 (n=%d)' % n)
        for L in ('긍', '부', '중'):
            out()
            out('## 내부망 y=%s — 구→신 플립' % L)
            for (O, N), c in sorted(flip[L].items(), key=lambda x: -x[1]):
                mark = ' ◀◀ 위반후보' if (L == '긍' and N == '부' and O != '부') else ''
                if O != N or c > 0:
                    out('- %s→%s: %d%s' % (O, N, c, mark))
        tot = sum(conf_new.values())
        agree = sum(v for (a, b), v in conf_new.items() if a == b)
        out()
        out('## 신규칙 vs 내부망 y 일치율: %.2f%% (어제 구규칙 90.48%%)' % (agree / tot * 100))
        out('- y=부 → dev 긍(잔존 부→긍): %d (어제 16,031)' % conf_new.get(('부', '긍'), 0))
        out('- y=긍 → dev 부: %d' % conf_new.get(('긍', '부'), 0))
        out()
        out('## y=긍인데 새로 부정이 된 행 (전수 %d, 최대 400 표시) — 블라인드 판정 대상' % len(p2neg_rows))
        for rn, p, ng, t in p2neg_rows[:120]:
            out('- [%s|pos%.2f neg%.2f] %s' % (rn, p, ng, t))
        out()
        out('## y=부 구긍정이 차단된 행 표본 (신규칙 도착지별)')
        for key in sorted(n_fixed_samp):
            out('### → %s' % key)
            for t in n_fixed_samp[key]:
                out('- %s' % t)


if __name__ == '__main__':
    main()
