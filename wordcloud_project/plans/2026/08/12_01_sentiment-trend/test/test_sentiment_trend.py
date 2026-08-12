"""12_01_sentiment-trend — 연도별 긍정/부정 추이 집계·차트 렌더 검증.

dev 환경에는 실배치 데이터가 없으므로(원데이터는 내부망 전용) 합성 데이터로 검증한다.
문장 점수 계산기(_get_sentence_level_scores)는 KoTE/HR 모델에 의존하므로
결정적 스텁으로 대체하고, **이번 작업에서 신규 작성한 집계 로직**만 검증한다.

검증 항목
  A. 연도별 분리 — row_values 로 준 연도마다 독립 집계되는가
  B. 중립 제외 — 문장 점수 0 은 긍정에도 부정에도 들어가지 않는가
  C. 중복 문장 1회 — save_to_deploy 와 동일하게 앞 80자 기준 중복 제거되는가
  D. 결측 연도 — 평가가 없는 연도는 None(선 끊김) + skipped_rows 기록인가
  E. 백분율 — 분모가 긍정+부정이고 합이 100 인가
  F. 단어 기준 경계 — score >= 0 이 긍정(중립 단어 포함), < 0 이 부정인가
  G. 차트 렌더 — PNG 파일이 실제로 생성되는가

실행: python test_sentiment_trend.py
"""
import os
import sys
import tempfile

_APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..'))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

from src.services import perspective_service as ps


# ── 합성 데이터 ──────────────────────────────────────────────────────────────
def _ev(year, doc, words):
    return {
        'evaluation': {
            'evaluation_id': f'E{year}-{abs(hash(doc)) % 1000}',
            '_db_id': abs(hash(doc)) % 100000,
            'evaluation_date': f'{year}0601',
            'evaluation_document': doc,
            'nlp_analysis_results': {'analysis': {
                'meaningful_words': words,
                'meaningful_words_with_pos': [[w, 'Noun'] for w in words],
            }},
        },
        'employee_id': 'EMP001',
    }


# 2024: 긍정 문장 2 · 부정 문장 1 · 중립 문장 1
# 2026: 긍정 문장 1 · 부정 문장 2
# 2025: 평가 없음 (결측 연도)
ITEMS = [
    _ev(2024, '업무를 좋게 처리한다. 협업이 좋다. 보고가 부족하다. 담당 업무를 수행한다.',
        ['업무', '협업', '보고']),
    _ev(2024, '업무를 좋게 처리한다.', ['업무']),          # 중복 문장(C)
    _ev(2026, '소통이 좋다. 일정이 부족하다. 대응이 부족하다.',
        ['소통', '일정', '대응']),
]


def _stub_sentence_scores(doc, threshold=0.20, weight=2.0, corrections=None,
                          sentence_cache=None, field=None):
    """'좋' 포함 → +1, '부족' 포함 → -1, 그 외 → 0(중립)."""
    out = []
    for sent in [s.strip() for s in doc.split('.') if s.strip()]:
        if '좋' in sent:
            score = 1.0
        elif '부족' in sent:
            score = -1.0
        else:
            score = 0.0
        pos = 1.0 if score > 0 else 0.0
        neg = 1.0 if score < 0 else 0.0
        neu = 1.0 if score == 0 else 0.0
        out.append((sent, score, pos, neg, neu))
    return out


def main():
    ps._get_sentence_level_scores = _stub_sentence_scores

    failures = []

    def check(label, actual, expected):
        ok = actual == expected
        print(('  OK  ' if ok else ' FAIL ') + label + f' — 실제={actual} 기대={expected}')
        if not ok:
            failures.append(label)

    # ── A~D. 문장 수 집계 ────────────────────────────────────────────────
    print('[A~D] metric=sentence_cnt, rows=2024/2025/2026')
    trend = ps.aggregate_sentiment_trend(
        ITEMS, 'evaluation_date__year', ['2024', '2025', '2026'], metric='sentence_cnt')
    check('rows 정렬', trend['rows'], ['2024', '2025', '2026'])
    # 2024: 긍정 '좋게 처리한다'/'협업이 좋다' 2건(중복 1건 제거), 부정 1건, 중립 1건 제외
    check('긍정 계열(2024/2025/2026)', trend['positive'], [2, None, 1])
    check('부정 계열(2024/2025/2026)', trend['negative'], [1, None, 2])
    check('결측 연도 기록', [s['row'] for s in trend['skipped_rows']], ['2025'])

    # ── E. 백분율 변환 ──────────────────────────────────────────────────
    print('[E] unit=pct — 분모 = 긍정+부정 (중립 제외)')
    pos_pct, neg_pct = ps._trend_series(trend, 'pct')
    check('긍정 %', pos_pct, [66.7, None, 33.3])
    check('부정 %', neg_pct, [33.3, None, 66.7])
    sums = [round(p + n) for p, n in zip(pos_pct, neg_pct) if p is not None]
    check('연도별 합 = 100', sums, [100, 100])

    print('[E-2] unit=count — 원값 유지')
    pos_cnt, neg_cnt = ps._trend_series(trend, 'count')
    check('긍정 수량', pos_cnt, [2, None, 1])
    check('부정 수량', neg_cnt, [1, None, 2])

    # ── 감정 강도 합 ────────────────────────────────────────────────────
    print('[E-3] metric=sentence_power')
    power = ps.aggregate_sentiment_trend(
        ITEMS, 'evaluation_date__year', ['2024', '2026'], metric='sentence_power')
    check('긍정 강도 합', power['positive'], [2.0, 1.0])
    check('부정 강도 합', power['negative'], [1.0, 2.0])

    # ── F. 단어 기준 경계(중립 단어는 긍정에 포함 — 워드클라우드와 동일) ──
    print('[F] metric=word_uniq / word_freq — 경계 score >= 0 이 긍정')
    word_trend = ps.aggregate_sentiment_trend(
        ITEMS, 'evaluation_date__year', ['2024', '2026'], metric='word_uniq')
    # 2024 단어: 업무(중립문장 포함 문장에서 +1 문장 우선 매칭) / 협업(+1) / 보고(-1)
    #   → 긍정 2종(업무·협업), 부정 1종(보고)
    # 2026 단어: 소통(+1) / 일정(-1) / 대응(-1) → 긍정 1종, 부정 2종
    check('긍정 단어 종류', word_trend['positive'], [2, 1])
    check('부정 단어 종류', word_trend['negative'], [1, 2])

    freq_trend = ps.aggregate_sentiment_trend(
        ITEMS, 'evaluation_date__year', ['2024', '2026'], metric='word_freq')
    # 2024 빈도: 업무 2회(두 평가) + 협업 1회 = 긍정 3, 보고 1회 = 부정 1
    check('긍정 단어 빈도', freq_trend['positive'], [3, 1])
    check('부정 단어 빈도', freq_trend['negative'], [1, 2])

    # ── row_values 미지정 시 데이터에서 연도 수집 ────────────────────────
    print('[A-2] row_values 미지정 — 데이터에 존재하는 연도만')
    auto = ps.aggregate_sentiment_trend(ITEMS, 'evaluation_date__year', None, metric='sentence_cnt')
    check('자동 수집 연도', auto['rows'], ['2024', '2026'])

    # ── G. 차트 렌더 ────────────────────────────────────────────────────
    print('[G] 차트 PNG 렌더')
    ps._setup_korean_font()
    out_dir = tempfile.mkdtemp(prefix='trend_chart_')
    for unit in ('pct', 'count'):
        path = os.path.join(out_dir, f'chart_{unit}.png')
        ok = ps._save_trend_chart_to_path(trend, path, {'unit': unit, 'width': 800, 'height': 600,
                                                        'title': 'TEST 직원 — 연도별 긍정/부정 비율'})
        size = os.path.getsize(path) if os.path.exists(path) else 0
        print(f'  {"OK  " if (ok and size > 1000) else "FAIL"} unit={unit} 생성={ok} 크기={size}B path={path}')
        if not (ok and size > 1000):
            failures.append(f'chart_{unit}')

    # 빈 입력 방어
    empty_ok = ps._save_trend_chart_to_path({'rows': []}, os.path.join(out_dir, 'x.png'), {})
    check('빈 rows 는 False 반환', empty_ok, False)

    print()
    if failures:
        print(f'FAIL {len(failures)}건: {failures}')
        return 1
    print('전 항목 통과')
    return 0


if __name__ == '__main__':
    sys.exit(main())
