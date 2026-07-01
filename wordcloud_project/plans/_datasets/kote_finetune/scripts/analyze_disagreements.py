# -*- coding: utf-8 -*-
"""사람 gold vs AI(ai_reference/현규칙) 불일치 분석 — 사람기준 라벨러 개선용.

완료된 검토셋(human_decision)에서 내 판정과 갈린 지점을 패턴화해, 라벨링 규칙을
사람 기준으로 정렬한다. 출력: 혼동행렬 + 불일치 예시(scratchpad).
"""
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
SCRATCH = r'C:/Users/ADMINI~1/AppData/Local/Temp/claude/D--dev-wordcloud/5b5229d3-4cd7-4e1a-b3cb-95a2369dd2c7/scratchpad'

FILES = ['group_needs_human_260624.jsonl', 'group_needs_human_g4_260624.jsonl',
         'field_conflict_review_260624.jsonl']


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass
    dump = []
    for fn in FILES:
        p = os.path.join(DATASET_DIR, 'eval', fn)
        if not os.path.isfile(p):
            continue
        rows = [json.loads(l) for l in open(p, encoding='utf-8')]
        done = [r for r in rows if r.get('human_decision')]
        conf = Counter()
        dis = []
        for r in done:
            hd = r['human_decision']
            if hd == 'skip':
                continue
            ai = (r.get('ai_reference') or {}).get('polarity')
            conf[(ai, hd)] += 1
            if ai and ai != hd:
                dis.append((ai, hd, r.get('text', '')))
        agree = sum(c for (a, h), c in conf.items() if a == h)
        tot = sum(conf.values())
        print(f'=== {fn} : 판정 {tot} · 일치 {agree} ({100*agree/max(1,tot):.0f}%) ===')
        for (a, h), c in conf.most_common():
            mark = '' if a == h else '  <불일치'
            print(f'   {a} → {h}: {c}{mark}')
        dump.append(f'\n##### {fn} 불일치 ({len(dis)}) #####')
        for a, h, t in dis[:60]:
            dump.append(f'[{a}→{h}] {t}')
    open(SCRATCH + '/disagreements.txt', 'w', encoding='utf-8').write('\n'.join(dump))
    print(f'\n불일치 예시 → disagreements.txt')


if __name__ == '__main__':
    main()
