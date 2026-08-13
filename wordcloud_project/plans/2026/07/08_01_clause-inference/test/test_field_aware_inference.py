# -*- coding: utf-8 -*-
"""Phase 1 회귀 — field-aware 추론 프리픽스 규약 잠금(모델 로드 없이).

검증:
  1) fields 있으면 학습과 동일 프리픽스 'f{field} 평가: {text}' 로 토크나이저에 전달.
  2) fields=None → 원문(하위호환, 기존 동작).
  3) falsy field('' / None 혼재) → 해당 문장만 원문.
프리픽스 규약이 finetune_sentiment.apply_field와 동일해야 train/serve 정합(긍↔부 안전).
"""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, ROOT)

from src.modules.hr_sentiment import _HRSentimentModel, _ID2LABEL  # noqa: E402


class _Enc(dict):
    """토크나이저 출력 대역 — .to(device) 지원 + model(**enc) 언팩 가능(dict)."""
    def to(self, _device):
        return self


class _FakeTok:
    """토크나이저 대역 — 받은 chunk(조립된 텍스트)를 기록. logits는 model이 낸다."""
    def __init__(self):
        self.seen = []

    def __call__(self, chunk, **kw):
        self.seen.extend(chunk)
        return _Enc({'_n': len(chunk)})


class _FakeLogits:
    def __init__(self, n):
        self._n = n

    def argmax(self, _axis):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return [0] * self._n  # 전부 positive(0) — 라벨 자체는 관심 밖, 조립만 검증


class _FakeModel:
    def __call__(self, **enc):
        class _O:
            logits = _FakeLogits(enc['_n'])
        return _O()


class _FakeTorch:
    class no_grad:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False


def _make_model():
    m = _HRSentimentModel.__new__(_HRSentimentModel)  # __init__ 우회(모델 미로드)
    m.torch = _FakeTorch()
    m.tokenizer = _FakeTok()
    m.model = _FakeModel()
    m.device = 'cpu'
    return m


class TestFieldAwarePrefix(unittest.TestCase):
    def test_field_prefix_applied(self):
        m = _make_model()
        out = m.predict(['능력 습득', '소통 부족'], fields=['장점', '단점'])
        self.assertEqual(m.tokenizer.seen, ['장점 평가: 능력 습득', '단점 평가: 소통 부족'])
        self.assertEqual(len(out), 2)
        self.assertTrue(all(o in _ID2LABEL.values() for o in out))

    def test_none_fields_raw(self):
        m = _make_model()
        m.predict(['능력 습득', '소통 부족'], fields=None)
        self.assertEqual(m.tokenizer.seen, ['능력 습득', '소통 부족'])

    def test_falsy_field_is_raw_per_sentence(self):
        m = _make_model()
        m.predict(['A', 'B', 'C'], fields=['장점', '', None])
        # 첫 문장만 프리픽스, 나머지(falsy)는 원문
        self.assertEqual(m.tokenizer.seen, ['장점 평가: A', 'B', 'C'])

    def test_matches_finetune_apply_field(self):
        """추론 프리픽스가 학습 apply_field 규약과 동일한지(정합 핵심)."""
        # finetune_sentiment.apply_field: field_token on & field → f'{field} 평가: {text}'
        field, text = '단점', '적극성 필요'
        expected = f'{field} 평가: {text}'
        m = _make_model()
        m.predict([text], fields=[field])
        self.assertEqual(m.tokenizer.seen, [expected])


if __name__ == '__main__':
    unittest.main(verbosity=2)
