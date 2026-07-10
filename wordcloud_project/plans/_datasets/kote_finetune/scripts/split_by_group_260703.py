# -*- coding: utf-8 -*-
"""검토 큐를 '패턴 그룹'별 파일로 재편성 — 그룹 내 규칙성이 균질해 그룹 단위 판단이 쉽도록.

사용자 요청(2026-07-03): 대부분 그룹은 규칙성이 비슷해 개별 판단이 반복적이다. 그룹별 파일로
묶으면 규칙이 잘 듣는 그룹(무결점·과잉호소·추측형필요 등)은 통째로 빠르게 확인/승인하고,
진짜 애매한 기타 그룹에만 집중할 수 있다.

파이프라인: regen → cleanup → (본 스크립트) split. 기존 3개 disagreement-type 파일(polysemy/
polflip/neutral_boundary)을 그룹 파일로 재발행하고 원본 3개는 백업으로 이동(게시판 중복 방지).

그룹(배타 우선순위): 1무응답·2무결점·3건강·4과잉호소·5노력필요·6추측형필요·7개선요청·8기타.
8기타는 이질적이라 현규칙 라벨(긍/부/중)로 3분할(8a/8b/8c). 각 파일은 field·라벨·정규화텍스트로
정렬해 유사행이 인접하도록 한다. 각 행에 'group' 태그 추가(판정/데이터 불변).
"""
import io
import json
import os
import re
import shutil
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'src'))
import services.perspective_service as P                                    # noqa: E402

EVAL = os.path.abspath(os.path.join(HERE, '..', 'eval'))
# 검토 전용 폴더 — 게시판은 이 폴더만 나열(벤치마크·gold·학습·소스는 eval/ 최상위에 그대로 둠).
REVIEW = os.path.join(EVAL, 'review')
SRC_FILES = ['polysemy_review_260702.jsonl', 'polflip_review_260702.jsonl',
             'neutral_boundary_review_260702.jsonl']
BACKUP = os.path.join(EVAL, '_gold_backup', 'pre_groupsplit_260703')
_WS = re.compile(r'[\s\W_]+')

# (그룹키, detector, 파일슬러그, 원하는극성)
GROUPS = [
    ('1_무응답',     P.is_no_response,              'grp1_no_response',  '중'),
    ('2_무결점',     P.is_no_weakness_declaration,  'grp2_no_weakness',  '중'),
    ('3_건강조언',   P.is_health_advice,            'grp3_health',       '중'),
    ('4_과잉호소',   P._is_excess_complaint,        'grp4_excess',       '부'),
    ('5_노력필요',   P._is_effort_needed,           'grp5_effort_need',  '부'),
    ('6_추측형필요', P._is_speculative_need,         'grp6_spec_need',    '부'),
    ('7_개선요청',   lambda t: (P._has_improvement_request_core(t)
                                or P.has_constructive_need(t)
                                or P.has_unnegated_deficiency(t)), 'grp7_improvement', '부'),
]
LABEL_SLUG = {'positive': '8a_other_pos', 'negative': '8b_other_neg', 'neutral': '8c_other_neu'}

# 도메인 축(내용 주제) — 검토 편의용 세분화(감정엔진 무관, 긍↔부 위험 없음). 코퍼스 빈출어 근거.
#   우선순위대로 첫 매칭. 정도부사(너무/과도/지나치)는 폴리세미 감시존이라 별도 축으로 먼저 뽑는다.
DOMAINS = [
    ('degree', ('너무', '과도', '지나치', '다소', '과하')),
    ('comm',   ('소통', '의사소통', '협업', '관계', '교류', '친화', '커뮤니', '경청', '공감', '대화')),
    ('expert', ('전문성', '전문', '지식', '역량', '업무능력', '업무이해', '이해도', '노하우', '실력')),
    ('drive',  ('적극', '열정', '노력', '책임감', '성실', '의지', '열의', '주도', '추진', '관심')),
    ('care',   ('배려', '상대방', '온화', '친절', '겸손', '인간적', '따뜻', '예의')),
    ('admin',  ('출근', '근태', '지각', '이석', '자리비', '시간 준수', '일찍', '휴가')),
    ('it',     ('IT', 'PC', '전산', '문서작성', '문서 작성', '엑셀', '한글', '컴퓨터', '전산화')),
    ('accuracy', ('실수', '오류', '정확성', '꼼꼼', '세밀', '디테일', '완성도', '정확도')),
    ('leader', ('리더십', '솔선', '모범', '통솔', '이끌')),
    ('trait',  ('성향', '성격', '경향', '스타일', '기질')),
]
# 도메인 세분화를 적용할 큰 버킷(7·8a·8b·8c). 1~6은 소형·균질이라 통짜 유지.
_SUBSPLIT = {'grp7_improvement', '8a_other_pos', '8b_other_neg', '8c_other_neu'}


def domain_of(t):
    for name, kws in DOMAINS:
        if any(k in t for k in kws):
            return name
    return 'etc'


def group_of(t):
    for name, fn, _slug, _d in GROUPS:
        try:
            if fn(t):
                return name
        except Exception:
            pass
    return '8_기타'


def slug_of(gr, row):
    base = None
    for name, _fn, slug, _d in GROUPS:
        if gr == name:
            base = slug
            break
    if base is None:
        base = LABEL_SLUG.get(row.get('cur_rule_label'), '8c_other_neu')
    if base in _SUBSPLIT:
        return '%s__%s' % (base, domain_of(row.get('text', '')))
    return base


def field_rank(f):
    return {'단점': 0, '장점': 1}.get(f, 2)


def _clear_stale_group_files():
    """이전 실행이 남긴 그룹 파일(*_260703.jsonl) 제거 — 재실행 시 유령파일 방지(review/·eval/ 둘 다)."""
    import glob
    for d in (REVIEW, EVAL):
        for p in glob.glob(os.path.join(d, '*_260703.jsonl')):
            os.remove(p)


def main():
    os.makedirs(REVIEW, exist_ok=True)
    _clear_stale_group_files()
    rows = []
    for fn in SRC_FILES:
        p = os.path.join(EVAL, fn)
        if not os.path.isfile(p):                        # 이미 백업으로 옮겨졌으면 백업본에서 읽음(재실행)
            bp = os.path.join(BACKUP, fn)
            if os.path.isfile(bp):
                p = bp
            else:
                continue
        for l in open(p, encoding='utf-8'):
            l = l.strip()
            if not l:
                continue
            r = json.loads(l)
            gr = group_of(r.get('text', ''))
            r['group'] = gr                                   # 그룹 태그(판정 불변)
            rows.append((slug_of(gr, r), r))

    buckets = {}
    for slug, r in rows:
        buckets.setdefault(slug, []).append(r)

    # 소형 도메인 버킷(<MIN_ROWS)은 해당 그룹의 __etc로 접어 파일 난립 방지(균질·실용 우선).
    MIN_ROWS = 40
    folded = {}
    for slug, rs in buckets.items():
        base, sep, dom = slug.partition('__')
        if sep and dom != 'etc' and len(rs) < MIN_ROWS:
            slug = '%s__etc' % base
        folded.setdefault(slug, []).extend(rs)
    buckets = folded

    # 그룹 내 정렬: field(단점→장점→미상) → 현규칙 → 정규화 텍스트 (유사행 인접)
    for slug in buckets:
        buckets[slug].sort(key=lambda r: (field_rank(r.get('field')),
                                          r.get('cur_rule_label') or '',
                                          _WS.sub('', r.get('text', '') or '')))

    # 원본 3파일 백업 이동(게시판 중복 방지)
    os.makedirs(BACKUP, exist_ok=True)
    for fn in SRC_FILES:
        p = os.path.join(EVAL, fn)
        if os.path.isfile(p):
            shutil.move(p, os.path.join(BACKUP, fn))

    DEC = ('positive', 'negative', 'neutral', 'not_group', 'skip')
    base_order = [g[2] for g in GROUPS] + ['8a_other_pos', '8b_other_neg', '8c_other_neu']
    dom_order = [d[0] for d in DOMAINS] + ['etc']

    def sort_key(slug):
        base, _, dom = slug.partition('__')
        bi = base_order.index(base) if base in base_order else 99
        di = dom_order.index(dom) if dom in dom_order else 99
        return (bi, di)

    total = 0
    print('그룹별 파일 생성:')
    for slug in sorted(buckets, key=sort_key):
        rs = buckets.get(slug, [])
        out = os.path.join(REVIEW, '%s_260703.jsonl' % slug)
        with open(out, 'w', encoding='utf-8') as f:
            for r in rs:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        j = sum(1 for r in rs if r.get('human_decision') in DEC)
        c = Counter(r.get('cur_rule_label') for r in rs)
        total += len(rs)
        print('  %-22s %6d행 (판정 %4d | 긍%d 부%d 중%d)'
              % (slug, len(rs), j, c.get('positive', 0), c.get('negative', 0), c.get('neutral', 0)))
    print('합계 %d행 → review/ 폴더(게시판 전용) · 원본 3파일 → %s'
          % (total, os.path.relpath(BACKUP, EVAL)))


if __name__ == '__main__':
    main()
