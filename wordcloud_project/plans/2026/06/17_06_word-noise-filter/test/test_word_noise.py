# -*- coding: utf-8 -*-
"""0617_06 P1 — 반복 도배 collapse 골든 테스트.

검증:
  1) '성실성실성실성실'(공백 없는 도배) → '성실' 1회만 추출.
  2) 정상 문장의 단어는 그대로 유지.
  3) 공백/다른 형태소로 분리된 정상 반복 언급은 collapse되지 않음(과교정 방지).

KoTE 불요. Kiwi(NLPAnalysis) 1회 로드. 서버·배치 불요.
출력: result/test_word_noise_<date>.md
"""
import os
import sys
from collections import Counter
from datetime import date

HERE = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.config.settings import NLP_CONFIG_PATH  # noqa: E402
from src.modules.nlp_analysis import NLPAnalysis  # noqa: E402


def words_of(analyzer, text):
    res = analyzer.analyze(text)
    mw = res.get('analysis', {}).get('meaningful_words', [])
    return mw if isinstance(mw, list) else []


def main():
    analyzer = NLPAnalysis(config_path=NLP_CONFIG_PATH)
    results = []

    def check(name, text, predicate, detail):
        words = words_of(analyzer, text)
        freq = Counter(words)
        ok = predicate(words, freq)
        results.append((name, ok, text, dict(freq), detail))
        return ok

    # 1) 공백 없는 도배 → 1회
    check('도배_성실x4', '성실성실성실성실',
          lambda w, f: f.get('성실', 0) == 1,
          "성실 1회만 남아야 함(4회 도배 collapse)")

    # 2) 정상 문장 — 단어 유지 (업무는 기존 불용어이므로 비-불용어 명사로 검증)
    check('정상문장', '성실하게 업무를 수행하였고 책임감이 강함',
          lambda w, f: f.get('수행', 0) == 1 and f.get('책임감', 0) == 1,
          "비-불용어 정상 명사(수행·책임감)가 각 1회 추출되어야 함")

    # 3) 공백으로 분리된 정상 반복 → 각각 유지(과교정 방지)
    check('정상반복_공백분리', '성실 성실 성실',
          lambda w, f: f.get('성실', 0) == 3,
          "공백 분리 반복은 collapse되지 않아야 함(별개 언급)")

    # 4) 다른 형태소 사이에 둔 반복 언급 → 유지
    check('정상반복_문장간', '성실하고 또한 성실하게 일함',
          lambda w, f: f.get('성실', 0) == 2,
          "사이에 다른 형태소가 있으면 반복으로 보지 않음")

    write_report(results)
    passed = sum(1 for _, ok, *_ in results if ok)
    print(f'[done] {passed}/{len(results)} 통과')
    for name, ok, text, freq, detail in results:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}: {freq}")


def write_report(results):
    passed = sum(1 for _, ok, *_ in results if ok)
    lines = [
        f'# 반복 도배 collapse 테스트 — {date.today().isoformat()}',
        '',
        f'> 0617_06 P1(§4-1) 골든 케이스. 결과: **{passed}/{len(results)} 통과**',
        '',
        '| 케이스 | 결과 | 입력 | 추출 빈도 | 기대 |',
        '|--------|------|------|-----------|------|',
    ]
    for name, ok, text, freq, detail in results:
        lines.append(f"| {name} | {'✅' if ok else '❌'} | "
                     f"{text.replace('|', '/')} | {freq} | {detail} |")
    lines.append('')
    out = os.path.join(HERE, '..', 'result',
                       f'test_word_noise_{date.today().strftime("%y%m%d")}.md')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'[write] {os.path.abspath(out)}')


if __name__ == '__main__':
    main()
