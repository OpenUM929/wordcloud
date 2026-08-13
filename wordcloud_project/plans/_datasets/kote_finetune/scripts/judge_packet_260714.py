# -*- coding: utf-8 -*-
"""23년 판정패킷(judge_batch_20260713_0, 171,872 items) — AI judge 단계 1/2: 티어 배정 + 블라인드 감사 표본.

패킷 실측(260714):
  - cur_rule_label == model_ref.label 171,872/171,872 (완전 일치) → 두 값은 독립 신호가 아니라
    같은 배포 스택 최종 라벨로 판단(모델 우선 경로). "규칙×모델 합의"를 근거로 쓰지 않는다.
  - 독립 신호 3개만 사용: ① item.kote(raw)로 로컬 규칙엔진(_sentence_sentiment_override_explain)
    재실행 ② model_ref.confidence(T scaling) ③ Claude 블라인드 판정(표본→정책 확정).

티어(per-row — 동일 (text,field)는 동일 결정 브로드캐스트, 그룹도장 아님·결정함수 동일입력):
  T0_STRUCT  : 구조적 중립규칙(무응답/쓰레기줄/건강·개인안녕) → neutral 확정.
               스택 라벨이 극성이면 **교정**(중립방향 = 긍↔부 생성 불가·안전).
  T3_CONFIRM : 로컬 규칙 라벨 == 모델 라벨 & conf>=0.7 → 그대로 확정(status=3, DB no-op).
  T3_MODEL   : 규칙-모델 불일치가 중립경계(긍↔부 아님) & conf>=0.9 → 모델 유지
               (project_override_bypass_is_correct: 모델>규칙, 중립경계는 게이트 비위반).
  REVIEW     : ①긍↔부 flip(로컬규칙 vs 모델) ②conf<0.7 ③중립경계 & conf<0.9
               → Claude 검토풀(유니크 text,field). 2단계에서 판정/escalation 확정.

이 스크립트는 상태를 확정하지 않는다(쓰기 없음·분석/표본만). 확정은 2단계
(judge_packet_finalize_260714.py)가 감사 결과 반영 후 수행.

출력:
  eval/review/packet_tier_stats_260714.json   — 티어 분포(정책 근거 기록)
  eval/review/packet_audit_sample_260714.jsonl — 블라인드 표본(라벨 비노출, Claude 판정용)
  eval/review/packet_review_pool_260714.jsonl  — REVIEW 유니크 풀(2단계 입력)
"""
import io
import json
import os
import random
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
WP = os.path.abspath(os.path.join(DS, '..', '..', '..'))
sys.path.insert(0, WP)

PACKET = r'D:\dev\wordcloud\data\23년 판정패킷.csv'
OUT_DIR = os.path.join(DS, 'eval', 'review')

random.seed(45)


def score_to_label(s):
    return 'positive' if s > 1e-6 else ('negative' if s < -1e-6 else 'neutral')


def main():
    from src.services.perspective_service import (
        _sentence_sentiment_override_explain as ov,
        is_no_response, is_health_advice, is_personal_wellbeing_neutral,
    )

    with io.open(PACKET, encoding='utf-8-sig') as f:
        pkt = json.load(f)
    items = pkt['items']
    print(f'items: {len(items)}')

    # 유니크 (text, field) 단위로 결정 — 동일 입력 동일 결정(171,872 → 유니크로 축약)
    uniq = {}
    for it in items:
        k = ((it.get('text') or '').strip(), it.get('field') or '')
        u = uniq.setdefault(k, {'n': 0, 'model': (it.get('model_ref') or {}).get('label'),
                                'conf_min': 1.0, 'kote': it.get('kote'),
                                'stack': it.get('cur_rule_label')})
        u['n'] += 1
        c = (it.get('model_ref') or {}).get('confidence')
        if c is not None:
            u['conf_min'] = min(u['conf_min'], c)
    print(f'unique (text,field): {len(uniq)}')

    tiers = defaultdict(list)
    for (text, field), u in uniq.items():
        m, conf = u['model'], u['conf_min']
        kote = u['kote'] or [0.0, 0.0, 0.0]
        pos, neg, neu = (list(kote) + [0.0, 0.0, 0.0])[:3]

        # T0 구조 중립(모델 라벨 무관 — 중립방향 안전). per-row 함수.
        if is_no_response(text) or is_health_advice(text) or is_personal_wellbeing_neutral(text):
            tiers['T0_STRUCT'].append((text, field, u, 'neutral'))
            continue

        # 로컬 규칙엔진(raw KoTE 입력) — 독립 신호
        try:
            s, rid = ov(pos, neg, text, True, 1, neutral=neu)
            rl = score_to_label(s)
        except Exception:
            rl, rid = None, 'rule_error'

        if rl == m and conf >= 0.7:
            tiers['T3_CONFIRM'].append((text, field, u, m))
        elif rl is not None and {rl, m} == {'positive', 'negative'}:
            tiers['REVIEW_flip'].append((text, field, u, None))
        elif conf < 0.7:
            tiers['REVIEW_lowconf'].append((text, field, u, None))
        elif rl != m and conf >= 0.9:
            tiers['T3_MODEL'].append((text, field, u, m))
        else:  # 중립경계 & 0.7<=conf<0.9
            tiers['REVIEW_neuboundary'].append((text, field, u, None))

    stats = {}
    for t, arr in sorted(tiers.items()):
        n_items = sum(x[2]['n'] for x in arr)
        stats[t] = {'unique': len(arr), 'items': n_items}
        print(f'{t:18s} unique={len(arr):6d} items={n_items:6d}')

    os.makedirs(OUT_DIR, exist_ok=True)

    # 블라인드 감사 표본 — 층화: 자동확정 티어 검증(40+20) + T0 교정 검증(30) + REVIEW 미리보기(30)
    sample = []

    def take(tier, n, note):
        arr = tiers.get(tier, [])
        for text, field, u, lab in random.sample(arr, min(n, len(arr))):
            sample.append({'tier': tier, 'text': text, 'field': field, 'note': note})

    take('T3_CONFIRM', 40, '자동확정 후보 — 오류율 추정')
    take('T3_MODEL', 20, '모델유지 후보 — 중립경계 오류율')
    take('T0_STRUCT', 30, '구조중립 교정 — 규칙 오발동 검사')
    take('REVIEW_flip', 15, '긍↔부 flip 미리보기')
    take('REVIEW_lowconf', 15, '저신뢰 미리보기')
    random.shuffle(sample)  # 티어 노출 순서 셔플(판정 편향 방지)
    with io.open(os.path.join(OUT_DIR, 'packet_audit_sample_260714.jsonl'), 'w', encoding='utf-8') as f:
        for i, r in enumerate(sample):
            f.write(json.dumps({'idx': i, **r}, ensure_ascii=False) + '\n')

    # REVIEW 풀(2단계 입력) — 라벨 신호 포함(2단계는 블라인드 아님·prefill용)
    with io.open(os.path.join(OUT_DIR, 'packet_review_pool_260714.jsonl'), 'w', encoding='utf-8') as f:
        for t in ('REVIEW_flip', 'REVIEW_lowconf', 'REVIEW_neuboundary'):
            for text, field, u, _ in tiers.get(t, []):
                f.write(json.dumps({'tier': t, 'text': text, 'field': field,
                                    'model': u['model'], 'conf': u['conf_min'],
                                    'stack': u['stack'], 'dup_n': u['n'],
                                    'kote': u['kote']}, ensure_ascii=False) + '\n')

    with io.open(os.path.join(OUT_DIR, 'packet_tier_stats_260714.json'), 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)

    # 자기검산: 티어 합 = 유니크 총계
    assert sum(len(a) for a in tiers.values()) == len(uniq), '티어 합 ≠ 유니크 총계'
    print(f'감사표본 {len(sample)} · REVIEW 풀 '
          f'{sum(len(tiers.get(t, [])) for t in ("REVIEW_flip", "REVIEW_lowconf", "REVIEW_neuboundary"))} 저장 → eval/review/')


if __name__ == '__main__':
    main()
