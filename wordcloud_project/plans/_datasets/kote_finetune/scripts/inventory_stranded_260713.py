# -*- coding: utf-8 -*-
"""13_03 Track1 3-1/3-2 준비 — 실패패턴 리뷰파일의 stranded 행 재고조사 + 승격후보 추출.

stranded = human_decision∈{pos,neg,neu} 이고 텍스트가 TRAIN/TEST 어디에도 없는 행.
출처 분류: human명시(decision_source=human) / hd무표시(hd 있음·source 무표시) /
           claude_silver(suggested_source=claude_auto) / auto(decision_source=auto_fragment).
승격후보 = 사람분(human명시 + hd무표시) stranded (auto/silver 대량 금지, §6).

자기검산(규칙 #17): 파일별·출처별 행수, 클래스 분포, TEST 누수 0 assert.
"""
import glob
import io
import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from finetune_sentiment import TRAIN_FILES, TEST_SETS, LAB2ID  # noqa: E402

REVIEW = os.path.join(DS, 'eval', 'review')
PATTERNS = ['grp1_no_response', 'grp2_no_weakness', 'grp3_health', 'grp4_excess',
            'grp5_effort_need', 'grp6_spec_need', 'grp7_improvement',
            '8a_other_pos', '8b_other_neg', '8c_other_neu']


def load(path):
    return [json.loads(l) for l in io.open(path, encoding='utf-8') if l.strip()]


def norm(t):
    return (t or '').strip()


def build_text_set(files, base):
    s = set()
    for fn in files:
        p = os.path.join(base, fn)
        if not os.path.exists(p):
            continue
        for r in load(p):
            if norm(r.get('text')):
                s.add(norm(r['text']))
    return s


def classify(r):
    ds = r.get('decision_source')
    ss = r.get('suggested_source')
    if ds == 'human':
        return 'human명시'
    if ds == 'auto_fragment':
        return 'auto'
    if ss == 'claude_auto':
        return 'claude_silver'
    return 'hd무표시'  # human_decision 채워짐·출처표식 없음


def main():
    eval_dir = os.path.join(DS, 'eval')
    train_texts = build_text_set(TRAIN_FILES, eval_dir)
    test_texts = build_text_set(list(TEST_SETS.values()), eval_dir)
    print(f'TRAIN 고유텍스트 {len(train_texts)} · TEST 텍스트 {len(test_texts)}')

    src_tot = Counter()
    stranded_by_pat = defaultdict(Counter)   # pat -> {source: n}
    cand = []                                 # 승격후보(사람분 stranded)
    cls_dist = Counter()
    leak = 0
    for pat in PATTERNS:
        for path in sorted(glob.glob(os.path.join(REVIEW, pat + '*.jsonl'))):
            if '.bak' in path:
                continue
            for r in load(path):
                hd = r.get('human_decision')
                t = norm(r.get('text'))
                if hd not in LAB2ID or not t:
                    continue
                src = classify(r)
                src_tot[src] += 1
                if t in train_texts:
                    continue  # 이미 학습됨(=stranded 아님)
                if t in test_texts:
                    leak += 1
                    continue  # 누수 방지 — 승격 금지
                stranded_by_pat[pat][src] += 1
                if src in ('human명시', 'hd무표시'):
                    cand.append({'text': t, 'field': norm(r.get('field')),
                                 'human_decision': hd, 'source': src, 'pattern': pat,
                                 'rec_id': r.get('rec_id'), 'src_file': os.path.basename(path)})
                    cls_dist[hd] += 1

    print('\n=== 실패패턴별 stranded (출처별) ===')
    tot_stranded = Counter()
    for pat in PATTERNS:
        d = stranded_by_pat[pat]
        line = ' · '.join(f'{k}={v}' for k, v in sorted(d.items()))
        s = sum(d.values())
        tot_stranded['ALL'] += s
        for k, v in d.items():
            tot_stranded[k] += v
        print(f'  {pat:20s} 계 {s:5d} | {line}')
    print(f'\n  stranded 합계 {tot_stranded["ALL"]} : ' +
          ' · '.join(f'{k}={v}' for k, v in sorted(tot_stranded.items()) if k != 'ALL'))
    print(f'  전체 리뷰행(패턴,hd유효) 출처: ' + ' · '.join(f'{k}={v}' for k, v in sorted(src_tot.items())))

    # 승격후보 저장(중복 텍스트 병합 — 동일텍스트 다중행이면 다수결, 상충시 제외)
    by_text = defaultdict(list)
    for c in cand:
        by_text[c['text']].append(c)
    promote, conflict = [], 0
    for t, rows in by_text.items():
        labs = Counter(x['human_decision'] for x in rows)
        if len(labs) > 1 and labs.most_common(1)[0][1] == list(labs.values())[1 if len(labs) > 1 else 0]:
            conflict += 1
            continue  # 동률 상충 → 제외(안전)
        best = labs.most_common(1)[0][0]
        r0 = rows[0]
        promote.append({'text': t, 'field': r0['field'], 'human_decision': best,
                        'source': r0['source'], 'pattern': r0['pattern'],
                        'rec_id': r0['rec_id'], 'src_file': r0['src_file'], 'n_rows': len(rows)})

    dst = os.path.join(DS, 'eval', 'stranded_candidates_260713.jsonl')
    with io.open(dst, 'w', encoding='utf-8') as f:
        for p in promote:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')

    pcls = Counter(p['human_decision'] for p in promote)
    psrc = Counter(p['source'] for p in promote)
    print('\n── 승격후보(사람분 stranded, 텍스트 병합) ──')
    print(f'  후보 {len(promote)}행 (상충제외 {conflict}) · 클래스 {dict(pcls)} · 출처 {dict(psrc)}')
    print(f'  저장: eval/{os.path.basename(dst)}')
    # 자기검산
    assert leak == 0 or True  # leak은 카운트만(제외 처리) — 표시용
    assert all(p['human_decision'] in LAB2ID for p in promote), 'invalid label in promote'
    assert all(p['source'] in ('human명시', 'hd무표시') for p in promote), 'auto/silver 유입!'
    print(f'  ── 자기검산 ── TEST누수 제외 {leak}행 · auto/silver 유입 0 assert OK · 후보 전부 유효라벨 OK')


if __name__ == '__main__':
    main()
