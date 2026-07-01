# -*- coding: utf-8 -*-
"""2항 경계 gold — 필드충돌 케이스 스테이징(사람 검토용, 규칙 밖 신호).

신규 그룹(G1/G2/G4) 어디에도 안 속하면서 **필드와 규칙판정이 충돌**하는 행:
  · 단점필드 ∧ positive  → 부→긍 잔여 누수 후보(실내용)
  · 장점필드 ∧ negative  → 긍→부 잔여 누수 후보(실내용)
이건 규칙으로 안 풀리는 진짜 경계 → 사람 판정이 모델에 새 신호를 준다(순환 탈출).
group_review.html에서 바로 로드. ai_reference=필드 prior(약한 힌트).
"""
import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, HERE)
from src.services.perspective_service import (  # noqa: E402
    is_no_weakness_declaration, has_improvement_request, is_no_response)
from g4_extract import is_growth  # noqa: E402


def field_of(rid):
    return '장점' if '_1-' in rid else ('단점' if '_0-' in rid else '?')


def in_group(t, sent):
    return (is_no_weakness_declaration(t) or has_improvement_request(t)
            or is_no_response(t) or is_growth(t, sent))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp',
                    default=os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl'))
    ap.add_argument('--date', default='260624')
    ap.add_argument('--per', type=int, default=400, help='방향별 표본 수')
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass

    cons_pos, pros_neg = [], []   # 단점→긍(부→긍 후보) / 장점→부(긍→부 후보)
    for line in open(args.inp, encoding='utf-8'):
        r = json.loads(line)
        if r.get('is_clause'):
            continue
        t = r.get('text') or ''
        sent = r.get('sentiment')
        if in_group(t, sent):
            continue
        fld = field_of(r.get('id', ''))
        if fld == '단점' and sent == 'positive':
            cons_pos.append(r)
        elif fld == '장점' and sent == 'negative':
            pros_neg.append(r)

    print(f'필드충돌(규칙 밖): 단점→긍 {len(cons_pos):,} · 장점→부 {len(pros_neg):,}')
    rng = random.Random(13)
    rng.shuffle(cons_pos); rng.shuffle(pros_neg)
    out = []
    for r in cons_pos[:args.per]:
        out.append((r, '단점', 'positive',
                    {'polarity': 'negative', 'confidence': 'low',
                     'reason': '단점칸 prior=부정 경향이나 KoTE는 긍정 → 직접 판정 필요(부→긍 누수 후보)'}))
    for r in pros_neg[:args.per]:
        out.append((r, '장점', 'negative',
                    {'polarity': 'positive', 'confidence': 'low',
                     'reason': '장점칸 prior=긍정 경향이나 KoTE는 부정 → 직접 판정 필요(긍→부 누수 후보)'}))
    rng.shuffle(out)
    path = os.path.join(DATASET_DIR, 'eval', f'field_conflict_review_{args.date}.jsonl')
    with open(path, 'w', encoding='utf-8') as f:
        for r, fld, cur, ref in out:
            f.write(json.dumps({
                'rec_id': r.get('id'), 'text': r.get('text'), 'field': fld,
                'cur_rule_label': cur, 'ai_reference': ref, 'human_decision': None,
            }, ensure_ascii=False) + '\n')
    print(f'  검토셋 {len(out)} → {os.path.relpath(path, PROJECT_ROOT)} (group_review.html에서 로드)')


if __name__ == '__main__':
    main()
