# -*- coding: utf-8 -*-
"""하드샘플(실패구역) 라벨링 큐 — 능동학습 1라운드. 사람이 긍/부/중 판정 → gold 승격.

모델이 틀리는 ~10%는 자동라벨이 바로 그곳에서 틀리는 영역(자기오류 강화 위험) → **사람 판정 전용**.
무라벨 코퍼스에서 실패 대리신호로 발굴(테스트 누수 없음·CPU·O(n)):
  S1 부→긍 누수후보(★핵심가치 최우선): 단점필드 ∧ override=positive ∧ (라벨러=negative or 미부정 결핍어)
  S2 긍→부 후보: 장점필드 ∧ override=negative ∧ 라벨러=positive
  S3 3신호 불일치(기타): override sentiment ≠ 라벨러
  S4 저마진 경계: |pos-neg| < 0.05 (모델 최저신뢰)
각 행 ai_reference=라벨러 힌트(정답 아님·대조용), human_decision 공란. gold 텍스트 중복제외·PII제외.
출력 eval/hard_failure_review_260630.jsonl → 0624_05 UI에서 판정 → promote_gold.py 적립 → 재학습.
"""
import argparse
import ast
import json
import os
import random
import re
import sys

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
GOLD = os.path.join(DATASET_DIR, 'emotion', 'emotion.jsonl')
OUT = os.path.join(DATASET_DIR, 'eval', 'hard_failure_review_260630.jsonl')
sys.path.insert(0, HERE)
import human_label as HL  # noqa: E402

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding='utf-8')
    except Exception:
        pass

PII = [re.compile(r'\d{6}\s*-\s*\d{7}'), re.compile(r'01\d\s*-?\s*\d{3,4}\s*-?\s*\d{4}'),
       re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')]


def field_of(rid):
    return '장점' if '_1-' in rid else ('단점' if '_0-' in rid else '?')


def norm(t):
    return re.sub(r'\s+', ' ', (t or '').strip())


def has_pii(t):
    return any(p.search(t or '') for p in PII)


def parse_margin(r):
    wk = r.get('weak_kote')
    if isinstance(wk, str):
        try:
            wk = ast.literal_eval(wk)
        except Exception:
            wk = {}
    wk = wk or {}
    return abs(float(wk.get('pos', 0)) - float(wk.get('neg', 0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weak', default=os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl'))
    ap.add_argument('--s1', type=int, default=250)   # 부→긍 누수후보
    ap.add_argument('--s2', type=int, default=50)    # 긍→부
    ap.add_argument('--s3', type=int, default=150)   # 불일치
    ap.add_argument('--s4', type=int, default=100)   # 저마진
    ap.add_argument('--seed', type=int, default=260630)
    args = ap.parse_args()

    gold_texts = set()
    if os.path.exists(GOLD):
        for line in open(GOLD, encoding='utf-8'):
            line = line.strip()
            if line:
                gold_texts.add(norm(json.loads(line).get('text', '')))

    S = {'s1': [], 's2': [], 's3': [], 's4': []}
    seen = set()
    for line in open(args.weak, encoding='utf-8'):
        r = json.loads(line)
        if str(r.get('is_clause')) == 'True':
            continue
        t = r.get('text') or ''
        nt = norm(t)
        if not nt or nt in gold_texts or nt in seen or has_pii(t):
            continue
        sent = r.get('sentiment')
        if sent not in ('positive', 'negative', 'neutral'):
            continue
        hl = HL.label(t)[0]
        fld = field_of(r.get('id', ''))
        unneg = HL._has_unnegated_neg(t)
        margin = parse_margin(r)
        bucket = None
        if fld == '단점' and sent == 'positive' and (hl == 'negative' or unneg):
            bucket = 's1'
        elif fld == '장점' and sent == 'negative' and hl == 'positive':
            bucket = 's2'
        elif sent != hl:
            bucket = 's3'
        elif margin < 0.05:
            bucket = 's4'
        if bucket:
            seen.add(nt)
            S[bucket].append({
                'rec_id': r.get('id'), 'text': t, 'field': fld,
                'cur_rule_label': sent,
                'ai_reference': json.dumps({'polarity': hl, 'confidence': HL.label(t)[1],
                                            'reason': HL.reason(t)}, ensure_ascii=False),
                'human_decision': None,
                'note': f'{bucket} override={sent} 라벨러={hl} margin={margin:.3f}',
            })

    rnd = random.Random(args.seed)
    label = {'s1': '부→긍 누수후보(★최우선)', 's2': '긍→부 후보',
             's3': '3신호 불일치', 's4': '저마진 경계'}
    caps = {'s1': args.s1, 's2': args.s2, 's3': args.s3, 's4': args.s4}
    picked = []
    print('=== 하드샘플(실패구역) 라벨링 큐 ===')
    for k in ('s1', 's2', 's3', 's4'):
        pool = S[k]
        take = pool if len(pool) <= caps[k] else rnd.sample(pool, caps[k])
        picked.extend(take)
        print(f'  {k} {label[k]}: 풀 {len(pool):,} → 채택 {len(take)}')
    rnd.shuffle(picked)
    with open(OUT, 'w', encoding='utf-8') as f:
        for r in picked:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'\n총 {len(picked)}행 → {os.path.basename(OUT)}')
    print('0624_05 group_review UI에서 파일 선택 → 긍/부/중/그룹아님 판정(키보드 1/2/3/0) → 저장.')
    print('판정 후: promote_gold.py SOURCE_FILES에 추가 → 정식 적립 → 재학습(능동학습 1라운드).')


if __name__ == '__main__':
    main()
