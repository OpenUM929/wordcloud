# -*- coding: utf-8 -*-
"""gold 증강 검토큐 빌더 (B: 미판정 후보 / C: weak positive 표본) — 0624_05 검토 UI 입력.

목적: 사람이 0624_05 group_review UI로 빠르게 gold를 확정하도록 **검토큐만** 만든다.
      gold 확정은 사람(추측 분류 금지). 각 행에 **독립 힌트 2개**를 동봉해 대조를 쉽게 한다:
        ① 군집/필드 polarity(약지도)   ② human_label 라벨러 판정(ai_reference, 이유 포함)
      두 신호가 갈리는 행 = 고가치(규칙 밖 신호) → 사람 판정이 모델에 새 신호.

산출(eval/, 0624_05 UI가 바로 로드 — human_decision 공란):
  B) group_gold_review_260630.jsonl    — group_gold_candidates*(1,518) 병합·UI화
  C) weak_positive_review_260630.jsonl — weak positive 층화표본(단점∧긍=누수후보 / 장점고신뢰=안전수확 / 저마진=경계)

제약: dev·로컬, plans 배포 제외, append-only 정식스트림 직접수정 안 함(검토 후 promote_gold.py로 적립), O(n).
"""
import argparse
import ast
import json
import os
import random
import sys

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
EVAL_DIR = os.path.join(DATASET_DIR, 'eval')
sys.path.insert(0, HERE)
import human_label as HL  # noqa: E402

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding='utf-8')
    except Exception:
        pass


def field_of(rid):
    return '장점' if '_1-' in rid else ('단점' if '_0-' in rid else '?')


def ai_ref(text):
    pol, conf = HL.label(text)
    return json.dumps({'polarity': pol, 'confidence': conf, 'reason': HL.reason(text)},
                      ensure_ascii=False)


def existing_review_ids():
    """이미 검토됨/검토큐에 있는 id → 중복 검토 방지."""
    ids = set()
    for fn in os.listdir(EVAL_DIR):
        if not fn.endswith('.jsonl'):
            continue
        for line in open(os.path.join(EVAL_DIR, fn), encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            rid = r.get('rec_id') or r.get('id')
            if rid:
                ids.add(rid)
    return ids


def build_B():
    out = os.path.join(EVAL_DIR, 'group_gold_review_260630.jsonl')
    srcs = ['group_gold_candidates_260624.jsonl', 'group_gold_candidates_g4_260624.jsonl']
    rows, agree, disagree = [], 0, 0
    for fn in srcs:
        p = os.path.join(EVAL_DIR, fn)
        if not os.path.exists(p):
            continue
        for line in open(p, encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            text = r.get('text', '')
            cluster_pol = r.get('polarity') or r.get('cur_rule_label')
            aref = ai_ref(text)
            hl_pol = json.loads(aref)['polarity']
            if cluster_pol and hl_pol == cluster_pol:
                agree += 1
            else:
                disagree += 1
            rows.append({
                'rec_id': r.get('rec_id'),
                'text': text,
                'field': r.get('field') or field_of(r.get('rec_id', '')),
                'group': r.get('group'),
                'cur_rule_label': r.get('cur_rule_label') or cluster_pol,
                'cluster_polarity': cluster_pol,
                'ai_reference': aref,
                'human_decision': None,
                'note': r.get('note'),
            })
    with open(out, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'[B] group_gold_review_260630.jsonl: {len(rows)}행 '
          f'(라벨러↔군집 일치 {agree} / 불일치 {disagree}=고가치 대조)')
    return out, len(rows)


def build_C(weak_path, per, seed, exclude):
    out = os.path.join(EVAL_DIR, 'weak_positive_review_260630.jsonl')
    cons_pos, pros_hi, lowmargin = [], [], []  # 단점∧긍 / 장점고신뢰 / 저마진
    seen = 0
    for line in open(weak_path, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if str(r.get('is_clause')) == 'True':
            continue
        if r.get('sentiment') != 'positive':
            continue
        rid = r.get('id', '')
        if rid in exclude:
            continue
        seen += 1
        try:
            wk = r.get('weak_kote')
            if isinstance(wk, str):          # 260623=stringified, 260624=실 dict 둘 다 지원
                wk = ast.literal_eval(wk) if wk else {}
            wk = wk or {}
            pos, neg = float(wk.get('pos', 0)), float(wk.get('neg', 0))
        except Exception:
            pos, neg = 0.0, 0.0
        fld = field_of(rid)
        margin = abs(pos - neg)
        rec = (rid, r.get('text', ''), fld, pos, neg, margin)
        if fld == '단점':
            cons_pos.append(rec)         # 부→긍 누수 후보 (최우선)
        elif fld == '장점' and pos >= 0.95:
            pros_hi.append(rec)          # 안전 positive 수확
        if margin < 0.10:
            lowmargin.append(rec)        # 경계
    rnd = random.Random(seed)

    def samp(bucket, k):
        return bucket if len(bucket) <= k else rnd.sample(bucket, k)

    picked, ids = [], set()
    for stratum, bucket in [('cons_pos(단점∧긍·누수후보)', cons_pos),
                            ('pros_hi(장점·pos≥0.95)', pros_hi),
                            ('lowmargin(|pos-neg|<0.1)', lowmargin)]:
        for rid, text, fld, pos, neg, margin in samp(bucket, per):
            if rid in ids:
                continue
            ids.add(rid)
            picked.append({
                'rec_id': rid,
                'text': text,
                'field': fld,
                'cur_rule_label': 'positive',
                'ai_reference': ai_ref(text),
                'human_decision': None,
                'note': f'{stratum} pos={pos:.2f} neg={neg:.2f} margin={margin:.2f}',
            })
    with open(out, 'w', encoding='utf-8') as f:
        for r in picked:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'[C] weak_positive_review_260630.jsonl: {len(picked)}행 (weak positive {seen:,} 중 층화표본)')
    print(f'    풀: 단점∧긍 {len(cons_pos):,} / 장점고신뢰 {len(pros_hi):,} / 저마진 {len(lowmargin):,}')
    return out, len(picked)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--weak', default=os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl'))
    ap.add_argument('--per', type=int, default=300, help='C 층별 표본 수')
    ap.add_argument('--seed', type=int, default=260630)
    args = ap.parse_args()

    print('=== gold 증강 검토큐 빌더 (B+C) ===')
    bpath, bn = build_B()
    excl = existing_review_ids()  # B 산출 포함(방금 기록) → C에서 중복 제외
    cpath, cn = build_C(args.weak, args.per, args.seed, excl)
    print(f'\n총 검토 대기: {bn + cn}행 → 0624_05 group_review UI에서 긍/부/중/그룹아님 판정 후 promote_gold.py로 적립')


if __name__ == '__main__':
    main()
