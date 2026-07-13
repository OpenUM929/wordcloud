# -*- coding: utf-8 -*-
"""HR 도메인 파인튜닝 감정모델(3분류 극성) 추론 — 싱글톤 + 안전 폴백.

문장 텍스트 → positive/negative/neutral. 베이스 KoTE(44감정)와 별개이며, 극성 결정만 담당.
설계 원칙(production 안전):
  · 모델 디렉터리 부재·로드 실패·추론 예외 시 **None 반환** → 호출부가 기존 규칙으로 폴백.
  · 지연 로드(최초 호출 시) + 스레드 안전. 설정 `USE_HR_SENTIMENT_MODEL`로 on/off.
라벨 순서(finetune_sentiment): 0=positive, 1=negative, 2=neutral.
"""
import hashlib
import json
import logging
import os
import threading

from src.config.settings import HR_SENTIMENT_MODEL_PATH

logger = logging.getLogger(__name__)
_ID2LABEL = {0: 'positive', 1: 'negative', 2: 'neutral'}


def _load_temperature(model_dir):
    """모델 디렉터리의 calibration.json에서 temperature 로드(0708_02 L3).

    부재·파싱실패·비양수 값이면 1.0(=캘리브레이션 없음과 동일). argmax 라벨은 T와 무관하므로
    이 값은 predict_proba 의 확률 눈금에만 영향을 준다.
    """
    path = os.path.join(model_dir, 'calibration.json')
    try:
        with open(path, encoding='utf-8') as f:
            t = float(json.load(f).get('temperature', 1.0))
        return t if t > 0 else 1.0
    except (OSError, ValueError, TypeError):
        return 1.0

_instance = None
_lock = threading.Lock()
_load_failed = False


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


class _HRSentimentModel:
    def __init__(self):
        import torch
        from datetime import datetime
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        # 로드 직전 디스크 가중치의 해시를 "메모리 로드본 지문"으로 기록 — 이후 파일이
        # 교체되어도 이 값은 남아, verify_integrity가 선언(VERSION.json)·디스크·메모리를
        # 3자 대조해 '파일 교체 후 서버 미재시작' 상태를 버전 모달에서 탐지할 수 있다.
        weights_path = os.path.join(HR_SENTIMENT_MODEL_PATH, 'model.safetensors')
        self.sha256 = _file_sha256(weights_path) if os.path.isfile(weights_path) else None
        self.loaded_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(HR_SENTIMENT_MODEL_PATH, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            HR_SENTIMENT_MODEL_PATH, local_files_only=True)
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.model.to(self.device).eval()
        self.temperature = _load_temperature(HR_SENTIMENT_MODEL_PATH)

    def _prefixed(self, texts, fields):
        """field(장점/단점) 프리픽스 적용 — 학습과 동일 규약(0707_01/0708_01), predict/proba 공용."""
        out = []
        for x, f in zip(texts, fields):
            s = (x or '')
            if f:
                s = f'{f} 평가: {s}'
            out.append(s)
        return out

    def predict(self, texts, fields=None):
        t = self.torch
        out = []
        n = len(texts)
        if fields is None:
            fields = [None] * n
        with t.no_grad():
            for i in range(0, n, 64):
                chunk = self._prefixed(texts[i:i + 64], fields[i:i + 64])
                enc = self.tokenizer(chunk, truncation=True, padding=True, max_length=64,
                                     return_tensors='pt').to(self.device)
                ids = self.model(**enc).logits.argmax(-1).cpu().tolist()
                out.extend(_ID2LABEL.get(j, 'neutral') for j in ids)
        return out

    def predict_proba(self, texts, fields=None):
        """캘리브레이션(T scaling)된 softmax 확률 반환(0708_02 L3).

        Returns: [{'label', 'confidence', 'probs': {positive, negative, neutral}}, ...]
        label 은 predict 와 동일(argmax는 T 불변) — 결정을 바꾸지 않고 확률 눈금만 보정.
        """
        t = self.torch
        out = []
        n = len(texts)
        if fields is None:
            fields = [None] * n
        with t.no_grad():
            for i in range(0, n, 64):
                chunk = self._prefixed(texts[i:i + 64], fields[i:i + 64])
                enc = self.tokenizer(chunk, truncation=True, padding=True, max_length=64,
                                     return_tensors='pt').to(self.device)
                probs = t.softmax(self.model(**enc).logits / self.temperature, dim=-1).cpu()
                for p in probs.tolist():
                    j = max(range(3), key=lambda k: p[k])
                    out.append({'label': _ID2LABEL[j], 'confidence': float(p[j]),
                                'probs': {_ID2LABEL[k]: float(p[k]) for k in range(3)}})
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
        dict with keys: enabled, dir_exists, loaded, load_failed,
                        loaded_sha256, loaded_at (모델 미로드 시 None)
    """
    import os
    from src.config.settings import USE_HR_SENTIMENT_MODEL, HR_SENTIMENT_MODEL_PATH
    return {
        'enabled': USE_HR_SENTIMENT_MODEL,
        'dir_exists': os.path.isdir(HR_SENTIMENT_MODEL_PATH),
        'loaded': _instance is not None,
        'load_failed': _load_failed,
        'loaded_sha256': getattr(_instance, 'sha256', None),
        'loaded_at': getattr(_instance, 'loaded_at', None),
    }


def predict_sentiments(texts, fields=None):
    """texts → ['positive'|'negative'|'neutral', ...] 또는 실패 시 None(호출부가 규칙 폴백).

    fields: texts와 동일 길이의 필드('장점'/'단점'/None 등) 리스트(선택). 값이 있으면 학습과 동일
            프리픽스 f'{field} 평가: {text}'를 적용(train/serve 정합, 0707_01·0708_01). None=원문(하위호환).
    """
    if not texts:
        return None
    m = _get()
    if m is None:
        return None
    try:
        return m.predict(list(texts), list(fields) if fields is not None else None)
    except Exception as e:
        logger.warning('HR 감정모델 추론 실패 → 규칙 폴백: %s', e)
        return None


def predict_proba(texts, fields=None):
    """texts → 캘리브레이션 확률 리스트(predict_sentiments와 동일 폴백 규약 — 실패 시 None).

    calibration.json(모델 디렉터리)이 없으면 T=1(무보정 softmax)로 동작. argmax 라벨은
    predict_sentiments 와 항상 일치 — 소비자는 신뢰도(escalation 라우팅)에만 쓸 것(0708_02 L3).
    """
    if not texts:
        return None
    m = _get()
    if m is None:
        return None
    try:
        return m.predict_proba(list(texts), list(fields) if fields is not None else None)
    except Exception as e:
        logger.warning('HR 감정모델 확률 추론 실패 → 미부착: %s', e)
        return None
