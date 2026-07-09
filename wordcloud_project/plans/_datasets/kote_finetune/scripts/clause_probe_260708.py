# -*- coding: utf-8 -*-
"""절 레버 전제검증 프로브 — 절 파인튜닝 착수 前 헤드룸 정량화(엔진보다 측정 먼저).

질문: 우리 gold의 **중립 라벨 문장 중 실제로 다절(多절)+반대극성 혼합문**이 얼마나 되나?
  - 유의미하면(중립의 상당수가 숨은 긍+부 혼합) → 절 레버에 헤드룸 있음.
  - 드물면 → 절 레버도 저효율(중립은 대부분 진짜 단일 비평가 화행).
방법: gold+test 전 문장을 split_clauses로 쪼갠 뒤, **현 배포모델(model_out, field-token on)** 로
  절별 극성 추정 → 문장 라벨 vs 절 극성 패턴 교차분석. (절 극성은 gold 아님, prevalence 추정용.)
리스크 점검: 극성(긍/부) 라벨 문장이 반대극성 절을 품는 비율(=절 분리가 라벨 뒤집을 위험).
"""
import os
import sys
from collections import Counter

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from finetune_sentiment import TRAIN_FILES, TEST_SETS, load, ID2LAB  # noqa: E402
from src.modules.text_preprocessing import split_clauses  # noqa: E402

MODEL_DIR = os.path.abspath(os.path.join(HERE, '..', 'model_out'))


def main():
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    # 중복제거 로드(문장,라벨,필드)
    seen = {}
    for f in list(TRAIN_FILES) + list(TEST_SETS.values()):
        try:
            for t, y, fld in load(f):
                seen[t] = (y, fld)
        except FileNotFoundError:
            pass
    rows = [(t, y, fld) for t, (y, fld) in seen.items()]
    print(f'고유 문장 {len(rows)}개 로드')

    tok = AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR, local_files_only=True)
    model.eval(); dev = model.device

    def predict(texts, fields):
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                ch = [f'{fl} 평가: {tt}' if fl else tt for tt, fl in zip(texts[i:i+64], fields[i:i+64])]
                enc = tok(ch, truncation=True, padding=True, max_length=64, return_tensors='pt').to(dev)
                out += model(**enc).logits.argmax(-1).cpu().tolist()
        return out

    # 절 분리
    multi = []   # (sent, y, fld, clauses)
    n_single = 0
    for t, y, fld in rows:
        cls = split_clauses(t)
        if len(cls) >= 2:
            multi.append((t, y, fld, cls))
        else:
            n_single += 1
    print(f'단절 {n_single} · 다절 {len(multi)} ({100*len(multi)/len(rows):.1f}%)')

    # 다절 문장의 절별 극성 추정
    flat_txt, flat_fld, owner = [], [], []
    for i, (t, y, fld, cls) in enumerate(multi):
        for c in cls:
            flat_txt.append(c); flat_fld.append(fld); owner.append(i)
    preds = predict(flat_txt, flat_fld)
    clause_pol = [[] for _ in multi]
    for o, p in zip(owner, preds):
        clause_pol[o].append(p)   # 0=긍 1=부 2=중

    # 라벨별 다절 분포 + 혼합패턴
    by_label_multi = Counter()
    hidden_mixed_neutral = 0        # 중립 라벨인데 절에 긍+부 공존
    neutral_multi = 0
    polar_with_opposite = 0         # 긍/부 라벨인데 반대극성 절 포함(분리 위험/기회)
    polar_multi = 0
    pattern_neutral = Counter()
    for (t, y, fld, cls), pols in zip(multi, clause_pol):
        by_label_multi[ID2LAB[y]] += 1
        has_pos = 0 in pols; has_neg = 1 in pols
        if y == 2:  # neutral
            neutral_multi += 1
            key = ('긍' if has_pos else '') + ('부' if has_neg else '') + ('중' if 2 in pols else '')
            pattern_neutral[key] += 1
            if has_pos and has_neg:
                hidden_mixed_neutral += 1
        else:       # polar
            polar_multi += 1
            opp = (y == 0 and has_neg) or (y == 1 and has_pos)
            if opp:
                polar_with_opposite += 1

    print('\n=== 다절 문장 라벨 분포 ===', dict(by_label_multi))
    print(f'\n[중립 라벨 다절 문장] {neutral_multi}개')
    print(f'  └ 절에 긍+부 공존(숨은 혼합) = {hidden_mixed_neutral}개 '
          f'({100*hidden_mixed_neutral/max(neutral_multi,1):.1f}% of 중립다절)')
    print('  절 극성 패턴:', dict(pattern_neutral.most_common()))
    tot_neutral = sum(1 for _, y, _ in rows if y == 2)
    print(f'  전체 중립 라벨 {tot_neutral}개 중 숨은혼합 {hidden_mixed_neutral} '
          f'({100*hidden_mixed_neutral/max(tot_neutral,1):.1f}%)')
    print(f'\n[극성(긍/부) 라벨 다절 문장] {polar_multi}개')
    print(f'  └ 반대극성 절 포함(분리 시 뒤집힘 위험) = {polar_with_opposite}개 '
          f'({100*polar_with_opposite/max(polar_multi,1):.1f}%)')

    # 숨은혼합 중립 예시 몇 개
    print('\n=== 숨은혼합 중립 예시(문장 → 절[극성]) ===')
    shown = 0
    for (t, y, fld, cls), pols in zip(multi, clause_pol):
        if y == 2 and (0 in pols) and (1 in pols):
            seg = ' | '.join(f'{c}[{ID2LAB[p][:1]}]' for c, p in zip(cls, pols))
            print(f'  ({fld}) {seg}')
            shown += 1
            if shown >= 12:
                break


if __name__ == '__main__':
    main()
