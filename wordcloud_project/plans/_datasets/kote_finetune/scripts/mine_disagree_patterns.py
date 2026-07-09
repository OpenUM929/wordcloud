# -*- coding: utf-8 -*-
"""불일치 패턴 전수 발굴 — 라벨러 vs 사람 gold(1,741건)에서 반복 단어를 체계 추출.

반응적 땜질이 아니라, 불일치 버킷별로 '내 라벨러가 못 잡는 단어'를 빈도순으로 뽑아
누락 표지(예: 아쉽)를 일괄 발견한다.
"""
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
import human_label as H  # noqa: E402

D = os.path.abspath(os.path.join(HERE, '..', 'eval'))
FILES = ['group_needs_human_260624.jsonl', 'group_needs_human_g4_260624.jsonl',
         'field_conflict_review_260624.jsonl', 'baseline_eval_260624.jsonl']
_TOK = re.compile(r'[가-힣]{2,}')


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass
    rows = []
    for fn in FILES:
        p = os.path.join(D, fn)
        if not os.path.isfile(p):
            continue
        for line in open(p, encoding='utf-8'):
            r = json.loads(line)
            hd = r.get('human_decision')
            if hd and hd != 'skip':
                rows.append((r.get('text', ''), hd))
    n = len(rows)
    conf = Counter()
    buckets = {}
    for t, hd in rows:
        pol = H.label(t)[0]
        conf[(pol, hd)] += 1
        if pol != hd:
            buckets.setdefault((pol, hd), []).append(t)
    agree = sum(c for (a, b), c in conf.items() if a == b)
    print(f'사람 gold {n}건 · 라벨러 일치 {agree} ({100*agree/n:.0f}%)')
    print('혼동(라벨러→사람):')
    for (a, b), c in conf.most_common():
        flag = '   <불일치' if a != b else ''
        print(f'  {a:>8} → {b:<8}: {c}{flag}')

    # 전체 토큰 빈도(기저) — 버킷 토큰의 '특이도' 보정용
    base = Counter()
    for t, _ in rows:
        base.update(set(_TOK.findall(t)))

    print('\n=== 불일치 버킷별 빈출 단어(내 라벨러가 놓친 신호) ===')
    for (a, b), texts in sorted(buckets.items(), key=lambda x: -len(x[1])):
        cnt = Counter()
        for t in texts:
            cnt.update(set(_TOK.findall(t)))
        # 이 버킷에서 흔하고(>=4), 라벨러 표지에 아직 없는 단어 위주
        known = set()
        for w in H._NEG:
            known.add(w)
        rare = []
        for w, c in cnt.most_common(40):
            if c < 4:
                continue
            tag = '[POS]' if H._POS.search(w) else ''
            tag += '[NEG]' if any(k in w or w in k for k in H._NEG) else ''
            rare.append(f'{w}:{c}{tag}')
        print(f'\n[{a}→{b}] {len(texts)}건 — 빈출어:')
        print('  ' + ', '.join(rare[:24]))


if __name__ == '__main__':
    main()
