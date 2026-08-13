# -*- coding: utf-8 -*-
"""대량 코퍼스 정제 → silver_v2 (encoder-large 스테이지A 학습용, 사용자 지시 260714).

소스: weak_export_260623/260624 (165만 행, kote 점수 보유) — field는 배치 매핑으로 복원
  (장점: 0622_0·0623_2·0624_1 / 단점: 0622_2·0623_1·0623_3·0624_0. 파일 단위 필드 반입이라 확정적).

왜 재라벨인가: 스냅샷의 sentiment는 6/23~24 당시 구규칙 산출(7/2 요청형→부정 정책전환·무결점
구조규칙 이전) — 그대로 쓰면 구정책 오라벨 대량 유입. 현행 규칙 엔진(_sentence_sentiment_
override_explain)으로 전량 재산출한다.

silver 채택(보수 — 긍↔부 0 우선, 애매하면 버린다. 버리는 게 남는 것):
  POS: 현행규칙 positive AND kote pos-neg 마진 ≥0.5 AND 요청표지 없음
  NEG: 현행규칙 negative AND (kote neg 우세 or 문서화 고정밀 부정규칙) AND 무결점부정형 아님
  NEU: 구조중립 규칙(무응답/건강/개인안녕/무결점(강긍정 없음))만
  공통 제외: is_clause · 양가태도 패턴(EXCESS+TRAIT 무귀결 — 계쟁지대, 학습오염 실증 260714) ·
             TEST 텍스트 · gold 텍스트 · (text,field) 중복 · 8자 미만/200자 초과
클래스 균형 cap: 각 20,000 (dup 빈도 가중 상위).
출력: emotion/silver_v2_260714.jsonl
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

OUT = os.path.join(DS, 'emotion', 'silver_v3_260715.jsonl')  # 260715 신규 규칙(detector 확장) 재정제
SRC = ['weak_export_260623.jsonl', 'weak_export_260624.jsonl']
BATCH_FIELD = {'batch_20260622_0': '장점', 'batch_20260623_2': '장점', 'batch_20260624_1': '장점',
               'batch_20260622_2': '단점', 'batch_20260623_1': '단점', 'batch_20260623_3': '단점',
               'batch_20260624_0': '단점'}
EXCESS = re.compile(r'(지나치|너무|과하|과도)')
TRAIT = re.compile(r'(친절|꼼꼼|성실|철저|완벽|열정|적극|책임감|신중|몰두|몰입|헌신|집중|청렴|원칙|소신)')
NOWEAK_NEG = re.compile(r'(보완|개선|단점|필요)\s*.{0,10}(불필요|없|어려움|어렵|찾지 못|발견하지 못)')
CAP = 20000
NEUTRAL_RULES = {'health_advice_neutral', 'personal_wellbeing_neutral', 'no_weakness_neutral',
                 'no_response_neutral', 'garbage_line_neutral', 'neutral_dominant',
                 # 0715 신규 detector(사용자 감사 반영): 혼합·평가불가·비평가메타·요청혼재
                 'mixed_pos_neg_neutral', 'cannot_assess_neutral', 'meta_comment_neutral',
                 'improvement_request_neutral'}
# 문서화된 고정밀 부정규칙(0630_03·0702_03 사용자 확정 계열)
NEG_RULES = {'improvement_request_neg', 'euphemistic_negative', 'deficiency_noun_negative'}


def s2l(s):
    return 'positive' if s > 1e-6 else ('negative' if s < -1e-6 else 'neutral')


def main():
    from src.services.perspective_service import (
        _sentence_sentiment_override_explain as ov, _has_request_marker)
    from finetune_sentiment import TRAIN_FILES, TEST_SETS, load as fload

    excl = set()
    for fn in TEST_SETS.values():
        for r in (json.loads(l) for l in io.open(os.path.join(DS, 'eval', fn), encoding='utf-8') if l.strip()):
            if (r.get('text') or '').strip():
                excl.add(r['text'].strip())
    for fn in TRAIN_FILES:
        for t, l, f in fload(fn):
            excl.add(t)
    print(f'제외 텍스트(TEST+gold): {len(excl)}')

    cand = {}   # (text,field) -> {label, n, kote, rid}
    stat = Counter()
    for fn in SRC:
        for line in io.open(os.path.join(DS, 'emotion', fn), encoding='utf-8'):
            r = json.loads(line)
            stat['in'] += 1
            if r.get('is_clause'):
                stat['skip_clause'] += 1
                continue
            t = (r.get('text') or '').strip()
            if not (8 <= len(t) <= 200):
                stat['skip_len'] += 1
                continue
            batch = (r.get('id') or '').rsplit('-', 1)[0]
            field = BATCH_FIELD.get(batch)
            if not field:
                stat['skip_nofield'] += 1
                continue
            if t in excl:
                stat['skip_excl'] += 1
                continue
            if EXCESS.search(t) and TRAIT.search(t):
                stat['skip_ambivalent'] += 1
                continue
            k = (t, field)
            if k in cand:
                cand[k]['n'] += 1
                stat['dup'] += 1
                continue
            kote = r.get('kote') or [0, 0, 0]
            pos, neg, neu = (list(kote) + [0, 0, 0])[:3]
            try:
                s, rid = ov(pos, neg, t, True, 1, neutral=neu)
                rl = s2l(s)
            except Exception:
                stat['rule_error'] += 1
                continue
            # 보수 채택 기준
            lab = None
            if rl == 'positive' and (pos - neg) >= 0.5 and not _has_request_marker(t):
                lab = 'positive'
            elif rl == 'negative' and not NOWEAK_NEG.search(t) and (neg > pos or rid in NEG_RULES):
                lab = 'negative'
            elif rl == 'neutral' and rid in NEUTRAL_RULES and not NOWEAK_NEG.search(t):
                lab = 'neutral'
            if lab is None:
                stat['skip_lowconf'] += 1
                continue
            cand[k] = {'label': lab, 'n': 1, 'kote': [pos, neg, neu], 'rid': rid, 'batch': batch}
            stat[f'take_{lab}'] += 1

    # 클래스 균형 cap (빈도 상위)
    by = {'positive': [], 'negative': [], 'neutral': []}
    for (t, f), v in cand.items():
        by[v['label']].append((t, f, v))
    rows = []
    for lab, arr in by.items():
        arr.sort(key=lambda x: -x[2]['n'])
        for t, f, v in arr[:CAP]:
            rows.append({'text': t, 'field': f, 'sentiment_silver': lab, 'tier': 'silver_v2',
                         'rule_id': v['rid'], 'kote': v['kote'], 'dup_n': v['n'], 'batch': v['batch'],
                         'label_source': 'current_rules_260714(재라벨)+kote_consensus'})
    with io.open(OUT, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    print('입력/필터:', dict(stat))
    print('채택(캡 전):', {k: len(v) for k, v in by.items()})
    print(f'silver_v2: {len(rows)}행 → emotion/{os.path.basename(OUT)}')
    lab_cnt = Counter(r['sentiment_silver'] for r in rows)
    print('최종 클래스:', dict(lab_cnt))


if __name__ == '__main__':
    main()
