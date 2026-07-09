# -*- coding: utf-8 -*-
"""감정 스트림 D4(judge) — 신규 그룹 대표 패킷 AI 1차 판정.

계획서 0624_04. group_packet_g1g2 의 items[].result 를 채운다. **선별 술어와 독립적인
trap·혼합신호 판정**으로 순환논리(같은 술어 재확인)를 피한다.

판정 규칙(보수적 — 긍↔부 0):
  - trap 패턴 매칭 → group=null, is_trap=true (그룹 아님, 제외).
  - 혼합(요청/선언 + 강한 칭찬어 or 미부정 강부정어) → needs_human (neutral 단정 위험).
  - G1 positive 경계(약점부재인데 현 규칙 긍정=칭찬형) → needs_human (polarity 재검).
  - 그 외 깨끗한 화행 → group 확정, polarity=neutral (gold 후보).
산출: judged 패킷 + gold 후보 jsonl + needs_human jsonl + 요약(히스토리).
"""
import argparse
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))

# 독립 trap 신호(선별 술어가 아닌, 판정 전용)
PRAISE = re.compile(r'훌륭|탁월|우수|뛰어|최고|모범|귀감|존경|성실|완벽|능숙')
KEEP_AS_IS = re.compile(r'(지금|현재|이대로|그대로)[^.]{0,6}유지|유지[^.]{0,4}(좋|바)')
IMPROVE_WILL = re.compile(r'개선[^.]{0,4}(의지|노력|하려)')
OVERCOME = re.compile(r'(어려움|난관|역경)[^.]{0,6}(극복|해소|헤쳐|이겨)')
STRONG_NEG = re.compile(r'무능|비협조|이기적|갑질|폭언|괴롭힘|성희롱|부패|비도덕|무책임|회피|폄|기만')

G1_TRAP = re.compile(r'장점[^.]{0,4}(없|부족)')   # "장점이 없음"=비판(약점부재 아님)


def judge(item):
    t = item.get('text') or ''
    grp = item.get('group')
    cur = item.get('cur_rule_label')
    # 1) trap
    if grp == 'hr_improvement_request':
        if KEEP_AS_IS.search(t) or IMPROVE_WILL.search(t) or OVERCOME.search(t):
            return {'group': None, 'polarity': None, 'is_trap': True,
                    'note': 'trap: 유지칭찬/개선의지/극복', 'status': 'excluded'}
    if grp == 'hr_no_weakness_declaration':
        if G1_TRAP.search(t):
            return {'group': None, 'polarity': None, 'is_trap': True,
                    'note': 'trap: 장점없음=비판', 'status': 'excluded'}
    # 2) 혼합 — 강한 칭찬어 동반 → neutral 단정 위험. ai_reference = 내 최선 판단(칭찬 지배 → positive)
    if PRAISE.search(t):
        return {'group': grp, 'polarity': None, 'is_trap': False,
                'note': '혼합: 칭찬어 동반 → polarity 재검', 'status': 'needs_human',
                'ai_reference': {'polarity': 'positive', 'confidence': 'high',
                                 'reason': '훌륭/탁월/우수 등 칭찬어가 화행을 지배 → 긍정으로 판단'}}
    # 3) 강부정 동반 → 진짜 부정 가능. ai_reference = negative
    if STRONG_NEG.search(t):
        return {'group': grp, 'polarity': None, 'is_trap': False,
                'note': '혼합: 강부정어 동반 → polarity 재검', 'status': 'needs_human',
                'ai_reference': {'polarity': 'negative', 'confidence': 'medium',
                                 'reason': '무능/비협조/갑질 등 강한 부정어 동반 → 부정으로 판단'}}
    # 4) G1 positive 경계(칭찬어 미검출이나 KoTE positive) → 재검. 진짜칭찬+중립노이즈 혼재 → low.
    if grp == 'hr_no_weakness_declaration' and cur == 'positive':
        return {'group': grp, 'polarity': None, 'is_trap': False,
                'note': 'G1 KoTE positive(칭찬어 미검출) → polarity 재검', 'status': 'needs_human',
                'ai_reference': {'polarity': 'positive', 'confidence': 'low',
                                 'reason': '명시 칭찬어는 없으나 KoTE가 긍정 → 약한 긍정/중립 경계(불확실, 사람 확인 권장)'}}
    # 5) 깨끗한 화행 → 그룹 확정·neutral(gold 후보)
    return {'group': grp, 'polarity': 'neutral', 'is_trap': False,
            'note': '깨끗한 화행', 'status': 'gold_candidate'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default='260624')
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass

    pkt_path = os.path.join(DATASET_DIR, 'eval', f'group_packet_g1g2_{args.date}.json')
    pkt = json.load(open(pkt_path, encoding='utf-8'))
    stat = Counter()
    by_group = Counter()
    gold, needs = [], []
    for it in pkt['items']:
        res = judge(it)
        it['result'] = res
        stat[res['status']] += 1
        by_group[(it['group'], res['status'])] += 1
        rec = {'rec_id': it['key']['rec_id'], 'text': it['text'], 'field': it['field'],
               'group': res['group'], 'polarity': res['polarity'],
               'cur_rule_label': it['cur_rule_label'], 'note': res['note']}
        if res['status'] == 'gold_candidate':
            gold.append(rec)
        elif res['status'] == 'needs_human':
            rec['human_decision'] = None          # 사람이 채울 칸(긍/부/중)
            rec['ai_reference'] = res.get('ai_reference')   # 참고: 내 판정(대조용)
            needs.append(rec)

    # judged 패킷 저장(in-place result)
    json.dump(pkt, open(pkt_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    gp = os.path.join(DATASET_DIR, 'eval', f'group_gold_candidates_{args.date}.jsonl')
    with open(gp, 'w', encoding='utf-8') as f:
        for r in gold:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    npth = os.path.join(DATASET_DIR, 'eval', f'group_needs_human_{args.date}.jsonl')
    with open(npth, 'w', encoding='utf-8') as f:
        for r in needs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    print('=== AI 1차 판정 결과 ===')
    for k in ('gold_candidate', 'needs_human', 'excluded'):
        print(f'  {k}: {stat[k]}')
    print('--- 그룹×상태 ---')
    for (g, s), c in sorted(by_group.items()):
        print(f'  {g} · {s}: {c}')
    summ = {'date': args.date, 'total': len(pkt['items']), 'status': dict(stat),
            'by_group': {f'{g}|{s}': c for (g, s), c in by_group.items()},
            'gold_candidates': len(gold), 'needs_human': len(needs), 'excluded_trap': stat['excluded']}
    sp = os.path.join(DATASET_DIR, 'result', f'group_judge_d4_{args.date}.json')
    json.dump(summ, open(sp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'gold 후보 → {os.path.basename(gp)} · needs_human → {os.path.basename(npth)} · 요약 → {os.path.basename(sp)}')


if __name__ == '__main__':
    main()
