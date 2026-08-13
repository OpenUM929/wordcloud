# -*- coding: utf-8 -*-
"""hard_queue prefill — 모델이 틀리는 제한된 패턴만 override.

Override 패턴 (프로젝트 문서화 규칙):
  - 건강/과로/사생활 → 중립 (grp3)
  - 무결점 선언(보완필요점 없음) → 중립 (grp2)
  - 개선요청(부족/미흡/개선필요) → 부정
  - 명시적 부정(고압적/무례/소통부재) → 부정

(※ '필요하'는 맥락 다의로 제외 — '필요한 네트워크 보유'=긍정 vs '소통 필요'=부정 구분 불가)
"""
import json
import os
import re
import sys

HERE = os.path.dirname(__file__)
DATASET_DIR = os.path.normpath(os.path.join(HERE, '..'))
REVIEW_DIR = os.path.join(DATASET_DIR, 'eval', 'review')

HEALTH_PAT = re.compile(r'건강|과로|야근|컨디션|휴가|다치|염려|걱정|몸[을]?[ ]?[생각]?|쉬[었]?[면]?[서]?|지장')

NO_WEAK_PAT = re.compile(
    r'보완[필요]*[점]*[이]*[ ]*없[습]?[니]?[다]?[습]?[니]?[ㄹ]?[까]?|'
    r'단점[ ]?[없]?[다]?[습]?[니]?[다]?|'
    r'특별[히]*[ ]?[할말]*[ ]?[없]?[다]?|'
    r'해당사항[ ]?[없]?[다]?[습]?[니]?[다]?|'
    r'잘모르[겠]?[습]?[니]?[다]?|'
    r'보완[필요]*[점]*[ ]?[미]?[발]?[견]?|'
    r'보완[필요]*[성]*[ ]?[해당]?[없]?[음]?|'
    r'-----------|oooooo+'
)

# '개선' 제외 — '개선을 하기 위해 노력'=긍정 vs '개선 필요'=부정 구분 불가
IMPROVE_PAT = re.compile(r'(부족[하]?[다]?|미흡[하]?[다]?)')

# 부재=명시적 부정, 소통은 부정 맥락에서만(소통 안 되/소통 부재)
BAD_ATTITUDE_PAT = re.compile(
    r'고압적|무례[하]?|이기적|독선적|험담|'
    r'딱딱[하]?[은]?|'
    r'부재|'
    r'소통[ ]?(안[ ]?되|부재|문제|어렵)|'
    r'편중'
)


def judge(text):
    if not text.strip():
        return 'neutral', 'Empty'
    if re.match(r'^[-]+$|^[oO]+$|^\d+$|^\s*$', text.strip()):
        return 'neutral', 'Noise'

    # grp3: 건강 = 중립
    if HEALTH_PAT.search(text):
        return 'neutral', '건강=중립(grp3)'
    # grp2: 무결점 = 중립
    if NO_WEAK_PAT.search(text):
        return 'neutral', '무결점=중립(grp2)'
    # 부족/미흡/개선 = 부정
    if IMPROVE_PAT.search(text):
        return 'negative', '개선요청=부정'
    # 태도 문제 = 부정
    if BAD_ATTITUDE_PAT.search(text):
        return 'negative', '태도=부정'

    return None, '모델추종'


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REVIEW_DIR, 'hard_queue_260713.jsonl')
    if not os.path.isabs(src):
        src = os.path.join(REVIEW_DIR, src)

    rows = [json.loads(l) for l in open(src, encoding='utf-8') if l.strip()]
    print(f'로드: {len(rows)}행')

    stats = {'positive': 0, 'negative': 0, 'neutral': 0, 'escalated': 0, 'model_follow': 0}
    for r in rows:
        text = r.get('text', '')
        model_pol = r['ai_reference']['polarity']

        judge_pol, reason = judge(text)

        if judge_pol is None:
            judge_pol = model_pol
            r['claude_judgment'] = judge_pol
            r['escalate'] = False
            r['note'] = f'claude=모델추종({judge_pol})'
            stats['model_follow'] += 1
        elif judge_pol != model_pol:
            r['claude_judgment'] = judge_pol
            r['escalate'] = True
            r['note'] = f'claude={judge_pol} vs model={model_pol} · {reason}'
            stats['escalated'] += 1
        else:
            r['claude_judgment'] = judge_pol
            r['escalate'] = False
            r['note'] = f'claude={judge_pol} (model일치) · {reason}'

        r['status'] = 3
        stats[judge_pol] += 1

    with open(src, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(f'완료: 긍정={stats["positive"]} · 부정={stats["negative"]} · 중립={stats["neutral"]}')
    print(f'모델추종={stats["model_follow"]} · escalation={stats["escalated"]}건')
    print(f'출력: {os.path.relpath(src, DATASET_DIR)}')

    # ── 자기검산(규칙 #17): 상위 AI가 재집계 없이 이 출력만 확인하도록 스크립트가 스스로 검증 ──
    # 손으로 집계한 표가 총계와 안 맞던 사고(13_02 §12: 부분합 101≠총계 74) 재발 방지.
    from collections import Counter as _C
    esc = [r for r in rows if r.get('escalate')]
    model_of = lambda r: r.get('ai_reference', {}).get('polarity')  # noqa: E731 (모델 예측)
    viol = sum(1 for r in rows
               if bool(r.get('escalate')) != (r.get('claude_judgment') != model_of(r)))
    comp = _C((r.get('claude_judgment'), model_of(r)) for r in esc)
    subtotal = sum(comp.values())
    print('── 자기검산 ──')
    print(f'  총계 정합: escalation {len(esc)} + 비escalation {len(rows) - len(esc)} = {len(rows)} '
          f'(비escalation = 규칙미발동 모델추종 {stats["model_follow"]} + 규칙-모델일치 '
          f'{len(rows) - len(esc) - stats["model_follow"]})')
    print(f'  로직 불변식(escalate ⇔ claude≠model) 위반: {viol} {"OK" if viol == 0 else "FAIL"}')
    print('  escalation 구성 (claude ← model):')
    for (cj, ml), v in sorted(comp.items(), key=lambda kv: -kv[1]):
        print(f'    {cj} ← {ml}: {v}')
    print(f'  부분합 합 {subtotal} = escalation 총계 {len(esc)} '
          f'{"OK" if subtotal == len(esc) else "FAIL"}')
    assert viol == 0, 'escalate 로직 위반 — 큐 무효'
    assert subtotal == len(esc), '부분합≠총계 — 집계 오류'


if __name__ == '__main__':
    main()
