# -*- coding: utf-8 -*-
"""검토큐 자동 정리 — 사용자 라벨링 3원칙 ① 무종결 단편 → 중립 (긍↔부 안전).

사용자 지시(2026-07-06, 메모리 feedback_incomplete_fragment_neutral):
  ① 무종결 단편(서술어 없는 명사구) → 중립  ② 요청/부정 표지 → 부정  ③ 명확한 행위서술 → 긍정.
8c_other_neu__etc 등 검토큐에 서술어 없는 미완성 문장·자모 난타가 대량 → 규칙대로 자동 정리.

대상: human_decision 이 아직 없는(미판정) 행만. 카테고리별 처리:
  - 자모 난타/키보드 노이즈  → not_group (그룹아님; 사용자도 그렇게 판정)
  - HTML 엔티티 깨짐(&#…)     → 손대지 않음(별도 정제 트랙; 극성 섞임)
  - 서술어 있는 완성문         → 손대지 않음(정상 검토)
  - 극성표지 있는 단편         → 손대지 않음(요청/부정 = 원칙②, 검토 유지)
  - 무종결 + 극성표지 없음     → neutral (원칙①)
안전: neutral/not_group 만 부여 → 긍↔부 오분류 불가. decision_source 태그로 사람/자동 구분(gold 승격 시
  자동분 별도 취급 가능). 원본 백업 후 재기록(재실행 멱등).
"""
import io
import json
import os
import re
import shutil
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

REVIEW_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'eval', 'review'))
BACKUP_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'eval',
                                           '_gold_backup', 'pre_fragment_cleanup_260706'))

_JAMO = re.compile(r'[ᄀ-ᇿ㄰-㆏ꥠ-꥿]')
# 종결 서술어 어미(문장 끝). 이걸로 끝나면 '완성문'으로 보고 건드리지 않는다.
_TERM = ('음', '함', '됨', '임', '슴', '짐', '움', '힘', '큼', '옴', '줌', '참', '봄', '씀', '픔',
         '다', '까', '요', '죠', '네', '라', '냐', '나', '지', '야', '해', '셔', '셨', '였', '웠',
         '았', '었', '니다', '드림', '바람')
# 부정/요청 표지(있으면 원칙② → 자동 중립서 제외, 검토 유지)
_POL = ('부족', '미흡', '필요', '아쉬', '개선', '소홀', '부재', '결여', '지나', '너무', '과도',
        '직설', '편견', '강요', '권위', '이기', '불만', '늦', '잦', '치우', '편향', '미숙',
        '불친절', '산만', '고압', '독단', '무관하게', '떨어', '못하', '안됨', '안 됨')
# 긍정 속성 표지(있으면 원칙③ 긍정 가능 → 자동 중립서 제외, 검토 유지). '탁월한 소통 능력'류 보호.
_POS = ('우수', '탁월', '뛰어', '훌륭', '최고', '모범', '적극', '성실', '원활', '원만', '능숙',
        '완벽', '풍부', '꼼꼼', '신속', '헌신', '솔선', '친절', '능통', '탄탄', '깔끔', '유능',
        '열정', '열의', '강점', '활발', '명확', '정확', '투철', '열심', '뛰월', '풍성', '기여')


def is_jamo_garbage(t):
    nsp = [c for c in t if not c.isspace()]
    if not nsp:
        return True
    j = sum(1 for c in nsp if _JAMO.match(c))
    return j >= 3 or j / len(nsp) > 0.3 or '가나다라마바사' in t


def has_predicate(t):
    s = t.strip().rstrip('.。,·/ ~!?)')
    return s.endswith(_TERM)


def has_polarity(t):
    return any(m in t for m in _POL)


def has_positive(t):
    return any(m in t for m in _POS)


def classify(t):
    if is_jamo_garbage(t):
        return 'jamo'
    if '&#' in t:
        return 'html'
    if has_predicate(t):
        return 'pred'
    if has_polarity(t) or has_positive(t):   # 부정·요청(②) 또는 긍정(③) 표지 → 검토 유지
        return 'frag_pol'
    return 'frag_neu'


def main():
    if not os.path.isdir(REVIEW_DIR):
        print('review dir 없음'); return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    tot = {'neutral': 0, 'not_group': 0, 'html': 0, 'skip_pred': 0, 'skip_pol': 0}
    for nm in sorted(os.listdir(REVIEW_DIR)):
        if not nm.endswith('.jsonl'):
            continue
        path = os.path.join(REVIEW_DIR, nm)
        rows = [json.loads(l) for l in open(path, encoding='utf-8') if l.strip()]
        # 무종결 단편→중립은 중립 버킷(8c)에만 적용(긍/부 버킷의 속성 단편 오중립 방지).
        allow_frag_neutral = nm.startswith('8c_other_neu')
        n_neu = n_ng = 0
        for r in rows:
            if r.get('human_decision') is not None:      # 사람 판정 보존
                continue
            cat = classify(r.get('text') or '')
            if cat == 'frag_neu' and not allow_frag_neutral:
                tot['skip_pol'] += 1     # 8c 외 파일의 단편은 검토 유지
                continue
            if cat == 'frag_neu':
                r['human_decision'] = 'neutral'
                r['decision_source'] = 'auto_fragment'
                r['claude_judgment'] = {'polarity': 'neutral',
                                        'reason': '무종결 단편(서술어 없는 명사구) → 중립 (라벨링 원칙①)'}
                n_neu += 1
            elif cat == 'jamo':
                r['human_decision'] = 'not_group'
                r['decision_source'] = 'auto_jamo'
                r['claude_judgment'] = {'polarity': 'not_group',
                                        'reason': '자모 난타/키보드 노이즈 = 평가문 아님 → 그룹아님'}
                n_ng += 1
            elif cat == 'html':
                tot['html'] += 1
            elif cat == 'pred':
                tot['skip_pred'] += 1
            else:
                tot['skip_pol'] += 1
        if n_neu or n_ng:
            shutil.copy2(path, os.path.join(BACKUP_DIR, nm))
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n')
            os.replace(tmp, path)
            print('  %-40s 중립 %4d · 그룹아님 %3d' % (nm, n_neu, n_ng))
        tot['neutral'] += n_neu
        tot['not_group'] += n_ng
    print('─' * 60)
    print('자동 정리: 중립 %d · 그룹아님 %d  |  잔여(검토): 완성문 %d · 극성단편 %d · HTML깨짐 %d(별도정제)'
          % (tot['neutral'], tot['not_group'], tot['skip_pred'], tot['skip_pol'], tot['html']))
    print('백업:', BACKUP_DIR)


if __name__ == '__main__':
    main()
