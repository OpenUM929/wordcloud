# -*- coding: utf-8 -*-
"""감정 스트림 D4 — 신규 그룹(G1 약점부재·G2 개선요청) 대표 판정 패킷 + 전/후 baseline 동결.

계획서 0624_04 D4. 군집(D1)에서 떠오른 화행 그룹을 **대표만 판정해 gold**(군집≠gold).
기존 술어 재사용으로 멤버 정밀 선별:
  G1 = is_no_weakness_declaration  (약점부재 선언, 기본 neutral)
  G2 = has_improvement_request     (개선요청/건설적 제언, 기본 neutral)

산출:
  1) eval/group_packet_g1g2_<date>.json  — 대표 층화표본 판정 패킷(자기설명). 경계(현 규칙≠neutral)
     우선 = 긍↔부 누수 케이스. judge가 group+polarity 확정·trap 거르면 gold 후보.
  2) eval/baseline_eval_<date>.jsonl     — 파인튜닝 전/후 비교용 **동결 평가셋**(층화, 현 규칙 라벨 동봉).
     학습 후 동일 셋 재채점 → before/after.

제약: dev·로컬, plans 배포 제외, 가명(스냅샷은 PII 격리분 제외), append-only는 emotion.jsonl 단계(D5).
"""
import argparse
import json
import os
import random
import sys
from collections import Counter

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.services.perspective_service import (  # noqa: E402
    is_no_weakness_declaration, has_improvement_request)


def field_of(rid):
    return '장점' if '_1-' in rid else ('단점' if '_0-' in rid else '?')


def load(path):
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if r.get('is_clause'):
                continue
            rows.append(r)
    return rows


def tag_groups(rows):
    """각 행에 그룹 태그(G1/G2/None) + 현 규칙판정 부여. (members, stats) 반환."""
    g1, g2 = [], []
    stat = {'G1': Counter(), 'G2': Counter()}
    for r in rows:
        t = r.get('text') or ''
        sent = r.get('sentiment') or 'none'
        if is_no_weakness_declaration(t):
            g1.append(r); stat['G1'][sent] += 1
        elif has_improvement_request(t):     # 배타(G1 우선 — 약점부재가 더 구체)
            g2.append(r); stat['G2'][sent] += 1
    return g1, g2, stat


def sample_reps(members, group_id, n, seed=11):
    """경계(현 규칙 != neutral) 우선 + 순수(neutral) 보충 층화표본."""
    rng = random.Random(seed)
    boundary = [r for r in members if (r.get('sentiment') or 'none') != 'neutral']
    pure = [r for r in members if (r.get('sentiment') or 'none') == 'neutral']
    rng.shuffle(boundary); rng.shuffle(pure)
    take_b = boundary[:n * 2 // 3]
    take_p = pure[:n - len(take_b)]
    picks = take_b + take_p
    items = []
    for r in picks:
        cur = r.get('sentiment') or 'none'
        items.append({
            'key': {'rec_id': r.get('id'), 'src_hash': r.get('src_hash')},
            'text': r.get('text'),
            'field': field_of(r.get('id', '')),
            'cur_rule_label': cur,
            'kote': r.get('kote'),
            'proposed_group': group_id,
            'proposed_polarity': 'neutral',
            'boundary': cur != 'neutral',     # True = 현 규칙이 긍/부로 본 누수 후보(우선 검수)
            'result': None,                   # judge가 채움: {group, polarity, is_trap, note}
        })
    return items


GROUP_DEFS = {
    'hr_no_weakness_declaration': {
        'display_name': '약점부재 선언', 'default_polarity': 'neutral',
        'definition': '평가 대상의 단점/보완점이 없다고 선언(비평가성).',
        'exemplars': ['보완필요점 없습니다', '특별한 보완사항 없음'],
        'traps': ['장점이 없음(=비판)', '보완 필요(없음 아님=개선요청)'],
    },
    'hr_improvement_request': {
        'display_name': '개선요청/건설적 제언', 'default_polarity': 'neutral',
        'definition': '현 상태 결핍을 정중한 요청/제언으로 표현(X 필요/보완/개선/했으면).',
        'exemplars': ['소통이 더 필요하다고 생각합니다', '자기중심적 사고의 개선필요'],
        'traps': ['보완점 없음(=약점부재)', '지금처럼 유지하면 좋겠(=칭찬)',
                  '개선하려는 의지(=긍정 자질)', '어려움 극복'],
    },
}


def build_packet(g1_items, g2_items, date_tag):
    return {
        '_doc': '신규 그룹 대표 판정 패킷(D4). judge는 각 items[].result 를 채운다: '
                '{"group": <group_id 또는 null>, "polarity": "neutral|positive|negative", '
                '"is_trap": bool, "note": str}. boundary=true(현 규칙이 긍/부로 본 행) 우선 검수 — '
                '긍↔부 누수 여부 직접 판정. trap이면 group=null·is_trap=true.',
        '_privacy': '가명 텍스트만(스냅샷은 PII 격리분 제외). rec_id/src_hash는 내부 키.',
        'schema_version': '1.0', 'packet_id': f'group_g1g2_{date_tag}',
        'group_defs': GROUP_DEFS,
        'stage': 'judge',
        'items': [{'group': 'hr_no_weakness_declaration', **it} for it in g1_items]
                 + [{'group': 'hr_improvement_request', **it} for it in g2_items],
    }


def build_baseline(rows, n, seed=23):
    """전/후 비교용 동결 평가셋 — 층화(필드×현규칙극성) + 그룹 경계 포함."""
    rng = random.Random(seed)
    strata = {}
    for r in rows:
        key = (field_of(r.get('id', '')), r.get('sentiment') or 'none')
        strata.setdefault(key, []).append(r)
    out = []
    per = max(1, n // max(1, len(strata)))
    for key, lst in strata.items():
        rng.shuffle(lst)
        for r in lst[:per]:
            out.append({
                'rec_id': r.get('id'), 'text': r.get('text'),
                'field': key[0], 'kote': r.get('kote'),
                'rule_label_before': key[1],   # 현 규칙(파인튜닝 前) 라벨 = baseline
                'gold': None,                  # 사람/AI 직접 판정 대기(held-out 정답)
            })
    rng.shuffle(out)
    return out[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp',
                    default=os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl'))
    ap.add_argument('--date', default='260624')
    ap.add_argument('--reps', type=int, default=250, help='그룹당 대표 표본 수')
    ap.add_argument('--baseline', type=int, default=600, help='동결 평가셋 크기')
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print(f'[1/4] 반입 {os.path.basename(args.inp)}')
    rows = load(args.inp)
    print(f'      문장 {len(rows):,}')
    print('[2/4] 그룹 태깅(G1 약점부재 / G2 개선요청)')
    g1, g2, stat = tag_groups(rows)
    print(f'      G1 {len(g1):,}  현규칙: {dict(stat["G1"])}')
    print(f'      G2 {len(g2):,}  현규칙: {dict(stat["G2"])}')
    leak_g2 = stat['G2']['positive']
    print(f'      ▶ G2 중 현재 positive(부→긍 누수 후보) = {leak_g2:,}')

    print(f'[3/4] 대표 판정 패킷(그룹당 {args.reps}, 경계 우선)')
    packet = build_packet(sample_reps(g1, 'hr_no_weakness_declaration', args.reps),
                          sample_reps(g2, 'hr_improvement_request', args.reps), args.date)
    pkt_path = os.path.join(DATASET_DIR, 'eval', f'group_packet_g1g2_{args.date}.json')
    os.makedirs(os.path.dirname(pkt_path), exist_ok=True)
    with open(pkt_path, 'w', encoding='utf-8') as f:
        json.dump(packet, f, ensure_ascii=False, indent=1)
    print(f'      items {len(packet["items"])} → {os.path.relpath(pkt_path, PROJECT_ROOT)}')

    print(f'[4/4] 전/후 비교용 동결 평가셋({args.baseline})')
    base = build_baseline(rows, args.baseline)
    base_path = os.path.join(DATASET_DIR, 'eval', f'baseline_eval_{args.date}.jsonl')
    with open(base_path, 'w', encoding='utf-8') as f:
        for r in base:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'      {len(base)}행 → {os.path.relpath(base_path, PROJECT_ROOT)}')

    # 요약(히스토리)
    summ = {'date': args.date, 'g1': len(g1), 'g2': len(g2),
            'g1_rule': dict(stat['G1']), 'g2_rule': dict(stat['G2']),
            'g2_leak_positive': leak_g2, 'reps_each': args.reps, 'baseline': len(base)}
    sp = os.path.join(DATASET_DIR, 'result', f'group_gold_d4_{args.date}.json')
    with open(sp, 'w', encoding='utf-8') as f:
        json.dump(summ, f, ensure_ascii=False, indent=1)
    print(f'      요약 → {os.path.relpath(sp, PROJECT_ROOT)}')


if __name__ == '__main__':
    main()
