# -*- coding: utf-8 -*-
"""13_03 Track1 — 긍↔부 5건 보드 규칙적용 결과 반영(사용자 확정 260713).

규칙 판정(모두 우리 확립규칙으로 결정 — 진짜 잔여 0):
  1 …모습은 찾아볼 수 없으며   → positive (부정어의 부정=칭찬. 현규칙 '했으면' 트랩으로 부정 오탐)
  2 업무에 너무 빠져있고 전문적 → positive (장점+전문성, 모델 과부정 오판)
  3 업무에 너무 전문적이다      → positive (장점+칭찬, 모델 과부정 오판)
  4 …적기 필요한 조치 요구       → not_group (무서술어·필드의존 [[project_field_signal_for_finetune]])
  5 너무 이성적이고 워커홀릭임   → not_group (무서술어·필드의존)

출력: eval/gold_hardsample_pn_260713.jsonl (positive 3, finetune load 호환) +
      보드 파일 human_decision 채워 갱신(감사기록). not_group 2건은 학습 제외(load가 자동).
자기검산: positive 3·not_group 2 assert · TEST 누수 0 · 기존 라벨충돌 0.
"""
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
BOARD = os.path.join(DS, 'eval', 'review', 'hardsample_pn_review_260713.jsonl')
GOLD = os.path.join(DS, 'eval', 'gold_hardsample_pn_260713.jsonl')
sys.path.insert(0, os.path.join(DS, 'scripts'))
from finetune_sentiment import TEST_SETS, load as fload  # noqa: E402

RESOLVE = {
    'val-batch_20260624_1-68322': ('positive', '부정어의 부정=칭찬. 현규칙 improvement_request_neg가 "했으면" 희망형 트랩으로 오탐. 모델(긍정) 맞음.'),
    'val-batch_20260624_1-45284': ('positive', '장점+업무몰입+전문성=긍정. 모델이 "너무 빠져있고"를 과잉부정 오판.'),
    'val-batch_20260624_1-204115': ('positive', '장점+"너무 전문적"=칭찬. 모델 과잉부정 오판.'),
    'val-batch_20260624_1-56689': ('not_group', '무서술어 단편(요구=명사종결)·필드의존(장점→긍/단점→부) → 단일 gold 금지, 필드 프리픽스가 극성 담당.'),
    'val-batch_20260624_1-400495': ('not_group', '무서술어 단편(워커홀릭임)·필드의존 → not_group, 학습 제외.'),
}


def loadl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()]


def main():
    rows = loadl(BOARD)
    # TEST 텍스트(누수가드)
    test_texts = set()
    for fn in TEST_SETS.values():
        for r in loadl(os.path.join(DS, 'eval', fn)):
            if (r.get('text') or '').strip():
                test_texts.add(r['text'].strip())
    # 기존 TRAIN 텍스트→라벨(충돌가드) — pn gold 신규파일 제외한 현 TRAIN
    from finetune_sentiment import TRAIN_FILES
    train_lab = {}
    for fn in TRAIN_FILES:
        if fn == 'gold_hardsample_pn_260713.jsonl':
            continue
        for t, l, f in fload(fn):
            train_lab[t] = l

    pos_rows, not_group = [], []
    for r in rows:
        rid = r.get('rec_id')
        dec, why = RESOLVE[rid]
        r['human_decision'] = dec
        r['resolution'] = 'rule_decided(user_confirmed_260713)'
        r['resolution_reason'] = why
        if dec == 'positive':
            assert r['text'].strip() not in test_texts, f'TEST 누수 {rid}'
            assert train_lab.get(r['text'].strip()) in (None, 0), f'라벨충돌 {rid}'  # 0=positive
            pos_rows.append(r)
        else:
            not_group.append(r)

    # 보드 갱신(감사기록)
    with io.open(BOARD, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    # positive gold
    with io.open(GOLD, 'w', encoding='utf-8') as f:
        for r in pos_rows:
            f.write(json.dumps({
                'text': r['text'], 'field': r['field'], 'human_decision': 'positive',
                'rec_id': r.get('rec_id'),
                'decision_source': 'human(group-review 260713)+opus',
                'note': '13_03 하드샘플 긍↔부: 모델이 명백 긍정(장점+전문성/부정어의부정)을 부정 오판 → 긍정 gold.',
            }, ensure_ascii=False) + '\n')

    print(f'positive gold: {len(pos_rows)}행 → eval/{os.path.basename(GOLD)}')
    print(f'not_group(학습제외): {len(not_group)}행 (보드에 기록)')
    # 자기검산
    assert len(pos_rows) == 3 and len(not_group) == 2, f'예상 3/2, 실제 {len(pos_rows)}/{len(not_group)}'
    assert all(r['human_decision'] == 'positive' for r in pos_rows)
    print(f'── 자기검산 ── positive 3·not_group 2 OK · TEST누수 0·라벨충돌 0 OK')


if __name__ == '__main__':
    main()
