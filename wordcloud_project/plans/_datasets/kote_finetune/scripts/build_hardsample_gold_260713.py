# -*- coding: utf-8 -*-
"""13_03 Track1(개정) 3-2 — 큐레이션 하드샘플 gold + 긍↔부 그룹검토 보드 생성.

입력: plans/2026/07/13_03_rule-alignment/test/gold_candidates_260713.jsonl(중립방향 35) +
      escalation_260713.jsonl(극성뒤집기 등 126).
출력:
  1) eval/gold_hardsample_neutral_260713.jsonl — 규칙확증 중립방향 gold(모델 극성오판 교정).
     스키마 = finetune load() 호환(text·field·human_decision). 긍↔부 불생성(전부 neutral).
  2) eval/review/hardsample_pn_review_260713.jsonl — 긍↔부 5건 사용자 확정 보드(내 의견 prefill).
자기검산: gold 전부 neutral assert · 보드 전부 긍↔부 assert · TEST 누수 재확인.
"""
import io
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
TEST = os.path.join(DS, '..', '..', '2026', '07', '13_03_rule-alignment', 'test')
GOLDC = os.path.join(TEST, 'gold_candidates_260713.jsonl')
ESC = os.path.join(TEST, 'escalation_260713.jsonl')
sys.path.insert(0, os.path.join(DS, 'scripts'))
from finetune_sentiment import TEST_SETS, LAB2ID  # noqa: E402

# 긍↔부 5건에 대한 [고] 판정 의견(text 앞부분으로 매칭).
PN_OPINIONS = {
    '업무할 때에도 본인이 더 했으면': {
        'my': 'positive', 'conf': 'high',
        'why': '"업무전가하는 모습은 찾아볼 수 없으며"=부정어의 부정=칭찬. hd(부정)이 오라벨, 모델(긍정)이 맞음. rule은 "했으면" 희망형 트랩에 걸림.'},
    '업무에 너무 빠져있고 전문적인': {
        'my': 'positive', 'conf': 'high',
        'why': '장점란·업무몰입+전문성=긍정. 모델이 "너무 빠져있고"를 과잉으로 오판(부). hd(긍정) 맞음.'},
    '업무에 너무 전문적이다': {
        'my': 'positive', 'conf': 'high',
        'why': '장점란·"너무 전문적"=칭찬. 모델이 "너무"를 과잉부정으로 오판. hd(긍정) 맞음.'},
    '분석 및 계획에 근거한 적기 필요한 조치 요구': {
        'my': 'positive', 'conf': 'low',
        'why': '장점란·분석/계획 역량 서술이나 "필요/요구" 폴리세미로 양가. 필드는 긍정 지지하나 확신 낮음 → 사용자 확정 요청.'},
    '너무 이성적이고 워커홀릭': {
        'my': 'uncertain', 'conf': 'low',
        'why': '장점란이나 "워커홀릭"은 양가(헌신↔과로). 명시 해악표지 없음 → 필드기준 긍정 가능하나 판단 위임.'},
}


def load(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()]


def build_test_texts():
    s = set()
    for fn in TEST_SETS.values():
        for r in load(os.path.join(DS, 'eval', fn)):
            t = (r.get('text') or '').strip()
            if t:
                s.add(t)
    return s


def match_opinion(text):
    for k, v in PN_OPINIONS.items():
        if text.strip().startswith(k):
            return v
    return None


def main():
    test_texts = build_test_texts()
    gold = load(GOLDC)
    esc = load(ESC)

    # 1) 중립 gold
    gpath = os.path.join(DS, 'eval', 'gold_hardsample_neutral_260713.jsonl')
    n_gold = 0
    with io.open(gpath, 'w', encoding='utf-8') as f:
        for r in gold:
            assert r['human_decision'] == 'neutral', 'gold에 비중립 혼입!'
            assert r['text'].strip() not in test_texts, f'TEST 누수: {r["text"][:20]}'
            f.write(json.dumps({
                'text': r['text'], 'field': r['field'], 'human_decision': 'neutral',
                'rec_id': r.get('rec_id'), 'source_file': r.get('src_file'),
                'decision_source': 'human(hd무표시)+opus_triage_rule_confirmed',
                'note': f'모델 {r["model"]} 과오판→중립(규칙 {r["rule_id"]} 확증). 13_03 하드샘플.',
            }, ensure_ascii=False) + '\n')
            n_gold += 1

    # 2) 긍↔부 보드
    pn = [r for r in esc if {r['human_decision'], r['model']} == {'positive', 'negative'}]
    bpath = os.path.join(DS, 'eval', 'review', 'hardsample_pn_review_260713.jsonl')
    n_board = 0
    with io.open(bpath, 'w', encoding='utf-8') as f:
        for r in pn:
            op = match_opinion(r['text']) or {'my': 'uncertain', 'conf': 'low', 'why': '판정 보류.'}
            f.write(json.dumps({
                'rec_id': r.get('rec_id'), 'text': r['text'], 'field': r['field'],
                'cur_rule_label': r['rule_label'],
                'ai_reference': f"모델={r['model']} · hd무표시={r['human_decision']} · 규칙={r['rule_id']} · [고]의견={op['my']}({op['conf']}): {op['why']}",
                'claude_judgment': op['my'],
                'human_decision': None,
                'group': 'hardsample_pn_260713', 'status': 2,
                'why_you_decide': '긍↔부(핵심가치) 교차 — hd무표시/모델/규칙이 상충하고 [고]도 일부 확신 낮음. 사용자 확정 필요.',
            }, ensure_ascii=False) + '\n')
            n_board += 1

    print(f'중립 gold: {n_gold}행 → eval/{os.path.basename(gpath)}')
    print(f'  클래스: {dict(Counter(g["human_decision"] for g in gold))} (전부 neutral 확인)')
    print(f'긍↔부 보드: {n_board}행 → eval/review/{os.path.basename(bpath)}')
    # 자기검산
    assert n_gold == len(gold) and all(g['human_decision'] == 'neutral' for g in gold)
    assert all(({r['human_decision'], r['model']} == {'positive', 'negative'}) for r in pn)
    assert n_board == 5, f'긍↔부 보드 예상 5, 실제 {n_board}'
    print(f'── 자기검산 ── gold 전부 neutral OK · 보드 전부 긍↔부 OK · TEST누수 0 OK · 보드 {n_board}=5 OK')


if __name__ == '__main__':
    main()
