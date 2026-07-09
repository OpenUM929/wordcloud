# -*- coding: utf-8 -*-
"""검증용 데이터셋 구성 — '평가가 틀렸던(불일치)' 케이스를 held-out 검증셋으로 분리.

목적(사용자 요구): 파일 prelabel(KoTE)과 우리 규칙 판정이 갈리는 케이스 = 평가가 틀렸거나
어려운 케이스다. 이를 모아두면 **향후 규칙/모델 변경 시 회귀·정확도 측정 기준**이 된다.

분류(불일치 유형):
  - pol_flip      : KoTE 극(긍↔부)과 override 극이 반대 — 핵심가치 직결(최우선 검증).
  - to_neutral    : KoTE 긍/부 → override 중립(중립 강등).
  - from_neutral  : KoTE 중립 → override 긍/부.
  - low_margin    : KoTE 자체가 |pos-neg|<0.05로 불확실(경계).

⚠️ override 라벨도 정답이 아니다 → 이 셋은 **사람 확정(gold)을 기다리는 검증 후보**다.
   각 행에 양쪽 라벨(kote/override)을 보존해 사람이 '어느 쪽이 맞나'를 판정한다.
   확정 후 train 스트림과 누수 분리(같은 src_hash가 train/val 양쪽에 가지 않도록 별 파일).

O(n)·서버/모델 불요. plans 배포 제외.
"""
import json
import os
import re
from collections import Counter

_WS = re.compile(r'\s+')
_LOW_MARGIN = 0.05


def _kote_label(pos, neg):
    if pos > neg:
        return 'positive'
    if neg > pos:
        return 'negative'
    return 'neutral'


def _norm(text):
    return _WS.sub(' ', (text or '').strip()).lower().strip(' .。!?！？·…-')


def classify(kote_label, ov_label, pos, neg):
    """불일치 유형 반환(없으면 None)."""
    if {kote_label, ov_label} == {'positive', 'negative'}:
        return 'pol_flip'
    if abs(pos - neg) < _LOW_MARGIN:
        return 'low_margin'
    if kote_label != ov_label:
        if ov_label == 'neutral':
            return 'to_neutral'
        if kote_label == 'neutral':
            return 'from_neutral'
        return 'other_mismatch'
    return None


def extract_validation(records, per_dup_cap=2):
    """레코드 리스트 → 검증 후보 리스트. 전체문장만(절 제외), 근접중복 캡."""
    out, seen = [], Counter()
    for r in records:
        if r.get('is_clause'):
            continue
        k = r.get('kote')
        if not k:
            continue
        pos, neg = k[0], k[1]
        klab = _kote_label(pos, neg)
        ov = r.get('sentiment')
        if ov is None:
            continue
        kind = classify(klab, ov, pos, neg)
        if kind is None:
            continue
        key = _norm(r.get('text'))
        if seen[key] >= per_dup_cap:
            continue
        seen[key] += 1
        bt = '_'.join(r['id'].split('-')[0].split('_')[:3])
        out.append({
            'id': 'val-' + r['id'],
            'text': r['text'],
            'kote': [round(pos, 4), round(neg, 4), round(k[2], 4)],
            'kote_label': klab,                # 파일 prelabel(=KoTE argmax)
            'override_label': ov,              # 우리 규칙 판정
            'applied_rule': r.get('applied_rule'),
            'disagreement': kind,
            'batch': bt,
            'src_hash': r.get('src_hash'),
            # 검증 gold(미확정) — 사람이 '어느 쪽이 맞나' 확정
            'gold': None, 'review_status': 'pending', 'purpose': 'validation',
        })
    return out


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def write_report(path, rows, date_tag):
    by_kind = Counter(r['disagreement'] for r in rows)
    by_batch = Counter(r['batch'] for r in rows)
    pol = [r for r in rows if r['disagreement'] == 'pol_flip']
    L = [f'# 검증용 데이터셋 요약 — {date_tag}', '',
         '> prelabel(KoTE)↔규칙 불일치 = 평가가 틀렸/어려운 케이스. 사람 확정 후 회귀·정확도 측정 기준.',
         '> ⚠️ override도 정답 아님 — 양쪽 라벨 보존, 사람이 판정. train과 누수 분리(별 파일).', '',
         f'- 검증 후보(근접중복 캡 후): **{len(rows)}**', '',
         '## 불일치 유형', '', '| 유형 | 수 |', '|---|---|']
    for k, c in by_kind.most_common():
        L.append(f'| {k} | {c} |')
    L += ['', '## 배치별', '', '| batch | 수 |', '|---|---|']
    for b, c in by_batch.most_common():
        L.append(f'| {b} | {c} |')
    L += ['', f'## 🔴 긍↔부 flip 예 (최우선 검증, 총 {len(pol)})', '']
    for r in pol[:15]:
        L.append(f"- [{r['kote_label']}→{r['override_label']} {r['applied_rule']}] {r['text'][:60]}")
    L.append('')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')


if __name__ == '__main__':
    import argparse
    from datetime import date
    HERE = os.path.dirname(__file__)
    DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
    ap = argparse.ArgumentParser(description='검증용 데이터셋(불일치 케이스) 구성')
    ap.add_argument('--snapshot', default=None, help='입력 스냅샷 jsonl(기본: 최신 weak_export_*)')
    ap.add_argument('--date', default=date.today().strftime('%y%m%d'))
    args = ap.parse_args()
    import glob
    snap = args.snapshot or sorted(glob.glob(os.path.join(DATASET_DIR, 'emotion', 'weak_export_*.jsonl')))[-1]
    print(f'[load] {snap}')
    recs = (json.loads(l) for l in open(snap, encoding='utf-8') if l.strip())
    val = extract_validation(recs)
    out = os.path.join(DATASET_DIR, 'eval', f'validation_candidates_{args.date}.jsonl')
    rep = os.path.join(DATASET_DIR, 'result', f'validation_set_{args.date}.md')
    write_jsonl(out, val)
    write_report(rep, val, args.date)
    print(f'[done] 검증 후보 {len(val)}행 → {out}')
    print(f'[report] {rep}')
