# -*- coding: utf-8 -*-
"""HR 도메인 파인튜닝 감정모델(3분류 극성) 추론 — 싱글톤 + 안전 폴백.

문장 텍스트 → positive/negative/neutral. 베이스 KoTE(44감정)와 별개이며, 극성 결정만 담당.
설계 원칙(production 안전):
  · 모델 디렉터리 부재·로드 실패·추론 예외 시 **None 반환** → 호출부가 기존 규칙으로 폴백.
  · 지연 로드(최초 호출 시) + 스레드 안전. 설정 `USE_HR_SENTIMENT_MODEL`로 on/off.
라벨 순서(finetune_sentiment): 0=positive, 1=negative, 2=neutral.
"""
import logging
import os
import threading

from src.config.settings import HR_SENTIMENT_MODEL_PATH

logger = logging.getLogger(__name__)
_ID2LABEL = {0: 'positive', 1: 'negative', 2: 'neutral'}

_instance = None
_lock = threading.Lock()
_load_failed = False


class _HRSentimentModel:
    def __init__(self):
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(HR_SENTIMENT_MODEL_PATH, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            HR_SENTIMENT_MODEL_PATH, local_files_only=True)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.model.to(self.device).eval()

    def predict(self, texts):
        t = self.torch
        out = []
        with t.no_grad():
            for i in range(0, len(texts), 64):
                chunk = [(x or '') for x in texts[i:i + 64]]
                enc = self.tokenizer(chunk, truncation=True, padding=True, max_length=64,
                                     return_tensors='pt').to(self.device)
                ids = self.model(**enc).logits.argmax(-1).cpu().tolist()
                out.extend(_ID2LABEL.get(j, 'neutral') for j in ids)
        return out


def _get():
    global _instance, _load_failed
    if _instance is not None or _load_failed:
        return _instance
    with _lock:
        if _instance is None and not _load_failed:
            if not os.path.isdir(HR_SENTIMENT_MODEL_PATH):
                logger.warning('HR 감정모델 디렉터리 없음 → 규칙 폴백: %s', HR_SENTIMENT_MODEL_PATH)
                _load_failed = True
                return None
            try:
                _instance = _HRSentimentModel()
                logger.info('HR 파인튜닝 감정모델 로드 완료 (device=%s)', _instance.device)
            except Exception as e:  # 어떤 이유로든 실패 → 폴백(production 무중단)
                logger.warning('HR 감정모델 로드 실패 → 규칙 폴백: %s', e)
                _load_failed = True
    return _instance


def model_status():
    """Return model status dict without triggering load.
    
    Returns:
        dict with keys: enabled, dir_exists, loaded, load_failed
    """
    import os
    from src.config.settings import USE_HR_SENTIMENT_MODEL, HR_SENTIMENT_MODEL_PATH
    return {
        'enabled': USE_HR_SENTIMENT_MODEL,
        'dir_exists': os.path.isdir(HR_SENTIMENT_MODEL_PATH),
        'loaded': _instance is not None,
        'load_failed': _load_failed,
    }


def predict_sentiments(texts):
    """texts → ['positive'|'negative'|'neutral', ...] 또는 실패 시 None(호출부가 규칙 폴백)."""
    if not texts:
        return None
    m = _get()
    if m is None:
        return None
    try:
        return m.predict(list(texts))
    except Exception as e:
        logger.warning('HR 감정모델 추론 실패 → 규칙 폴백: %s', e)
        return None
