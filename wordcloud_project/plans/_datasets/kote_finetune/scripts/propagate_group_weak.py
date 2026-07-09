# -*- coding: utf-8 -*-
"""감정 스트림 D5 — 신규 그룹 weak 전파(전체 멤버, 학습 볼륨).

계획서 0624_04 D5. G1·G2 **전체 멤버**에 그룹+극성 weak 라벨을 부여(군집 멤버십 전파).
gold(대표)와 달리 weak는 전량 — 파인튜닝 학습 신호의 본체. judge_group_packet.judge 재사용
(trap 제외·칭찬형 positive·강부정 negative·깨끗 neutral) → 라벨 진위는 대표 gold가 받침.

append-only: 정본 emotion.jsonl 직접 수정 대신 날짜 스냅샷(group_weak_<date>.jsonl)으로 적립.
production 코드 무변경(데이터 트랙) → 긍↔부 0 회귀 대상 아님(규칙 미추가).
"""
import argparse
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, HERE)

from src.services.perspective_service import (  # noqa: E402
    is_no_weakness_declaration, has_improvement_request)
import judge_group_packet as jp  # noqa: E402


def field_of(rid):
    return '장점' if '_1-' in rid else ('단점' if '_0-' in rid else '?')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp',
                    default=os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl'))
    ap.add_argument('--date', default='260624')
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass

    out_path = os.path.join(DATASET_DIR, 'emotion', f'group_weak_{args.date}.jsonl')
    stat = Counter()
    pol = Counter()
    n = 0
    with open(args.inp, encoding='utf-8') as f, open(out_path, 'w', encoding='utf-8') as w:
        for line in f:
            r = json.loads(line)
            if r.get('is_clause'):
                continue
            n += 1
            t = r.get('text') or ''
            if is_no_weakness_declaration(t):
                grp = 'hr_no_weakness_declaration'
            elif has_improvement_request(t):
                grp = 'hr_improvement_request'
            else:
                continue
            res = jp.judge({'text': t, 'group': grp, 'cur_rule_label': r.get('sentiment')})
            stat[(grp, res['status'])] += 1
            if res['group'] is None:        # trap 제외
                pol['excluded_trap'] += 1
                continue
            # weak 극성: 깨끗=neutral / 칭찬형=positive / 강부정=negative(ai_reference 따름)
            wpol = res.get('polarity') or (res.get('ai_reference') or {}).get('polarity') or 'neutral'
            pol[wpol] += 1
            w.write(json.dumps({
                'rec_id': r.get('id'), 'src_hash': r.get('src_hash'),
                'text': t, 'field': field_of(r.get('id', '')),
                'group_weak': res['group'], 'polarity_weak': wpol,
                'label_source': 'cluster_propagation', 'review_status': 'weak',
            }, ensure_ascii=False) + '\n')

    total_grp = sum(v for k, v in stat.items())
    print(f'전체 문장 {n:,} → 그룹 멤버 {total_grp:,} weak 전파')
    print('--- 그룹×judge상태 ---')
    for (g, s), c in sorted(stat.items()):
        print(f'  {g} · {s}: {c:,}')
    print('--- weak 극성 분포 ---')
    for k, c in pol.most_common():
        print(f'  {k}: {c:,}')
    print(f'→ {os.path.relpath(out_path, PROJECT_ROOT)}')

    summ = {'date': args.date, 'sentences': n, 'group_members': total_grp,
            'by_group_status': {f'{g}|{s}': c for (g, s), c in stat.items()},
            'weak_polarity': dict(pol)}
    sp = os.path.join(DATASET_DIR, 'result', f'group_weak_d5_{args.date}.json')
    json.dump(summ, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'요약 → {os.path.relpath(sp, PROJECT_ROOT)}')


if __name__ == '__main__':
    main()
