"""단어 가점(boost) 관리 모듈 — 싱글톤 패턴, stopword_manager와 동일한 구조."""

import json
import os
import threading
from typing import Dict, List, Optional


class WordBoostManager:
    """워드클라우드 단어 가점 사전 관리."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._lock = threading.Lock()
        self._data = self._load()

    # ── 내부 로드/저장 ───────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not os.path.exists(self.config_path):
            return {"boost_words": [], "settings": {"max_factor": 5.0, "min_factor": 1.1}}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"boost_words": [], "settings": {"max_factor": 5.0, "min_factor": 1.1}}

    def _save(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ── 조회 ─────────────────────────────────────────────────────────────────

    def get_all(self) -> List[dict]:
        """전체 가점 단어 목록 반환."""
        return list(self._data.get("boost_words", []))

    def get_categories(self) -> List[str]:
        """카테고리 목록 반환 (중복 제거, 순서 유지)."""
        seen = []
        for item in self._data.get("boost_words", []):
            c = item.get("category", "")
            if c and c not in seen:
                seen.append(c)
        return seen

    def get_boost_factor(self, word: str) -> float:
        """단어의 가점 배율 반환. enabled가 아니거나 없으면 1.0."""
        for item in self._data.get("boost_words", []):
            if item.get("word") == word and item.get("enabled", True):
                return float(item.get("factor", 1.0))
        return 1.0

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def add(self, word: str, factor: float, category: str = "") -> bool:
        word = word.strip()
        if not word:
            return False
        factor = round(max(1.0, min(float(factor), self._data["settings"]["max_factor"])), 2)
        with self._lock:
            for item in self._data["boost_words"]:
                if item["word"] == word:
                    item["factor"] = factor
                    item["category"] = category
                    item["enabled"] = True
                    self._save()
                    return True
            self._data["boost_words"].append({
                "word": word, "factor": factor,
                "category": category, "enabled": True
            })
            self._save()
        return True

    def remove(self, word: str) -> bool:
        with self._lock:
            before = len(self._data["boost_words"])
            self._data["boost_words"] = [
                i for i in self._data["boost_words"] if i["word"] != word
            ]
            if len(self._data["boost_words"]) < before:
                self._save()
                return True
        return False

    def update(self, word: str, factor: float = None, enabled: bool = None,
               category: str = None) -> bool:
        with self._lock:
            for item in self._data["boost_words"]:
                if item["word"] == word:
                    if factor is not None:
                        item["factor"] = round(
                            max(1.0, min(float(factor), self._data["settings"]["max_factor"])), 2
                        )
                    if enabled is not None:
                        item["enabled"] = enabled
                    if category is not None:
                        item["category"] = category
                    self._save()
                    return True
        return False

    # ── 파이프라인 적용 ───────────────────────────────────────────────────────

    def apply_to_frequency(self, word_freq: dict) -> dict:
        """word_frequency 딕셔너리에 가점 배율을 적용해 새 딕셔너리 반환.

        enabled된 단어만 factor를 곱한다. 나머지는 그대로 유지.
        반환값은 float 빈도 딕셔너리 (WordCloudGenerator와 호환).
        """
        boosts = {
            item["word"]: float(item["factor"])
            for item in self._data.get("boost_words", [])
            if item.get("enabled", True) and float(item.get("factor", 1.0)) != 1.0
        }
        if not boosts:
            return word_freq  # 가점 없으면 그대로
        return {
            word: freq * boosts.get(word, 1.0)
            for word, freq in word_freq.items()
        }


# ── 싱글톤 ───────────────────────────────────────────────────────────────────

_instance: Optional[WordBoostManager] = None
_instance_lock = threading.Lock()


def get_word_boost_manager() -> WordBoostManager:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                from src.config.settings import WORD_BOOST_CONFIG_PATH
                _instance = WordBoostManager(WORD_BOOST_CONFIG_PATH)
    return _instance
