# -*- coding: utf-8 -*-
"""packet23 TRAIN v3 — v2 FAIL(c3 부→긍 5) 원인 반영: 패턴 내부 대조 학습.

v2 진단: G1 긍정(양가/존경/유지) 238이 반례 없이 들어가 '너무+긍정특질' 표면 전체를
긍정으로 과일반화 → "회사를 너무 편하게 다님"(비꼼)·"전문가 되기"(요청 축약)까지 긍정.
(c3 잔여 2건은 라벨 정책충돌 — 양가=긍정(사용자 재정) vs c3 gold=부정. 사용자 확정 별도.)

v3 = v2 + 같은 표면의 반례(전부 Claude 수동판정 b346, field 포함):
  B6_NEG 36  '너무+특질'인데 명시 해악귀결(지연·간섭·힘듦·호불호) → negative
  B6_NEU 22  '너무+특질'인데 개인안녕 귀결(휴식·체력·워라밸) → neutral
  B4_NEG 12  귀감/가르침 표면인데 전수요청·조건부 → negative
→ 패턴 내부 3파전 대조로 경계(해악=부정/안녕=중립/그외=긍정) 학습.
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
from judge_packet_finalize_260714 import B4_NEG, B4_NEU, B6_NEG, B6_NEU, B6_UNC  # noqa: E402

OUT = os.path.join(DS, 'eval', 'gold_packet23_train_260714c.jsonl')
B346 = os.path.join(DS, 'eval', 'review', 'packet_b346_pool_260714.jsonl')
REQ_SURFACE = re.compile(r'(주시면|주었으면|했으면|바랍|바람|좋겠)')
G2_CAP, G3_CAP = 500, 300


def loadl(name):
    return [json.loads(l) for l in io.open(os.path.join(DS, 'eval', name), encoding='utf-8') if l.strip()]


def main():
    from src.services.perspective_service import is_health_advice, is_personal_wellbeing_neutral

    g1 = loadl('gold_packet23_G1_positive_260714.jsonl')
    g2 = loadl('gold_packet23_G2_neutral_260714.jsonl')
    g3 = loadl('gold_packet23_G3_negative_260714.jsonl')
    b346 = [json.loads(l) for l in io.open(B346, encoding='utf-8')]

    # 패턴 내부 반례(수동판정): B6_NEG/B6_NEU/B4_NEG (+B4_NEU) — B6_UNC 제외
    counters = []
    for r in b346:
        i = r['i']
        if i in B6_UNC:
            continue
        if i in B6_NEG or i in B4_NEG:
            counters.append((r, 'negative'))
        elif i in B6_NEU or i in B4_NEU:
            counters.append((r, 'neutral'))

    g2h = sorted((r for r in g2 if is_health_advice(r['text']) or is_personal_wellbeing_neutral(r['text'])),
                 key=lambda r: -r.get('dup_n', 1))[:G2_CAP]
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

    def add(src, text, field, label, route, dup_n):
        t = text.strip()
        k = (t, field or '')
        if k in seen:
            stat['dup_skip'] += 1
            return
        seen.add(k)
        if t in test_texts:
            stat['leak_skip'] += 1
            return
        old = train_lab.get(t)
        if old is not None:
            stat['conflict_or_dup_skip' if old != LAB2ID[label] else 'same_dup_skip'] += 1
            return
        rows.append({'text': t, 'field': field or '', 'human_decision': label,
                     'decision_source': 'packet23_judge_260714_v3', 'route': route, 'dup_n': dup_n, 'src': src})
        stat[f'add_{src}'] += 1

    for r in g1:
        add('G1', r['text'], r.get('field'), r['label'], r.get('route'), r.get('dup_n', 1))
    for r, lab in counters:
        add('B346ctr', r['text'], r.get('field'), lab, 'b346_counterweight', r.get('dup_n', 1))
    for r in g2h:
        add('G2h', r['text'], r.get('field'), r['label'], r.get('route'), r.get('dup_n', 1))
    for r in g3w:
        add('G3w', r['text'], r.get('field'), r['label'], r.get('route'), r.get('dup_n', 1))

    with io.open(OUT, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'v3 기록 {len(rows)}행 → {os.path.basename(OUT)}')
    print('클래스:', dict(Counter(r['human_decision'] for r in rows)), '| 스킵:', dict(stat))


if __name__ == '__main__':
    main()
