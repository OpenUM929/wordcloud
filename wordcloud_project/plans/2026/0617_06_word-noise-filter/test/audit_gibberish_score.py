# -*- coding: utf-8 -*-
"""0617_06 P2 — Gibberish 후보 코퍼스 감사 (비-🟡, 분석 전용).

목적(§4-2): 임계값을 추측으로 정하기 전에, 실제 코퍼스에서
  - NNP/SL 태그 토큰의 음절당 score 분포
  - 고립 자모(ㄱ~ㅎ, ㅏ~ㅣ 등 완성형 아닌 호환 자모) 포함 토큰
가 얼마나 존재하는지 **표본 수를 먼저 보고**한다. 표본이 희소하면
score 임계값 보정은 보류하고 결정적 자모 신호를 보조로 검토한다.

입력: data/new_260617.csv (dev에서 acquired_sentences=0건이므로 CSV 단독, §8-4 결정).
KoTE 불요. Kiwi 직접 사용. 출력: result/gibberish_audit_<date>.md
"""
import csv
import os
import sys
import unicodedata
from collections import Counter
from datetime import date

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
REPO_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, '..'))
sys.path.insert(0, PROJECT_ROOT)

DEFAULT_CSV = os.path.join(REPO_ROOT, 'data', 'new_260617.csv')

# 호환 자모(고립된 단일 ㄱ/ㅏ 등) 범위
_JAMO_RANGES = [(0x3130, 0x318F)]


def has_isolated_jamo(s):
    return any(any(lo <= ord(ch) <= hi for lo, hi in _JAMO_RANGES) for ch in s)


def syllable_ratio(s):
    """완성형 한글 음절(가~힣) 비율 — 정상 한국어 토큰은 1.0에 가까움."""
    if not s:
        return 0.0
    hangul = sum(1 for ch in s if 0xAC00 <= ord(ch) <= 0xD7A3)
    return hangul / len(s)


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    if not os.path.exists(csv_path):
        print(f'[error] CSV 없음: {csv_path}')
        sys.exit(1)

    from kiwipiepy import Kiwi
    kiwi = Kiwi()

    rows = list(csv.DictReader(open(csv_path, encoding='utf-8-sig')))

    nnp_sl = []           # (form, tag, score, len, per_char_score)
    jamo_tokens = []      # 고립 자모 포함 토큰
    tag_ct = Counter()
    total_tokens = 0

    for r in rows:
        text = (r.get('sentence_text') or '').strip()
        if not text:
            continue
        for tok in kiwi.tokenize(text):
            total_tokens += 1
            tag = tok.tag
            tag_str = tag if isinstance(tag, str) else (tag.name if hasattr(tag, 'name') else str(tag).split('.')[-1])
            tag_ct[tag_str] += 1
            form = tok.form
            if has_isolated_jamo(form):
                jamo_tokens.append((form, tag_str, round(tok.score, 2)))
            if tag_str in ('NNP', 'SL') and len(form) > 1:
                per_char = tok.score / max(len(form), 1)
                nnp_sl.append((form, tag_str, round(tok.score, 2),
                               len(form), round(per_char, 2)))

    write_report(csv_path, len(rows), total_tokens, tag_ct, nnp_sl, jamo_tokens)
    print(f'[done] 문장 {len(rows)} · 토큰 {total_tokens}')
    print(f'  NNP/SL(len>1) 후보: {len(nnp_sl)}건 · 고립자모 토큰: {len(jamo_tokens)}건')


def _tbl(items, cols, fmt):
    out = ['| ' + ' | '.join(cols) + ' |', '|' + '|'.join('---' for _ in cols) + '|']
    out += [fmt(i) for i in items]
    return '\n'.join(out)


def write_report(csv_path, n_rows, total_tokens, tag_ct, nnp_sl, jamo_tokens):
    # per_char score 오름차순(가장 의심스러운 것부터)
    nnp_sorted = sorted(nnp_sl, key=lambda x: x[4])
    # per_char 구간 히스토그램
    bins = Counter()
    for *_, per_char in [(f, t, s, l, pc) for f, t, s, l, pc in nnp_sl]:
        b = int(per_char // 5) * 5
        bins[b] += 1

    lines = [
        f'# Gibberish 후보 감사 — {date.today().isoformat()}',
        '',
        f'> 입력: `{os.path.relpath(csv_path, REPO_ROOT)}` · 0617_06 §4-2 P2',
        '> 목적: 임계값 확정 전 **표본 수**를 먼저 확인(데이터 기아 여부 판단).',
        '',
        '## 요약',
        '',
        f'- 문장 수: **{n_rows}** · 전체 토큰: **{total_tokens}**',
        f'- NNP/SL(len>1) 후보 토큰: **{len(nnp_sl)}**',
        f'- 고립 자모 포함 토큰: **{len(jamo_tokens)}**',
        '',
        '## NNP/SL per-char score 히스토그램 (구간별 건수)',
        '',
        _tbl(sorted(bins.items()), ['per_char score 구간', '건수'],
             lambda kv: f'| {kv[0]} ~ {kv[0] + 5} | {kv[1]} |'),
        '',
        '## per-char score 최저 30건 (gibberish 의심 상위)',
        '',
        _tbl(nnp_sorted[:30], ['form', 'tag', 'score', 'len', 'per_char'],
             lambda x: f'| {x[0]} | {x[1]} | {x[2]} | {x[3]} | {x[4]} |'),
        '',
        '## 고립 자모 포함 토큰 (결정적 신호 후보)',
        '',
    ]
    if jamo_tokens:
        lines.append(_tbl(jamo_tokens[:40], ['form', 'tag', 'score'],
                          lambda x: f'| {x[0]} | {x[1]} | {x[2]} |'))
    else:
        lines.append('_없음._')
    lines.append('')
    out = os.path.join(HERE, '..', 'result',
                       f'gibberish_audit_{date.today().strftime("%y%m%d")}.md')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'[write] {os.path.abspath(out)}')


if __name__ == '__main__':
    main()
