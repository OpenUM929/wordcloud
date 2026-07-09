# -*- coding: utf-8 -*-
"""내부망 배치 결과 감사 (batch_20260708_0) — 그룹단위 + dev 재현 대조.

group_audit_260703.py 골격 재사용. 차이점:
 - 라벨 소스가 dev 재계산이 아니라 **내부망 실행이 실제로 낸 최종판정 y**(p/n/u).
 - 추가로 dev 현재 규칙(ov)으로 같은 문장·같은 KoTE 점수(s)를 재판정하여
   내부망 y와의 일치율을 측정(배포본↔dev 버전 드리프트 검출).

출력:
 1) 그룹 × 내부망 y 교차표 + 원하는값 대비 일치율 (그룹단위 감사).
 2) 목표그룹 누수 표본.
 3) 내부망 y vs dev 재현 라벨 혼동행렬 + 불일치 표본 (긍↔부 플립 우선).

실행: 프로젝트 루트에서  python plans/_datasets/kote_finetune/scripts/group_audit_260708.py
"""
import io
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
REPO = os.path.abspath(os.path.join(ROOT, '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'src'))
import services.perspective_service as P                                    # noqa: E402
from services.perspective_service import _sentence_sentiment_override_explain as ov  # noqa: E402

BATCH = os.path.join(REPO, 'data', 'batch_20260708_0.csv')

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

Y2L = {'p': '긍', 'n': '부', 'u': '중'}


def lab(s):
    return '긍' if s > 1e-6 else ('부' if s < -1e-6 else '중')


def main():
    cross = defaultdict(Counter)
    leak_samp = defaultdict(list)
    confusion = Counter()          # (내부망y, dev재현) 쌍
    drift_samp = defaultdict(list)
    n = 0
    for line in open(BATCH, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        t = r.get('x', '') or ''
        y = r.get('y')
        s3 = r.get('s')
        if not t or y not in Y2L or not s3:
            continue
        p, ng, u = s3
        n += 1
        L = Y2L[y]

        g = group_of(t)
        cross[g][L] += 1
        d = DESIRED[g]
        if d in ('긍', '부', '중') and L != d and len(leak_samp[g]) < 10:
            leak_samp[g].append((L, round(p, 2), t[:60]))

        try:
            sc, rule = ov(p, ng, t, True, 1, neutral=u)
            D = lab(sc)
        except Exception:
            continue
        confusion[(L, D)] += 1
        if L != D:
            key = '%s→%s' % (L, D)
            if len(drift_samp[key]) < 10:
                drift_samp[key].append((rule, round(p, 2), round(ng, 2), t[:60]))

    print('총 %d행 (batch_20260708_0, 라벨=내부망 최종판정 y)\n' % n)
    print('=== 1) 그룹 × 내부망 판정 교차표 ===')
    print('%-14s %9s | %7s %7s %7s | %s' % ('그룹', '건수', '긍', '부', '중', '원하는값→일치율'))
    for g in sorted(cross):
        c = cross[g]
        tot = sum(c.values())
        d = DESIRED[g]
        mk = '—'
        if d in ('긍', '부', '중') and tot:
            mk = '%s → %.1f%%' % (d, c.get(d, 0) / tot * 100)
        print('%-14s %9d | %7d %7d %7d | %s'
              % (g, tot, c.get('긍', 0), c.get('부', 0), c.get('중', 0), mk))

    print('\n=== 2) 목표그룹 누수 표본 (내부망 판정이 원하는값과 다른 행) ===')
    for g in sorted(leak_samp):
        if DESIRED[g] == '—' or not leak_samp[g]:
            continue
        print('--- %s (원하는값 %s) ---' % (g, DESIRED[g]))
        for L, p, t in leak_samp[g][:8]:
            print('     [%s|pos%.2f] %s' % (L, p, t))

    print('\n=== 3) 내부망 y vs dev 재현 (드리프트 검출) ===')
    tot = sum(confusion.values())
    agree = sum(v for (a, b), v in confusion.items() if a == b)
    print('일치율: %.2f%% (%d/%d)' % (agree / tot * 100, agree, tot))
    print('%-6s %9s %9s %9s' % ('y\\dev', '긍', '부', '중'))
    for a in ('긍', '부', '중'):
        print('%-6s %9d %9d %9d' % (a, confusion.get((a, '긍'), 0),
                                    confusion.get((a, '부'), 0),
                                    confusion.get((a, '중'), 0)))
    print('\n--- 불일치 표본 (긍↔부 우선) ---')
    order = ['긍→부', '부→긍', '긍→중', '중→긍', '부→중', '중→부']
    for key in order:
        if key not in drift_samp:
            continue
        print('--- %s (%d건 표본) ---' % (key, len(drift_samp[key])))
        for rule, p, ng, t in drift_samp[key][:8]:
            print('     [%s|pos%.2f neg%.2f] %s' % (rule, p, ng, t))


if __name__ == '__main__':
    main()
