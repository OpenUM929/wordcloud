# -*- coding: utf-8 -*-
"""0702 — 경계 검토큐 L2(조사·어미·철자 변이) 유사중복 제거.

L1(공백·기호) dedup 후에도 "보완 필요점은 없음 / 보완필요점이 없음 / 특별한 보완 필요점 없음"
처럼 조사·띄어쓰기·철자만 다른 유사중복이 계열당 수십 개 남아 검토 반복을 유발.
→ 순수 조사·어미·기능토큰 + 공백을 제거한 L2 키로 전역 dedup(3파일 통합, 파일간 반복도 제거).
부정(없/않/못)·내용어는 보존 → 뜻이 다른 문장(특히 긍↔부)은 안 뭉침(사전검사 0건 확인).

- 대표행: 판정된 행 우선. 사람판정 보존.
- 판정 충돌 군집(같은 L2키에 서로 다른 판정): human_decision=null 로 재검토 전환.
- 각 대표는 원래 파일(포켓)에 유지.
"""
import json
import os
import re
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL = os.path.abspath(os.path.join(HERE, '..', 'eval'))
FILES = ['polysemy_review_260702.jsonl', 'polflip_review_260702.jsonl',
         'neutral_boundary_review_260702.jsonl']
JOSA = ['을', '를', '이', '가', '은', '는', '에서', '에게', '에', '의', '와', '과', '도',
        '으로', '로', '및', '좀', '더', '수', '하는', '위한', '위해', '하게', '하고',
        '하여', '스러운', '스럽', '들', '것', '점', '한', '인', '적']
DEC = ('positive', 'negative', 'neutral', 'not_group', 'skip')
_WS = re.compile(r'[\s\W_]+')


def L2(t):
    s = _WS.sub('', t or '')
    for j in sorted(JOSA, key=len, reverse=True):
        s = s.replace(j, '')
    return s


def main():
    # 파일별 행 로드(원 파일 태그 유지)
    rows = []
    for fn in FILES:
        for l in open(os.path.join(EVAL, fn), encoding='utf-8'):
            l = l.strip()
            if not l:
                continue
            r = json.loads(l)
            r['_file'] = fn
            rows.append(r)
    total_in = len(rows)
    # L2 군집
    grp = collections.defaultdict(list)
    for r in rows:
        grp[L2(r['text'])].append(r)
    out = collections.defaultdict(list)
    conflict = 0
    propagated = 0
    for key, g in grp.items():
        decs = set(r['human_decision'] for r in g if r.get('human_decision') in DEC)
        rep = next((r for r in g if r.get('human_decision') in DEC), g[0])
        rep = dict(rep)
        if len(decs) > 1:                    # 판정 충돌 → 재검토
            rep['human_decision'] = None
            conflict += 1
        elif decs:
            d = next(iter(decs))
            if rep.get('human_decision') != d:
                propagated += 1
            rep['human_decision'] = d
        fn = rep.pop('_file')
        out[fn].append(rep)
    print('입력 %d행 → L2 고유 %d행 (제거 %d)' % (total_in, len(grp), total_in - len(grp)))
    print('판정 충돌 재검토전환 %d군집 | 동일뜻 판정 이관 %d행' % (conflict, propagated))
    for fn in FILES:
        with open(os.path.join(EVAL, fn), 'w', encoding='utf-8') as f:
            for r in out[fn]:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        j = sum(1 for r in out[fn] if r.get('human_decision') in DEC)
        print('  %-34s %6d행 (판정 %d)' % (fn, len(out[fn]), j))


if __name__ == '__main__':
    main()
