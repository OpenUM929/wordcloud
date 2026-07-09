# -*- coding: utf-8 -*-
"""grp1~7 검토파일에 claude_judgment(네 판정=Claude 그룹판정 + 근거)를 백필한다.

배경(2026-07-06): 게시판 "내 판정(참고)"는 실은 규칙엔진 산출값(ai_reference)이었다.
사용자 요청으로 컬럼을 '알고리즘 결과'로 정직하게 relabel하고, Claude의 독립 판정을
별도 컬럼 "네 판정"으로 분리했다. 이 스크립트가 그 컬럼의 데이터(claude_judgment)를 채운다.

- 판정은 그룹 단위(파일 접두사)로 균질하게 부여한다(그룹 감사 방법론과 동일 — 그룹의
  대표 화행으로 극성 결정). 각 행에 동일 {polarity, reason}을 기록.
- append/수정 안전: 기존 모든 필드 보존, claude_judgment 키만 덮어씀(재실행 멱등).
- 대상은 grp1~7 review 파일뿐. 8a/8b/8c(잔여 긍·부·중)는 그룹 극성이 균질하지 않아
  건드리지 않는다(claude_judgment=null 유지 → 게시판에 '—'로 표시).
- ⚠️ regen/split 재생성 시 이 필드가 사라질 수 있음 → 재편 후 본 스크립트 재실행.
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
REVIEW_DIR = os.path.normpath(os.path.join(HERE, '..', 'eval', 'review'))

# 파일 접두사 → (극성, 근거). 접두사 우선순위: 긴 것 먼저 매칭.
GROUP_JUDGMENT = [
    ('grp1_no_response', ('neutral',
        '평가불가·내용없음(무응답)은 감정 판정 대상이 아님 → 중립')),
    ('grp2_no_weakness', ('neutral',
        '무결점 선언("단점 없음")은 비판의 부재일 뿐 칭찬이 아님 → 중립'
        '(단, 완벽·뛰어남 등 명시적 강긍정 동반 시 긍정)')),
    ('grp3_health', ('neutral',
        '개인 건강·사생활 조언은 업무역량 평가가 아님 → 무조건 중립')),
    ('grp4_excess', ('negative',
        "과잉('너무/지나치게')+부정적 귀결(오해·못따라·부담·힘듦)은 업무지장 지적 → 부정")),
    ('grp5_effort_need', ('negative',
        "'노력이 필요'는 현재 노력이 결여됐다는 개선요청 → 부정")),
    ('grp6_spec_need', ('negative',
        "'~필요한 것 같/필요한 듯' 추측형 요청도 결핍 지적 → 부정")),
    ('grp7_improvement', ('negative',
        "'X 필요·부족·개선' 개선요청 프레이밍은 역량 결여 지적 → 부정"
        "(순수 대조문·명시적 강긍정은 판정 보류=중립)")),
]


def match_group(fname):
    for prefix, verdict in GROUP_JUDGMENT:
        if fname.startswith(prefix):
            return verdict
    return None


def main():
    if not os.path.isdir(REVIEW_DIR):
        print('review dir 없음:', REVIEW_DIR)
        return
    total_files, total_rows = 0, 0
    for nm in sorted(os.listdir(REVIEW_DIR)):
        if not nm.endswith('.jsonl'):
            continue
        verdict = match_group(nm)
        if verdict is None:
            continue
        pol, reason = verdict
        path = os.path.join(REVIEW_DIR, nm)
        out_lines, n = [], 0
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.rstrip('\n')
                if not line.strip():
                    continue
                r = json.loads(line)
                r['claude_judgment'] = {'polarity': pol, 'reason': reason}
                out_lines.append(json.dumps(r, ensure_ascii=False))
                n += 1
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out_lines) + '\n')
        os.replace(tmp, path)
        total_files += 1
        total_rows += n
        print('  %-38s %s  (%d행)' % (nm, pol, n))
    print('완료: %d파일 %d행 백필' % (total_files, total_rows))


if __name__ == '__main__':
    main()
