# -*- coding: utf-8 -*-
"""Back-translation service for sentiment analysis enhancement."""

import hashlib
import json
import os
from typing import Dict, Any, Optional

# Simple file-based cache
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'outputs', 'translation_cache')
os.makedirs(_CACHE_DIR, exist_ok=True)

# Lazy-loaded models
_ko_en_model = None
_en_ko_model = None
_nllb_tokenizer = None
_nllb_model = None

def _get_cache_key(text: str, model_type: str) -> str:
    return hashlib.md5(f"{model_type}:{text}".encode('utf-8')).hexdigest()

def _get_cached(text: str, model_type: str) -> Optional[str]:
    key = _get_cache_key(text, model_type)
    path = os.path.join(_CACHE_DIR, f"{key}.json")
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f).get('result')
        except Exception:
            pass
    return None

def _set_cached(text: str, model_type: str, result: str):
    key = _get_cache_key(text, model_type)
    path = os.path.join(_CACHE_DIR, f"{key}.json")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'source': text, 'model': model_type, 'result': result}, f, ensure_ascii=False)
    except Exception:
        pass

def _load_opus_models():
    global _ko_en_model, _en_ko_model
    if _ko_en_model is None:
        from transformers import MarianMTModel, MarianTokenizer
        _ko_en_model = {
            'tokenizer': MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-ko-en"),
            'model': MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-ko-en")
        }
    if _en_ko_model is None:
        from transformers import MarianMTModel, MarianTokenizer
        _en_ko_model = {
            'tokenizer': MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-en-ko"),
            'model': MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-en-ko")
        }

def _load_nllb_model():
    global _nllb_tokenizer, _nllb_model
    if _nllb_tokenizer is None:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        _nllb_tokenizer = AutoTokenizer.from_pretrained("facebook/nllb-200-distilled-600M")
        _nllb_model = AutoModelForSeq2SeqLM.from_pretrained("facebook/nllb-200-distilled-600M")

def _translate_opus(text: str, src_lang: str, tgt_lang: str) -> str:
    """Translate using Helsinki-NLP opus-mt models."""
    _load_opus_models()
    
    if src_lang == 'ko' and tgt_lang == 'en':
        model_dict = _ko_en_model
    elif src_lang == 'en' and tgt_lang == 'ko':
        model_dict = _en_ko_model
    else:
        return text
    
    tokenizer = model_dict['tokenizer']
    model = model_dict['model']
    
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
    translated = model.generate(**inputs)
    result = tokenizer.decode(translated[0], skip_special_tokens=True)
    return result

def _translate_nllb(text: str, src_lang: str, tgt_lang: str) -> str:
    """Translate using Facebook NLLB-200 model."""
    _load_nllb_model()
    
    tokenizer = _nllb_tokenizer
    model = _nllb_model
    
    lang_map = {
        'ko': 'kor_Hang',
        'en': 'eng_Latn'
    }
    
    src = lang_map.get(src_lang, src_lang)
    tgt = lang_map.get(tgt_lang, tgt_lang)
    
    tokenizer.src_lang = src
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
    translated_tokens = model.generate(
        **inputs,
        forced_bos_token_id=tokenizer.lang_code_to_id[tgt]
    )
    result = tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)[0]
    return result

def back_translate(text: str, model_type: str = 'opus') -> Dict[str, Any]:
    """Perform back-translation: ko -> en -> ko.
    
    Args:
        text: Korean source text
        model_type: 'opus' or 'nllb'
    
    Returns:
        dict with 'original', 'english', 'back_translated'
    """
    if not text or not text.strip():
        return {'original': text, 'english': text, 'back_translated': text}
    
    # Check cache for final result
    cache_key = f"{model_type}_backtrans"
    cached = _get_cached(text, cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    
    # Step 1: ko -> en
    en_cache = _get_cached(text, f"{model_type}_ko_en")
    if en_cache:
        english = en_cache
    else:
        if model_type == 'opus':
            english = _translate_opus(text, 'ko', 'en')
        else:
            english = _translate_nllb(text, 'ko', 'en')
        _set_cached(text, f"{model_type}_ko_en", english)
    
    # Step 2: en -> ko
    ko_cache = _get_cached(english, f"{model_type}_en_ko")
    if ko_cache:
        back_translated = ko_cache
    else:
        if model_type == 'opus':
            back_translated = _translate_opus(english, 'en', 'ko')
        else:
            back_translated = _translate_nllb(english, 'ko', 'ko')
        _set_cached(english, f"{model_type}_en_ko", back_translated)
    
    result = {
        'original': text,
        'english': english,
        'back_translated': back_translated
    }
    
    _set_cached(text, cache_key, json.dumps(result, ensure_ascii=False))
    return result

def analyze_with_back_translation(text: str) -> Dict[str, Any]:
    """Analyze sentiment with both original and back-translated text.
    
    Returns comparison of original vs back-translation results.
    """
    from src.modules.emotion_analysis import analyze_emotion
    
    # Original
    orig_result = analyze_emotion(text)
    orig_scores = orig_result.get('analysis', {}).get('base_result', {}).get('mapped', {}).get('sentiment_scores', {})
    
    # Opus back-translation
    opus_bt = back_translate(text, 'opus')
    opus_result = analyze_emotion(opus_bt['back_translated'])
    opus_scores = opus_result.get('analysis', {}).get('base_result', {}).get('mapped', {}).get('sentiment_scores', {})
    
    # NLLB back-translation
    nllb_bt = back_translate(text, 'nllb')
    nllb_result = analyze_emotion(nllb_bt['back_translated'])
    nllb_scores = nllb_result.get('analysis', {}).get('base_result', {}).get('mapped', {}).get('sentiment_scores', {})
    
    return {
        'original': {
            'text': text,
            'pos': orig_scores.get('positive', 0.0),
            'neg': orig_scores.get('negative', 0.0),
        },
        'opus': {
            'english': opus_bt['english'],
            'back_translated': opus_bt['back_translated'],
            'pos': opus_scores.get('positive', 0.0),
            'neg': opus_scores.get('negative', 0.0),
        },
        'nllb': {
            'english': nllb_bt['english'],
            'back_translated': nllb_bt['back_translated'],
            'pos': nllb_scores.get('positive', 0.0),
            'neg': nllb_scores.get('negative', 0.0),
        }
    }
