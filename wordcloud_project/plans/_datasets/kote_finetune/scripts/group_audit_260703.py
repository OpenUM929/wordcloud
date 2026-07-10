# -*- coding: utf-8 -*-
"""그룹 단위 분류 감사 — 문장 하나하나가 아니라 '패턴 그룹'이 원하는 극성으로 나오는지 검증.

사용자 요청(2026-07-03 생각의 전환): 개별 문장 대신 그룹별로 프로그램이 원하는 대로
분류하는지 본다. 규칙 수정 후 매번 재실행해 그룹별 일치율·누수 원인을 확인하는 상시 하니스.

출력:
 1) 그룹 × 엔진라벨(긍/부/중) 교차표 + 원하는값 대비 일치율.
 2) 목표그룹(부/중)에서 반대로 새는 행의 발동규칙 분포 + 표본(누수 원인 진단).

실행: 프로젝트 루트에서  python plans/_datasets/kote_finetune/scripts/group_audit_260703.py
"""
import io
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'src'))
import services.perspective_service as P                                    # noqa: E402
from services.perspective_service import _sentence_sentiment_override_explain as ov  # noqa: E402

CORPUS = os.path.join(ROOT, 'plans', '_datasets', 'kote_finetune', 'emotion',
                      'weak_export_260624.jsonl')

# 배타 우선순위 그룹 할당(위→아래). 각 그룹의 전용 detector는 perspective_service의 함수.
GROUPS = [
    ('1_무응답',            P.is_no_response,               '중'),
    ('2_무결점',            P.is_no_weakness_declaration,   '중'),
    ('3_건강조언',          P.is_health_advice,             '중'),
    ('4_과잉호소',          P._is_excess_complaint,         '부'),
    ('5_노력필요',          P._is_effort_needed,            '부'),
    ('6_추측형필요',        P._is_speculative_need,          '부'),
    ('7_개선요청',          lambda t: (P._has_improvement_request_core(t)
                                       or P.has_constructive_need(t)
                                       or P.has_unnegated_deficiency(t)), '부'),
]


def group_of(t):
    for name, fn, _ in GROUPS:
        try:
            if fn(t):
                return name
        except Exception:
            pass
    return '8_기타'


DESIRED = {g: d for g, _, d in GROUPS}
DESIRED['8_기타'] = '—'


def lab(s):
    return '긍' if s > 1e-6 else ('부' if s < -1e-6 else '중')


def main():
    cross = defaultdict(Counter)
    leak_cause = defaultdict(Counter)
    leak_samp = defaultdict(list)
    n = 0
    for line in open(CORPUS, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        t = r.get('text', '') or ''
        k = r.get('kote')
        if not k:
            continue
        p, ng, u = k
        n += 1
        g = group_of(t)
        try:
            s, rule = ov(p, ng, t, True, 1, neutral=u)
        except Exception:
            continue
        L = lab(s)
        cross[g][L] += 1
        d = DESIRED[g]
        if d in ('긍', '부', '중') and L != d:                # 원하는값과 반대 = 누수
            cause = rule + ('|대조' if P.has_contrastive(t) else '')
            leak_cause[g][cause] += 1
            if len(leak_samp[g]) < 10:
                leak_samp[g].append((L, rule, round(p, 2), t[:50]))

    print('총 %d행\n' % n)
    print('%-14s %9s | %6s %6s %6s | %s' % ('그룹', '건수', '긍', '부', '중', '원하는값→일치율'))
    for g in sorted(cross):
        c = cross[g]
        tot = sum(c.values())
        d = DESIRED[g]
        mk = '—'
        if d in ('긍', '부', '중') and tot:
            mk = '%s → %.0f%%' % (d, c.get(d, 0) / tot * 100)
        print('%-14s %9d | %6d %6d %6d | %s'
              % (g, tot, c.get('긍', 0), c.get('부', 0), c.get('중', 0), mk))

    print('\n=== 목표그룹 누수 원인(원하는값 대비 반대로 나온 행) ===')
    for g in sorted(leak_cause):
        print('--- %s (원하는값 %s) ---' % (g, DESIRED[g]))
        for cause, cnt in leak_cause[g].most_common(6):
            print('   %-34s %d' % (cause, cnt))
        for L, rule, p, t in leak_samp[g][:6]:
            print('     [%s|%s|%.2f] %s' % (L, rule, p, t))


if __name__ == '__main__':
    main()
