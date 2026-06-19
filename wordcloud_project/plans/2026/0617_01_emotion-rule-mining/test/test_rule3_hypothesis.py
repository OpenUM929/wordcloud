# -*- coding: utf-8 -*-
"""가설 검증 테스트 (step2 확정)

가설: 인사평가 단문 강점이 부정으로 오분류되는 직접 원인은 보정 규칙 `rule3_last_low`이며,
      매핑 편향(부정25/긍정16)으로 KoTE 단계에서 긍정이 거의 뜨지 않는다.

방법: 반입 CSV 475문장에 refine_acquired_row(KoTE 재계산 + 보정 재현)를 그대로 돌려
      raw_model_label(보정 전) / applied_rule / corrected_label(보정 후)을 수집·집계.

서버·DB 불요. KoTE 모델만 로드(일회성). 앱 코드 무변경.
"""
import os, sys, csv, json, collections

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))  # wordcloud_project
sys.path.insert(0, PROJ)
os.chdir(PROJ)  # config의 ../model 상대경로 해석을 위해

from src.services.perspective_service import refine_acquired_row  # noqa: E402

CSV = os.path.join(PROJ, '..', 'data', 'acquired_sentences_20260617.csv')


def main():
    rows = list(csv.DictReader(open(CSV, encoding='utf-8-sig')))
    print(f'[입력] {len(rows)}행 — KoTE 재계산 시작(시간 소요)...')

    out = []
    for i, r in enumerate(rows):
        meta = refine_acquired_row(r)
        meta['id'] = r['id']
        meta['model_label_at_capture'] = (r.get('model_label') or '').strip()
        meta['sentence_text'] = r['sentence_text']
        out.append(meta)
        if (i + 1) % 50 == 0:
            print(f'  ...{i+1}/{len(rows)}')

    # 재현 검증: 보정후 corrected_label vs 캡처당시 model_label
    repro = sum(1 for m in out if m['corrected_label'] == m['model_label_at_capture'])
    print('\n=== (0) 재현 검증: corrected_label == model_label_at_capture ===')
    print(f'  {repro}/{len(out)} ({100*repro/len(out):.1f}%) 일치  -> 파이프라인 재현 신뢰도')

    # (1) 보정 전(KoTE raw) 분포
    print('\n=== (1) 보정 전 raw_model_label (KoTE argmax) 분포 ===')
    print(' ', dict(collections.Counter(m['raw_model_label'] for m in out)))

    # (2) 보정 후 corrected_label 분포
    print('\n=== (2) 보정 후 corrected_label 분포 ===')
    print(' ', dict(collections.Counter(m['corrected_label'] for m in out)))

    # (3) ★ 가설 핵심: corrected_label=negative 행의 발동 규칙
    neg = [m for m in out if m['corrected_label'] == 'negative']
    print(f'\n=== (3) ★ corrected_label=negative {len(neg)}건의 발동 규칙(applied_rule) ===')
    for rule, c in collections.Counter(m['applied_rule'] for m in neg).most_common():
        print(f'  {rule:24s}: {c}건')

    # (4) rule3_last_low로 부정이 된 행: 보정 전엔 무엇이었나
    r3 = [m for m in out if m['applied_rule'] == 'rule3_last_low']
    print(f'\n=== (4) rule3_last_low 발동 {len(r3)}건의 보정 전(raw_model_label) ===')
    print(' ', dict(collections.Counter(m['raw_model_label'] for m in r3)))
    print(f'  -> rule3로 부정 강등된 건 중 보정 전 비부정(긍정+중립): '
          f"{sum(1 for m in r3 if m['raw_model_label'] != 'negative')}건")

    # (5) 전체 applied_rule 분포
    print('\n=== (5) 전체 applied_rule 분포 ===')
    for rule, c in collections.Counter(m['applied_rule'] for m in out).most_common():
        print(f'  {rule:24s}: {c}건')

    # 결과 CSV 저장(검토용)
    outcsv = os.path.join(HERE, '..', 'result', 'refine_diag_260617.csv')
    keys = ['id', 'sentence_text', 'kote_pos', 'kote_neg', 'kote_neutral',
            'raw_model_label', 'applied_rule', 'corrected_label', 'override_score',
            'is_last', 'total_sentences', 'model_label_at_capture']
    with open(outcsv, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
        w.writeheader()
        for m in out:
            w.writerow(m)
    print(f'\n[저장] {os.path.abspath(outcsv)}')


if __name__ == '__main__':
    main()
