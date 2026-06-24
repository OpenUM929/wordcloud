# -*- coding: utf-8 -*-
"""규칙/패턴 마이너 — 데이터셋에서 '판정을 정확하게 만들 규칙·패턴 후보'를 발굴.

목적(사용자 요구): 데이터셋은 입력일 뿐이고, 진짜 산출은 **거기서 규칙·패턴을 찾아
다면평가 판정을 정확하게** 만드는 것이다. 본 모듈은 RUNBOOK §2-5(규칙 재마이닝)를
수기 단계가 아니라 파이프라인의 1급 단계로 자동화한다.

⚠️ 발굴은 **후보 제시까지만**. 어휘집/규칙 자동 수정 금지(추측 분류 금지). 후보는
   `hr_context_lexicon`/`perspective_service`에 사람이 additive append + 회귀 통과 후에만
   반영한다(긍↔부 0 유지). 본 모듈은 근거 건수·예문이 있는 '발굴 리포트'를 만든다.

발굴 구역(오분류가 몰리는 곳):
  A. 규칙이 KoTE argmax를 뒤집는 지점(특히 긍↔부 방향) — 과/미보정 감사.
  B. 긍정표지 + 직후 negation(§9 패턴) — 상쇄명사 유무로 분기, 신규 CANCEL_NOUN 후보.
  C. 긍정표지 + 결핍명사(부족/부재/결여/미흡/소홀) — 지배적 부→긍 위험.
  D. 어떤 표지도 매칭 안 되는데 KoTE는 확신(|pos-neg|>0.5) — 신규 표지 후보(빈출 bigram).
  E. 절 분리 후에도 남은 반전 표지(혼합 잔존) — 분리기 개선 후보.

O(n)·서버/모델 불요. plans 배포 제외.
"""
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

# 결핍명사(긍정표지 뒤에 오면 부→긍 위험) / 상쇄명사(negation을 흡수 → 칭찬 유지)
DEFICIENCY_NOUNS = ['부족', '부재', '결여', '미흡', '소홀', '저조', '미달', '결핍']
CANCEL_NOUNS = ['문제', '부족', '어려움', '이슈', '걱정', '불만', '갈등',
                '미흡', '결여', '부재', '거리낌', '차질', '흠', '하자']
NEGATION_TOKENS = ['않', '없', '아니', '안 ', '안한', '안하', '못하', '못 ']
_POS_NEG_WINDOW = 12

_NOUN_BIGRAM = re.compile(r'[가-힣]{2,}')


def _label_from_kote(pos, neg):
    if pos > neg:
        return 'positive'
    if neg > pos:
        return 'negative'
    return 'neutral'


def _has_negation_near(text, after):
    return any(t in text[after:after + _POS_NEG_WINDOW] for t in NEGATION_TOKENS)


def mine(records, pos_markers, neg_markers, examples_per=4):
    """records(list of dict: text, kote=[pos,neg,neu], sentiment, applied_rule) → 발굴 결과 dict.

    pos_markers/neg_markers = 현재 어휘집(이미 커버된 표지) — 신규 후보 분리용.
    """
    res = {
        'n': len(records),
        'rule_flips': Counter(),          # applied_rule -> kote→override 방향이 바뀐 수
        'pol_flips': [],                  # 긍↔부 방향 뒤집기(최우선 감사)
        'pos_neg_criticism': [],          # B: 긍정표지+negation, 상쇄명사 없음(비판 후보)
        'pos_neg_cancel': [],             # B: 긍정표지+negation, 상쇄명사 있음(칭찬 유지)
        'deficiency': [],                 # C: 긍정표지+결핍명사
        'new_marker_grams': Counter(),    # D: 미매칭+고확신 문장의 빈출 표현
        'residual_contrast': 0,           # E: 반전표지 잔존(분리 실패 후보)
        'examples': {},
    }
    ex = {k: [] for k in ('pol_flips', 'pos_neg_criticism', 'pos_neg_cancel',
                          'deficiency', 'new_marker_grams', 'residual_contrast')}
    contrast_re = ['지만', '으나', '하지만', '그러나', '반면', '에도 불구']

    for r in records:
        text = r.get('text') or ''
        pos, neg = (r.get('kote') or [0, 0, 0])[:2]
        rule = r.get('applied_rule') or '(none)'
        kote_label = _label_from_kote(pos, neg)
        ov_label = r.get('sentiment') or kote_label

        # A. 규칙이 KoTE 방향을 뒤집음
        if ov_label != kote_label:
            res['rule_flips'][rule] += 1
            if {kote_label, ov_label} == {'positive', 'negative'}:
                res['pol_flips'].append((rule, kote_label, ov_label, text))
                if len(ex['pol_flips']) < examples_per * 3:
                    ex['pol_flips'].append(f"[{rule}] {kote_label}→{ov_label}: {text[:60]}")

        # B/C. 긍정표지 뒤 negation / 결핍명사
        for m in pos_markers:
            mp = text.find(m)
            if mp == -1:
                continue
            after = mp + len(m)
            tail = text[after:after + _POS_NEG_WINDOW]
            if any(d in tail for d in DEFICIENCY_NOUNS):
                res['deficiency'].append((m, text))
                if len(ex['deficiency']) < examples_per:
                    ex['deficiency'].append(f"표지'{m}'+결핍: {text[:60]}")
                break
            if _has_negation_near(text, after):
                if any(c in tail for c in CANCEL_NOUNS):
                    res['pos_neg_cancel'].append((m, text))
                    if len(ex['pos_neg_cancel']) < examples_per:
                        ex['pos_neg_cancel'].append(f"표지'{m}'+상쇄+neg(칭찬유지): {text[:60]}")
                else:
                    res['pos_neg_criticism'].append((m, text))
                    if len(ex['pos_neg_criticism']) < examples_per:
                        ex['pos_neg_criticism'].append(f"표지'{m}'+neg(비판후보): {text[:60]}")
                break

        # D. 미매칭 + 고확신 → 신규 표지 후보
        has_marker = any(m in text for m in pos_markers) or any(m in text for m in neg_markers)
        if not has_marker and abs(pos - neg) > 0.5:
            for g in _NOUN_BIGRAM.findall(text):
                if 2 <= len(g) <= 6:
                    res['new_marker_grams'][g] += 1

        # E. 반전표지 잔존(절 분리가 못 쪼갠 혼합)
        if sum(c in text for c in contrast_re) >= 1 and r.get('is_clause'):
            res['residual_contrast'] += 1
            if len(ex['residual_contrast']) < examples_per:
                ex['residual_contrast'].append(text[:60])

    res['examples'] = ex
    return res


def write_report(path, res, date_tag):
    """발굴 결과를 마크다운 리포트로 기록(가명화 예문 짧게)."""
    L = [
        f'# 규칙/패턴 발굴 리포트 — {date_tag}',
        '',
        '> 데이터셋에서 다면평가 판정을 정밀화할 **규칙·패턴 후보**를 발굴(RUNBOOK §2-5 자동화).',
        '> ⚠️ 후보 제시까지만 — 어휘집/규칙 반영은 사람 additive append + 회귀(긍↔부 0) 통과 후에만.',
        '',
        f'- 분석 레코드: **{res["n"]}**',
        '',
        '## A. 규칙이 KoTE 방향을 뒤집은 지점 (과/미보정 감사)',
        '',
    ]
    L.append('| applied_rule | flip 수 |')
    L.append('|---|---|')
    for rule, c in res['rule_flips'].most_common():
        L.append(f'| {rule} | {c} |')
    L += ['',
          f'### 🔴 긍↔부 방향 뒤집기 (최우선 감사): **{len(res["pol_flips"])}건**',
          '> 규칙이 KoTE 긍↔부를 반대로 뒤집은 행. 규칙이 교정한 것인지 망친 것인지 표본 확인 필수.', '']
    for line in res['examples']['pol_flips']:
        L.append(f'- {line}')
    L += ['',
          '## B. 긍정표지 + 직후 negation (§9 패턴)',
          '',
          f'- 비판 후보(상쇄명사 없음, 부→긍 위험): **{len(res["pos_neg_criticism"])}**',
          f'- 칭찬 유지(상쇄명사 있음): **{len(res["pos_neg_cancel"])}**',
          '']
    for line in res['examples']['pos_neg_criticism']:
        L.append(f'- (비판후보) {line}')
    for line in res['examples']['pos_neg_cancel']:
        L.append(f'- (칭찬유지) {line}')
    L += ['',
          '## C. 긍정표지 + 결핍명사(부족/부재/결여/미흡/소홀) — 지배적 부→긍 위험',
          '',
          f'- 해당 행: **{len(res["deficiency"])}**', '']
    for line in res['examples']['deficiency']:
        L.append(f'- {line}')
    L += ['',
          '## D. 미매칭 + 고확신 문장의 빈출 표현 (신규 표지 후보)',
          '> 현 어휘집이 못 잡는데 KoTE는 확신(|pos-neg|>0.5)한 문장의 빈출 명사구. 표지 승격 후보(근거 검토 후).',
          '', '| 표현 | 빈도 |', '|---|---|']
    for g, c in res['new_marker_grams'].most_common(30):
        L.append(f'| {g} | {c} |')
    L += ['',
          '## E. 절 분리 후 반전표지 잔존 (분리기 개선 후보)',
          '',
          f'- 잔존 행: **{res["residual_contrast"]}**', '']
    for line in res['examples']['residual_contrast']:
        L.append(f'- {line}')
    L += ['',
          '## 다음 행동(사람 검토 큐)',
          '- A 긍↔부 flip + B 비판후보 + C 결핍 → **최우선** 표본 감사 → 규칙 보강/회귀.',
          '- D 빈출 표현 → 신규 표지 후보(코퍼스 근거 확인 후 additive).',
          '- E 잔존 → split_clauses 연결어미 보강 후보.', '']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
