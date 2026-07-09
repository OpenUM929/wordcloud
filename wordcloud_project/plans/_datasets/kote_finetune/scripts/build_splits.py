# -*- coding: utf-8 -*-
"""hr-kote-finetune 분할/중복제거/품질 리포트 (비-🟡 독립 스크립트).

설계 근거: plans/2026/0617_05_kote-finetune-data §8(품질·균형·분할).

동작:
  1) export_jsonl.py가 만든 약지도 스냅샷 JSONL을 읽는다.
  2) 중복제거: 정규화 동일 문장은 src_hash당 최대 N개로 캡(무응답류가 학습셋 지배 방지).
  3) 누수방지 분할: 동일 src_hash(=동일 평가자)는 train/val/test에 분산되지 않도록
     그룹 단위 결정적 해시 분할(기본 80/10/10). src_hash 없는 행은 'unassigned'.
  4) split 부여 사본(*.split.jsonl) + 품질 리포트(result/) 출력.

핵심가치: 긍↔부 오분류 방지 — 분할 후 긍/부/중 분포를 리포트로 노출(편중 점검).
서버/배치 불요. 모델 미로드(JSONL만 처리).
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
REPO_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '..'))

_WS = re.compile(r'\s+')


def normalize(text):
    """근접중복 판정용 정규화 — 공백 축약 + 양끝 구두점/공백 제거 + 소문자."""
    t = _WS.sub(' ', (text or '').strip()).lower()
    return t.strip(' .。!?！？·…-')


def split_of(src_hash, ratios):
    """src_hash → 그룹 결정적 분할. 동일 평가자는 항상 같은 split(누수 방지)."""
    if not src_hash:
        return 'unassigned'
    bucket = int(hashlib.sha256(src_hash.encode()).hexdigest(), 16) % 100
    tr, va = ratios
    if bucket < tr:
        return 'train'
    if bucket < tr + va:
        return 'val'
    return 'test'


def find_latest_export():
    cands = sorted(glob.glob(os.path.join(DATASET_DIR, 'emotion', 'weak_export_*.jsonl')))
    cands = [c for c in cands if not c.endswith('.split.jsonl')]
    return cands[-1] if cands else None


def main():
    ap = argparse.ArgumentParser(description='hr-kote-finetune 분할/중복제거/리포트')
    ap.add_argument('--in', dest='inp', default=None,
                    help='입력 JSONL(기본: 최신 weak_export_*.jsonl)')
    ap.add_argument('--dup-cap', type=int, default=10,
                    help='src_hash당 동일 문장 최대 보존 수(기본 10)')
    ap.add_argument('--train', type=int, default=80, help='train 비율(%)')
    ap.add_argument('--val', type=int, default=10, help='val 비율(%)')
    args = ap.parse_args()

    inp = args.inp or find_latest_export()
    if not inp or not os.path.exists(inp):
        print('[error] 입력 JSONL을 찾을 수 없음. 먼저 export_jsonl.py 실행.')
        sys.exit(1)

    records = [json.loads(l) for l in open(inp, encoding='utf-8') if l.strip()]

    # 2) 중복제거 — (src_hash, normalized_text) 그룹당 dup_cap개까지
    seen = defaultdict(int)
    kept, dropped = [], 0
    for rec in records:
        key = (rec.get('src_hash'), normalize(rec.get('text')))
        if seen[key] >= args.dup_cap:
            dropped += 1
            continue
        seen[key] += 1
        kept.append(rec)

    # 3) 누수방지 그룹 분할
    ratios = (args.train, args.val)
    split_ct = Counter()
    split_sent = defaultdict(Counter)     # split → gold 분포
    groups_in_split = defaultdict(set)
    for rec in kept:
        sp = split_of(rec.get('src_hash'), ratios)
        rec['split'] = sp
        split_ct[sp] += 1
        split_sent[sp][rec.get('sentiment_gold') or '(없음)'] += 1
        if rec.get('src_hash'):
            groups_in_split[sp].add(rec['src_hash'])

    # 누수 검증: 그룹이 둘 이상 split에 걸치지 않는지(설계상 불가하지만 명시 확인)
    overlap = _group_leak_check(groups_in_split)

    out_path = inp.replace('.jsonl', '.split.jsonl')
    with open(out_path, 'w', encoding='utf-8') as f:
        for rec in kept:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

    tag = date.today().strftime('%y%m%d')
    report_path = os.path.join(DATASET_DIR, 'result', f'split_report_{tag}.md')
    write_report(report_path, inp, out_path, len(records), len(kept), dropped,
                 args, split_ct, split_sent, groups_in_split, overlap)
    print(f'[done] 입력 {len(records)} → 중복제거 후 {len(kept)} (드롭 {dropped})')
    print(f'  분할: {dict(split_ct)}  · 누수: {"없음" if not overlap else overlap}')
    print(f'[write] {out_path}')
    print(f'[write] {report_path}')


def _group_leak_check(groups_in_split):
    splits = [s for s in groups_in_split if s != 'unassigned']
    leaks = []
    for i, a in enumerate(splits):
        for b in splits[i + 1:]:
            inter = groups_in_split[a] & groups_in_split[b]
            if inter:
                leaks.append((a, b, len(inter)))
    return leaks


def _tbl(items, cols, fmt):
    out = ['| ' + ' | '.join(cols) + ' |', '|' + '|'.join('---' for _ in cols) + '|']
    out += [fmt(i) for i in items]
    return '\n'.join(out)


def write_report(path, inp, out_path, n_in, n_kept, dropped, args,
                 split_ct, split_sent, groups_in_split, overlap):
    lines = [
        f'# 분할/중복제거/품질 리포트 — {date.today().isoformat()}',
        '',
        f'> 입력: `{os.path.basename(inp)}` · 출력: `{os.path.basename(out_path)}`',
        f'> 설계: 0617_05 §8 · dup_cap={args.dup_cap}, 비율 train/val/test='
        f'{args.train}/{args.val}/{100 - args.train - args.val}',
        '',
        '## 요약',
        '',
        f'- 입력 행: **{n_in}**',
        f'- 중복제거 후: **{n_kept}** (드롭 {dropped})',
        f'- 그룹 누수: **{"없음" if not overlap else overlap}** '
        '(동일 src_hash가 복수 split에 걸치지 않음)',
        '',
        '## split 분포',
        '',
        _tbl(sorted(split_ct.items()), ['split', '행', '평가자(그룹) 수'],
             lambda kv: f'| {kv[0]} | {kv[1]} | {len(groups_in_split.get(kv[0], set()))} |'),
        '',
        '## split별 잠정 gold(sentiment) 분포',
        '',
    ]
    for sp in sorted(split_sent):
        lines.append(f'**{sp}**')
        lines.append('')
        lines.append(_tbl(sorted(split_sent[sp].items(), key=lambda x: -x[1]),
                          ['label', '건수'], lambda kv: f'| {kv[0]} | {kv[1]} |'))
        lines.append('')
    lines += [
        '> ⚠️ positive 잠정 gold가 희소하면(§8) 긍정 gold 확보가 선결 — 학습 전 사람 검토 필요.',
        '',
    ]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
