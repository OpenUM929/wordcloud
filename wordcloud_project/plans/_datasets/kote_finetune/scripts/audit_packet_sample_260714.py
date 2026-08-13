# -*- coding: utf-8 -*-
"""23년 판정패킷 블라인드 감사 — Claude 판정(라벨 비노출 상태 선판정) vs 티어 라벨 대조.

CJ = Claude가 packet_audit_sample_260714.jsonl 텍스트만 보고(티어·모델라벨 미노출) 판정한 값.
판정 원칙(확립): 건강/개인안녕→중립 · 업무 개선요청/결핍→부정 · 무결점선언→중립 ·
무응답/쓰레기→중립 · 무종결 단편→중립 · 양가태도(명시 해악표지 없으면)→긍정(기업관점) ·
긍부혼재→중립 · 장점필드 명사구 칭찬→긍정.

대조 산출: 티어별 일치율(자동확정 티어 오류율 추정) + 불일치 전수 목록(패턴 분석).
"""
import io
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
WP = os.path.abspath(os.path.join(DS, '..', '..', '..'))
sys.path.insert(0, WP)
REVIEW_DIR = os.path.join(DS, 'eval', 'review')

CJ = {
    0: 'negative', 1: 'negative', 2: 'negative', 3: 'negative', 4: 'neutral',
    5: 'positive', 6: 'positive', 7: 'neutral', 8: 'negative', 9: 'neutral',
    10: 'positive', 11: 'positive', 12: 'negative', 13: 'neutral', 14: 'positive',
    15: 'neutral', 16: 'neutral', 17: 'neutral', 18: 'negative', 19: 'neutral',
    20: 'neutral', 21: 'negative', 22: 'negative', 23: 'negative', 24: 'negative',
    25: 'neutral', 26: 'negative', 27: 'negative', 28: 'neutral', 29: 'positive',
    30: 'negative', 31: 'positive', 32: 'neutral', 33: 'positive', 34: 'neutral',
    35: 'positive', 36: 'negative', 37: 'neutral', 38: 'neutral', 39: 'negative',
    40: 'neutral', 41: 'negative', 42: 'positive', 43: 'neutral', 44: 'neutral',
    45: 'negative', 46: 'neutral', 47: 'positive', 48: 'neutral', 49: 'negative',
    50: 'negative', 51: 'neutral', 52: 'neutral', 53: 'negative', 54: 'neutral',
    55: 'neutral', 56: 'negative', 57: 'negative', 58: 'negative', 59: 'neutral',
    60: 'neutral', 61: 'positive', 62: 'negative', 63: 'negative', 64: 'negative',
    65: 'negative', 66: 'neutral', 67: 'positive', 68: 'negative', 69: 'neutral',
    70: 'neutral', 71: 'neutral', 72: 'positive', 73: 'negative', 74: 'neutral',
    75: 'neutral', 76: 'negative', 77: 'neutral', 78: 'negative', 79: 'neutral',
    80: 'negative', 81: 'neutral', 82: 'positive', 83: 'positive', 84: 'positive',
    85: 'positive', 86: 'neutral', 87: 'neutral', 88: 'negative', 89: 'negative',
    90: 'positive', 91: 'negative', 92: 'neutral', 93: 'positive', 94: 'positive',
    95: 'neutral', 96: 'neutral', 97: 'negative', 98: 'positive', 99: 'neutral',
    100: 'positive', 101: 'neutral', 102: 'negative', 103: 'positive', 104: 'negative',
    105: 'neutral', 106: 'neutral', 107: 'neutral', 108: 'neutral', 109: 'positive',
    110: 'negative', 111: 'negative', 112: 'neutral', 113: 'negative', 114: 'negative',
    115: 'negative', 116: 'positive', 117: 'neutral', 118: 'negative', 119: 'negative',
}


def main():
    sample = [json.loads(l) for l in io.open(
        os.path.join(REVIEW_DIR, 'packet_audit_sample_260714.jsonl'), encoding='utf-8')]
    assert len(sample) == len(CJ), f'표본 {len(sample)} vs 판정 {len(CJ)}'

    # 티어 라벨 복원: T0=neutral, T3_CONFIRM/T3_MODEL=모델 라벨(패킷 재조회), REVIEW=모델 라벨(참고)
    with io.open(r'D:\dev\wordcloud\data\23년 판정패킷.csv', encoding='utf-8-sig') as f:
        pkt = json.load(f)
    model_of = {}
    for it in pkt['items']:
        k = ((it.get('text') or '').strip(), it.get('field') or '')
        model_of.setdefault(k, (it.get('model_ref') or {}).get('label'))

    per_tier = defaultdict(Counter)
    mism = []
    for r in sample:
        cj = CJ[r['idx']]
        k = (r['text'].strip(), r['field'])
        tier_label = 'neutral' if r['tier'] == 'T0_STRUCT' else model_of.get(k)
        agree = (cj == tier_label)
        pn = {cj, tier_label} == {'positive', 'negative'}
        per_tier[r['tier']]['n'] += 1
        per_tier[r['tier']]['agree' if agree else 'diff'] += 1
        if pn:
            per_tier[r['tier']]['PN'] += 1
        if not agree:
            mism.append({'idx': r['idx'], 'tier': r['tier'], 'field': r['field'],
                         'tier_label': tier_label, 'cj': cj, 'text': r['text']})

    print('티어별 일치율 (Claude 블라인드 vs 티어확정 라벨):')
    for t, c in sorted(per_tier.items()):
        n = c['n']
        print(f"  {t:18s} n={n:3d} 일치 {c['agree']:3d} ({c['agree']/n*100:5.1f}%)  "
              f"불일치 {c['diff']:3d}  긍↔부 {c['PN']}")
    out = os.path.join(REVIEW_DIR, 'packet_audit_mismatch_260714.jsonl')
    with io.open(out, 'w', encoding='utf-8') as f:
        for m in mism:
            f.write(json.dumps(m, ensure_ascii=False) + '\n')
    print(f'불일치 {len(mism)}건 → {os.path.basename(out)}')
    for m in mism:
        print(f"  #{m['idx']:3d} {m['tier'][:12]:12s} [{m['field']}] 티어={m['tier_label']:8s} CJ={m['cj']:8s} {m['text'][:60]}")


if __name__ == '__main__':
    main()
