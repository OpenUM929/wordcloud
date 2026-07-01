# -*- coding: utf-8 -*-
"""옛 gold 중립경계 재정렬 큐 — 규약 일관화(능동학습 1라운드 측정서 드러난 불일치).

round1 측정: 하드샘플(사용자 규약)과 옛 gold(baseline·기존검토) 중립경계 규약 충돌 → 모델 혼란.
옛 gold에서 **다툼 범주**만 추출해 사용자가 일관 규약으로 재판정:
  request_hope  개선요청·업무희망(...필요/했으면/좋겠)  — 사용자: 업무결여=부정
  wellwish      비평가적 기원(건강·안전·계셔)            — 사용자: 중립
  strength_abs  장점부재(장점 없음/보이지 않음)
  fragment      무종결 단편(맨 명사구)                   — 중립 vs 극성
하드샘플(source_file=hard_failure_*)은 이미 사용자 규약 → 제외. UI 호환(human_decision=null).
출력 eval/gold_reconcile_review_260701.jsonl → 0624_05 UI 재판정 → 정정 반영 → 하드 held-out 재측정.
"""
import argparse
import json
import os
import random
import re
import sys

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
STREAM = os.path.join(DATASET_DIR, 'emotion', 'emotion.jsonl')
OUT = os.path.join(DATASET_DIR, 'eval', 'gold_reconcile_review_260701.jsonl')
sys.path.insert(0, HERE)
import human_label as HL  # noqa: E402

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding='utf-8')
    except Exception:
        pass

OLD_SOURCES = {'group_needs_human_260624.jsonl', 'group_needs_human_g4_260624.jsonl',
               'field_conflict_review_260624.jsonl', 'baseline_eval_260624.jsonl'}

RE_WELLWISH = re.compile(r'건강|안전|행복|건승|쾌차|계셔|오래.{0,4}함께|무탈')
RE_REQUEST = re.compile(r'필요|좋겠|했으면|좋을|바람|바랍|되길|되시|당부|요망|권장|키웠|길러|가졌으면|임해야|해야')
RE_STRENGTH_ABS = re.compile(r'(장점|강점|특장점).{0,8}(없|보이지|꼽을)')


def norm(t):
    return re.sub(r'\s+', ' ', (t or '').strip())


def categorize(t):
    if RE_STRENGTH_ABS.search(t):
        return 'strength_abs'
    if RE_WELLWISH.search(t):
        return 'wellwish'
    if RE_REQUEST.search(t):
        return 'request_hope'
    if not HL._END.search(t) and len(t) <= 22:
        return 'fragment'
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--caps', default='request_hope:250,wellwish:60,strength_abs:60,fragment:120')
    ap.add_argument('--seed', type=int, default=260701)
    args = ap.parse_args()
    caps = dict((k, int(v)) for k, v in (x.split(':') for x in args.caps.split(',')))

    buckets = {k: {} for k in caps}   # cat -> {norm_text: row}
    for line in open(STREAM, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        g = json.loads(line)
        if g.get('source_file') not in OLD_SOURCES:    # 하드샘플 제외(이미 사용자 규약)
            continue
        t = g.get('text', '')
        nt = norm(t)
        cat = categorize(t)
        if not cat or nt in buckets[cat]:
            continue
        buckets[cat][nt] = {
            'rec_id': g.get('id'), 'text': t, 'field': g.get('field'),
            'cur_rule_label': g.get('sentiment_gold'),   # 현재 gold(재판정 대상)
            'ai_reference': json.dumps({'polarity': HL.label(t)[0], 'confidence': HL.label(t)[1],
                                        'reason': HL.reason(t)}, ensure_ascii=False),
            'human_decision': None,
            'note': f'{cat} 현gold={g.get("sentiment_gold")}',
        }

    rnd = random.Random(args.seed)
    picked = []
    print('=== 옛 gold 중립경계 재정렬 큐 ===')
    for cat in caps:
        rows = list(buckets[cat].values())
        take = rows if len(rows) <= caps[cat] else rnd.sample(rows, caps[cat])
        picked.extend(take)
        # 현 gold 분포(불일치 가시화)
        from collections import Counter
        dist = Counter(r['cur_rule_label'] for r in rows)
        print(f'  {cat}: 풀 {len(rows)} → 채택 {len(take)}  현gold분포={dict(dist)}')
    rnd.shuffle(picked)
    with open(OUT, 'w', encoding='utf-8') as f:
        for r in picked:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'\n총 {len(picked)}행 → {os.path.basename(OUT)} (0624_05 UI 재판정)')


if __name__ == '__main__':
    main()
