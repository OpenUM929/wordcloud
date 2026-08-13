# -*- coding: utf-8 -*-
"""P3 — 프로덕션 홀드아웃 슬라이스 추출.

batch_20260709_0에서 층화 표본(~150행, 극성 층화)을 추출하여
TEST_SETS에 등록할 gold(사람확정라벨)용 JSONL을 생성한다.

용도: 8c_hard(n=140)의 ±3pp 노이즈를 보완하는 프로덕션 분포 측정 전용.
      학습 미포함(holdout) — finetune_sentiment의 TEST_SETS에 등록.

출력: DS/eval/holdout_prod_YYMMDD.jsonl (raw, y필드: p/n/u)
      → 사용자 확정 후 gold_ 접두사로 rename + TEST_SETS 등록
"""
import argparse
import datetime
import json
import os
import random
import sys

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.normpath(os.path.join(HERE, '..'))
PROJECT_ROOT = os.path.normpath(os.path.join(HERE, '..', '..', '..', '..'))
BATCH_PATH = os.path.join(PROJECT_ROOT, '..', 'data', 'batch_20260709_0.csv')
EVAL_DIR = os.path.join(DATASET_DIR, 'eval')

LAB_MAP = {'p': 0, 'n': 1, 'u': 2}
ID2LAB_LONG = {0: 'positive', 1: 'negative', 2: 'neutral'}
LAB_LONG_SHORT = {'positive': 'p', 'negative': 'n', 'neutral': 'u'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=150, help='표본 크기')
    ap.add_argument('--seed', type=int, default=42, help='재현용 시드')
    ap.add_argument('--batch', default=BATCH_PATH, help='배치 JSONL 입력 경로')
    ap.add_argument('--out', default='', help='출력 경로(기본 eval/holdout_prod_YYMMDD.jsonl)')
    args = ap.parse_args()

    batch_path = os.path.abspath(args.batch)
    if not os.path.exists(batch_path):
        print(f'배치 없음: {batch_path}')
        sys.exit(1)

    # ── 배치 로드 ──
    strata = {'p': [], 'n': [], 'u': []}
    total = 0
    for line in open(batch_path, encoding='utf-8'):
        stripped = line.strip()
        if not stripped or stripped.startswith('{"#'):
            continue
        r = json.loads(stripped)
        y = r.get('y', '')
        if y not in strata:
            continue
        strata[y].append(r)
        total += 1

    print(f'배치: {total}행')
    dist_all = {k: len(v) for k, v in strata.items()}
    print(f'극성분포: p={dist_all.get("p",0)} n={dist_all.get("n",0)} u={dist_all.get("u",0)}')

    # ── 층화 표본 ──
    rng = random.Random(args.seed)
    picked = []
    dist_sample = {}
    remaining = args.n
    # 각 층에서 비례 배분 (최소 1건)
    for lab in ['p', 'n', 'u']:
        pool = strata[lab]
        if not pool:
            continue
        frac = len(pool) / total
        n_from = max(1, round(frac * args.n))
        n_from = min(n_from, len(pool), remaining - (3 - len([x for x in ['p','n','u'] if x != lab and strata[x]])))
        n_from = max(0, min(n_from, len(pool), remaining))
        sampled = rng.sample(pool, n_from)
        picked.extend(sampled)
        dist_sample[lab] = len(sampled)
        remaining -= n_from
    # 남은 할당: 가장 큰 층에 추가
    if remaining > 0:
        largest = max(['p', 'n', 'u'], key=lambda x: len(strata[x]))
        extra = rng.sample(strata[largest], min(remaining, len(strata[largest])))
        picked.extend(extra)
        dist_sample[largest] = dist_sample.get(largest, 0) + len(extra)

    print(f'표본: {len(picked)}행 (목표 {args.n})')
    print(f'표본분포: {dist_sample}')

    # ── 출력 JSONL ──
    today = datetime.date.today().strftime('%y%m%d')
    out = args.out or os.path.join(EVAL_DIR, f'holdout_prod_{today}.jsonl')
    os.makedirs(os.path.dirname(out), exist_ok=True)

    with open(out, 'w', encoding='utf-8') as f:
        for r in picked:
            # TEST_SETS 형식: text, y, field
            f.write(json.dumps({
                'text': r.get('x', ''),
                'y': r.get('y', ''),
                'field': '',  # batch에 field 없음
                's': r.get('s', []),
                'source': 'holdout_prod',
            }, ensure_ascii=False) + '\n')

    print(f'출력: {os.path.relpath(out, PROJECT_ROOT)} ({len(picked)}행)')
    print()
    print('--- 다음 단계 ---')
    print(f'  (1) 사용자: {len(picked)}행 라벨 확정')
    print(f'  (2) Claude: gold_holdout_prod_{today}.jsonl 로 rename')
    print(f'  (3) Claude: finetune_sentiment.py TEST_SETS에 등록')
    print(f'        → "holdout_prod": "gold_holdout_prod_{today}.jsonl"')


if __name__ == '__main__':
    main()
