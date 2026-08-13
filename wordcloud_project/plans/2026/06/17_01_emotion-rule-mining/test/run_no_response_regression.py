# -*- coding: utf-8 -*-
"""감정보정 override no_response_neutral 회귀 잠금 — §0-A #2(무응답 중립화).

refine_diag_260617.csv의 KoTE 점수(kote_pos/neg/neutral)·is_last·total_sentences를
explain()에 무손실 재투입해 KoTE 재실행 없이 rule_id를 정확 재현한다.

격리: 동일 현재 코드에서 신규 술어 is_no_response만 on/off(monkeypatch)하여
순수하게 no_response_neutral 추가분만 비교한다(다른 변경 영향 배제).

검증(핵심가치: 긍↔부 오분류만 방지):
  - 변경된 행은 전부 'no_response_neutral'로만 전이된다(다른 rule_id 불변).
  - 전이 방향은 부정/중립 → 중립(0.0)뿐. 긍정으로의 전이 0, 긍정에서의 전이 0.
  - 이미 중립이던 낙서(neutral_dominant)는 불변(neutral_dominant가 선행 처리).

출력: result/감정보정_무응답_회귀_260617.md
"""
import csv
import os
import sys

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, ROOT)

import src.services.perspective_service as ps
from src.services.perspective_service import _sentence_sentiment_override_explain as explain

CSV_PATH = os.path.join(HERE, '..', 'result', 'refine_diag_260617.csv')
OUT_PATH = os.path.join(HERE, '..', 'result', '감정보정_무응답_회귀_260617.md')


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _b(v):
    return str(v).strip().lower() in ('true', '1', 'yes')


def _label(score):
    if score > 1e-6:
        return 'positive'
    if score < -1e-6:
        return 'negative'
    return 'neutral'


_real_inp = ps.is_no_response  # 신규 술어 원본 보관(monkeypatch 복원용)


def main():
    changed = []
    total = 0
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            text = (r.get('sentence_text') or '').strip()
            if not text:
                continue
            total += 1
            pos = _f(r.get('kote_pos'))
            neg = _f(r.get('kote_neg'))
            neu = _f(r.get('kote_neutral'))
            is_last = _b(r.get('is_last'))
            tot = int(_f(r.get('total_sentences'), 1))

            # before: 신규 분기 비활성 / after: 현재 코드 그대로
            ps.is_no_response = lambda s: False
            old_score, old_rule = explain(pos, neg, text, is_last, tot, neutral=neu)
            ps.is_no_response = _real_inp
            new_score, new_rule = explain(pos, neg, text, is_last, tot, neutral=neu)

            if new_rule != old_rule or abs(new_score - old_score) > 1e-9:
                changed.append({
                    'id': r.get('id', ''), 'text': text,
                    'old': old_rule, 'new': new_rule,
                    'old_score': round(old_score, 3), 'new_score': round(new_score, 3),
                    'old_label': _label(old_score), 'new_label': _label(new_score),
                })

    # 검증
    fails = []
    for c in changed:
        if c['new'] != 'no_response_neutral':
            fails.append(('신규분기 외 rule 변경', c))
        if c['new_label'] != 'neutral':
            fails.append(('중립 아닌 결과로 전이', c))
        if c['old_label'] == 'positive':
            fails.append(('긍정이 중립화됨(긍↔부/긍 손실)', c))

    write_report(total, changed, fails)
    print(f'[done] 전체 {total}문장 | 변경 {len(changed)}건 (전부 no_response_neutral→중립 기대)')
    for c in sorted(changed, key=lambda x: int(x['id'] or 0)):
        print(f"  {c['id']}: {c['old']}({c['old_score']}) -> {c['new']}({c['new_score']}) "
              f"| {c['old_label']}->{c['new_label']} | {c['text'][:30]}")
    if fails:
        print(f'[FAIL] 위반 {len(fails)}건')
        for tag, c in fails:
            print(f'  - {tag}: {c}')
        sys.exit(1)
    print('[OK] 변경은 전부 no_response_neutral→중립, 긍정 손실 0, 긍↔부 오분류 0')


def write_report(total, changed, fails):
    status = '✅ 통과' if not fails else f'❌ 위반 {len(fails)}건'
    rows = ['| id | 문장 | 변경 전(rule/score) | 변경 후(rule/score) | 라벨 전→후 |',
            '|----|------|--------------------|--------------------|-----------|']
    for c in sorted(changed, key=lambda x: int(x['id'] or 0)):
        t = c['text'].replace('|', '\\|')
        if len(t) > 40:
            t = t[:40] + '…'
        rows.append(f"| {c['id']} | {t} | {c['old']} / {c['old_score']} | "
                    f"{c['new']} / {c['new_score']} | {c['old_label']}→{c['new_label']} |")
    neg2neu = sum(1 for c in changed if c['old_label'] == 'negative')
    out = f"""# 감정보정 no_response_neutral 회귀 잠금 — 2026-06-17

> §0-A #2(무응답 중립화). `result/refine_diag_260617.csv`(475문장)의 KoTE 점수·is_last를
> explain()에 무손실 재투입한 변경 전/후 비교(신규 술어 is_no_response on/off 격리).

## 결과 요약: {status}

- 전체 문장: **{total}**
- 변경: **{len(changed)}건** (기대: 전부 `no_response_neutral`로 전이, 결과=중립)
  - 부정→중립 교정: **{neg2neu}건** (중립→부정 오분류 제거)
- 신규 분기 외 변경: **{sum(1 for t, _ in fails if t == '신규분기 외 rule 변경')}건** 위반
- 긍정 손실(긍→중): **{sum(1 for t, _ in fails if t.startswith('긍정'))}건** 위반

기존 rule_id의 분기 조건·점수·`sentence_sentiment_override` 시그니처는 불변이며, 변경은 오직
새 분기 `no_response_neutral`(평가불가/내용없음/낙서)이 부정으로 강등되던 비평가 문장을
중립으로 되돌린 것뿐이다(중립→부정 오류 제거, 긍↔부 오분류 0). 이미 중립이던 낙서
(neutral_dominant)는 선행 처리되어 불변이다.

## 변경 행 (전 → 후)

{chr(10).join(rows)}
"""
    if fails:
        out += '\n## ⚠ 위반 상세\n\n'
        for tag, c in fails:
            out += f"- **{tag}**: id={c['id']} `{c['text'][:50]}` ({c['old']}→{c['new']})\n"
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'[write] {OUT_PATH}')


if __name__ == '__main__':
    main()
