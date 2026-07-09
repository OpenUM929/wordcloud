# -*- coding: utf-8 -*-
"""gold 재감사 정정 적용 — 개선요청 화행 경계행 개별 재판정 결과 반영.

재감사(gold_audit_260630.md): 긍↔부 오염 0. 정정 대상은 **중립 경계만**(neutral↔극성, 허용 방향).
개별 재판정 결과 = '발전지향·연성제안·칭찬우세' 개선요청을 negative/positive → **neutral**로 정정.
명시적 결여·과잉·요구(...없/않/부족/과도/너무/해야, 기본자질 결여 지적)는 negative 유지(사용자 원의도).

provenance: 원 행 백업(emotion.jsonl.bak_<date>) + 정정행에 prev_gold/rev/label_source=human+ai_audit.
정정 감사기록 eval/gold_corrections_260630.jsonl. 긍↔부 0 불변(중립 방향만).
"""
import json
import os
import shutil
import sys
from datetime import date

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
STREAM = os.path.join(DATASET_DIR, 'emotion', 'emotion.jsonl')
SUSPECTS = os.path.join(DATASET_DIR, 'eval', 'gold_audit_suspects_260630.jsonl')
CORR = os.path.join(DATASET_DIR, 'eval', 'gold_corrections_260630.jsonl')

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 개별 재판정 → neutral 정정 대상(고유 부분문자열). 나머지 의심행은 현 라벨 유지.
TO_NEUTRAL = [
    '의사소통이 뛰어나나 개선필요',            # 칭찬+경미 요청(혼합)
    '의견수렴해주세요',                       # 환경 요청(해주세요)
    '노하우를 후배들에게 공유 필요',            # 경험 칭찬+공유 제안
    '계속적인 직무학습이 바람직함',            # 발전지향 권고
    '사내교육을 적극 수강하면 좋을듯함',        # 약점부재+연성제안
    '버리기 등으로 경감 필요',                # 칭찬우세+업무경감 제안(3변형 공통)
    '의사전달을 해도 괜찮을 것 같음',          # 연성 선택제안(해도 괜찮)
    '적극성을 띌수있도록 하여야한다',          # 부하 육성 지향
    '본부의 중추로 성장할 것',                # 발전 잠재력(격려)
    '마음을 조금 더 내길',                    # 연성 바람
    '성과가 더욱 빛남',                       # 긍정 프레이밍 건설제언
    '의사표시를 할 수 있었으면 좋겠음',        # 희망형 연성
    '열의를 가져도 좋을 듯 함',               # 연성 선택제안
    '신중하고 차분한 스타일로 적극적인 업무자세 필요',  # 칭찬(신중차분)+요청
    '적극적인 업무참여와 노력',               # 무종결 단편
    '원활히 하시면 좋을것같음',               # 연성 제안(하시면 좋을)
]


def main():
    suspect_ids = set()
    for line in open(SUSPECTS, encoding='utf-8'):
        line = line.strip()
        if line:
            r = json.loads(line)
            suspect_ids.add(r.get('rec_id') or r.get('id'))

    gold = [json.loads(l) for l in open(STREAM, encoding='utf-8') if l.strip()]
    today = date.today().strftime('%Y-%m-%d')
    bak = STREAM + f'.bak_{today.replace("-", "")[2:]}'
    shutil.copyfile(STREAM, bak)

    corrections = []
    for g in gold:
        rid = g.get('id')
        if rid not in suspect_ids:
            continue
        text = g.get('text', '')
        if any(frag in text for frag in TO_NEUTRAL) and g['sentiment_gold'] != 'neutral':
            old = g['sentiment_gold']
            g['sentiment_gold'] = 'neutral'
            g['prev_gold'] = old
            g['rev'] = 2
            g['label_source'] = 'human+ai_audit'
            g['review_status'] = 'confirmed_audited'
            corrections.append({'id': rid, 'text': text, 'old': old, 'new': 'neutral',
                                'reason': '개선요청 경계 개별재판정→중립(발전지향/연성/칭찬우세)'})

    with open(STREAM, 'w', encoding='utf-8') as f:
        for g in gold:
            f.write(json.dumps(g, ensure_ascii=False) + '\n')
    with open(CORR, 'w', encoding='utf-8') as f:
        for c in corrections:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')

    from collections import Counter
    p2n = sum(1 for c in corrections if c['old'] == 'positive')
    n2n = sum(1 for c in corrections if c['old'] == 'negative')
    dist = Counter(g['sentiment_gold'] for g in gold)
    print('=== gold 재감사 정정 적용 ===')
    print(f'백업: {os.path.basename(bak)}')
    print(f'정정(→neutral): {len(corrections)}  (positive→neu {p2n} / negative→neu {n2n})')
    print(f'정정 후 분포: {dict(dist)}  (총 {len(gold)})')
    print(f'감사기록 → {os.path.basename(CORR)}')
    print('※ 모든 정정은 중립 방향(neutral↔극성) — 긍↔부 0 불변.')


if __name__ == '__main__':
    main()
