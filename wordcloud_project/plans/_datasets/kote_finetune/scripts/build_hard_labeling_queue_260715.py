# -*- coding: utf-8 -*-
"""중립경계 하드샘플 라벨링 큐 — group-review 게시판용(사용자 지시 260715: 판정+라벨링 동시).

배경(260715 실측): 배포모델이 에스컬레이션의 68%를 고확신으로 판정하나 중립경계에서
  양방향으로 확신하며 틀림(neu↔neg·neu↔pos) = 오늘 12개 도전자가 막힌 c3 병목과 동일.
  → 확신오류(계통)는 "같은 경계의 일관 라벨 대량"으로만 밀림. 능동학습으로 이 지대를 채굴,
  사용자가 라벨링해 counter-example 볼륨을 만든다.

입력: eval/review/hard_queue_260715.jsonl (mine_hard_samples 산출 300: low_margin+neu_boundary·field100%).
프리필: prefill_hard_queue.judge()(문서화 보수규칙)로 내 판정 1차 — 단 게시판 스키마에 맞춰
  claude_judgment 를 {polarity,reason} 딕셔너리로 출력(문자열이면 '내 판정'열 공란되는 UI버그 회피).
  빈칸 큐 금지(feedback_prefill_judgment_escalate_uncertain): 사용자는 확인/정정만.
정렬: 모델과 불일치(내가 뒤집자는 것) 먼저 → neu_boundary → 확신 높은 순(확신오류 우선).
출력: eval/review/hard_labeling_260715.jsonl (human_decision=null → 게시판 미판정 노출).
재실행 시 rec_id 병합 — 사용자 판정 보존(멱등). 사용자 확정분은 hard gold로 승격(별도 스크립트).
"""
import io
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.abspath(os.path.join(HERE, '..'))
REVIEW = os.path.join(DS, 'eval', 'review')
SRC = os.path.join(REVIEW, 'hard_queue_260715.jsonl')
OUT = os.path.join(REVIEW, 'hard_labeling_260715.jsonl')
sys.path.insert(0, HERE)
from prefill_hard_queue import judge  # noqa: E402  문서화 보수 판정규칙 재사용


def loadl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()] if os.path.exists(p) else []


def main():
    src = loadl(SRC)
    prev = {str(r.get('rec_id')): r for r in loadl(OUT)}
    rows, stat, preserved = [], Counter(), 0

    for r in src:
        text = r.get('text', '')
        model_pol = r['ai_reference']['polarity']
        rule_pol = r.get('cur_rule_label')               # 규칙엔진(문서화 정책 전부) — 프리필 정본
        # 프리필 = 규칙엔진(모델추종 아님). 보수규칙이 추가로 잡아내면 그 근거를 병기.
        jp, jreason = judge(text)
        pol = rule_pol or model_pol
        reason = (f'규칙정책={pol}'
                  + (f'·{jreason}' if jp == pol and jp is not None else '')
                  + (f' vs 모델={model_pol}' if pol != model_pol else '(모델일치)'))
        disagree = bool(rule_pol) and rule_pol != model_pol
        row = {
            'rec_id': r['rec_id'],
            'text': text,
            'field': r.get('field'),
            'cur_rule_label': r.get('cur_rule_label'),      # 현규칙 열
            'ai_reference': r.get('ai_reference'),           # 알고리즘참고 열(모델 확신·tier)
            'claude_judgment': {'polarity': pol, 'reason': reason},  # 내 판정 열(딕셔너리 필수·규칙정책)
            'suggested': pol,
            'suggested_source': 'claude_auto',
            'human_decision': None,                          # 미판정 노출
            'group': r.get('group'),                          # low_margin / neu_boundary
            'source_file': 'hard_queue_260715.jsonl',
            'note': 'hard_labeling_260715',
            '_disagree': disagree,
            '_conf': float(r['ai_reference'].get('confidence') or 0),
            '_tier': r.get('group'),
        }
        old = prev.get(row['rec_id'])
        if old and old.get('human_decision') is not None:
            row['human_decision'] = old['human_decision']
            row['decision_source'] = old.get('decision_source', 'human')
            preserved += 1
        rows.append(row)
        stat['disagree' if disagree else 'follow'] += 1
        stat[f'pol_{pol}'] += 1

    # 정렬: ①내가 뒤집자는 것(확신오류 후보) ②neu_boundary ③확신 높은 순
    rows.sort(key=lambda x: (not x['_disagree'], x['_tier'] != 'neu_boundary', -x['_conf']))

    with io.open(OUT, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    pend = sum(1 for r in rows if r.get('human_decision') is None)
    print(f'하드 라벨링 큐: {len(rows)}행 → review/{os.path.basename(OUT)}')
    print(f'  · 미판정(게시판 노출): {pend} · 사용자판정 보존: {preserved}')
    print(f'  · 내판정≠모델(확신오류 후보·상단): {stat["disagree"]} · 모델추종: {stat["follow"]}')
    print(f'  · 프리필 극성: 긍={stat["pol_positive"]} 부={stat["pol_negative"]} 중={stat["pol_neutral"]}')
    print(f'  · tier: {dict(Counter(r["_tier"] for r in rows))}')
    print(f'\n게시판 파일 선택: hard_labeling_260715.jsonl (0/{len(rows)}로 떠야 정상)')


if __name__ == '__main__':
    main()
