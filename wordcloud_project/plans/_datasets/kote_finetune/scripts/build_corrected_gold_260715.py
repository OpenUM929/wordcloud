# -*- coding: utf-8 -*-
"""260715 교정 gold 통합 — 사용자 판정/동의 + A~D 패턴 + 새 규칙 정제분을 재학습 gold로.

사용자 지시 반영:
  · 게시판 미표시=동의(user_agreed) + 명시판정(human) 전부 확정 gold로 수용.
  · 내 의견(memo/tags) 플래그 = 보류(재검토). 필드의존("필드에 따라 결과 결정") = 학습 제외
    (단일라벨 불가, 입력에 정답 없음 — 넣으면 노이즈). field-contrast는 별도 트랙.
  · A~D 하드코딩 패턴 gold(자동분) 포함. D_trait_pos 단점(부→긍 위험)은 검토파일이라 제외.
출력: eval/gold_corrected_260715.jsonl (train 스키마). 학습제외: eval/exclude_field_dependent_260715.jsonl.
가드: 테스트 누수 0 · (text,field) dedup · 기존 TRAIN 라벨충돌 스킵 · not_group/skip 제외.
"""
import io
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
WP = os.path.abspath(os.path.join(DS, '..', '..', '..'))
REVIEW = os.path.join(DS, 'eval', 'review')
sys.path.insert(0, WP)
sys.path.insert(0, HERE)

OUT = os.path.join(DS, 'eval', 'gold_corrected_260715.jsonl')
EXCL_OUT = os.path.join(DS, 'eval', 'exclude_field_dependent_260715.jsonl')
QUEUES = ['label_audit_escalation_260715.jsonl', 'hard_labeling_260715.jsonl']
PATTERN = os.path.join(DS, 'eval', 'gold_pattern_260715.jsonl')
LAB = {'positive', 'negative', 'neutral'}
FIELD_DEP_MARK = ('필드에 따라', '긍정/부정 필드', '이중성', '필드의존')


def loadl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()] if os.path.exists(p) else []


def is_field_dep(r):
    m = (r.get('memo') or '')
    tags = r.get('memo_tags') or []
    return any(k in m for k in FIELD_DEP_MARK) or '필드의존' in tags


def main():
    from finetune_sentiment import TRAIN_FILES, TEST_SETS, load as fload
    test_texts, train_lab = set(), {}
    for fn in TEST_SETS.values():
        for t, l, f in fload(fn):
            test_texts.add(t)
    for fn in TRAIN_FILES:
        for t, l, f in fload(fn):
            train_lab.setdefault(t, l)
    LAB2ID = {'positive': 0, 'negative': 1, 'neutral': 2}

    rows, excl, stat, seen = [], [], Counter(), set()

    def add(text, field, label, src):
        t = (text or '').strip()
        if label not in LAB:
            stat['skip_notlab'] += 1
            return
        k = (t, field or '')
        if k in seen:
            stat['dup'] += 1
            return
        seen.add(k)
        if t in test_texts:
            stat['leak'] += 1
            return
        old = train_lab.get(t)
        if old is not None and old != LAB2ID[label]:
            stat['conflict'] += 1
            return
        rows.append({'text': t, 'field': field or '', 'human_decision': label,
                     'decision_source': src})
        stat[f'add_{src}'] += 1
        stat[f'lab_{label}'] += 1

    # 1) 게시판 사용자 판정/동의 + 필드의존 제외
    for q in QUEUES:
        for r in loadl(os.path.join(REVIEW, q)):
            if is_field_dep(r):
                excl.append({'text': r['text'], 'field': r.get('field', ''),
                             'reason': 'field_dependent', 'memo': r.get('memo')})
                stat['excl_fielddep'] += 1
                continue
            hd = r.get('human_decision')
            if hd in LAB:
                add(r['text'], r.get('field'), hd, r.get('decision_source') or 'human')

    # 2) 새 규칙이 자동해소(중립/필드극성)한 silver — 사장님이 원한 '재정제' 결과(health/wellbeing/
    #    no_weakness/mixed/meta/bare_np). rule_silver 티어로 수용(중립 클래스 보강).
    for q in QUEUES:
        sp = os.path.join(REVIEW, q.replace('.jsonl', '.silver_260715.jsonl'))
        for r in loadl(sp):
            cj = r.get('claude_judgment')
            lab = cj.get('polarity') if isinstance(cj, dict) else (cj or r.get('suggested'))
            add(r['text'], r.get('field'), lab, 'rule_silver')

    # 3) A~D 패턴 자동 gold
    for r in loadl(PATTERN):
        add(r['text'], r.get('field'), r['human_decision'], 'pattern_' + r.get('pattern', 'AD'))

    with io.open(OUT, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    with io.open(EXCL_OUT, 'w', encoding='utf-8') as f:
        for r in excl:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f'교정 gold: {len(rows)}행 → eval/{os.path.basename(OUT)}')
    print(f'  라벨: 긍{stat["lab_positive"]}/부{stat["lab_negative"]}/중{stat["lab_neutral"]}')
    print(f'  출처: {dict((k, v) for k, v in stat.items() if k.startswith("add_"))}')
    print(f'  학습제외(필드의존): {len(excl)} → eval/{os.path.basename(EXCL_OUT)}')
    print(f'  가드 스킵: 누수{stat["leak"]}·중복{stat["dup"]}·라벨충돌{stat["conflict"]}')


if __name__ == '__main__':
    main()
