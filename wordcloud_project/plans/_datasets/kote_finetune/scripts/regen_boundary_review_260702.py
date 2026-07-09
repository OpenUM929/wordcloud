# -*- coding: utf-8 -*-
"""0702 재생성 — 경계 검토큐를 현재+C-1 규칙엔진으로 다시 생성.

동기: 최초 추출 소스(validation_candidates_260624)의 override_label/disagreement가
06-24 동결본이라 06-30 규칙(improvement_request_neutral)·C-1(no_response 가드) 미반영.
→ 현재 엔진으로 라벨·disagreement 재계산 + 정규화 dedup + 사용자 판정 보존.

원칙:
- 라벨/disagreement = 현재 `perspective_service` 엔진(실파이프라인 동일, neutral 인자 포함) 재계산.
- 사용자 판정(기존 3파일의 human_decision)은 정규화 텍스트로 보존 — 더 이상 disagreement가
  아니어도 판정분은 유지(gold 유실 방지).
- 미판정 & 현재 disagreement 아님 → 드롭(현재 규칙이 이미 해결 → 검토 불요).
- 배타 분할(폴리세미>긍↔부>중립경계), low_margin 제외. dedup 정규화·행당 1.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, ROOT)
from src.services.perspective_service import _sentence_sentiment_override_explain as ov

EVAL = os.path.abspath(os.path.join(HERE, '..', 'eval'))
SRC = os.path.join(EVAL, 'validation_candidates_260624.jsonl')
POLY = ['노력', '너무', '개선', '향상', '필요', '부분', '부족', '아쉬', '어려']
LOW_MARGIN = 0.05
OUT = {'polysemy': 'polysemy_review_260702.jsonl',
       'polflip': 'polflip_review_260702.jsonl',
       'neutral_boundary': 'neutral_boundary_review_260702.jsonl'}
_WS = re.compile(r'[\s\W_]+')


def norm(t):
    return _WS.sub('', t or '')


def kote_label(p, n):
    return 'positive' if p > n else 'negative' if n > p else 'neutral'


def classify(kl, ov_l, p, n):
    if {kl, ov_l} == {'positive', 'negative'}:
        return 'pol_flip'
    if abs(p - n) < LOW_MARGIN:
        return 'low_margin'
    if kl != ov_l and ov_l == 'neutral':
        return 'to_neutral'
    return None


def load_decisions():
    """기존 판정 human_decision → 정규화텍스트 map(gold 보존).

    소스(최신 우선): eval/review/*.jsonl(그룹재편성 후 사용자 판정이 여기 쌓임) → 백업 canonical →
    eval/ 최상위 canonical. 같은 텍스트는 먼저 만난 값 유지(review/가 최신이라 우선).
    """
    import glob
    dec = {}
    DEC = ('positive', 'negative', 'neutral', 'not_group', 'skip')
    review_files = sorted(glob.glob(os.path.join(EVAL, 'review', '*.jsonl')))
    backup_canon = [os.path.join(EVAL, '_gold_backup', 'pre_groupsplit_260703', fn)
                    for fn in OUT.values()]
    eval_canon = [os.path.join(EVAL, fn) for fn in OUT.values()]
    for p in review_files + backup_canon + eval_canon:
        if not os.path.isfile(p):
            continue
        for l in open(p, encoding='utf-8'):
            l = l.strip()
            if not l:
                continue
            r = json.loads(l)
            if r.get('human_decision') in DEC:
                dec.setdefault(norm(r['text']), r['human_decision'])
    return dec


def main():
    decisions = load_decisions()
    buckets = {k: [] for k in OUT}
    seen = set()
    kept_judged = 0
    n = 0
    for line in open(SRC, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        n += 1
        p, neg, u = d['kote']
        t = d.get('text', '')
        score, rule = ov(p, neg, t, is_last=True, total_sentences=1, neutral=u)
        new = 'positive' if score > 1e-6 else 'negative' if score < -1e-6 else 'neutral'
        kl = kote_label(p, neg)
        dis = classify(kl, new, p, neg)
        key = norm(t)
        judged = decisions.get(key)
        # 미판정 & 현재 비-disagreement(폴리세미 포켓 대상 아님) → 드롭
        in_pocket = dis in ('pol_flip', 'to_neutral')
        if not judged and not in_pocket:
            continue
        if key in seen:
            continue
        seen.add(key)
        row = {
            'rec_id': d.get('id'), 'text': t, 'field': '',
            'cur_rule_label': new,
            # 0702_03: '내 판정(참고)' polarity를 **규칙 결과**(new)로 맞춤. 이전엔 raw KoTE(kl)를
            #   넣어 "참고가 규칙과 안 맞는다"는 혼란 유발(KoTE는 규칙이 교정하는 원본이라 당연히 불일치).
            #   raw KoTE는 reason에 맥락으로만 보존.
            'ai_reference': {'polarity': new, 'confidence': 'low',
                             'reason': '규칙=%s (%s) · KoTE원본=%s · %s' % (new, rule, kl, dis or 'resolved')},
            'human_decision': judged,
        }
        if judged:
            kept_judged += 1
        has_poly = any(w in t for w in POLY)
        if has_poly and in_pocket:
            buckets['polysemy'].append(row)
        elif dis == 'pol_flip':
            buckets['polflip'].append(row)
        elif dis == 'to_neutral':
            buckets['neutral_boundary'].append(row)
        elif judged:                       # 판정분인데 포켓 분류 안되면 폴리세미로 보존
            buckets['polysemy'].append(row)

    print('입력 %d행 | 기존 판정 %d키 | 판정 보존 %d행' % (n, len(decisions), kept_judged))
    for k, fn in OUT.items():
        rows = buckets[k]
        with open(os.path.join(EVAL, fn), 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        judged = sum(1 for r in rows if r.get('human_decision'))
        print('  %-34s %6d행 (판정 %d, 미판정 %d)' % (fn, len(rows), judged, len(rows) - judged))
    print('합계 %d행 (재생성 전 34,457)' % sum(len(v) for v in buckets.values()))


if __name__ == '__main__':
    main()
