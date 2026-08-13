# -*- coding: utf-8 -*-
"""0708_02 L3 — T scaling 서빙 배선 단위테스트.

검증(계획서 §7-4): predict_proba 확률합 1 · 폴백 None · calibration.json 부재 시 T=1 ·
argmax 라벨이 predict_sentiments 와 일치 · 패킷 model_ref 선택 소비(실패 시 무부착).
실행: (GPU 학습과 병행 안전하게) CUDA_VISIBLE_DEVICES= python -m pytest test_l3_calibration.py -v
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.modules import hr_sentiment as hs                     # noqa: E402
from src.services import judgment_packet_service as jps        # noqa: E402


# ── _load_temperature ──────────────────────────────────────────

def test_load_temperature_valid(tmp_path):
    (tmp_path / 'calibration.json').write_text('{"temperature": 1.6}', encoding='utf-8')
    assert hs._load_temperature(str(tmp_path)) == 1.6


def test_load_temperature_missing_file(tmp_path):
    assert hs._load_temperature(str(tmp_path)) == 1.0


def test_load_temperature_invalid_json(tmp_path):
    (tmp_path / 'calibration.json').write_text('not json', encoding='utf-8')
    assert hs._load_temperature(str(tmp_path)) == 1.0


def test_load_temperature_nonpositive(tmp_path):
    (tmp_path / 'calibration.json').write_text('{"temperature": 0}', encoding='utf-8')
    assert hs._load_temperature(str(tmp_path)) == 1.0


# ── 폴백 규약 ──────────────────────────────────────────────────

def test_predict_proba_empty_returns_none():
    assert hs.predict_proba([]) is None


def test_predict_proba_model_dir_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(hs, '_instance', None)
    monkeypatch.setattr(hs, '_load_failed', False)
    monkeypatch.setattr(hs, 'HR_SENTIMENT_MODEL_PATH', str(tmp_path / 'no_such_dir'))
    assert hs.predict_proba(['문장']) is None
    assert hs._load_failed is True


# ── 실모델 통합(있을 때만 · CPU 권장) ──────────────────────────

_model_dir = None
try:
    from src.config.settings import HR_SENTIMENT_MODEL_PATH as _model_dir
except Exception:
    pass
_has_model = bool(_model_dir) and os.path.isfile(os.path.join(_model_dir or '', 'model.safetensors'))


@pytest.mark.skipif(not _has_model, reason='배포 모델 없음')
def test_predict_proba_real_model_consistency():
    texts = ['협업이 원활하고 소통이 뛰어납니다', '보고가 늦어 개선이 필요합니다', '올해 상반기 업무를 수행함']
    fields = ['장점', '단점', None]
    labels = hs.predict_sentiments(texts, fields=fields)
    probas = hs.predict_proba(texts, fields=fields)
    assert labels is not None and probas is not None
    for lab, pr in zip(labels, probas):
        assert pr['label'] == lab                                  # argmax는 T 불변 → 라벨 일치
        assert abs(sum(pr['probs'].values()) - 1.0) < 1e-5          # 확률합 1
        assert 0.0 < pr['confidence'] <= 1.0
        assert pr['confidence'] == pytest.approx(max(pr['probs'].values()))
    inst = hs._get()
    assert inst.temperature == hs._load_temperature(_model_dir)     # 동봉 T 로드 확인


# ── 패킷 model_ref 선택 소비 ───────────────────────────────────

def _items():
    return [{'rec_id': '1_0', 'text': '협업이 원활함', 'field': '장점'},
            {'rec_id': '1_1', 'text': '보고 지연', 'field': ''}]


def test_annotate_model_confidence_attaches(monkeypatch):
    def fake_proba(texts, fields=None):
        return [{'label': 'positive', 'confidence': 0.91234, 'probs': {}} for _ in texts]
    monkeypatch.setattr(hs, 'predict_proba', fake_proba)
    items = _items()
    jps._annotate_model_confidence(items)
    assert items[0]['model_ref'] == {'label': 'positive', 'confidence': 0.9123}
    assert items[1]['model_ref']['label'] == 'positive'


def test_annotate_model_confidence_none_result_no_attach(monkeypatch):
    monkeypatch.setattr(hs, 'predict_proba', lambda texts, fields=None: None)
    items = _items()
    jps._annotate_model_confidence(items)
    assert all('model_ref' not in it for it in items)               # 실패 시 무부착(기존 소비자 무영향)


def test_annotate_model_confidence_flag_off_no_attach(monkeypatch):
    import src.config.settings as st
    monkeypatch.setattr(st, 'USE_HR_SENTIMENT_MODEL', False)
    called = []
    monkeypatch.setattr(hs, 'predict_proba',
                        lambda texts, fields=None: called.append(1))
    items = _items()
    jps._annotate_model_confidence(items)
    assert not called and all('model_ref' not in it for it in items)


def test_annotate_model_confidence_empty_items_ok():
    jps._annotate_model_confidence([])                              # 예외 없이 통과
