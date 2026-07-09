# -*- coding: utf-8 -*-
"""검토 파일에 personal_wellbeing_neutral 수정을 재적용(re-run)하고 claude_judgment를 per-row 교정.

배경(2026-07-06): 사용자 피드백 — 건강·개인안녕(스트레스/휴식/상처) 문장이 부정으로 나오고,
Claude 판정(claude_judgment)도 그룹째 도장이라 '단편적'. perspective_service에 개인 심신안녕
도메인 게이트(is_personal_wellbeing_neutral)를 추가했고, 이 스크립트가 그 결과를 검토 파일에 반영한다.

동작(각 행):
- is_personal_wellbeing_neutral(text) 발동 → cur_rule_label='neutral', ai_reference=규칙근거,
  claude_judgment=개인안녕 중립 근거. (게이트는 override 첫 분기라 KoTE 없이 중립 확정.)
- 비발동 & grp1~7 파일 → claude_judgment=그룹 기준(진짜 개선요청은 부정 유지 → per-row 정밀화).
- 그 외(8a/8b/8c) 비발동 → claude_judgment 원본 유지.
- human_decision·gold·group·text·field·rec_id 등 전 필드 보존. 재실행 멱등.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import src.services.perspective_service as ps  # noqa: E402

REVIEW_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'eval', 'review'))

WELLBEING_CJ = {'polarity': 'neutral',
                'reason': '개인 건강·심신 안녕(업무 무관)에 대한 바람/염려/조언 → 중립'}
WELLBEING_REF = {'polarity': 'neutral', 'confidence': 'rule',
                 'reason': '규칙=neutral (personal_wellbeing_neutral) · 개인 심신안녕=업무무관'}

GROUP_JUDGMENT = [
    ('grp1_no_response', ('neutral', '평가불가·내용없음(무응답)은 감정 판정 대상이 아님 → 중립')),
    ('grp2_no_weakness', ('neutral', '무결점 선언("단점 없음")은 비판의 부재일 뿐 칭찬이 아님 → 중립'
                          '(단, 완벽·뛰어남 등 명시적 강긍정 동반 시 긍정)')),
    ('grp3_health', ('neutral', '개인 건강·사생활 조언은 업무역량 평가가 아님 → 무조건 중립')),
    ('grp4_excess', ('negative', "과잉('너무/지나치게')+부정적 귀결(오해·못따라·부담·힘듦)은 업무지장 지적 → 부정")),
    ('grp5_effort_need', ('negative', "'노력이 필요'는 현재 노력이 결여됐다는 개선요청 → 부정")),
    ('grp6_spec_need', ('negative', "'~필요한 것 같/필요한 듯' 추측형 요청도 결핍 지적 → 부정")),
    ('grp7_improvement', ('negative', "'X 필요·부족·개선' 개선요청 프레이밍은 역량 결여 지적 → 부정"
                          "(순수 대조문·명시적 강긍정은 판정 보류=중립)")),
]


def group_default(fname):
    for prefix, verdict in GROUP_JUDGMENT:
        if fname.startswith(prefix):
            return verdict
    return None


def main():
    if not os.path.isdir(REVIEW_DIR):
        print('review dir 없음:', REVIEW_DIR)
        return
    tot_fired = tot_corrected = 0
    for nm in sorted(os.listdir(REVIEW_DIR)):
        if not nm.endswith('.jsonl'):
            continue
        gdef = group_default(nm)
        path = os.path.join(REVIEW_DIR, nm)
        out, fired, corrected = [], 0, 0
        with open(path, encoding='utf-8') as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                t = r.get('text') or ''
                if ps.is_personal_wellbeing_neutral(t):
                    fired += 1
                    if r.get('cur_rule_label') != 'neutral':
                        corrected += 1
                    r['cur_rule_label'] = 'neutral'
                    r['ai_reference'] = dict(WELLBEING_REF)
                    r['claude_judgment'] = dict(WELLBEING_CJ)
                elif gdef is not None:
                    r['claude_judgment'] = {'polarity': gdef[0], 'reason': gdef[1]}
                out.append(json.dumps(r, ensure_ascii=False))
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out) + '\n')
        os.replace(tmp, path)
        tot_fired += fired
        tot_corrected += corrected
        if fired:
            print('  %-40s 발동 %d (부/긍→중 교정 %d)' % (nm, fired, corrected))
    print('완료: 게이트 발동 %d행 · 라벨 교정(비중립→중립) %d행' % (tot_fired, tot_corrected))


if __name__ == '__main__':
    main()
