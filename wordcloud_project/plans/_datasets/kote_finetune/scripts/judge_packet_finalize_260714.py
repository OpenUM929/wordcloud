# -*- coding: utf-8 -*-
"""23년 판정패킷 judge 단계 2/2 — 최종 판정 기입 + gold 후보 추출.

정책(블라인드 감사 120건 + B2 표본 40건 + flip rule_id 분해로 확정):
  · cur_rule_label==model_ref.label 전건 일치 → 두 값은 같은 신호(배포 스택 최종 라벨).
  · flip(로컬 규칙 vs 모델 긍↔부)의 대부분 = raw KoTE 규칙 트랩(positive_rescue·rule4 등)
    → 모델 유지(13_03 A/B: 모델>규칙, 하드셋 긍↔부 16→1 근거).
  · 모델의 체계적 과부정 3패턴은 Claude가 유니크 전수 판정(B3 유지칭찬·B4 존경/배움·B6 양가태도)
    — 사용자 재정 규칙(feedback_ambiguous_trait_employer_lens 등) 적용, 판정은 b346 인덱스 고정.
  · B2(개선요청→부정)는 model==negative 합의분만 자동, 트랩 가드:
    무결점 부정형(보완 불필요/확인 어려움)→중립, 유지칭찬 변형→escalation(prefill 긍정).
  · T0 구조중립(무응답/건강/개인안녕) — 강부정·역량요청 동반 시 부정으로 교정(감사 #8·#88).
  · 저신뢰(<0.7) 잔여 = 진짜 불확실 → status=2 (prefill=모델), 사람 게시판.
  · status=3 확정, status=2 사람행. ai_reference {polarity, confidence, reason} 기입.

gold 후보(사용자 확정 전 후보일 뿐 — TRAIN 배선은 확정 후 별도):
  G1 Claude 판정 positive & 모델 negative (B3/B4/B6) — field 포함 긍정 하드샘플
  G2 구조중립 교정(스택 극성→중립, NEUTRAL_RULES 전례) — field 포함 중립
  G3 B2 합의 negative 중 KoTE-flip이던 것 — rule_evidenced negative 전례(0623_03)
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

PACKET = r'D:\dev\wordcloud\data\23년 판정패킷.csv'
OUT_PACKET = r'D:\dev\wordcloud\data\23년 판정패킷_judged.json'
B346 = os.path.join(DS, 'eval', 'review', 'packet_b346_pool_260714.jsonl')

# ── Claude 유니크 전수 판정(b346 파일 i 인덱스 고정 — 재실행 멱등) ─────────────
B4_NEG = {22, 23, 24, 29, 31, 32, 33, 35, 38, 39, 40, 41}
B4_NEU = {34}
B6_NEG = {43, 76, 102, 112, 133, 136, 146, 151, 165, 174, 175, 176, 190, 191, 209,
          218, 223, 227, 235, 239, 267, 277, 283, 291, 297, 302, 304, 306, 310,
          313, 314, 318, 319, 322, 323, 324}
B6_NEU = {70, 95, 108, 116, 124, 137, 141, 195, 200, 213, 214, 222, 226, 233, 284,
          298, 300, 305, 312, 315, 317, 321}
B6_UNC = {173}   # 반어 극찬 의심("성실·청렴이 오히려 보완점") → 사람 확정

# ── 패턴(가드) ────────────────────────────────────────────────────────────────
KEEP = re.compile(r'(앞으로도|지금처럼|현재처럼|이대로|계속)\s*.{0,14}(임해|유지|부탁|바랍|주시|해주)')
KEEP_EXT = re.compile(r'(현재와 같이|지금처럼|앞으로도|내년에도|올해처럼)\s*.{0,16}(잘|수행|추진|하면 좋|하기 바람|였으면)')
LEARN = re.compile(r'(가르쳐|배우고\s*싶|본받고|귀감)')
EXCESS = re.compile(r'(지나치|너무|과하|과도)')
TRAIT = re.compile(r'(친절|꼼꼼|성실|철저|완벽|열정|적극|책임감|신중|몰두|몰입|헌신|집중)')
CONSEQ = re.compile(r'(부담|피로|스트레스|오해|지장|누락|힘들|지치|건강|무리|놓치|못\s|않|균형)')
NOWEAK_NEG = re.compile(r'(보완|개선|단점|필요)\s*.{0,10}(불필요|없|어려움|어렵|찾지 못|발견하지 못)')
STRONGNEG = re.compile(r'(태만|무능|불성실|무책임|갑질|폭언|괴롭|불친절|이기적|기만|폄하|험담|성희롱)')
COMPREQ = re.compile(r'(능력|역량|소통|협업|전문성|리더십|교류|스킬)\s*.{0,8}(확보|필요|배양|개발|강화|향상)')
GROWTH = re.compile(r'(쌓이면|쌓인다면|경험이 더|성장할 것|재목|발전할 것)')
WLB = re.compile(r'워라밸|일과 삶')


def s2l(s):
    return 'positive' if s > 1e-6 else ('negative' if s < -1e-6 else 'neutral')


def main():
    from src.services.perspective_service import (
        _sentence_sentiment_override_explain as ov,
        is_no_response, is_health_advice, is_personal_wellbeing_neutral,
        has_improvement_request, _has_request_marker,
    )

    b346 = {}
    for l in io.open(B346, encoding='utf-8'):
        r = json.loads(l)
        i, b = r['i'], r['bucket']
        if i in B6_UNC:
            lab, st, why = None, 2, '반어 극찬 의심 — 사람 확정 필요'
        elif b == 'B3':
            lab, st, why = 'positive', 3, '유지칭찬(현재 상태 긍정+유지 요청)=칭찬 화행'
        elif b == 'B4':
            lab = 'negative' if i in B4_NEG else ('neutral' if i in B4_NEU else 'positive')
            st, why = 3, ('존경/배움 화행=긍정' if lab == 'positive' else
                          '전수요청/조건부 귀감=개선요청' if lab == 'negative' else '격려 단편=중립')
        else:  # B6
            lab = 'negative' if i in B6_NEG else ('neutral' if i in B6_NEU else 'positive')
            st, why = 3, ('양가태도(과잉+긍정특질, 해악표지 없음)=기업관점 긍정(사용자 재정)' if lab == 'positive' else
                          '과잉+명시 해악귀결(지연/간섭/힘듦 등)=부정' if lab == 'negative' else
                          '개인안녕 귀결(휴식/체력/워라밸)=중립')
        b346[(r['text'].strip(), r['field'])] = (lab, st, why)

    with io.open(PACKET, encoding='utf-8-sig') as f:
        pkt = json.load(f)
    items = pkt['items']

    # ── 유니크 결정 ──────────────────────────────────────────────────────────
    uniq = {}
    for it in items:
        k = ((it.get('text') or '').strip(), it.get('field') or '')
        u = uniq.setdefault(k, {'model': (it.get('model_ref') or {}).get('label'),
                                'conf': 1.0, 'kote': it.get('kote'), 'n': 0})
        u['n'] += 1
        c = (it.get('model_ref') or {}).get('confidence')
        if c is not None:
            u['conf'] = min(u['conf'], c)

    decisions = {}   # k -> (label, status, confidence, reason, route)
    route_cnt = Counter()

    for k, u in uniq.items():
        text, field = k
        m, conf = u['model'], u['conf']
        kote = (list(u['kote'] or []) + [0.0, 0.0, 0.0])[:3]

        # 1) Claude 전수 판정(B3/B4/B6)
        if k in b346:
            lab, st, why = b346[k]
            decisions[k] = (lab if st == 3 else (lab or m), st,
                            'high' if st == 3 else 'low', why, 'claude_b346')
            continue

        # 2) 구조 중립(무응답/건강/개인안녕) + 오발동 가드
        struct = is_no_response(text) or is_health_advice(text) or is_personal_wellbeing_neutral(text)
        if struct:
            if STRONGNEG.search(text):
                decisions[k] = ('negative', 3, 'high', '강부정 표지 동반(태만 등) — 구조중립 오발동 교정', 'struct_guard_neg')
            elif COMPREQ.search(text):
                decisions[k] = ('negative', 3, 'high', '역량 개선요청 동반 혼합문 — 요청 우세(감사 #8)', 'struct_guard_neg')
            else:
                decisions[k] = ('neutral', 3, 'high', '무응답/건강/개인안녕=중립(확립 구조규칙)', 'struct_neutral')
            continue

        # 3) 로컬 규칙엔진(raw KoTE) — 독립 신호
        try:
            s, rid = ov(kote[0], kote[1], text, True, 1, neutral=kote[2])
            rl = s2l(s)
        except Exception:
            rl, rid = None, 'rule_error'

        # 4) 요청/무결점/유지칭찬 계열
        req = has_improvement_request(text) or _has_request_marker(text)
        if req:
            if NOWEAK_NEG.search(text):
                decisions[k] = ('neutral', 3, 'high', '무결점 부정형(보완 불필요/확인 어려움)=중립', 'noweak_neutral')
                continue
            if WLB.search(text):
                decisions[k] = ('neutral', 3, 'medium', '워라밸/개인안녕 요청=중립', 'wlb_neutral')
                continue
            if KEEP.search(text) or KEEP_EXT.search(text):
                decisions[k] = ('positive', 2, 'medium', '유지칭찬 변형 의심 — prefill 긍정, 사람 확정', 'keep_escalate')
                continue
            if m == 'negative':
                decisions[k] = ('negative', 3, 'high', '개선요청/결핍=부정(사용자 확정 규칙)+모델 합의', 'req_negative')
                continue
            # 모델이 긍/중인데 요청표지 — 오발동 가능(장점 필드 칭찬 등)
            if field == '장점' and m == 'positive':
                decisions[k] = ('positive', 3, 'medium', '장점 필드+모델 긍정 — 요청표지 오발동 판단', 'req_fp_positive')
            else:
                decisions[k] = (m, 2, 'low', '요청표지 vs 모델 불일치 — 사람 확정', 'req_escalate')
            continue

        # 5) 성장기대/존경 잔여(모델 과부정 의심 패턴) → escalation(prefill 긍정)
        if m == 'negative' and (GROWTH.search(text) or LEARN.search(text)):
            decisions[k] = ('positive', 2, 'medium', '성장기대/존경 화행 의심 — prefill 긍정, 사람 확정', 'growth_escalate')
            continue

        # 6) flip(로컬 규칙 vs 모델 긍↔부) → 모델 유지(규칙 트랩 실증)
        if rl is not None and {rl, m} == {'positive', 'negative'}:
            decisions[k] = (m, 3, 'high' if conf >= 0.9 else 'medium',
                            f'로컬규칙({rid})은 raw-KoTE 트랩 — 모델 유지(13_03 A/B 실증)', 'flip_model')
            continue

        # 7) 저신뢰(<0.7) 잔여 = 진짜 불확실 → 사람
        if conf < 0.7:
            decisions[k] = (m, 2, 'low', '모델 저신뢰(T scaling<0.7)·규칙 무판정 — 사람 확정', 'lowconf_escalate')
            continue

        # 8) 나머지(합의 or 중립경계) → 모델 확정
        decisions[k] = (m, 3, 'high' if (rl == m and conf >= 0.9) else 'medium',
                        '규칙-모델 합의' if rl == m else '중립경계 — field-aware 모델 유지(긍↔부 무관)',
                        'confirm' if rl == m else 'neuboundary_model')

    for k, d in decisions.items():
        route_cnt[d[4]] += uniq[k]['n']

    # ── 아이템 기입(브로드캐스트) ─────────────────────────────────────────────
    n3 = n2 = 0
    pn_change = Counter()
    for it in items:
        k = ((it.get('text') or '').strip(), it.get('field') or '')
        lab, st, cf, why, route = decisions[k]
        it['ai_reference'] = {'polarity': lab, 'confidence': cf, 'reason': why}
        it['status'] = st
        old = (it.get('model_ref') or {}).get('label')
        if st == 3 and {old, lab} == {'positive', 'negative'}:
            pn_change[(old, lab, route)] += 1
        if st == 3:
            n3 += 1
        else:
            n2 += 1

    # ── 자기검산 ────────────────────────────────────────────────────────────
    assert n3 + n2 == len(items), 'status 합 불일치'
    assert all(it['status'] in (2, 3) for it in items), 'status=1 잔존'
    # 긍↔부 라벨 변경(3 확정)은 Claude 전수판정(claude_b346)과 가드 경로만 허용
    for (o, l, r), n in pn_change.items():
        assert r in ('claude_b346', 'struct_guard_neg'), f'무근거 긍↔부 자동변경: {r} {n}건'

    # ── 패킷 메타 갱신 + 저장 ────────────────────────────────────────────────
    import datetime
    pkt['_status']['current_stage'] = 'insert'
    pkt['_status']['counts']['judged'] = len(items)
    pkt['_status']['history'].append({
        'stage': 'judge', 'by': 'AI(Claude Fable, dev 260714)',
        'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'n': len(items), 'status3': n3, 'status2': n2,
        'method': '티어링(구조중립·규칙재실행·신뢰도)+Claude 유니크 전수판정(B3/B4/B6 326)+블라인드 감사 120',
    })
    pkt['_stages']['judge']['done'] = True
    with io.open(OUT_PACKET, 'w', encoding='utf-8') as f:
        json.dump(pkt, f, ensure_ascii=False)

    # ── gold 후보 추출(field 포함 — 사용자 확정 전 '후보') ───────────────────
    gold = {'G1_positive': [], 'G2_neutral': [], 'G3_negative': []}
    for k, (lab, st, cf, why, route) in decisions.items():
        if st != 3:
            continue
        text, field = k
        m = uniq[k]['model']
        rec = {'text': text, 'field': field, 'label': lab, 'model_was': m,
               'reason': why, 'route': route, 'dup_n': uniq[k]['n'],
               'source': 'judge_batch_20260713_0_judged_260714'}
        if route == 'claude_b346' and lab == 'positive' and m == 'negative':
            gold['G1_positive'].append(rec)
        elif route in ('struct_neutral', 'noweak_neutral') and m in ('positive', 'negative'):
            gold['G2_neutral'].append(rec)
        elif route == 'req_negative':
            kote = (list(uniq[k]['kote'] or []) + [0, 0, 0])[:3]
            if kote[0] > kote[1]:   # raw KoTE는 긍정우세였던 것만(하드샘플 가치)
                gold['G3_negative'].append(rec)
    for name, rows in gold.items():
        p = os.path.join(DS, 'eval', f'gold_packet23_{name}_260714.jsonl')
        with io.open(p, 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f'items {len(items)} → status3 {n3} · status2 {n2} (사람행 {n2/len(items)*100:.1f}%)')
    print('routes(items):')
    for r, n in route_cnt.most_common():
        print(f'  {r:20s} {n:7d}')
    print('긍↔부 확정변경(모델→최종, 경로):', dict(pn_change))
    print('gold 후보:', {k: len(v) for k, v in gold.items()})
    print(f'judged 패킷 → {OUT_PACKET}')


if __name__ == '__main__':
    main()
