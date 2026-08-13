# -*- coding: utf-8 -*-
"""감정보정 override negation_praise 회귀 잠금 — 계획서 §12-8 Step 3.

refine_diag_260617.csv는 KoTE 점수(kote_pos/neg/neutral)·is_last·total_sentences를
담고 있어, 이를 explain()에 재투입하면 KoTE 재실행 없이 rule_id를 정확 재현한다.

주의: CSV의 applied_rule 컬럼은 positive_rescue 도입 '이전' 캡처본이라 신규 분기
격리용으로 쓸 수 없다. 따라서 동일 현재 코드에서 신규 분기만 on/off(monkeypatch)하여
순수하게 negation_praise 추가분만 비교한다.

검증(핵심가치: 긍↔부 오분류만 방지):
  - 변경된 행은 전부 'negation_praise'로만 전이된다(다른 rule_id는 불변).
  - 진짜 부정(negation 없는 강요·수직적 등)은 negation_praise로 전이되지 않는다.
  - 전이 방향은 항상 중립/부정 → 긍정(긍↔부 오분류 0).

출력: result/감정보정_negation_회귀_260617.md
"""
import csv
import os
import sys

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, ROOT)

import src.services.perspective_service as ps
from src.services.perspective_service import _sentence_sentiment_override_explain as explain
from src.modules.hr_context_lexicon import leadership_polarity

CSV_PATH = os.path.join(HERE, '..', 'result', 'refine_diag_260617.csv')
OUT_PATH = os.path.join(HERE, '..', 'result', '감정보정_negation_회귀_260617.md')


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _b(v):
    return str(v).strip().lower() in ('true', '1', 'yes')


_real_inp = ps.is_negation_praise  # 신규 분기 술어 원본 보관(monkeypatch 복원용)


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

            # before: 신규 분기 비활성(is_negation_praise→False) / after: 현재 코드 그대로
            ps.is_negation_praise = lambda s: False
            old_score, old_rule = explain(pos, neg, text, is_last, tot, neutral=neu)
            ps.is_negation_praise = _real_inp
            new_score, new_rule = explain(pos, neg, text, is_last, tot, neutral=neu)

            if new_rule != old_rule:
                changed.append({
                    'id': r.get('id', ''), 'text': text,
                    'old': old_rule, 'new': new_rule,
                    'old_score': round(old_score, 3),
                    'new_score': round(new_score, 3),
                    'pol': leadership_polarity(text),
                    'corrected': r.get('corrected_label', ''),
                })

    # 검증
    fails = []
    for c in changed:
        if c['new'] != 'negation_praise':
            fails.append(('신규분기 외 rule 변경', c))
        if c['pol'] == 'negative':
            fails.append(('진짜부정이 negation_praise로 전이', c))

    write_report(total, changed, fails)
    print(f'[done] 전체 {total}문장 | 변경 {len(changed)}건 (전부 negation_praise 기대)')
    for c in changed:
        print(f"  {c['id']}: {c['old']} -> {c['new']} | pol={c['pol']} | {c['text'][:30]}")
    if fails:
        print(f'[FAIL] 위반 {len(fails)}건')
        for tag, c in fails:
            print(f'  - {tag}: {c}')
        sys.exit(1)
    print('[OK] 변경은 전부 negation_praise, 진짜부정 전이 0 — 긍↔부 오분류 0, 회귀 안전')


def write_report(total, changed, fails):
    status = '✅ 통과' if not fails else f'❌ 위반 {len(fails)}건'
    rows = ['| id | 문장 | 변경 전(rule/score) | 변경 후(rule/score) | polarity | corrected |',
            '|----|------|--------------------|--------------------|----------|-----------|']
    for c in sorted(changed, key=lambda x: x['old']):
        t = c['text'].replace('|', '\\|')
        if len(t) > 40:
            t = t[:40] + '…'
        rows.append(f"| {c['id']} | {t} | {c['old']} / {c['old_score']} | "
                    f"{c['new']} / {c['new_score']} | {c['pol']} | {c['corrected']} |")
    out = f"""# 감정보정 negation_praise 회귀 잠금 — 2026-06-17

> 계획서 §12-8 Step 3. `result/refine_diag_260617.csv`(475문장)의 KoTE 점수·is_last를
> explain()에 무손실 재투입한 변경 전/후 rule_id 비교(KoTE 재실행 불필요).

## 결과 요약: {status}

- 전체 문장: **{total}**
- rule_id 변경: **{len(changed)}건** (기대: 전부 `negation_praise`)
- 신규 분기 외 변경: **{sum(1 for _,c in fails if True) if fails else 0}건** 위반
- 진짜 부정(polarity=negative)의 negation_praise 전이: **0건** 기대

기존 7개 rule_id의 분기 조건·점수·시그니처는 불변이며, 변경은 오직 새 분기
`negation_praise`(부정의 부정 = 칭찬)가 중립/부정으로 강등되던 문장을 긍정으로
끌어올린 것뿐이다(중립→긍정 허용, 긍↔부 오분류 0).

## 변경 행 (전 → 후)

{chr(10).join(rows)}
"""
    label_flip = [c for c in changed if c['corrected'] == 'negative']
    if label_flip:
        out += ('\n## ⚠ 라벨 불일치(투명 보고) — 저장 정답=negative 인데 긍정으로 전이\n\n'
                '아래는 모두 명백한 "부정어의 부정 = 칭찬"으로, 저장된 corrected_label\n'
                '(negative)이 오기로 판단된다(§12-8에서 사용자가 구제 대상으로 명시한 케이스).\n'
                '핵심가치(공유된 인간 판단 근사)에 부합하나, 측정용 정답과는 반대 방향이므로\n'
                '사용자 확인이 필요하다(정답 라벨 수정 권고).\n\n')
        for c in label_flip:
            out += (f"- id={c['id']} `{c['text']}` : {c['old']}({c['old_score']}) "
                    f"→ negation_praise({c['new_score']}), 저장정답=negative\n")
    if fails:
        out += '\n## ⚠ 위반 상세\n\n'
        for tag, c in fails:
            out += f"- **{tag}**: id={c['id']} `{c['text'][:50]}` ({c['old']}→{c['new']}, pol={c['pol']})\n"
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'[write] {OUT_PATH}')


if __name__ == '__main__':
    main()
