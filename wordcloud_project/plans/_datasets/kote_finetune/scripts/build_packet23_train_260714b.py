# -*- coding: utf-8 -*-
"""packet23 TRAIN v2 — v1 A/B FAIL(전슬라이스 하락·c3 긍↔부4) 원인 반영 재구성.

v1 진단(회귀 diff 실측):
  ① G2에 무결점(noweak_neutral)·무응답 경로 포함 → 강긍정 동반 무결점(gold=긍정)과
     "무슨 일 하는지 모르겠음"(비판, gold=부정)까지 중립으로 오학습.
  ② 중립 1,704 + 부정 1,000이 긍정 238 압도 → 중립 과예측(장점 명사구까지 중립화).
  ③ 일부 "회귀"는 테스트 gold의 정책 세대 불일치(건강조언: baseline=부정(6/24) vs
     현행 확정 정책=중립(7/2)) — 데이터가 아닌 테스트 정합 문제로 별도 트랙.

v2 구성:
  G1 positive 전량(238) — 진짜 긍↔부 교정(v1과 동일).
  G2 neutral  = 건강/개인안녕 경로만(무결점·무응답 제외) + dup_n 내림차순 cap 500.
  G3w negative = 요청형 평형추 cap 300 (v1 1000 → 압도 방지).
출력: eval/gold_packet23_train_260714b.jsonl (v1 파일은 append-only 보존, TRAIN 스왑만)
"""
import io
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
WP = os.path.abspath(os.path.join(DS, '..', '..', '..'))
sys.path.insert(0, WP)
sys.path.insert(0, HERE)
from finetune_sentiment import TRAIN_FILES, TEST_SETS, load as fload, LAB2ID  # noqa: E402

OUT = os.path.join(DS, 'eval', 'gold_packet23_train_260714b.jsonl')
REQ_SURFACE = re.compile(r'(주시면|주었으면|했으면|바랍|바람|좋겠)')
G2_CAP, G3_CAP = 500, 300


def loadl(name):
    return [json.loads(l) for l in io.open(os.path.join(DS, 'eval', name), encoding='utf-8') if l.strip()]


def main():
    from src.services.perspective_service import is_health_advice, is_personal_wellbeing_neutral

    g1 = loadl('gold_packet23_G1_positive_260714.jsonl')
    g2 = loadl('gold_packet23_G2_neutral_260714.jsonl')
    g3 = loadl('gold_packet23_G3_negative_260714.jsonl')

    # G2: 건강/개인안녕만(무결점·무응답 제외) — 13_03에서 검증된 안전 이음새
    g2h = [r for r in g2 if is_health_advice(r['text']) or is_personal_wellbeing_neutral(r['text'])]
    g2h = sorted(g2h, key=lambda r: -r.get('dup_n', 1))[:G2_CAP]
    g3w = sorted((r for r in g3 if REQ_SURFACE.search(r['text'])),
                 key=lambda r: -r.get('dup_n', 1))[:G3_CAP]

    train_lab = {}
    for fn in TRAIN_FILES:
        if fn.startswith('gold_packet23_train'):
            continue
        for t, l, f in fload(fn):
            train_lab.setdefault(t, l)
    test_texts = set()
    for fn in TEST_SETS.values():
        for r in loadl(fn):
            if (r.get('text') or '').strip():
                test_texts.add(r['text'].strip())

    rows, stat, seen = [], Counter(), set()
    for src, arr in (('G1', g1), ('G2h', g2h), ('G3w', g3w)):
        for r in arr:
            t = r['text'].strip()
            k = (t, r.get('field') or '')
            if k in seen:
                stat['dup_skip'] += 1
                continue
            seen.add(k)
            if t in test_texts:
                stat['leak_skip'] += 1
                continue
            old = train_lab.get(t)
            if old is not None:
                stat['conflict_or_dup_skip' if old != LAB2ID[r['label']] else 'same_dup_skip'] += 1
                continue
            rows.append({'text': t, 'field': r.get('field') or '', 'human_decision': r['label'],
                         'decision_source': 'packet23_judge_260714_v2', 'route': r.get('route'),
                         'dup_n': r.get('dup_n', 1), 'src': src})
            stat[f'add_{src}'] += 1

    with io.open(OUT, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'v2 기록 {len(rows)}행 → {os.path.basename(OUT)}')
    print('클래스:', dict(Counter(r['human_decision'] for r in rows)), '| 스킵:', dict(stat))


if __name__ == '__main__':
    main()
