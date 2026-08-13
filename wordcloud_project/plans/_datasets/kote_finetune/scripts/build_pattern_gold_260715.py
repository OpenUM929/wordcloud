# -*- coding: utf-8 -*-
"""A~D 하드코딩 패턴 → 필드조건부 gold 생성 (사용자 지시 260715, 재학습용 anchor gold).

배경: 1번 '이중성' 케이스 중 재사용 어휘 anchor가 있는 것은 필드조건부 gold로 만들면
  모델이 배울 수 있다(적용불가→적용가능). 규칙엔진은 field 파라미터가 없어 필드조건부 불가 →
  field 보유한 이 생성 레이어에서 패턴 gold를 뽑아 재학습에 넣는다.

패턴(코퍼스 실증, 260715):
  A 업무와 관련없는/무관 → 부정(양 필드 무관, 비업무=결함)
  B 타부서 입장(에서)    → 장점=긍정(협업) / 단점=부정(우리부서 소홀·결여)  [코퍼스 장23/단87]
  C 너무+[긍정특질] + 단점 → 부정(과잉) / 장점 → 긍정(강조)                 [필드조건부]
  D 양가태도(완벽/꼼꼼/철저/신중/소신/원칙/객관/섬세) + 해악표지(과도/지나치/너무/경직/고집)
    → 부정 / 해악표지 없으면 긍정(employer-lens, feedback_ambiguous_trait_employer_lens)
제외(적용불가): 부서외 단독·병행·일회성 표현(신뢰 anchor 없음).

안전: 테스트/기존 gold 텍스트 제외 · (text,field) dedup · 패턴별 cap · 부정의부정 가드 ·
  각 패턴 태그 부착(spot-check용). 출력 eval/gold_pattern_260715.jsonl (human_decision 스키마).
⚠ 이건 후보 생성 — 재학습 전 반드시 표본 검증(오탐 확인). 자동승격 아님.
"""
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
WP = os.path.abspath(os.path.join(DS, '..', '..', '..'))
sys.path.insert(0, WP)
sys.path.insert(0, HERE)

OUT = os.path.join(DS, 'eval', 'gold_pattern_260715.jsonl')
CORPUS = os.path.join(DS, 'emotion', 'weak_export_260624.jsonl')
BF = {'batch_20260622_0': '장점', 'batch_20260623_2': '장점', 'batch_20260624_1': '장점',
      'batch_20260622_2': '단점', 'batch_20260623_1': '단점', 'batch_20260623_3': '단점',
      'batch_20260624_0': '단점'}
CAP = 400  # 패턴×라벨당 상한(빈도 상위)

# ── 패턴 ──────────────────────────────────────────────────────────────
A_OFFTASK = re.compile(r'업무[와과]?\s*(관련\s*없|무관|관계\s*없)')
A_NEG_GUARD = re.compile(r'(관련\s*없는?\s*(일|것)?\s*없|무관하지\s*않)')  # 부정의부정 제외
B_OTHERDEPT = re.compile(r'타\s*부서\s*입장')
C_EXCESS = re.compile(r'너무\s*(적극|열심|세심|꼼꼼|완벽|친절|많|강|열정|활발|나서)')
C_POS_CONSEQ = re.compile(r'(좋|우수|뛰어|훌륭|강점|장점)')  # 장점란서 '너무 좋음' 등 긍정귀결
D_TRAIT = re.compile(r'(완벽|꼼꼼|철저|신중|소신|원칙|객관|섬세|디테일)')
D_HARM = re.compile(r'(과도|과하|과해|과함|지나치|지나칠|너무|심하|경직|고집|답답|융통성\s*없|'
                    r'유연.{0,3}부족|강박|강요|압박|부담|불필요|소홀|놓치|간과|오히려|'
                    r'늦|지연|느림|느려|느리|오래\s*걸)')  # 활용형(과해)·downside(늦/지연/느림) 보강
D_NEG_OTHER = re.compile(r'(부족|미흡|없음|안\s|못\s|떨어|결여|우유부단|소홀)')  # 다른 명시 부정 동반


def classify(text, field):
    """(label, pattern_tag) 또는 (None, None). 우선순위: A>D(해악)>B>C."""
    t = text
    # A: 비업무 → 부정(부정의부정 제외)
    if A_OFFTASK.search(t) and not A_NEG_GUARD.search(t):
        return 'negative', 'A_offtask'
    # D: 양가태도 — 해악표지 있으면 부정, 없으면 긍정(단 다른 명시부정 동반 시 제외=애매)
    if D_TRAIT.search(t):
        if D_HARM.search(t):
            return 'negative', 'D_trait_harm'
        if not D_NEG_OTHER.search(t):
            return 'positive', 'D_trait_pos'
        return None, None  # 양가태도 + 다른부정 → 애매(혼합), 잔여
    # B: 타부서 입장 → 필드극성
    if B_OTHERDEPT.search(t):
        return ('positive' if field == '장점' else 'negative'), f'B_otherdept_{field}'
    # C: 너무+특질 → 필드조건부(장점 긍정·단점 부정), 장점 긍정귀결 확인
    if C_EXCESS.search(t):
        if field == '단점':
            return 'negative', 'C_excess_단점'
        if field == '장점':
            return 'positive', 'C_excess_장점'
    return None, None


def loadl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()] if os.path.exists(p) else []


def main():
    from finetune_sentiment import TRAIN_FILES, TEST_SETS, load as fload
    excl = set()
    for fn in list(TEST_SETS.values()):
        for r in loadl(os.path.join(DS, 'eval', fn)):
            if (r.get('text') or '').strip():
                excl.add(r['text'].strip())
    for fn in TRAIN_FILES:
        for t, l, f in fload(fn):
            excl.add(t)

    cand = {}  # (text,field) -> {label,tag,n}
    seen_stat = Counter()
    n = 0
    for line in io.open(CORPUS, encoding='utf-8'):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get('is_clause'):
            continue
        n += 1
        t = (r.get('text') or '').strip()
        if not (5 <= len(t) <= 120):
            continue
        field = BF.get((r.get('id') or '').rsplit('-', 1)[0])
        if not field or t in excl:
            continue
        lab, tag = classify(t, field)
        if lab is None:
            continue
        k = (t, field)
        if k in cand:
            cand[k]['n'] += 1
        else:
            cand[k] = {'label': lab, 'tag': tag, 'n': 1}
            seen_stat[tag] += 1

    # 패턴×라벨 cap(빈도 상위)
    by_tag = defaultdict(list)
    for (t, f), v in cand.items():
        by_tag[v['tag']].append((t, f, v))
    rows = []
    for tag, arr in by_tag.items():
        arr.sort(key=lambda x: -x[2]['n'])
        for t, f, v in arr[:CAP]:
            rows.append({'text': t, 'field': f, 'human_decision': v['label'],
                         'decision_source': 'pattern_hardcode_260715', 'pattern': v['tag'],
                         'dup_n': v['n']})
    # D_trait_pos(단점란 양가태도→긍정)는 부→긍 위험방향 + case-dependent → 자동 gold 아닌 사용자 검토.
    review = [r for r in rows if r['pattern'] == 'D_trait_pos' and r['field'] == '단점']
    auto = [r for r in rows if not (r['pattern'] == 'D_trait_pos' and r['field'] == '단점')]
    with io.open(OUT, 'w', encoding='utf-8') as f:
        for r in auto:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    REVIEW_OUT = os.path.join(DS, 'eval', 'review', 'pattern_D_traitpos_review_260715.jsonl')
    with io.open(REVIEW_OUT, 'w', encoding='utf-8') as f:
        for r in review:
            # 게시판 스키마(프리필=긍정, 사용자 확인)
            f.write(json.dumps({'rec_id': f"Dtp-{hash(r['text']) & 0xffffff}", 'text': r['text'],
                                'field': r['field'], 'cur_rule_label': 'positive',
                                'claude_judgment': {'polarity': 'positive', 'reason': '양가태도(해악표지 없음)→employer-lens 긍정. 단점란이라 확인요'},
                                'ai_reference': {'polarity': 'positive', 'confidence': 0.5, 'reason': f"D_trait_pos·dup{r['dup_n']}"},
                                'human_decision': None, 'suggested_source': 'claude_auto',
                                'group': 'D_trait_pos_단점', 'note': 'pattern_review_260715',
                                'dup_n': r['dup_n']}, ensure_ascii=False) + '\n')
    rows = auto  # 이후 통계는 auto 기준

    print(f'코퍼스 {n:,}행 스캔 · 유니크 후보 {len(cand)} · 자동 gold {len(auto)} · D_trait_pos단점 검토 {len(review)}')
    print('패턴별 유니크:', dict(seen_stat))
    print('최종 라벨:', dict(Counter(r['human_decision'] for r in rows)))
    print(f'→ eval/{os.path.basename(OUT)}')
    # spot-check 샘플
    print('\n--- 패턴별 표본(오탐 점검) ---')
    shown = defaultdict(int)
    for r in sorted(rows, key=lambda x: -x['dup_n']):
        if shown[r['pattern']] < 3:
            shown[r['pattern']] += 1
            print(f"  [{r['pattern']}] {r['field']}→{r['human_decision'][:3]} ({r['dup_n']}) {r['text'][:46]}")


if __name__ == '__main__':
    main()
