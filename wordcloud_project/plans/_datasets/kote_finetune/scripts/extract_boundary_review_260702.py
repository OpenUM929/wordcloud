# -*- coding: utf-8 -*-
"""0702 — 성장여지 포켓을 그룹검토 게시판용 jsonl로 추출.

입력: eval/validation_candidates_260624.jsonl (미확정 하드후보 51,724건).
출력: eval/*.jsonl 3종 (게시판 /group-review/load 계약과 동일 스키마).
  행 스키마: {rec_id, text, field, cur_rule_label, ai_reference, human_decision}
우선순위 배타 분할(한 행은 한 파일에만):
  1) polysemy_review   — 폴리세미 표지 포함 & 극성 흔들림(pol_flip|to_neutral)  [최고 효율]
  2) polflip_review    — 긍↔부 직접 반전(pol_flip), 폴리세미 제외              [핵심가치 보험]
  3) neutral_boundary_review — 중립 경계(to_neutral), 폴리세미 제외            [neutral recall 레버]
low_margin(노이즈 많음)은 제외. 서버/GPU 불요. append 아님(재실행 시 덮어씀).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.abspath(os.path.join(HERE, '..', 'eval'))
SRC = os.path.join(EVAL, 'validation_candidates_260624.jsonl')

POLY = ['노력', '너무', '개선', '향상', '필요', '부분', '부족', '아쉬', '어려']


def make_ai_ref(d):
    """검토자 참고용 힌트(판정 강제 아님) — KoTE vs 규칙 override 근거."""
    return {
        'polarity': d.get('kote_label'),
        'confidence': 'low',
        'reason': 'KoTE=%s → 규칙override=%s (%s); %s' % (
            d.get('kote_label'), d.get('override_label'),
            d.get('applied_rule'), d.get('disagreement')),
    }


def row(d):
    return {
        'rec_id': d.get('id'),
        'text': d.get('text'),
        'field': '',                       # 후보 풀에 필드 없음(원천 미보유)
        'cur_rule_label': d.get('override_label'),
        'ai_reference': make_ai_ref(d),
        'human_decision': None,
    }


def main():
    buckets = {'polysemy': [], 'polflip': [], 'neutral_boundary': []}
    seen = set()
    dup = 0
    total = 0
    for line in open(SRC, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        total += 1
        rid = d.get('id')
        if rid in seen:
            dup += 1
            continue
        seen.add(rid)
        dis = d.get('disagreement')
        text = d.get('text') or ''
        has_poly = any(w in text for w in POLY)
        if has_poly and dis in ('pol_flip', 'to_neutral'):
            buckets['polysemy'].append(row(d))
        elif dis == 'pol_flip':
            buckets['polflip'].append(row(d))
        elif dis == 'to_neutral':
            buckets['neutral_boundary'].append(row(d))
        # low_margin 및 그 외는 제외
    out = {
        'polysemy': 'polysemy_review_260702.jsonl',
        'polflip': 'polflip_review_260702.jsonl',
        'neutral_boundary': 'neutral_boundary_review_260702.jsonl',
    }
    print('입력 %d행 (중복 id %d 제외)' % (total, dup))
    for k, fn in out.items():
        rows = buckets[k]
        p = os.path.join(EVAL, fn)
        with open(p, 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        print('  %-32s %6d행' % (fn, len(rows)))
    print('합계 추출 %d행 (low_margin 제외)' % sum(len(v) for v in buckets.values()))


if __name__ == '__main__':
    main()
