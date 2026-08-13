# -*- coding: utf-8 -*-
"""13_03 Track1(개정) 3-1→3-2 — 승격후보 불일치를 3자(모델·규칙·hd) 대조로 트리아지.

각 불일치행에 대해 model / rule(_sentence_sentiment_override_explain) / hd 를 구해 버킷팅:
  GOLD    : rule_label==hd != model  AND rule_id ∈ 고정밀 문서규칙  → 모델오류를 규칙이 확증 = 안전·고가치 gold
  DISCARD : rule_label==model != hd                               → hd가 노이즈(규칙·모델 합의) = 승격 제외
  ESCALATE: 그 외(긍↔부·rule4_default 무판정·규칙이 hd/model 어느쪽도 확증 못함) → 사용자 그룹검토

출력: gold_candidates(GOLD) + escalation(ESCALATE, 보드 스키마) + 자기검산(버킷 합=총계).
"""
import io
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
WP = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '..'))
sys.path.insert(0, WP)
DS = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '_datasets', 'kote_finetune'))
CAND = os.path.join(DS, 'eval', 'stranded_candidates_260713.jsonl')

# 자동 GOLD 허용 = **중립방향 규칙만**(긍↔부 생성 불가·트랩 무해). 극성뒤집기 규칙
#   (positive_rescue·improvement_request_neg·excess·negation_praise)은 트랩 상습(집요함·했으면·
#   개인안녕 오발동)이라 자동 gold 금지 → escalation. hd==neutral 이고 모델이 극성 오판한 것만 채택.
NEUTRAL_RULES = {
    'health_advice_neutral', 'personal_wellbeing_neutral', 'no_weakness_neutral',
    'no_response_neutral', 'garbage_line_neutral',
}


def score_to_label(s):
    return 'positive' if s > 1e-6 else ('negative' if s < -1e-6 else 'neutral')


def main():
    cand = [json.loads(l) for l in io.open(CAND, encoding='utf-8') if l.strip()]
    from src.modules.hr_sentiment import predict_sentiments
    from src.modules.sentence_emotion import compute_sentence_raw_scores
    from src.services.perspective_service import _sentence_sentiment_override_explain as ov

    model = predict_sentiments([c['text'] for c in cand], fields=[c['field'] for c in cand])

    gold, escalate, discard = [], [], []
    bucket = Counter()
    rule_conf = Counter()   # GOLD 규칙별
    for c, m in zip(cand, model):
        hd = c['human_decision']
        if hd == m:
            continue  # 일치분(85.6%)은 트리아지 불요 — 모델이 이미 앎
        cache = compute_sentence_raw_scores(c['text'])
        if cache:
            e = cache[0]; pos, neg, neu = e['pos'], e['neg'], e['neutral']
        else:
            pos = neg = neu = 0.0
        s, rid = ov(pos, neg, c['text'], True, 1, neutral=neu)
        rl = score_to_label(s)
        row = {**c, 'model': m, 'rule_label': rl, 'rule_id': rid}
        # 자동 GOLD: 중립방향 규칙이 hd=중립을 확증 + 모델이 극성 오판 → 안전(긍↔부 불생성)
        if hd == 'neutral' and rl == 'neutral' and m in ('positive', 'negative') and rid in NEUTRAL_RULES:
            bucket['GOLD'] += 1
            rule_conf[rid] += 1
            gold.append(row)
        elif rl == m and rl != hd:
            bucket['DISCARD'] += 1              # 규칙+모델 합의로 hd 기각 = 노이즈
            discard.append(row)
        else:
            bucket['ESCALATE'] += 1            # 극성뒤집기·규칙무판정·3자상충 → 사용자 확정
            escalate.append(row)

    n_dis = sum(bucket.values())
    print(f'불일치 {n_dis}행 트리아지: {dict(bucket)}')
    print(f'  GOLD 규칙별: {dict(rule_conf)}')
    # GOLD 클래스 분포
    print(f'  GOLD 클래스: {dict(Counter(g["human_decision"] for g in gold))}')
    print(f'  ESCALATE 혼동(hd→model): {dict(Counter((e["human_decision"], e["model"]) for e in escalate))}')

    # 저장
    gp = os.path.join(HERE, 'gold_candidates_260713.jsonl')
    ep = os.path.join(HERE, 'escalation_260713.jsonl')
    for path, rows in ((gp, gold), (ep, escalate)):
        with io.open(path, 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    # 자기검산
    assert bucket['GOLD'] + bucket['DISCARD'] + bucket['ESCALATE'] == n_dis, '버킷 합≠총계'
    assert all(g['rule_label'] == g['human_decision'] for g in gold), 'GOLD 규칙≠hd'
    assert all(g['human_decision'] != g['model'] for g in gold), 'GOLD가 모델과 동일(무가치)'
    print(f'── 자기검산 ── 버킷합={n_dis} OK · GOLD 전부 규칙확증&모델오류 OK')
    print(f'저장: gold_candidates_260713.jsonl({len(gold)}) · escalation_260713.jsonl({len(escalate)})')


if __name__ == '__main__':
    main()
