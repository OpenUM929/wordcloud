# -*- coding: utf-8 -*-
"""신규 데이터(data/new_260617.csv) 분류 검증 — 신규 규칙/강화 알고리즘 실측.

목적(사용자 요청): 0617_01 계획으로 추가된 신규 분기
  positive_rescue / negation_praise / no_response_neutral
및 강화 알고리즘이 신규 코퍼스를 "제대로" 분류하는지 KoTE 실행으로 확인한다.

방식:
  - refine_acquired_row(row)를 그대로 사용(프로덕션과 동일한 KoTE→override 경로).
  - 각 행의 csv model_label(반입 당시 라벨) → 신규 파이프라인 corrected_label 전이 집계.
  - 신규 분기 발동 건과, 긍↔부(negative↔positive) 방향 전이 전부 표로 출력해 검수.

핵심 가치: 긍↔부 오분류만 방지(중립→긍정 허용). 따라서 negative↔positive 전이는
전부 나열해 사람이 검수할 수 있게 한다(코어밸류 위반 여부 판단 근거).

KoTE 1회 로드. DB·배치·서버 불요. 출력: result/신규데이터_분류검증_260617.md
"""
import csv
import os
import sys
from collections import Counter

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, ROOT)

from src.services.perspective_service import refine_acquired_row  # noqa: E402

CSV_PATH = os.path.join(ROOT, '..', 'data', 'new_260617.csv')
OUT_PATH = os.path.join(HERE, '..', 'result', '신규데이터_분류검증_260617.md')

NEW_RULES = {'positive_rescue', 'negation_praise', 'no_response_neutral'}


def main():
    rows = list(csv.DictReader(open(CSV_PATH, encoding='utf-8-sig')))
    total = len(rows)
    rule_ct = Counter()
    trans_ct = Counter()        # (before_label, after_label)
    new_hits = []               # 신규 분기 발동 행
    polarity_flips = []         # negative<->positive 전이 행(검수 대상)

    for r in rows:
        before = (r.get('model_label') or '').strip()  # 반입 당시 라벨
        meta = refine_acquired_row(r)
        after = meta['corrected_label']
        rule = meta['applied_rule']
        rule_ct[rule] += 1
        trans_ct[(before, after)] += 1
        rec = {
            'id': r.get('id', ''), 'text': r.get('sentence_text', '').strip(),
            'before': before, 'after': after, 'rule': rule,
            'pos': meta['kote_pos'], 'neg': meta['kote_neg'], 'neu': meta['kote_neutral'],
            'score': meta['override_score'],
        }
        if rule in NEW_RULES:
            new_hits.append(rec)
        if {before, after} == {'negative', 'positive'}:
            polarity_flips.append(rec)

    write_report(total, rule_ct, trans_ct, new_hits, polarity_flips)
    print(f'[done] 전체 {total}행')
    print('  rule 분포:', dict(rule_ct))
    print('  전이(before->after):', dict(trans_ct))
    print(f'  신규 분기 발동: {len(new_hits)}건  (positive_rescue/negation_praise/no_response_neutral)')
    print(f'  긍↔부 전이(검수): {len(polarity_flips)}건')
    for c in polarity_flips:
        print(f"    [{c['rule']}] {c['before']}->{c['after']} | {c['text'][:40]}")


def _tbl(rows, cols, fmt):
    out = ['| ' + ' | '.join(cols) + ' |', '|' + '|'.join('---' for _ in cols) + '|']
    out += [fmt(r) for r in rows]
    return '\n'.join(out)


def write_report(total, rule_ct, trans_ct, new_hits, flips):
    new_by_rule = Counter(h['rule'] for h in new_hits)
    lines = [
        '# 신규 데이터 분류 검증 — 2026-06-17',
        '',
        '> `data/new_260617.csv` 전수를 신규 규칙/강화 알고리즘으로 재분류(KoTE 실행).',
        '> 경로=`refine_acquired_row`(프로덕션과 동일한 KoTE→override). 신규 분기/긍↔부 전이 검수.',
        '',
        f'## 요약',
        '',
        f'- 전체: **{total}행**',
        f'- 신규 분기 발동: **{len(new_hits)}건** '
        f"(positive_rescue {new_by_rule.get('positive_rescue', 0)} / "
        f"negation_praise {new_by_rule.get('negation_praise', 0)} / "
        f"no_response_neutral {new_by_rule.get('no_response_neutral', 0)})",
        f'- 긍↔부(negative↔positive) 전이: **{len(flips)}건** (아래 전수 검수)',
        '',
        '## 발동 규칙 분포',
        '',
        _tbl(sorted(rule_ct.items(), key=lambda x: -x[1]), ['rule_id', '건수'],
             lambda kv: f'| {kv[0]} | {kv[1]} |'),
        '',
        '## 라벨 전이 (반입 라벨 → 신규 파이프라인)',
        '',
        _tbl(sorted(trans_ct.items(), key=lambda x: -x[1]), ['before', 'after', '건수'],
             lambda kv: f'| {kv[0][0]} | {kv[0][1]} | {kv[1]} |'),
        '',
        '## 긍↔부 전이 전수 (코어밸류 검수 대상)',
        '',
    ]
    if flips:
        lines.append(_tbl(
            flips, ['id', 'before→after', 'rule', 'pos/neg/neu', 'score', '문장'],
            lambda c: f"| {c['id']} | {c['before']}→{c['after']} | {c['rule']} | "
                      f"{c['pos']}/{c['neg']}/{c['neu']} | {c['score']} | "
                      f"{c['text'][:50].replace('|', '/')} |"))
    else:
        lines.append('_없음 — negative↔positive 전이 0건._')
    lines += ['', '## 신규 분기 발동 전수', '',
              _tbl(sorted(new_hits, key=lambda x: x['rule']),
                   ['id', 'rule', 'before→after', 'score', '문장'],
                   lambda c: f"| {c['id']} | {c['rule']} | {c['before']}→{c['after']} | "
                             f"{c['score']} | {c['text'][:50].replace('|', '/')} |")]
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'[write] {os.path.abspath(OUT_PATH)}')


if __name__ == '__main__':
    main()
