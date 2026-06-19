#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""emotion_analysis / leadership_analysis가 공유하는 KoTE 모델 싱글톤."""

import threading
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch


class KoTEModel:
    """emotion + leadership 공유 KoTE 모델 싱글톤 (Thread-safe)"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    from src.config.settings import MODEL_PATH
                    instance.tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, local_files_only=True)
                    instance.model = AutoModelForSequenceClassification.from_pretrained(MODEL_PATH, local_files_only=True)
                    if torch.cuda.is_available():
                        instance.model = instance.model.to('cuda')
                    instance.device = next(instance.model.parameters()).device
                    cls._instance = instance
        return cls._instance
