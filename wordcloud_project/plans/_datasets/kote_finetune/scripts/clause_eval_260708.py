# -*- coding: utf-8 -*-
"""Phase 2a — 절(clause) 분리 추론의 끝단 이득·위험 정량화(production 무변경, 측정 우선).

프로브(clause_probe)는 prevalence만 봤다. 여기선 배포모델(seed45, field-aware)로 실제
문장-단위 vs 절-단위 판정을 비교해 게이트 지표를 낸다:
  (1) 단절 문장(98.5%) 불변 — 절 분리가 문장판정을 바꾸지 않음(회귀 0) 확인.
  (2) 부→긍 위험 — 사람이 '부정'이라 라벨한 문장에서 절 분리가 '긍정' 절 방출을 만드나?
      (워드클라우드에 긍정 단어로 새는 케이스. 게이트: 정당한 '각각 평가'인지 개별 검토.)
  (3) 중립 회수 — 사람이 '극성'인데 문장판정=중립인 것을 절 분리가 올바른 극성으로 살리나?
집계 없이 절별 극성을 그대로 방출(사용자 결정: 긍/부 공존은 상쇄 말고 각각 평가).
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

    # gold+test 중복제거(문장,라벨,필드). test는 진짜 라벨(사람/claude확정) 기준.
    seen = {}
    for f in list(TRAIN_FILES) + list(TEST_SETS.values()):
        try:
            for t, y, fld in load(f):
                seen[t] = (y, fld)
        except FileNotFoundError:
            pass
    rows = [(t, y, fld) for t, (y, fld) in seen.items()]
    print(f'고유 문장 {len(rows)}개')

    tok = AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR, local_files_only=True)
    model.eval(); dev = model.device

    def predict(texts, fields):
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                ch = [f'{fl} 평가: {tt}' if fl else tt
                      for tt, fl in zip(texts[i:i + 64], fields[i:i + 64])]
                enc = tok(ch, truncation=True, padding=True, max_length=64,
                          return_tensors='pt').to(dev)
                out += model(**enc).logits.argmax(-1).cpu().tolist()
        return out

    # 문장-단위 판정
    sent_pred = predict([t for t, _, _ in rows], [f for _, _, f in rows])

    # 절 분리 + 절별 판정
    flat_txt, flat_fld, owner = [], [], []
    clauses_of = []
    for i, (t, y, fld) in enumerate(rows):
        cls = split_clauses(t)
        clauses_of.append(cls)
        for c in cls:
            flat_txt.append(c); flat_fld.append(fld); owner.append(i)
    clause_pred_flat = predict(flat_txt, flat_fld)
    clause_pols = [[] for _ in rows]
    for o, p in zip(owner, clause_pred_flat):
        clause_pols[o].append(p)

    single = multi = 0
    single_mismatch = 0          # (1) 단절인데 문장판정≠절판정 (있으면 안 됨)
    neg_to_pos_emit = []         # (2) 부정 라벨 문장의 긍정 절 방출
    neutral_recovery = []        # (3) 극성 라벨·문장판정=중립인데 절이 올바른 극성
    mixed_multi = 0              # 다절 중 절 극성이 실제로 갈리는 것

    for i, (t, y, fld) in enumerate(rows):
        cls = clauses_of[i]
        pols = clause_pols[i]
        sp = sent_pred[i]
        if len(cls) == 1:
            single += 1
            if pols[0] != sp:
                single_mismatch += 1
            continue
        multi += 1
        pset = set(pols)
        if len({p for p in pols if p in (0, 1)}) == 2:
            mixed_multi += 1
        # (2) 부정(1) 라벨 문장에 긍정(0) 절
        if y == 1 and 0 in pols:
            segs = ' | '.join(f'{c}[{ID2LAB[p][:1]}]' for c, p in zip(cls, pols))
            neg_to_pos_emit.append((fld, segs))
        # (3) 극성 라벨(긍0/부1)인데 문장판정 중립(2), 절에 올바른 극성
        if y in (0, 1) and sp == 2 and y in pols:
            segs = ' | '.join(f'{c}[{ID2LAB[p][:1]}]' for c, p in zip(cls, pols))
            neutral_recovery.append((ID2LAB[y], fld, segs))

    print(f'\n단절 {single} · 다절 {multi} (다절 중 극성혼합 {mixed_multi})')
    print(f'(1) 단절 문장 판정 불변 검사: 불일치 {single_mismatch}건 '
          f'(0이어야 회귀 0 — split_clauses가 단절은 [문장] 그대로 반환)')
    print(f'(2) ★부→긍 위험: 부정 라벨 문장의 긍정 절 방출 {len(neg_to_pos_emit)}건')
    for fld, segs in neg_to_pos_emit[:20]:
        print(f'    ({fld}) {segs}')
    print(f'(3) 중립 회수: 극성 라벨·문장판정=중립인데 절이 극성 복원 {len(neutral_recovery)}건')
    for y, fld, segs in neutral_recovery[:20]:
        print(f'    [{y}]({fld}) {segs}')


if __name__ == '__main__':
    main()
