# -*- coding: utf-8 -*-
"""G4 자기개발/학습지향 — 파이프라인 편입(weak 전파 + 대표 gold 패킷).

g4_extract.is_growth(검증된 선별기)로 멤버 태깅 → 기본극성 positive로 weak 전파 +
대표 gold 후보/needs_human(단점필드 경계는 ai_reference 동봉) 분리. G1/G2(D4/D5)와 동형.
신규 그룹이라 순환 아님(기존 규칙 없음). gold는 대표 판정으로 확정(군집≠gold).
"""
import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from g4_extract import is_growth  # noqa: E402
import human_label as HL  # noqa: E402 (고친 라벨러로 극성 재판정 — 단점필드 positive 오류 정리)

GROUP = 'hr_growth_orientation'


def field_of(rid):
    return '장점' if '_1-' in rid else ('단점' if '_0-' in rid else '?')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp',
                    default=os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl'))
    ap.add_argument('--date', default='260624')
    ap.add_argument('--reps', type=int, default=300)
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass

    weak_path = os.path.join(DATASET_DIR, 'emotion', f'group_weak_g4_{args.date}.jsonl')
    members, boundary = [], []
    n = 0
    with open(args.inp, encoding='utf-8') as f, open(weak_path, 'w', encoding='utf-8') as w:
        for line in f:
            r = json.loads(line)
            if r.get('is_clause'):
                continue
            n += 1
            t = r.get('text') or ''
            if not is_growth(t, r.get('sentiment')):
                continue
            fld = field_of(r.get('id', ''))
            members.append(r)
            if fld == '단점':            # 단점칸에 성장서술 = 경계(검수 권장)
                boundary.append(r)
            pol = HL.label(t)[0]          # 라벨러 극성(요청/무종결은 중립·부정으로 정리)
            w.write(json.dumps({
                'rec_id': r.get('id'), 'src_hash': r.get('src_hash'),
                'text': t, 'field': fld, 'group_weak': GROUP, 'polarity_weak': pol,
                'label_source': 'g4_selector+human_label', 'review_status': 'weak',
            }, ensure_ascii=False) + '\n')

    print(f'전체 {n:,} → G4 멤버 {len(members):,} (단점필드 경계 {len(boundary):,}) weak 전파')
    print(f'  → {os.path.relpath(weak_path, os.path.abspath(os.path.join(DATASET_DIR, "..", "..")))}')

    # 대표 gold 패킷 — 장점필드 clean=positive gold후보 / 단점필드=needs_human(ai_reference positive)
    rng = random.Random(7)
    pros = [r for r in members if field_of(r.get('id', '')) == '장점']
    rng.shuffle(pros); rng.shuffle(boundary)
    reps_pros = pros[:args.reps * 2 // 3]
    reps_bnd = boundary[:args.reps - len(reps_pros)]
    gold, needs = [], []
    for r in reps_pros:
        gold.append({'rec_id': r.get('id'), 'text': r.get('text'), 'field': '장점',
                     'group': GROUP, 'polarity': 'positive', 'note': '성장행위 서술(장점)'})
    for r in reps_bnd:
        needs.append({'rec_id': r.get('id'), 'text': r.get('text'), 'field': '단점',
                      'group': GROUP, 'human_decision': None,
                      'ai_reference': {'polarity': 'positive', 'confidence': 'medium',
                                       'reason': '단점칸이나 성장행위 서술 → 긍정 판단(칸 불일치, 확인 권장)'}})
    gp = os.path.join(DATASET_DIR, 'eval', f'group_gold_candidates_g4_{args.date}.jsonl')
    with open(gp, 'w', encoding='utf-8') as f:
        for x in gold:
            f.write(json.dumps(x, ensure_ascii=False) + '\n')
    npth = os.path.join(DATASET_DIR, 'eval', f'group_needs_human_g4_{args.date}.jsonl')
    # 🔴 사람 판정 보호: 이미 검토된 파일이면 덮어쓰지 않음(재생성이 gold를 지우는 사고 방지).
    if os.path.isfile(npth) and any(
            json.loads(l).get('human_decision') for l in open(npth, encoding='utf-8') if l.strip()):
        print(f'  ⚠ {os.path.basename(npth)} 사람 판정 존재 → 덮어쓰기 생략(보호)')
    else:
        with open(npth, 'w', encoding='utf-8') as f:
            for x in needs:
                f.write(json.dumps(x, ensure_ascii=False) + '\n')
    print(f'  gold후보(장점) {len(gold)} → {os.path.basename(gp)}')
    print(f'  needs_human(단점경계) {len(needs)} → {os.path.basename(npth)}')

    summ = {'date': args.date, 'group': GROUP, 'members': len(members),
            'field_pros': len(pros), 'field_cons_boundary': len(boundary),
            'gold_candidates': len(gold), 'needs_human': len(needs)}
    sp = os.path.join(DATASET_DIR, 'result', f'group_g4_{args.date}.json')
    json.dump(summ, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'  요약 → {os.path.basename(sp)}')


if __name__ == '__main__':
    main()
