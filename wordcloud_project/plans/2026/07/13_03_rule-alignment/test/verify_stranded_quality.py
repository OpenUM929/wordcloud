# -*- coding: utf-8 -*-
"""13_03 Track1 3-1 — 승격후보(hd무표시 1,942) 품질·가치·위험 진단.

핵심 질문:
  (A) hd무표시 라벨이 현 모델과 얼마나 다른가? (hd==model → 승격 무가치 / hd≠model → 가치+위험)
  (B) 불일치가 긍↔부인가? (핵심가치 위협 — c6 회귀 재현 위험)
  (C) 방향 편중(개선요청 부정 대량)이 c6 회귀 패턴인가?
출력: 패턴별 hd vs model 혼동, 긍↔부 불일치, 클래스분포. + 표본(불일치) 덤프.
"""
import io
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
WP = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '..'))
sys.path.insert(0, WP)
DS = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '_datasets', 'kote_finetune'))
CAND = os.path.join(DS, 'eval', 'stranded_candidates_260713.jsonl')


def main():
    cand = [json.loads(l) for l in io.open(CAND, encoding='utf-8') if l.strip()]
    from src.modules.hr_sentiment import predict_sentiments
    texts = [c['text'] for c in cand]
    fields = [c['field'] for c in cand]
    model = predict_sentiments(texts, fields=fields)

    agree = 0
    pn = 0                                    # hd↔model 긍↔부 불일치
    conf = Counter()                          # (hd, model)
    by_pat = defaultdict(lambda: {'n': 0, 'agree': 0, 'pn': 0})
    disagreements = []
    for c, m in zip(cand, model):
        hd = c['human_decision']
        conf[(hd, m)] += 1
        p = c['pattern']
        by_pat[p]['n'] += 1
        if hd == m:
            agree += 1
            by_pat[p]['agree'] += 1
        else:
            if {hd, m} == {'positive', 'negative'}:
                pn += 1
                by_pat[p]['pn'] += 1
            disagreements.append({**c, 'model': m})

    n = len(cand)
    print(f'후보 {n}행 · hd==model 일치 {agree} ({100*agree/n:.1f}%) · 불일치 {n-agree}')
    print(f'그중 긍↔부(hd↔model) {pn}행  ← 승격 시 모델을 이 방향으로 당김(c6 회귀 위험 지표)')
    print('\n혼동(hd→model):')
    for (hd, m), v in sorted(conf.items(), key=lambda x: -x[1]):
        tag = '  ★긍↔부' if {hd, m} == {'positive', 'negative'} else ''
        print(f'  {hd:8s} → {m:8s} : {v:5d}{tag}')
    print('\n패턴별 (n · hd==model% · 긍↔부):')
    for p, d in sorted(by_pat.items(), key=lambda x: -x[1]['n']):
        print(f'  {p:20s} n={d["n"]:5d} · 일치 {100*d["agree"]/d["n"]:4.0f}% · 긍↔부 {d["pn"]}')

    # 표본 덤프: 긍↔부 불일치 전량 + 기타 불일치 표본
    pn_rows = [d for d in disagreements if {d['human_decision'], d['model']} == {'positive', 'negative'}]
    dst = os.path.join(HERE, 'stranded_pn_disagreements.jsonl')
    with io.open(dst, 'w', encoding='utf-8') as f:
        for d in pn_rows:
            f.write(json.dumps(d, ensure_ascii=False) + '\n')
    print(f'\n긍↔부 불일치 {len(pn_rows)}행 → {os.path.relpath(dst, HERE)} (표본검증 대상)')


if __name__ == '__main__':
    main()
