# -*- coding: utf-8 -*-
"""정식 gold 긍↔부 오염 재감사 스크린 — 파인튜닝 투입 전 안전검사.

핵심가치=긍↔부 0. 오염 정의:
  · 부→긍: sentiment_gold=positive 인데 텍스트가 진짜 부정(비판) → 치명적(모델에 오류 학습).
  · 긍→부: sentiment_gold=negative 인데 텍스트가 진짜 긍정 → 치명적(양방향).
  (중립↔긍정 모호는 허용방향이라 오염 아님 — 별도 집계만.)

이 스크린은 **고recall 의심행 추출기**(과다추출 OK — 사람/AI가 판정). 두 독립신호:
  ① human_label.label  ② 미부정 부정어/긍정표지 직접탐지(HL._has_unnegated_neg / HL._POS)
→ result/gold_audit_260630.md + 의심행 jsonl. 판정은 후속(추측 분류 금지).
"""
import json
import os
import sys

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
STREAM = os.path.join(DATASET_DIR, 'emotion', 'emotion.jsonl')
OUT = os.path.join(DATASET_DIR, 'eval', 'gold_audit_suspects_260630.jsonl')
sys.path.insert(0, HERE)
import human_label as HL  # noqa: E402

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding='utf-8')
    except Exception:
        pass


def screen():
    gold = [json.loads(l) for l in open(STREAM, encoding='utf-8')]
    pos = [g for g in gold if g['sentiment_gold'] == 'positive']
    neg = [g for g in gold if g['sentiment_gold'] == 'negative']

    p2n, n2p = [], []   # 부→긍 의심 / 긍→부 의심
    for g in pos:
        t = g['text']
        hl = HL.label(t)[0]
        unneg = HL._has_unnegated_neg(t)
        if hl == 'negative' or unneg:
            g['_signal'] = f"HL={hl}{' +미부정부정어' if unneg else ''}"
            p2n.append(g)
    for g in neg:
        t = g['text']
        hl = HL.label(t)[0]
        pos_marker = bool(HL._POS.search(t)) and not HL._has_unnegated_neg(t)
        if hl == 'positive' or pos_marker:
            g['_signal'] = f"HL={hl}{' +긍정표지' if pos_marker else ''}"
            n2p.append(g)

    with open(OUT, 'w', encoding='utf-8') as f:
        for g in p2n + n2p:
            f.write(json.dumps(g, ensure_ascii=False) + '\n')

    print('=== gold 긍↔부 오염 재감사 스크린 ===')
    print(f'positive gold {len(pos)} → 부→긍 의심 {len(p2n)} ({100*len(p2n)/max(len(pos),1):.1f}%)')
    print(f'negative gold {len(neg)} → 긍→부 의심 {len(n2p)} ({100*len(n2p)/max(len(neg),1):.1f}%)')
    print(f'의심행 → {OUT}\n')

    print('--- 부→긍 의심 (positive gold인데 부정신호) ---')
    for g in p2n:
        print(f"  [{g['field']}] {g['_signal']:22s} | {g['text'][:48]}")
    print('\n--- 긍→부 의심 (negative gold인데 긍정신호) ---')
    for g in n2p:
        print(f"  [{g['field']}] {g['_signal']:22s} | {g['text'][:48]}")


if __name__ == '__main__':
    screen()
