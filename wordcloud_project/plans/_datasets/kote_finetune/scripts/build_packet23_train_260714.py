# -*- coding: utf-8 -*-
"""23년 판정패킷 gold 후보 → TRAIN 파일 빌드 (사용자 지시 260714: 현재 데이터로 파인튜닝 준비).

구성(천장 실증 반영 — 모델이 틀리던 자리만, 합의 대량은 배제):
  G1 positive 전량 : 모델 negative→Claude 전수판정 positive (유지칭찬/존경/양가) = 진짜 교정.
  G2 neutral  전량 : 모델 극성→구조중립(무결점/무응답/건강/안녕) = 진짜 교정(중립방향 안전).
  G3 negative 소량 : 모델도 negative인 합의분이라 교정가치 없음 → 전량 배선 금지.
                     단 G1이 "요청형 표면=긍정"으로 과일반화하지 않게, G1과 표면이 닮은
                     요청형(주시면/했으면/바랍/좋겠)만 dup_n 내림차순 ≤1000 평형추로 포함.
가드: TEST 누수 0 · 기존 TRAIN 라벨충돌 skip(기존 우선·건수 보고) · 파일 내 (text,field) 유일.
출력: eval/gold_packet23_train_260714.jsonl (human_decision 스키마 — load() 호환)
"""
import io
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from finetune_sentiment import TRAIN_FILES, TEST_SETS, load as fload, LAB2ID  # noqa: E402

OUT = os.path.join(DS, 'eval', 'gold_packet23_train_260714.jsonl')
REQ_SURFACE = re.compile(r'(주시면|주었으면|했으면|바랍|바람|좋겠)')
G3_CAP = 1000


def loadl(name):
    p = os.path.join(DS, 'eval', name)
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()]


def main():
    g1 = loadl('gold_packet23_G1_positive_260714.jsonl')
    g2 = loadl('gold_packet23_G2_neutral_260714.jsonl')
    g3 = loadl('gold_packet23_G3_negative_260714.jsonl')

    # G3 평형추: 요청형 표면만, dup_n 내림차순 cap
    g3w = sorted((r for r in g3 if REQ_SURFACE.search(r['text'])),
                 key=lambda r: -r.get('dup_n', 1))[:G3_CAP]

    # 기존 TRAIN 텍스트→라벨(충돌가드) / TEST 텍스트(누수가드)
    train_lab = {}
    for fn in TRAIN_FILES:
        for t, l, f in fload(fn):
            train_lab.setdefault(t, l)
    test_texts = set()
    for fn in TEST_SETS.values():
        for r in loadl(fn):
            if (r.get('text') or '').strip():
                test_texts.add(r['text'].strip())

    rows, stat = [], Counter()
    seen = set()
    for src, arr in (('G1', g1), ('G2', g2), ('G3w', g3w)):
        for r in arr:
            t = r['text'].strip()
            k = (t, r.get('field') or '')
            lab = r['label']
            assert lab in LAB2ID, f'라벨 이상 {lab}'
            if k in seen:
                stat['dup_skip'] += 1
                continue
            seen.add(k)
            if t in test_texts:
                stat['test_leak_skip'] += 1
                continue
            old = train_lab.get(t)
            if old is not None:
                if old != LAB2ID[lab]:
                    stat[f'conflict_skip_{src}'] += 1
                else:
                    stat['same_label_dup_skip'] += 1
                continue
            rows.append({
                'text': t, 'field': r.get('field') or '', 'human_decision': lab,
                'decision_source': 'packet23_judge_260714(claude_b346/struct/req_counterweight)',
                'route': r.get('route'), 'dup_n': r.get('dup_n', 1), 'src': src,
                'note': '23년 판정패킷 judge — G1/G2=모델 오답 교정, G3w=요청형 평형추',
            })
            stat[f'add_{src}'] += 1

    with io.open(OUT, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # 자기검산
    lab_cnt = Counter(r['human_decision'] for r in rows)
    assert stat.get('test_leak_skip', 0) >= 0
    assert all(r['text'] not in test_texts for r in rows), 'TEST 누수'
    print(f'입력: G1 {len(g1)} · G2 {len(g2)} · G3 {len(g3)}(평형추 후보 {len(g3w)})')
    print(f'기록: {len(rows)}행 → {os.path.basename(OUT)}  클래스: {dict(lab_cnt)}')
    print(f'스킵: {dict(stat)}')


if __name__ == '__main__':
    main()
