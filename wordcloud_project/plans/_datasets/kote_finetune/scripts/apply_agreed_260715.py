# -*- coding: utf-8 -*-
"""게시판 미표시 행 = 사용자 동의 → 내 프리필을 확정 라벨로 채택 (사용자 지시 260715).

사용자 원칙: "내 의견(memo/tags)이 있거나 판정이 존재하는 경우가 아니면 = 네 의견에 찬성.
  네가 니 의견에 찬성하면 나보고 판정 안해도 된다." → 규칙/프리필이 확정한 것을 되묻지 않는다
  ([[feedback_escalate_only_rule_residual]], [[feedback_prefill_judgment_escalate_uncertain]]).

동작: 큐의 각 행에서
  - human_decision 있음 → 사용자 판정(그대로).
  - memo 또는 memo_tags 있음 → 사용자 이슈제기(플래그) → 판정 보류(잔여 유지, 내가 재검토).
  - 둘 다 없음 → 사용자 동의 → claude_judgment.polarity 를 human_decision 으로 확정,
    decision_source='user_agreed'(프리필 동의). not_group/None 프리필은 스킵(학습제외).
출력: 동파일 in-place 갱신 + 감사로그. 백업(.bak_agreed260715).
"""
import argparse
import io
import json
import os
import shutil
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
REVIEW = os.path.join(DS, 'eval', 'review')
VALID = {'positive', 'negative', 'neutral', 'not_group'}


def loadl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()]


def prefill_pol(r):
    cj = r.get('claude_judgment')
    if isinstance(cj, dict):
        return cj.get('polarity')
    if isinstance(cj, str):
        return cj
    return r.get('suggested')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('queue')
    ap.add_argument('--apply', action='store_true', help='실제 반영(미지정=DRY-RUN)')
    a = ap.parse_args()
    path = os.path.join(REVIEW, a.queue)
    rows = loadl(path)
    stat = Counter()
    for r in rows:
        if r.get('human_decision') is not None:
            stat['user_decided'] += 1
            continue
        if r.get('memo') or r.get('memo_tags'):
            stat['user_flagged(보류)'] += 1
            continue
        pol = prefill_pol(r)
        if pol not in VALID or pol == 'not_group':
            stat['skip(프리필무효/노그룹)'] += 1
            continue
        stat[f'agreed_{pol}'] += 1
        stat['agreed_total'] += 1
        if a.apply:
            r['human_decision'] = pol
            r['decision_source'] = 'user_agreed'   # 프리필 동의(명시판정 'human'과 구분)
    if a.apply:
        if not os.path.exists(path + '.bak_agreed260715'):
            shutil.copy2(path, path + '.bak_agreed260715')
        with io.open(path, 'w', encoding='utf-8') as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f'[{"반영" if a.apply else "DRY-RUN"}] {a.queue}: {dict(stat)}')


if __name__ == '__main__':
    main()
