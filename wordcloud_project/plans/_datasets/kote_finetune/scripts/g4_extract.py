# -*- coding: utf-8 -*-
"""G4 자기개발/학습지향 — 신규 그룹 선별기 정의 + 표본 검증(1차).

G1/G2와 달리 기존 규칙 없음(진짜 신규=순환 아님). 군집 C7(residual) 근거로 학습·자기개발만
정밀 타깃(일반 역량 소통/협업 제외). 표본 읽고 정밀도 확인 후 패킷/전파로 확장.

기본 극성 positive(실제 성장행위 서술). trap: "학습 필요"(=개선요청 G2)·"학습능력 부족"(부정).
"""
import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
DATASET_DIR = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, PROJECT_ROOT)
from src.services.perspective_service import has_improvement_request  # noqa: E402

# 학습·자기개발 표지(C7 근거). 정밀화: '자발적' 단독 제거('자발적 참여 유도'=리더십 오포착),
#   학습·자기개발에 한정. '자발적 학습/배움'만 명시 허용.
GROWTH = ['자기개발', '자기 개발', '자기계발', '자기 계발', '학습', '배움', '배우려', '배우고자',
          '공부', '역량개발', '역량 개발', '최신지식', '최신 지식', '최신기술', '최신 기술',
          '신기술', '트렌드', '탐구', '독학', '자격증', '전문성 향상', '전문성 강화',
          '학구열', '자기발전', '자기 발전', '자발적 학습', '자발적인 학습', '배우려는 자세',
          '배우려는 의지', '끊임없이 배', '꾸준히 학습', '연구개발']
# 결핍/요청 신호가 문장 어디든 있으면 성장'행위'가 아니라 결핍/요청(G2/부정) → 제외.
DEFICIT = ('부족', '미흡', '떨어', '못함', '못합', '결여', '저조', '안 됨', '안됨')


def is_growth(text, sentiment):
    if not text:
        return False
    if sentiment != 'positive':           # G4=positive 성장행위만(결핍/요청은 타 그룹)
        return False
    if has_improvement_request(text):     # "학습 필요" 등 개선요청은 G2
        return False
    if any(d in text for d in DEFICIT):   # "습득 능력 떨어짐" 등 결핍 배제
        return False
    for m in GROWTH:                       # 표지 직후 '필요/요함' = 개선요청(G2) → 제외
        i = text.find(m)
        while i != -1:
            if '필요' not in text[i + len(m):i + len(m) + 6] and '요함' not in text[i + len(m):i + len(m) + 6]:
                return True
            i = text.find(m, i + len(m))
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp',
                    default=os.path.join(DATASET_DIR, 'emotion', 'weak_export_260624.jsonl'))
    ap.add_argument('--sample', type=int, default=45)
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding='utf-8')
        except Exception:
            pass

    members, pol = [], {'positive': 0, 'negative': 0, 'neutral': 0, 'none': 0}
    fld = {'장점': 0, '단점': 0, '?': 0}
    n = 0
    for line in open(args.inp, encoding='utf-8'):
        r = json.loads(line)
        if r.get('is_clause'):
            continue
        n += 1
        if is_growth(r.get('text') or '', r.get('sentiment')):
            members.append(r)
            pol[r.get('sentiment') or 'none'] = pol.get(r.get('sentiment') or 'none', 0) + 1
            f = '장점' if '_1-' in r.get('id', '') else ('단점' if '_0-' in r.get('id', '') else '?')
            fld[f] += 1
    print(f'전체 {n:,} → G4 자기개발 후보 {len(members):,}')
    print(f'  필드: {fld}')
    print(f'  현규칙 극성: {pol}')
    rng = random.Random(3)
    S = r'C:/Users/ADMINI~1/AppData/Local/Temp/claude/D--dev-wordcloud/5b5229d3-4cd7-4e1a-b3cb-95a2369dd2c7/scratchpad'
    samp = rng.sample(members, min(args.sample, len(members)))
    with open(S + '/g4_sample.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join('[%s] %s' % (r.get('sentiment'), r.get('text')) for r in samp))
    print(f'  표본 {len(samp)} → g4_sample.txt')


if __name__ == '__main__':
    main()
