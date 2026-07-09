# -*- coding: utf-8 -*-
"""Phase 1 배포 게이트 — seed45(model_out) 배포 前 train/serve 정합 검증.

질문 2개:
  (A) field-aware 추론(학습과 동일 프리픽스)이 gold를 재현하나? → ★긍↔부 0 유지?
  (B) raw 추론(무프리픽스, = 프로덕션 필드미상 데이터 경로)이 긍↔부를 악화시키나?
      최신 모델은 field-token 학습이라 무필드 데이터엔 프리픽스가 안 붙는다.
      이 경로가 긍↔부 오분류를 만들면 배포는 위험 → 게이트 실패.

방법: model_out(seed45)을 직접 로드해 predict_sentiments와 **동일 프리픽스 규약**으로 두 번 채점.
게이트 통과 기준(핵심가치): 모든 테스트셋에서 field-aware·raw 둘 다 ★긍↔부 = 0.
(중립→극성/극성→중립은 허용 — 긍↔부만 금지선.)
"""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)
from finetune_sentiment import TEST_SETS, load, metrics  # noqa: E402

MODEL_DIR = os.path.abspath(os.path.join(HERE, '..', 'model_out'))


def main():
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification

    tok = AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR, local_files_only=True)
    model.eval()
    dev = model.device

    def predict(texts, fields):
        """predict_sentiments와 동일 규약: field 있으면 'f{field} 평가: {text}', 없으면 원문."""
        out = []
        with torch.no_grad():
            for i in range(0, len(texts), 64):
                chunk = []
                for tt, fl in zip(texts[i:i + 64], fields[i:i + 64]):
                    s = tt or ''
                    if fl:
                        s = f'{fl} 평가: {s}'
                    chunk.append(s)
                enc = tok(chunk, truncation=True, padding=True, max_length=64,
                          return_tensors='pt').to(dev)
                out += model(**enc).logits.argmax(-1).cpu().tolist()
        return out

    print(f'모델: {MODEL_DIR}\n')
    all_pass = True
    for name, fn in TEST_SETS.items():
        try:
            rows = load(fn)
        except FileNotFoundError:
            print(f'[{name}] 파일 없음 — 건너뜀')
            continue
        texts = [t for t, _, _ in rows]
        y = [lab for _, lab, _ in rows]
        real_fields = [fld for _, _, fld in rows]
        n_field = sum(1 for f in real_fields if f)

        print(f'=== {name} (n={len(rows)}, field보유 {n_field}) ===')
        print(' [field-aware] ', end='')
        m_fa = metrics(name, y, predict(texts, real_fields))
        print(' [raw(무필드)] ', end='')
        m_raw = metrics(name, y, predict(texts, [None] * len(texts)))
        if m_fa['pos_neg_err'] != 0:
            all_pass = False
            print(f'   [!] field-aware 긍<->부 {m_fa["pos_neg_err"]} != 0')
        if m_raw['pos_neg_err'] != 0:
            all_pass = False
            print(f'   [!] raw 긍<->부 {m_raw["pos_neg_err"]} != 0')
        print()

    print('=' * 50)
    print('게이트:', 'PASS (모든 셋 field-aware/raw 긍<->부 0)' if all_pass
          else 'FAIL -- 긍<->부 오분류 발생, 판단 필요')


if __name__ == '__main__':
    main()
