# -*- coding: utf-8 -*-
"""AI 합의 silver 증강셋 빌더 — 다면평가 코퍼스 → 고정밀 자동라벨(human gold와 분리).

human gold 1,976이 작고 부정클래스가 얇아, **3신호 합의 구역**(KoTE override == human_label 라벨러 ==
필드 prior, 트랩 없음)에서 고정밀 silver를 추출해 증강한다. silver는 **별도 계층**:
  · label_source='ai_consensus', review_status='ai_auto', tier='silver' (human gold와 절대 혼합 금지)
  · 학습 시 gold=앵커·테스트, silver=증강(가중치 분리).
긍↔부 안전: 필드게이트(장점→neg 금지·단점→pos 금지) + 3신호 합의 + 대조/양보 트랩 제외 → 하드존(불일치)은
**의도적으로 제외**(거기는 사람 검토 C큐 몫). 빌드 후 표본 적대감사로 긍↔부 0 재확인.

클래스 균형 10k/클래스(텍스트 중복제거·gold 중복제외·PII 제외). dev·로컬·plans 배포제외·O(n).
"""
import argparse
import json
import os
import random
import re
import sys

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
GOLD = os.path.join(DATASET_DIR, 'emotion', 'emotion.jsonl')
OUT = os.path.join(DATASET_DIR, 'emotion', 'silver_consensus_260630.jsonl')
sys.path.insert(0, HERE)
import human_label as HL  # noqa: E402

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding='utf-8')
    except Exception:
        pass

CONTRAST = ('지만', '으나', '하나', '는데', '라도', '어도', '에도', '반면', '그러나')
PII = [re.compile(r'\d{6}\s*-\s*\d{7}'), re.compile(r'01\d\s*-?\s*\d{3,4}\s*-?\s*\d{4}'),
       re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')]
NEG_TOK = ('부족', '미흡', '결여', '부재', '소홀', '저조', '불성실', '미숙', '못함', '결함', '강압', '회피', '독단')
POS = HL._POS


def field_of(rid):
    return '장점' if '_1-' in rid else ('단점' if '_0-' in rid else '?')


def norm(t):
    return re.sub(r'\s+', ' ', (t or '').strip())


def has_pii(t):
    return any(p.search(t or '') for p in PII)


def unnegated_neg(t):
    for tok in NEG_TOK:
        i = t.find(tok)
        if i >= 0 and not any(n in t[i + len(tok):i + len(tok) + 8] for n in ('없', '않', '아니')):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weak', default=os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl'))
    ap.add_argument('--per', type=int, default=10000)
    ap.add_argument('--seed', type=int, default=260630)
    args = ap.parse_args()

    gold_texts = set()
    if os.path.exists(GOLD):
        for line in open(GOLD, encoding='utf-8'):
            line = line.strip()
            if line:
                gold_texts.add(norm(json.loads(line).get('text', '')))

    buckets = {'positive': {}, 'negative': {}, 'neutral': {}}  # label -> {norm_text: row}
    for line in open(args.weak, encoding='utf-8'):
        r = json.loads(line)
        if str(r.get('is_clause')) == 'True':
            continue
        t = r.get('text') or ''
        nt = norm(t)
        if not nt or nt in gold_texts or has_pii(t):
            continue
        sent = r.get('sentiment')
        hl = HL.label(t)[0]
        fld = field_of(r.get('id', ''))
        contrast = any(c in t for c in CONTRAST)
        label = None
        if fld == '장점' and sent == 'positive' and hl == 'positive' and not contrast:
            label = 'positive'
        elif fld == '단점' and sent == 'negative' and hl == 'negative' and not contrast:
            label = 'negative'
        elif sent == 'neutral' and hl == 'neutral':
            label = 'neutral'
        if label and nt not in buckets[label]:
            buckets[label][nt] = {
                'id': r.get('id'), 'text': t, 'field': fld,
                'sentiment_silver': label, 'label_source': 'ai_consensus',
                'signals': {'kote_override': sent, 'human_label': hl}, 'tier': 'silver',
                'review_status': 'ai_auto', 'src_hash': None, 'built_at': '2026-06-30',
            }

    rnd = random.Random(args.seed)
    picked = []
    print('=== AI 합의 silver 빌드 ===')
    for label in ('positive', 'negative', 'neutral'):
        rows = list(buckets[label].values())
        take = rows if len(rows) <= args.per else rnd.sample(rows, args.per)
        picked.extend(take)
        print(f'  {label}: 고유 {len(rows):,} → 채택 {len(take):,}')
    rnd.shuffle(picked)
    with open(OUT, 'w', encoding='utf-8') as f:
        for r in picked:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'silver → {os.path.basename(OUT)} ({len(picked):,}행, human gold와 분리)')

    # 표본 적대감사 — 긍↔부 트랩 잔존 확인
    print('\n=== silver 표본 적대감사(긍↔부 트랩) ===')
    pos = [r for r in picked if r['sentiment_silver'] == 'positive']
    neg = [r for r in picked if r['sentiment_silver'] == 'negative']
    p_susp = [r for r in pos if unnegated_neg(r['text'])]      # positive인데 미부정 부정어
    n_susp = [r for r in neg if POS.search(r['text']) and not unnegated_neg(r['text'])]  # negative인데 긍정표지
    print(f'  positive {len(pos):,} → 부→긍 트랩의심 {len(p_susp)} ({100*len(p_susp)/max(len(pos),1):.2f}%)')
    print(f'  negative {len(neg):,} → 긍→부 트랩의심 {len(n_susp)} ({100*len(n_susp)/max(len(neg),1):.2f}%)')
    for r in p_susp[:5]:
        print(f'    [P?] {r["text"][:46]}')
    for r in n_susp[:5]:
        print(f'    [N?] {r["text"][:46]}')


if __name__ == '__main__':
    main()
