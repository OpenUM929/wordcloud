# -*- coding: utf-8 -*-
"""0702 재생성 후 정리 — 필드복원 + 규칙정상처리분 제거 + L2 유사중복 제거(판정 보존).

regen_boundary_review_260702.py 직후 실행. 순서:
 1) 필드 복원: rec_id 배치 suffix(_0=단점·_1=장점)로 field 채움(강한 prior).
 2) 규칙-정상 무결점 제거: is_no_weakness_declaration ∧ cur_rule_label=='neutral' ∧ 미판정 →
    규칙이 이미 맞게 중립화한 저가치 반복 → 드롭. 누수(규칙≠neutral)·판정분은 유지.
 3) L2 유사중복 제거: 조사·어미·기능토큰+공백 제거 키로 전역(3파일) dedup. 부정어·내용어 보존.
    판정 대표 우선, 판정충돌 군집은 재검토(human_decision=null).
백업은 호출측(_gold_backup)에서 이미 수행. 원 파일 in-place 재기록.
"""
import json, os, re, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, ROOT)
from src.services.perspective_service import (is_no_weakness_declaration, is_no_response,
                                               is_health_advice)

EVAL = os.path.abspath(os.path.join(HERE, '..', 'eval'))
FILES = ['polysemy_review_260702.jsonl', 'polflip_review_260702.jsonl',
         'neutral_boundary_review_260702.jsonl']
DEC = ('positive', 'negative', 'neutral', 'not_group', 'skip')
JOSA = ['을', '를', '이', '가', '은', '는', '에서', '에게', '에', '의', '와', '과', '도',
        '으로', '로', '및', '좀', '더', '수', '하는', '위한', '위해', '하게', '하고',
        '하여', '스러운', '스럽', '들', '것', '점', '한', '인', '적']
_WS = re.compile(r'[\s\W_]+')


# 큐 정리 전용(엔진 미변경) — 느슨한 무결점/정착 탐지. 프로덕션 is_no_weakness_declaration이
#   놓치는 원거리·이표현·오타 무결점 선언을 잡아 검토큐에서만 제거(라벨/데이터 불변).
#   조건: 무결점 명사 ∧ 부재표지 공존. "X 보완 필요"(개선요청, 부재표지 없음)는 미매치→보존.
_NW_NOUN = ('보완', '개선점', '보완점', '필요점', '특이사항', '지적사항', '미흡', '단점', '결점')
_NW_ABSENT = ('없', '않', '존재하지', '생각나지', '생각이나지', '생각이 나지', '모르', '모름',
              '어려움', '어렵', '불가', '불요', '해당없', '해당 없', '업음', '업슴', '엇음',
              '사항음', '아님')


def is_settled_noweak_loose(t):
    if not t:
        return False
    return any(x in t for x in _NW_NOUN) and any(x in t for x in _NW_ABSENT)


def field_of(rid):
    # rec_id 예: 'val-batch_20260624_1-36' → 마지막 '-' 앞 = 'val-batch_20260624_1',
    #   그 마지막 '_' 뒤 = '1'(장점)/'0'(단점).
    try:
        head = str(rid).rsplit('-', 1)[0]
        return {'1': '장점', '0': '단점'}.get(head.rsplit('_', 1)[1], '')
    except Exception:
        return ''


def L2(t):
    s = _WS.sub('', t or '')
    for j in sorted(JOSA, key=len, reverse=True):
        s = s.replace(j, '')
    return s


_SKEL_SUF = ['습니다', '합니다', '됩니다', '입니다', '하다', '한다', '스러운', '스럽',
             '하는', '하고', '하여', '있음', '없음', '필요', '함', '음', '됨', '임', '기', '며']


def SKEL(t):
    """내용어 골격 키 — 2글자+ 토큰의 어미/조사 꼬리를 벗기고 집합·정렬.
    조사/어미 변이를 넘어 '같은 내용어 조합'을 근접중복으로 묶는다(같은 라벨끼리만 병합)."""
    toks = [w for w in _WS.sub(' ', t or '').split() if len(w) >= 2]
    base = []
    for w in toks:
        for suf in _SKEL_SUF:
            if w.endswith(suf) and len(w) > len(suf):
                w = w[:-len(suf)]
                break
        base.append(w)
    return ' '.join(sorted(set(base)))


def main():
    rows = []
    for fn in FILES:
        for l in open(os.path.join(EVAL, fn), encoding='utf-8'):
            l = l.strip()
            if not l:
                continue
            r = json.loads(l)
            r['_file'] = fn
            rows.append(r)
    n_in = len(rows)

    # 1) 필드 복원
    fld = collections.Counter()
    for r in rows:
        f = field_of(r.get('rec_id', ''))
        r['field'] = f
        fld[f or '?'] += 1

    # 2) 규칙-정상 무결점/무응답 제거(미판정만) — 규칙이 이미 맞게 중립화한 저가치 반복.
    #    누수(규칙≠neutral)·판정분은 유지.
    kept = []
    dropped_nw = dropped_nr = dropped_loose = dropped_health = 0
    for r in rows:
        judged = r.get('human_decision') in DEC
        t = r.get('text', '')
        lab = r.get('cur_rule_label')
        if not judged and lab == 'neutral':
            if is_no_weakness_declaration(t):
                dropped_nw += 1
                continue
            if is_no_response(t):
                dropped_nr += 1
                continue
            # 건강조언 중립(규칙 확정) — "건강관리가 필요함"류 저가치 반복 → 큐에서 제외(라벨 불변).
            if is_health_advice(t):
                dropped_health += 1
                continue
        # 느슨한 무결점: 미판정 ∧ 라벨이 부정 아님(부정=혼합 개선요청일 수 있어 검토 보존).
        if not judged and lab != 'negative' and is_settled_noweak_loose(t):
            dropped_loose += 1
            continue
        kept.append(r)
    rows = kept

    # 3) L2(조사·어미 변이) → 4) SKEL(내용어 골격) 2단 전역 dedup.
    #    각 단계: 대표=판정분 우선, 판정충돌 군집은 human_decision=null 재검토 전환.
    #    ⚠️ SKEL은 cur_rule_label이 같은 행끼리만 병합 → 서로 다른 극성 문장 오병합(긍↔부) 방지.
    def dedup(rowlist, keyfn, same_label=False):
        grp = collections.defaultdict(list)
        for r in rowlist:
            k = keyfn(r['text'])
            if same_label:
                k = (r.get('cur_rule_label'), k)
            grp[k].append(r)
        res = []
        conf = 0
        for _k, g in grp.items():
            decs = set(r['human_decision'] for r in g if r.get('human_decision') in DEC)
            rep = dict(next((r for r in g if r.get('human_decision') in DEC), g[0]))
            if len(decs) > 1:
                rep['human_decision'] = None
                conf += 1
            elif decs:
                rep['human_decision'] = next(iter(decs))
            res.append(rep)
        return res, conf

    after_l2, conf_l2 = dedup(rows, L2)
    after_skel, conf_sk = dedup(after_l2, SKEL, same_label=True)

    # 5) 규칙확신 개선요청 표본화(사용자 확정) — 단점필드 + 요청형표지 + 부정 + 미판정 =
    #    규칙이 이미 맞힌 쉬운 반복(하드샘플 아님). 다양한 대표 KEEP_SAMPLE건만 gold검토용 유지,
    #    나머지는 검토큐에서 제거(라벨/데이터 불변, silver로 자동 부정 유지). 애매(장점필드·긍/중·
    #    요청형표지 없는 부정)·판정분은 전량 보존.
    REQ_MARK = ('필요', '보완', '향상', '제고', '요함', '요망', '바람', '개선', '함양', '배양', '모색')
    KEEP_SAMPLE = 200

    def is_confident_request(r):
        return (r.get('human_decision') not in DEC and r.get('cur_rule_label') == 'negative'
                and r.get('field') == '단점' and any(m in r['text'] for m in REQ_MARK))

    easy = [r for r in after_skel if is_confident_request(r)]
    rest = [r for r in after_skel if not is_confident_request(r)]
    easy_sorted = sorted(easy, key=lambda r: SKEL(r['text']))
    if len(easy_sorted) > KEEP_SAMPLE:
        step = len(easy_sorted) / KEEP_SAMPLE
        sample = [easy_sorted[int(i * step)] for i in range(KEEP_SAMPLE)]
    else:
        sample = easy_sorted
    dropped_easy = len(easy) - len(sample)
    final = rest + sample

    out = collections.defaultdict(list)
    for r in final:
        out[r.pop('_file')].append(r)

    print('입력 %d행' % n_in)
    print('  필드복원: %s' % dict(fld))
    print('  규칙-정상 무결점 제거: %d | 무응답: %d | 건강조언: %d | 느슨한 무결점(원거리·오타): %d'
          % (dropped_nw, dropped_nr, dropped_health, dropped_loose))
    print('  L2 유사중복: %d → %d (충돌 %d)' % (len(rows), len(after_l2), conf_l2))
    print('  SKEL 근접중복(동일라벨): %d → %d (충돌 %d)' % (len(after_l2), len(after_skel), conf_sk))
    print('  규칙확신 개선요청 표본화: %d건 중 %d 유지, %d 제거' % (len(easy), len(sample), dropped_easy))
    for fn in FILES:
        with open(os.path.join(EVAL, fn), 'w', encoding='utf-8') as f:
            for r in out[fn]:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        j = sum(1 for r in out[fn] if r.get('human_decision') in DEC)
        print('  %-40s %6d행 (판정 %d, 미판정 %d)'
              % (fn, len(out[fn]), j, len(out[fn]) - j))
    print('합계 %d행' % sum(len(v) for v in out.values()))


if __name__ == '__main__':
    main()
