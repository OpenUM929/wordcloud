# -*- coding: utf-8 -*-
"""부→긍 드리프트 적대검증 (q.txt ②, 260709).

내부망 y='n' 인데 dev 현재 규칙이 긍정으로 재판정하는 축(16k, 77% positive_rescue)을
전량 추출해 (1) dev rule 분포, (2) positive_rescue 부분집합의 의심 토큰 패턴 빈도,
(3) 패턴별 층화 표본을 만든다. 표본은 블라인드 판정(원칙 기반) 후 가드 설계에 쓴다.

주의: 내부망 y도 구버전 규칙 출력일 뿐 정답이 아니다(사전라벨 불신). 표본 판정이 정본.

실행: 프로젝트 루트에서  python plans/_datasets/kote_finetune/scripts/rescue_adv_260709.py
출력: eval/rescue_adv_drift_260709.jsonl (전량) · result/rescue_adv_260709.md (요약+표본)
"""
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
from services.perspective_service import _sentence_sentiment_override_explain as ov  # noqa: E402

BATCH = os.path.join(REPO, 'data', 'batch_20260708_0.csv')
OUT_JSONL = os.path.join(HERE, '..', 'eval', 'rescue_adv_drift_260709.jsonl')
OUT_MD = os.path.join(HERE, '..', 'result', 'rescue_adv_260709.md')

# 의심 토큰(진짜 부정일 개연 표지) — 표본 층화용. 가드 후보이지 가드 자체가 아님.
PATTERNS = [
    ('보완', lambda t: '보완' in t),
    ('노력해야/노력요', lambda t: any(m in t for m in
                                 ('노력해야', '노력 해야', '노력이 요', '노력요', '노력 요함',
                                  '노력하여야', '노력을 해야', '노력 필요', '노력이 필요'))),
    ('~해야/되어야', lambda t: any(m in t for m in ('해야', '되어야', '져야', '어야'))),
    ('필요', lambda t: '필요' in t),
    ('바람/기대', lambda t: any(m in t for m in ('바람', '바랍', '기대함', '기대합'))),
    ('고압/지시', lambda t: any(m in t for m in ('고압', '세세하게 지시', '강압'))),
    ('아쉬/미흡/부족', lambda t: any(m in t for m in ('아쉬', '미흡', '부족'))),
]


def pat_of(t):
    for name, fn in PATTERNS:
        if fn(t):
            return name
    return '0_기타'


def lab(s):
    return '긍' if s > 1e-6 else ('부' if s < -1e-6 else '중')


def main():
    rule_cnt = Counter()
    pat_cnt = Counter()
    samples = defaultdict(list)
    total = 0
    n_drift = 0
    with open(OUT_JSONL, 'w', encoding='utf-8') as w:
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
            if not t or y != 'n' or not s3:
                continue
            total += 1
            p, ng, u = s3
            try:
                sc, rule = ov(p, ng, t, True, 1, neutral=u)
            except Exception:
                continue
            if lab(sc) != '긍':
                continue
            n_drift += 1
            rule_cnt[rule] += 1
            pat = pat_of(t) if rule == 'positive_rescue' else None
            if pat:
                pat_cnt[pat] += 1
                if len(samples[pat]) < 12:
                    samples[pat].append((round(p, 2), round(ng, 2), t[:90]))
            w.write(json.dumps({'x': t, 's': s3, 'rule': rule, 'pat': pat},
                               ensure_ascii=False) + '\n')

    with open(OUT_MD, 'w', encoding='utf-8') as f:
        def out(s=''):
            print(s)
            f.write(s + '\n')
        out('# 부→긍 드리프트 적대검증 — 260709')
        out()
        out('- 내부망 부정(y=n) 행: %d' % total)
        out('- dev 재현이 긍정으로 뒤집는 행: %d (%.2f%%)' % (n_drift, n_drift / max(total, 1) * 100))
        out()
        out('## dev rule 분포')
        for rule, c in rule_cnt.most_common():
            out('- %s: %d' % (rule, c))
        out()
        out('## positive_rescue 부분집합 의심 패턴 분포(첫 매칭 기준)')
        for patn, c in pat_cnt.most_common():
            out('- %s: %d' % (patn, c))
        out()
        out('## 패턴별 표본 (블라인드 판정용)')
        for patn, _ in pat_cnt.most_common():
            out('### %s' % patn)
            for p, ng, t in samples[patn]:
                out('- [pos%.2f neg%.2f] %s' % (p, ng, t))
            out()


if __name__ == '__main__':
    main()
