# -*- coding: utf-8 -*-
"""리더십 게이트 운영 검증 (코퍼스 회귀) — 계획서 §12-8 Step 1.

목적:
  refine_diag_260617.csv(475문장)에서 리더십 표지(긍정/부정)를 가진 문장을 뽑아,
  leadership_analysis 게이트의 전(legacy: polarity=neutral 강제)/후(실제 polarity)
  점수를 비교한다. KoTE는 1회만 로드하며 DB/배치/서버를 건드리지 않는다.

검증 기준(핵심가치: 긍↔부 오분류만 방지):
  A) 긍정표지 문장        → polarity != negative → 점수 불변(회귀 안전)
  B) negation 칭찬(부정의 부정) → polarity == positive → 0점화 금지
  C) 진짜 부정            → polarity == negative → 0점(개선영역)

출력: result/리더십게이트_회귀_260617.md
"""
import csv
import os
import sys

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, ROOT)

from src.modules.hr_context_lexicon import (
    leadership_polarity,
    NEGATIVE_MARKERS,
    POSITIVE_MARKERS,
    _has_negation_after,
)

CSV_PATH = os.path.join(HERE, '..', 'result', 'refine_diag_260617.csv')
OUT_PATH = os.path.join(HERE, '..', 'result', '리더십게이트_회귀_260617.md')


def classify_flags(text):
    """문장의 (진짜부정 여부, negation칭찬 여부, 긍정표지 여부)를 재현한다."""
    has_real_negative = False
    has_negated_praise = False
    for marker in NEGATIVE_MARKERS:
        idx = 0
        while True:
            pos = text.find(marker, idx)
            if pos == -1:
                break
            after = pos + len(marker)
            if _has_negation_after(text, after):
                has_negated_praise = True
            else:
                has_real_negative = True
            idx = after
    has_positive = any(m in text for m in POSITIVE_MARKERS)
    return has_real_negative, has_negated_praise, has_positive


def load_marker_sentences():
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            text = (r.get('sentence_text') or '').strip()
            if not text:
                continue
            real_neg, neg_praise, has_pos = classify_flags(text)
            if not (real_neg or neg_praise or has_pos):
                continue  # 리더십 표지 없는 문장은 검증 대상 아님(중립, 게이트 영향 0)
            rows.append({
                'id': r.get('id', ''),
                'text': text,
                'real_neg': real_neg,
                'neg_praise': neg_praise,
                'has_pos': has_pos,
                'polarity': leadership_polarity(text),
                'corrected_label': r.get('corrected_label', ''),
            })
    return rows


def overall_score(la, text, polarity):
    """analyze 한 번 분량의 감정결과로 6역량 평균 점수를 계산한다(게이트 polarity 적용)."""
    emo = la._analyze_emotions(text)
    total = 0.0
    for info in la.leadership_competencies.values():
        total += la._calculate_competency_score(text, emo, info, polarity) * info['weight']
    return round(total / len(la.leadership_competencies), 3)


def main():
    rows = load_marker_sentences()
    print(f'[load] 표지 보유 문장 {len(rows)}건 — KoTE 로드 시작...')

    from src.modules.leadership_analysis import LeadershipAnalysis
    la = LeadershipAnalysis()
    print('[load] KoTE 로드 완료. 점수 계산 중...')

    cat = {'positive_marker': [], 'negation_praise': [], 'real_negative': []}
    for row in rows:
        legacy = overall_score(la, row['text'], 'neutral')   # 게이트 전
        gated = overall_score(la, row['text'], row['polarity'])  # 게이트 후
        row['legacy'] = legacy
        row['gated'] = gated
        row['delta'] = round(gated - legacy, 3)
        if row['real_neg']:
            cat['real_negative'].append(row)
        elif row['neg_praise']:
            cat['negation_praise'].append(row)
        else:
            cat['positive_marker'].append(row)

    # 검증
    fails = []
    for row in cat['positive_marker']:
        if row['delta'] != 0.0:
            fails.append(('A 긍정표지 점수변동', row))
    for row in cat['negation_praise']:
        if row['gated'] == 0.0 and row['legacy'] > 0.0:
            fails.append(('B negation칭찬 0점화', row))
        if row['polarity'] != 'positive':
            fails.append(('B negation칭찬 극성오류', row))
    for row in cat['real_negative']:
        if row['polarity'] != 'negative':
            fails.append(('C 진짜부정 미검출', row))
        if row['gated'] != 0.0:
            fails.append(('C 진짜부정 미차단', row))

    write_report(cat, fails)
    print(f'[done] 표지문장 {len(rows)} | 긍정표지 {len(cat["positive_marker"])} '
          f'negation칭찬 {len(cat["negation_praise"])} 진짜부정 {len(cat["real_negative"])}')
    if fails:
        print(f'[FAIL] 위반 {len(fails)}건')
        for tag, row in fails:
            print(f'  - {tag}: id={row["id"]} {row["text"][:30]} '
                  f'(pol={row["polarity"]} legacy={row["legacy"]} gated={row["gated"]})')
        sys.exit(1)
    print('[OK] 전체 기준 통과 — 긍↔부 오분류 0, 회귀 안전')


def _table(rows):
    lines = ['| id | 문장 | polarity | 게이트전 | 게이트후 | Δ | corrected |',
             '|----|------|----------|---------|---------|---|-----------|']
    for r in sorted(rows, key=lambda x: x['delta']):
        t = r['text'].replace('|', '\\|')
        if len(t) > 40:
            t = t[:40] + '…'
        lines.append(f"| {r['id']} | {t} | {r['polarity']} | {r['legacy']} | "
                     f"{r['gated']} | {r['delta']} | {r['corrected_label']} |")
    return '\n'.join(lines)


def write_report(cat, fails):
    pm, npz, rn = cat['positive_marker'], cat['negation_praise'], cat['real_negative']
    status = '✅ 통과' if not fails else f'❌ 위반 {len(fails)}건'
    out = f"""# 리더십 게이트 운영 검증 (코퍼스 회귀) — 2026-06-17

> 계획서 §12-8 Step 1. KoTE 1회 로드, DB/배치/서버 미사용.
> 데이터: `result/refine_diag_260617.csv` (475문장 중 리더십 표지 보유분).
> 게이트 전 = polarity를 neutral로 강제(레거시 동작), 게이트 후 = 실제 polarity 적용.

## 결과 요약: {status}

| 분류 | 문장수 | 기대 | 결과 |
|------|--------|------|------|
| A. 긍정표지 | {len(pm)} | 점수 불변(Δ=0) | {'전부 Δ=0' if all(r['delta']==0.0 for r in pm) else '변동 발생'} |
| B. negation 칭찬(부정의 부정) | {len(npz)} | positive·0점화 금지 | {'보존' if all(r['polarity']=='positive' for r in npz) else '극성오류'} |
| C. 진짜 부정 | {len(rn)} | negative·0점 차단 | {'전부 0점화' if all(r['gated']==0.0 for r in rn) else '미차단'} |

핵심가치(긍↔부 오분류만 방지) 위반: **{len(fails)}건**

## C. 진짜 부정 — 게이트로 강점 가점 차단(개선영역)

{_table(rn)}

## B. negation 칭찬 — 게이트 무영향(긍정 보존)

{_table(npz)}

## A. 긍정표지 — 게이트 무영향(회귀 안전)

{_table(pm)}
"""
    if fails:
        out += '\n## ⚠ 위반 상세\n\n'
        for tag, r in fails:
            out += f"- **{tag}** id={r['id']} `{r['text'][:50]}` (pol={r['polarity']} legacy={r['legacy']} gated={r['gated']})\n"
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'[write] {OUT_PATH}')


if __name__ == '__main__':
    main()
