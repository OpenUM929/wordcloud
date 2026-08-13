# -*- coding: utf-8 -*-
"""group-review 사용자 확정분 → 원본 TRAIN/TEST 역반영 (사용자가 게시판 판정 완료 후 실행).

입력: review/label_audit_escalation_260715.jsonl 중 human_decision 있고 decision_source=='human'.
각 행의 _audit{file,line,orig}로 원본 파일 행을 찾아 human_decision 을 사용자 확정값으로 교체
  (positive/negative/neutral만 반영. not_group/skip 은 학습 제외 표식 → not_group으로 기록).
prev는 label_rev 에 보존(append). ★긍↔부 방향 전환은 별도 카운트·로그(핵심가치 감시).

안전: 파일별 백업(.bak_gr260715) · text 교차확인(불일치 시 skip+로그) · 감사로그.
DRY-RUN 기본. 실제 반영은 --apply. (미리보기로 무엇이 바뀌는지 먼저 확인)
"""
import argparse
import io
import json
import os
import shutil
from collections import Counter
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
EVAL = os.path.join(DS, 'eval')
QUEUE = os.path.join(EVAL, 'review', 'label_audit_escalation_260715.jsonl')
AUDIT_OUT = os.path.join(EVAL, 'group_review_propagation_260715.jsonl')
TODAY = date.today().strftime('%y%m%d')
VALID = {'positive', 'negative', 'neutral', 'not_group'}


def loadl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()] if os.path.exists(p) else []


def writel(p, rows):
    with io.open(p, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='실제 반영(미지정 시 DRY-RUN)')
    a = ap.parse_args()

    q = [r for r in loadl(QUEUE)
         if r.get('human_decision') in VALID and r.get('decision_source') == 'human']
    print(f'사용자 확정분: {len(q)}건' + ('' if q else ' — 게시판 판정 후 다시 실행하세요.'))
    if not q:
        return

    by_file, log, stat = {}, [], Counter()
    for r in q:
        au = r.get('_audit') or {}
        fn = au.get('file')
        if not fn:
            stat['no_audit'] += 1
            continue
        by_file.setdefault(fn, []).append(r)

    for fn, rs in sorted(by_file.items()):
        path = os.path.join(EVAL, fn)
        if not os.path.exists(path):
            stat['file_missing'] += 1
            log.append({'action': 'FILE_MISSING', 'file': fn})
            continue
        rows = loadl(path)
        if a.apply:
            b = path + '.bak_gr260715'
            if not os.path.exists(b):
                shutil.copy2(path, b)
        for r in rs:
            au = r['_audit']
            idx = (au.get('line') or 0) - 1
            tgt = rows[idx] if 0 <= idx < len(rows) else None
            if tgt is None or (tgt.get('text') or '').strip() != (r.get('text') or '').strip():
                cand = [x for x in rows if (x.get('text') or '').strip() == (r.get('text') or '').strip()]
                if len(cand) != 1:
                    stat['nomatch'] += 1
                    log.append({'action': 'NOMATCH', 'file': fn, 'text': r.get('text')})
                    continue
                tgt = cand[0]
            new = r['human_decision']
            cur = tgt.get('human_decision')
            if cur == new:
                stat['already'] += 1
                continue
            pn = {cur, new} == {'positive', 'negative'}
            if a.apply:
                tgt.setdefault('label_rev', []).append(
                    {'from': cur, 'to': new, 'by': 'group_review_260715', 'at': TODAY, 'pn': pn})
                tgt['human_decision'] = new
            stat['fixed'] += 1
            stat['fixed_pn'] += int(pn)
            log.append({'action': 'FIX' if a.apply else 'WOULD_FIX', 'file': fn,
                        'text': r.get('text'), 'from': cur, 'to': new, 'pn': pn})
        if a.apply:
            writel(path, rows)

    writel(AUDIT_OUT, log)
    mode = '반영완료' if a.apply else 'DRY-RUN(미반영)'
    print(f'[{mode}] {dict(stat)}')
    print(f'  ★긍↔부 방향전환: {stat.get("fixed_pn", 0)}건 (핵심가치 — 반드시 사용자 확정분만)')
    print(f'감사로그 → {os.path.relpath(AUDIT_OUT, DS)}')
    if not a.apply and stat.get('fixed'):
        print('\n미리보기 확인 후 실제 반영: python propagate_group_review_260715.py --apply')


if __name__ == '__main__':
    main()
