# -*- coding: utf-8 -*-
"""baseline 평가셋 재구성 — 혼합극성 절 분리 + 중복 제거 + 축소 + ai_reference(3원칙).

사용자 피드백(2026-06-24):
  · 긍/부 혼재 문장은 분리("…임하다보니 / 건강이 걱정"). production split_clauses가 못 잡는
    '다보니·하나'를 데이터셋용 확장 분리기로 보강(production 불변).
  · baseline이 겹치는 내용 대부분 → 정규화 중복 제거 후 축소.
  · ai_reference에 라벨링 3원칙 적용([[feedback_incomplete_fragment_neutral]]):
    요청표지→부정, 무종결 단편→중립, 명확 행위서술→(KoTE 극성).
"""
import argparse
import json
import os
import random
import re
import sys
from collections import Counter

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, HERE)
from src.modules.text_preprocessing import split_clauses  # noqa: E402
import human_label as HL  # noqa: E402 (사람정렬 라벨러: 불일치 학습 규칙)

# 데이터셋용 추가 연결어미(production 미포함, 고정밀만). 앞 2자 용언 어간 가정.
_EXTRA = ['다보니', '다 보니', '다보면', '다 보면']
_HANA_SKIP_NEXT = set('의을를가씩도만은는라이')   # '하나' 뒤가 조사면 수사/명사 → 분리 안 함


def split_ext(text):
    """split_clauses 결과를 추가 연결어미('다보니'·'하나')로 한 번 더 분리(데이터셋 전용)."""
    out = []
    for cl in split_clauses(text):
        cuts = set()
        for mk in _EXTRA:
            s = 0
            while True:
                p = cl.find(mk, s)
                if p == -1:
                    break
                if p >= 2:
                    cuts.add(p + len(mk))
                s = p + len(mk)
        s = 0                                  # '하나'(연결어미) — 뒤가 조사면 제외
        while True:
            p = cl.find('하나', s)
            if p == -1:
                break
            nxt = cl[p + 2:p + 3]
            if p >= 2 and (nxt == '' or nxt == ' ' or nxt not in _HANA_SKIP_NEXT):
                cuts.add(p + 2)
            s = p + 2
        if not cuts:
            out.append(cl)
            continue
        prev = 0
        for b in sorted(c for c in cuts if 0 < c < len(cl)):
            out.append(cl[prev:b].strip())
            prev = b
        out.append(cl[prev:].strip())
    return [p for p in out if len(p) >= 4]


_REQ = re.compile(r'필요|권고|해야|요구|바람|바랍|요망|당부|했으면|하면 좋|개선 필요|보완 필요')
_END = re.compile(r'(함|합니다|음|됨|임|뜀|옴|움|감|짐|킴|다|요|까|네|죠|니다|있음|없음|보임|드림|줌)$')
_POS = re.compile(r'우수|탁월|뛰어|훌륭|적극|성실|책임|원활|친절|모범|열정|꼼꼼|능숙|기여')
_NEG = re.compile(r'부족|미흡|결여|부재|소홀|떨어|어려움|문제|불만|비협조|이기|고압|갈등')


def ai_ref(text):
    """라벨링 3원칙 힌트."""
    if _REQ.search(text):
        return {'polarity': 'negative', 'confidence': 'low', 'reason': '요청표지(필요/권고/해야) → 개선요청'}
    if not _END.search(text.strip()):
        return {'polarity': 'neutral', 'confidence': 'low', 'reason': '무종결 단편 → 필요/행위 미상 → 중립'}
    if _POS.search(text) and not _NEG.search(text):
        return {'polarity': 'positive', 'confidence': 'low', 'reason': '긍정표지 + 종결'}
    if _NEG.search(text):
        return {'polarity': 'negative', 'confidence': 'low', 'reason': '부정표지 + 종결'}
    return {'polarity': 'neutral', 'confidence': 'low', 'reason': '판단 보류'}


def norm(t):
    return re.sub(r'[\s,./·\-]', '', t)


def field_of(rid):
    return '장점' if '_1-' in rid else ('단점' if '_0-' in rid else '?')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp',
                    default=os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl'))
    ap.add_argument('--date', default='260624')
    ap.add_argument('--target', type=int, default=600)
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass

    seen, units = set(), []
    rawn = 0
    for line in open(args.inp, encoding='utf-8'):
        r = json.loads(line)
        if r.get('is_clause'):
            continue
        rawn += 1
        fld = field_of(r.get('id', ''))
        for cl in split_ext(r.get('text') or ''):
            k = norm(cl)
            if len(k) < 3 or k in seen:
                continue
            seen.add(k)
            units.append({'rec_id': r.get('id'), 'text': cl, 'field': fld})

    print(f'문장 {rawn:,} → 절 분리·중복제거 후 고유 단위 {len(units):,}')
    # 층화(필드) 후 축소 표본
    rng = random.Random(17)
    by = {}
    for u in units:
        by.setdefault(u['field'], []).append(u)
    out = []
    for f, lst in by.items():
        rng.shuffle(lst)
        out += lst[:max(1, args.target * len(lst) // len(units))]
    rng.shuffle(out)
    out = out[:args.target]
    # 사람정렬 라벨러로 힌트 — 신뢰 규칙(표지+종결·요청)만 high, 무종결·약점부재는 low(사람 본질)
    RELIABLE = {'종결+긍정표지 → 긍정', '종결+부정표지 → 부정', '요청표지 → 부정(개선요청)'}
    for u in out:
        pol, _c = HL.label(u['text']); rs = HL.reason(u['text'])
        u['ai_reference'] = {'polarity': pol, 'confidence': 'high' if rs in RELIABLE else 'low', 'reason': rs}
        u['human_decision'] = None

    path = os.path.join(DATASET_DIR, 'eval', f'baseline_eval_{args.date}.jsonl')
    # 🔴 사람 판정 보존: 기존 파일에 human_decision이 있으면 텍스트 키로 이월(재생성이 작업을 지우지 않게).
    prior = {}
    if os.path.isfile(path):
        for line in open(path, encoding='utf-8'):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get('human_decision'):
                prior[norm(r.get('text', ''))] = r['human_decision']
    carried = 0
    for u in out:
        hd = prior.get(norm(u['text']))
        if hd:
            u['human_decision'] = hd
            carried += 1
    if prior:
        print(f'  기존 사람 판정 {len(prior)}건 중 {carried}건 이월(보존)')
    with open(path, 'w', encoding='utf-8') as f:
        for u in out:
            f.write(json.dumps(u, ensure_ascii=False) + '\n')
    dist = Counter(u['ai_reference']['polarity'] for u in out)
    print(f'baseline 재구성 {len(out)}행(목표 {args.target}) → {os.path.relpath(path, PROJECT_ROOT)}')
    print(f'  ai_reference 분포: {dict(dist)} · 필드: {Counter(u["field"] for u in out)}')


if __name__ == '__main__':
    main()
