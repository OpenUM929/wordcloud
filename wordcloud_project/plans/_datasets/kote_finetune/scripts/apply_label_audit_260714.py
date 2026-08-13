# -*- coding: utf-8 -*-
"""L1 라벨 일관성 감사(0708_02) 정정 적용 — 사용자 실행 지시(260714 "2항 실시하자").

입력: eval/review/label_audit_prefill_260708.jsonl 의 proposal=='change' 행(중복 file:line 제거).
  - TRAIN 정정: file:line(1-index)로 행 특정 → text 교차확인(불일치 시 text 검색 폴백) →
    human_decision=claude_judgment, prev는 label_rev에 보존. 이미 같은 값이면 skip(13_03 선정정분).
  - TEST 정정: kind=test_slice → (slice, text, field) 매칭. 전부 비긍↔부 방향(게이트 안전).
  - 추가 2행(260714 A/B 실증 정책충돌): c3 '완벽추구' 양가태도 negative→positive
    (사용자 재정 feedback_ambiguous_trait_employer_lens — 명시 해악귀결 없음).
긍↔부 방향 12행은 Claude가 260714 재판정으로 전건 현행 확정규칙 방향과 일치 확인.
안전: 파일별 백업(.bak_la260714) + 감사로그(eval/label_audit_corrections_260714.jsonl).
"""
import io
import json
import os
import shutil
from collections import Counter
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
EVAL = os.path.join(DS, 'eval')
PREFILL = os.path.join(EVAL, 'review', 'label_audit_prefill_260708.jsonl')
AUDIT_OUT = os.path.join(EVAL, 'label_audit_corrections_260714.jsonl')
TODAY = date.today().strftime('%y%m%d')

SLICE_FILES = {'baseline399': 'baseline_eval_260624.jsonl',
               '8c_hard': 'gold_8c_test_260706.jsonl',
               'c3_neu149': 'gold_8c_test_c3neu_260707.jsonl',
               'sa_speech74': 'gold_speechact_test_260707.jsonl'}

# 260714 A/B 실증 정책충돌 2행(c3) — 양가태도(과잉+긍정특질·해악 없음)=긍정(사용자 재정)
EXTRA_TEST = [
    {'slice': 'c3_neu149', 'text_sub': '완벽을 추구하는 성품', 'to': 'positive',
     'reason': '양가태도=기업관점 긍정(사용자 재정 260706) — v2 A/B 부→긍 오탐의 정책충돌 행'},
    {'slice': 'c3_neu149', 'text_sub': '너무 완벽한 업무처리 추구', 'to': 'positive',
     'reason': '양가태도=기업관점 긍정(사용자 재정 260706) — 동일'},
]


def loadl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()]


def writel(p, rows):
    with io.open(p, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def backup(p):
    b = p + '.bak_la260714'
    if not os.path.exists(b):
        shutil.copy2(p, b)


def main():
    prefill = loadl(PREFILL)
    changes = [r for r in prefill if r.get('proposal') == 'change']
    log, stat = [], Counter()

    # ── TRAIN 정정 (file:line 유니크) ───────────────────────────────────────
    by_file = {}
    seen = set()
    for r in changes:
        if r['kind'] == 'test_slice':
            continue
        k = (r.get('file'), r.get('line'))
        if not k[0] or k in seen:
            stat['train_dup'] += 1
            continue
        seen.add(k)
        by_file.setdefault(k[0], []).append(r)

    for fn, rs in sorted(by_file.items()):
        path = os.path.join(EVAL, fn)
        rows = loadl(path)
        backup(path)
        for r in rs:
            idx = r['line'] - 1
            tgt = rows[idx] if 0 <= idx < len(rows) else None
            if tgt is None or (tgt.get('text') or '').strip() != r['text'].strip():
                cand = [x for x in rows if (x.get('text') or '').strip() == r['text'].strip()]
                if len(cand) != 1:
                    stat['train_nomatch'] += 1
                    log.append({'action': 'NOMATCH', **{k: r.get(k) for k in ('file', 'line', 'text', 'gold', 'claude_judgment')}})
                    continue
                tgt = cand[0]
            new = r['claude_judgment']
            cur = tgt.get('human_decision')
            if cur == new:
                stat['train_already'] += 1
                log.append({'action': 'ALREADY', 'file': fn, 'text': r['text'], 'label': new})
                continue
            pn = {cur, new} == {'positive', 'negative'}
            tgt.setdefault('label_rev', []).append(
                {'from': cur, 'to': new, 'by': 'L1_audit_260708+claude_reverify_260714',
                 'at': TODAY, 'reason': r.get('claude_reason'), 'pn': pn})
            tgt['human_decision'] = new
            stat['train_fixed'] += 1
            stat['train_fixed_pn'] += int(pn)
            log.append({'action': 'FIX', 'file': fn, 'text': r['text'], 'from': cur, 'to': new, 'pn': pn})
        writel(path, rows)

    # ── TEST 정정 ((slice,text,field) 매칭 + EXTRA 2행) ─────────────────────
    test_changes = [r for r in changes if r['kind'] == 'test_slice']
    by_slice = {}
    for r in test_changes:
        by_slice.setdefault(r['slice'], []).append(
            {'text': r['text'].strip(), 'field': (r.get('field') or '').strip(),
             'to': r['claude_judgment'], 'reason': r.get('claude_reason')})
    for e in EXTRA_TEST:
        by_slice.setdefault(e['slice'], []).append(e)

    for sl, rs in sorted(by_slice.items()):
        path = os.path.join(EVAL, SLICE_FILES[sl])
        rows = loadl(path)
        backup(path)
        for r in rs:
            if 'text_sub' in r:
                cand = [x for x in rows if r['text_sub'] in (x.get('text') or '')]
            else:
                cand = [x for x in rows if (x.get('text') or '').strip() == r['text']
                        and (x.get('field') or '').strip() == r['field']]
            if len(cand) != 1:
                stat['test_nomatch'] += 1
                log.append({'action': 'NOMATCH', 'slice': sl, **r})
                continue
            tgt = cand[0]
            cur = tgt.get('human_decision')
            if cur == r['to']:
                stat['test_already'] += 1
                continue
            pn = {cur, r['to']} == {'positive', 'negative'}
            tgt.setdefault('label_rev', []).append(
                {'from': cur, 'to': r['to'], 'by': 'L1_audit+claude_260714', 'at': TODAY,
                 'reason': r.get('reason'), 'pn': pn})
            tgt['human_decision'] = r['to']
            stat['test_fixed'] += 1
            stat['test_fixed_pn'] += int(pn)
            log.append({'action': 'FIX', 'slice': sl, 'text': tgt['text'], 'from': cur, 'to': r['to'], 'pn': pn})
        writel(path, rows)

    writel(AUDIT_OUT, log)
    print('결과:', dict(stat))
    print(f'감사로그 {len(log)}행 → {os.path.relpath(AUDIT_OUT, DS)}')
    # 자기검산: TEST 정정에 긍↔부는 EXTRA 2행(정책충돌 실증)만 허용
    assert stat.get('test_fixed_pn', 0) <= 2, 'TEST 긍↔부 정정이 예정(2) 초과'


if __name__ == '__main__':
    main()
