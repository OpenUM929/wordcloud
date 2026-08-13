#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import threading
from typing import Dict, List, Optional
from utils.logger import setup_logger, get_log_file_path, get_timestamp
from src.modules.nlp_analysis import NLPAnalysis

# Okt 품사 태그-카테고리 매핑
POS_CATEGORY_MAPPING = {
    # 관사/대명사
    'Determiner': '관사/대명사',
    'Noun': '명사',
    'Pronoun': '관사/대명사',

    # 조사
    'Josa': '조사',

    # 동사
    'Verb': '동사',
    'Adjective': '형용사',
    'Adverb': '부사',

    # 접속사
    'Conjunction': '접속사',

    # 감탄사
    'Exclamation': '감탄사',

    # 기타
    'Foreign': '기타',
    'Alpha': '기타',
    'Number': '기타',
    'Punctuation': '기타',
    'Suffix': '기타',
    'Prefix': '기타',
    'Unknown': '기타'
}

# 이름 전용 불용어 파일(stopwords_names.json)의 카테고리명 — 항상 이 값으로 고정된다.
NAMES_CATEGORY = '인명'


class StopwordManager:
    """불용어 사전 관리 모듈

    저장 파일은 두 곳으로 분리된다(2026-08-13 stopword-import 계획 D-3):
    - 일반 불용어: config_path (기본 settings.STOPWORDS_CONFIG_PATH, stopwords.json)
    - 직원 실명 전용: settings.STOPWORDS_NAMES_CONFIG_PATH (stopwords_names.json, PII·배포 제외)

    런타임 조회(is_stopword 등)는 두 파일의 단어를 합쳐서 판단하지만, 저장은 항상
    출처 파일에만 반영한다 — 이름이 stopwords.json 에 섞여 배포 패키지로 유출되지
    않게 하기 위함(DL-9).
    """

    def __init__(self, config_path: str = "configs/stopwords.json"):
        """
        불용어 관리자 초기화

        Args:
            config_path: 일반 불용어 설정 파일 경로
        """
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.timestamp = get_timestamp()

        # 로거 설정
        log_file = get_log_file_path(self.config["module_name"], self.timestamp)
        self.logger = setup_logger(self.config["module_name"], log_file)

        # 일반 불용어 리스트 로드
        self.stopwords: Dict[str, List[str]] = self._load_stopwords()

        # 이름 전용 불용어 파일 로드 — 없으면 빈 것으로 취급(에러 아님)
        self.names_config_path = self._resolve_names_config_path()
        self._names_config, self._names_words = self._load_names_file(self.names_config_path)
        if self._names_words:
            merged = list(self.stopwords.get(NAMES_CATEGORY, []))
            seen = set(merged)
            for w in self._names_words:
                if w not in seen:
                    merged.append(w)
                    seen.add(w)
            self.stopwords[NAMES_CATEGORY] = merged

        # 조회용 평탄화 리스트 + O(1) 조회용 set (둘 다 이름 파일 포함)
        self._stopword_index: set = set()
        self.all_stopwords: List[str] = self._flatten_stopwords()

        # NLP 분석기 초기화를 지연시켜 JVM 초기화 오류 방지
        self.nlp_analyzer = None

        self.logger.info("불용어 사전 초기화 완료")
        self.logger.info(f"불용어 카테고리 수: {len(self.stopwords)}")
        self.logger.info(f"총 불용어 수: {len(self.all_stopwords)}")

    # ── 이름 전용 파일 로드/저장 ─────────────────────────────────────────────

    def _resolve_names_config_path(self) -> str:
        """settings.STOPWORDS_NAMES_CONFIG_PATH 를 얻는다. import 실패 시(단독 실행 등)
        일반 설정 파일과 같은 디렉터리의 stopwords_names.json 으로 대체한다."""
        try:
            from src.config.settings import STOPWORDS_NAMES_CONFIG_PATH
            return STOPWORDS_NAMES_CONFIG_PATH
        except Exception:
            base_dir = os.path.dirname(self.config_path) or "."
            return os.path.join(base_dir, "stopwords_names.json")

    def _load_names_file(self, path: str):
        """이름 전용 불용어 파일 로드. 파일이 없으면 (None, []) — 에러 아님."""
        if not path or not os.path.exists(path):
            return None, []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception as e:
            self.logger.error(f"이름 불용어 파일 로드 실패: {path} - {e}")
            return None, []

        words: List[str] = []
        seen = set()
        for category in cfg.get("categories", []):
            if category.get("name") != NAMES_CATEGORY:
                continue
            for w in category.get("words", []):
                if w not in seen:
                    seen.add(w)
                    words.append(w)
        return cfg, words

    def _save_names_stopwords(self) -> bool:
        """이름 전용 불용어 파일(stopwords_names.json) 저장 — 일반 stopwords.json 은
        건드리지 않는다. 파일이 처음 만들어지는 경우 stopwords.json 과 동일한 스키마로
        생성한다."""
        try:
            path = self.names_config_path
            cfg = self._names_config
            if not cfg:
                cfg = {
                    "module_name": "stopword_manager_names",
                    "description": "직원 실명 전용 불용어 사전 (PII — 배포 패키지 제외 대상)",
                    "categories": [],
                    "settings": {
                        "ignore_comments": True,
                        "normalize_case": True,
                        "min_word_length": 1,
                        "max_word_length": 10
                    }
                }
            cfg["categories"] = [{"name": NAMES_CATEGORY, "words": list(self._names_words)}]

            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)

            self._names_config = cfg
            self.logger.info("이름 불용어 사전 저장 완료")
            return True
        except Exception as e:
            self.logger.error(f"이름 불용어 사전 저장 실패: {e}")
            return False

    def _get_nlp_analyzer(self):
        """NLP 분석기 인스턴스 가져오기 (지연 초기화)"""
        if self.nlp_analyzer is None:
            from src.config.settings import NLP_CONFIG_PATH
            self.nlp_analyzer = NLPAnalysis.get_instance(NLP_CONFIG_PATH)
        return self.nlp_analyzer

    def _analyze_word_pos(self, word: str) -> str:
        """
        단어의 품사 분석 (NLPAnalysis 사용)

        Args:
            word: 분석할 단어

        Returns:
            품사 태그
        """
        try:
            # NLPAnalysis를 통해 단어의 품사 분석 (지연 초기화)
            pos = self._get_nlp_analyzer().analyze_word_pos(word)
            return pos
        except Exception as e:
            self.logger.error(f"단어 품사 분석 실패: {word} - {e}")

        return 'Unknown'

    def _pos_to_category(self, pos: str) -> str:
        """
        품사 태그를 카테고리로 변환

        Args:
            pos: 품사 태그

        Returns:
            카테고리 이름
        """
        return POS_CATEGORY_MAPPING.get(pos, '기타')

    def auto_classify_word(self, word: str) -> str:
        """
        단어를 자동으로 카테고리 분류

        Args:
            word: 분류할 단어

        Returns:
            자동으로 분류된 카테고리 이름
        """
        word = word.strip()
        if not word:
            return '기타'

        # 품사 분석
        pos = self._analyze_word_pos(word)

        # 카테고리 매핑
        category = self._pos_to_category(pos)

        self.logger.info(f"단어 '{word}' 자동 분류: {pos} -> {category}")

        return category

    def _load_config(self, config_path: str) -> Dict:
        """설정 파일 로드"""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # 기본 설정
            return {
                "module_name": "stopword_manager",
                "description": "한국어 불용어 사전 - 일반적인 불용어 + 업무 분석에 적합한 불용어",
                "categories": [
                    {
                        "name": "일반 불용어",
                        "words": ["이", "그", "저", "것", "수", "등", "때"]
                    },
                    {
                        "name": "관사/대명사",
                        "words": ["는", "을", "를", "이", "가", "에", "의", "으로", "로", "에서", "랑", "과", "도", "만", "뿐", "까지", "부터"]
                    },
                    {
                        "name": "조사",
                        "words": ["은", "는", "이", "가", "을", "를", "에", "의", "로", "으로", "에서", "부터", "까지"]
                    },
                    {
                        "name": "동사",
                        "words": ["있", "하", "되", "수", "있다", "한다", "되다"]
                    },
                    {
                        "name": "접속사",
                        "words": ["그리고", "그러나", "하지만", "때문에", "그래서", "따라서", "그런데", "만약", "만약에", "하도록", "하시면", "있는", "없는", "있을", "없을"]
                    },
                    {
                        "name": "형용사",
                        "words": ["좋", "나쁘", "크", "작", "높", "낮", "빠르", "느리", "강", "약"]
                    },
                    {
                        "name": "명사",
                        "words": ["사람", "것", "일", "년", "월", "일", "시간", "분", "초", "장소", "방법", "이유", "문제", "생각", "사실", "경우", "예", "가지"]
                    },
                    {
                        "name": "업무 관련",
                        "words": ["직원", "사원", "팀원", "매니저", "리더", "책임자", "부서", "회사", "업무", "일", "프로젝트", "계획", "보고", "회의"]
                    }
                ],
                "settings": {
                    "ignore_comments": True,
                    "normalize_case": True,
                    "min_word_length": 1,
                    "max_word_length": 10
                }
            }

    def _load_stopwords(self) -> Dict[str, List[str]]:
        """불용어 리스트 로드 (JSON 파일만 로드)"""
        stopwords = {}

        # JSON 파일에서 카테고리별 불용어 로드 (전체 카테고리에서 중복 제거)
        seen_words = set()
        for category in self.config.get("categories", []):
            unique_words = []
            for word in category["words"]:
                if word not in seen_words:
                    unique_words.append(word)
                    seen_words.add(word)
            stopwords[category["name"]] = unique_words

        return stopwords

    def _flatten_stopwords(self) -> List[str]:
        """모든 카테고리의 불용어를 평탄화한 리스트 반환.

        부수효과로 self._stopword_index(set)도 함께 갱신한다 — is_stopword 의
        O(1) 조회를 위한 인덱스이며, 이 메서드를 호출하는 모든 지점
        (__init__·add_stopword·add_stopwords_bulk·remove_stopword)에서 자동으로
        같이 갱신된다.
        """
        all_stopwords = []
        for category in self.stopwords.values():
            all_stopwords.extend(category)
        self._stopword_index = set(all_stopwords)
        return all_stopwords  # 중복이 이미 제거된 상태이므로 리스트 자체엔 set 불필요

    def get_stopwords_by_category(self, category: str) -> Optional[List[str]]:
        """
        카테고리별 불용어 리스트 반환

        Args:
            category: 카테고리 이름

        Returns:
            카테고리에 해당하는 불용어 리스트, 없으면 None
        """
        return self.stopwords.get(category)

    def get_all_categories(self) -> List[str]:
        """모든 카테고리 이름 반환"""
        return list(self.stopwords.keys())

    def get_all_stopwords(self) -> List[str]:
        """전체 불용어 리스트 반환 (기존 반환 계약 유지 — 리스트)"""
        return self.all_stopwords

    def is_stopword(self, word: str) -> bool:
        """
        단어가 불용어인지 확인 (O(1) set 조회 — 이름 수천 건 등록 후에도 성능 저하 없음)

        Args:
            word: 확인할 단어

        Returns:
            불용어 여부 (True/False)
        """
        return word.strip() in self._stopword_index

    def filter_stopwords(self, text: str) -> str:
        """
        텍스트에서 불용어 제거

        Args:
            text: 필터링할 텍스트

        Returns:
            불용어가 제거된 텍스트
        """
        self.logger.info(f"텍스트 필터링 시작: {len(text)}자")

        words = text.split()
        filtered_words = []
        for word in words:
            if not self.is_stopword(word):
                filtered_words.append(word)

        filtered_text = ' '.join(filtered_words)
        self.logger.info(f"텍스트 필터링 완료: {len(text) - len(filtered_text)}자 제거")

        return filtered_text

    def add_stopword(self, word: str, category: str = "기타") -> bool:
        """
        불용어 추가

        Args:
            word: 추가할 불용어
            category: 카테고리 이름 (기본: 기타)

        Returns:
            성공 여부 (True/False)
        """
        word = word.strip()
        if not word:
            self.logger.warning("빈 단어는 추가할 수 없습니다.")
            return False

        if category not in self.stopwords:
            self.stopwords[category] = []

        if word not in self.stopwords[category]:
            self.stopwords[category].append(word)
            self.all_stopwords = self._flatten_stopwords()
            self.logger.info(f"불용어 추가: {word} ({category})")
            return True
        else:
            self.logger.warning(f"불용어 already exists: {word} ({category})")
            return False

    def add_stopwords_bulk(self, words, category: str = '기타', dry_run: bool = False,
                            target: str = 'general') -> Dict:
        """단어 목록을 한 번에 추가한다(파일 일괄 등록용).

        Args:
            words: 단어 목록(리스트·pandas Series 등 반복 가능). None·NaN·빈 문자열 포함 가능.
            category: 저장할 카테고리. target='names' 면 무시되고 항상 '인명'으로 강제된다.
            dry_run: True 면 사전·파일을 변경하지 않고 집계만 반환한다(미리보기).
            target: 'general'(기존 stopwords.json) | 'names'(stopwords_names.json, 실명 전용).

        Returns:
            {'total','added','duplicated','invalid','added_words','duplicated_words','invalid_words'}

        Raises:
            ValueError: target 이 유효하지 않거나, target='general' 인데 category='인명' 인 경우
                        (인명은 이름 업로드 전용 — 일반 업로드에서 거부).
        """
        if target not in ('general', 'names'):
            raise ValueError(f"target은 'general' 또는 'names' 여야 합니다: {target!r}")

        if target == 'names':
            category = NAMES_CATEGORY
        elif category == NAMES_CATEGORY:
            raise ValueError("일반 업로드에는 '인명' 카테고리를 사용할 수 없습니다. 이름 업로드를 이용해 주세요.")

        words = list(words)

        # 정규화 + 분류 (빈 값/nan 제외, 길이<=1 무효, 사전에 이미 있거나 파일 내 중복이면 duplicated)
        existing_words = set(self.stopwords.get(category, []))
        seen = set(existing_words)

        added_words: List[str] = []
        duplicated_words: List[str] = []
        invalid_words: List[str] = []

        for raw in words:
            if raw is None:
                invalid_words.append('')
                continue
            w = str(raw).strip()
            if not w or w.lower() == 'nan':
                invalid_words.append(w)
                continue
            if len(w) <= 1:
                invalid_words.append(w)
                continue
            if w in seen:
                duplicated_words.append(w)
                continue
            seen.add(w)
            added_words.append(w)

        result = {
            'total': len(words),
            'added': len(added_words),
            'duplicated': len(duplicated_words),
            'invalid': len(invalid_words),
            'added_words': added_words,
            'duplicated_words': duplicated_words,
            'invalid_words': invalid_words,
        }

        if dry_run or not added_words:
            return result

        if category not in self.stopwords:
            self.stopwords[category] = []
        self.stopwords[category].extend(added_words)
        self.all_stopwords = self._flatten_stopwords()

        if target == 'names':
            self._names_words = list(self._names_words) + added_words
            self._save_names_stopwords()
        else:
            self.save_stopwords()

        return result

    def remove_stopword(self, word: str) -> bool:
        """
        불용어 삭제

        Args:
            word: 삭제할 불용어

        Returns:
            성공 여부 (True/False)
        """
        word = word.strip()
        removed = False

        for category in self.stopwords:
            if word in self.stopwords[category]:
                self.stopwords[category].remove(word)
                removed = True

        if removed:
            self.all_stopwords = self._flatten_stopwords()
            self.logger.info(f"불용어 삭제: {word}")
            return True
        else:
            self.logger.warning(f"불용어 not found: {word}")
            return False

    def save_stopwords(self, config_path: Optional[str] = None) -> bool:
        """
        불용어 사전 저장 (일반 stopwords.json 만 대상 — 이름 전용 파일은
        _save_names_stopwords() 가 별도로 처리한다)

        Args:
            config_path: 저장 경로. None 이면 settings.STOPWORDS_CONFIG_PATH
                         (모듈 생성 시 받은 config_path 로 폴백)를 사용한다 —
                         실행 디렉터리와 무관하게 정본 경로에 저장하기 위함.

        Returns:
            성공 여부 (True/False)
        """
        if config_path is None:
            try:
                from src.config.settings import STOPWORDS_CONFIG_PATH
                config_path = STOPWORDS_CONFIG_PATH
            except Exception:
                config_path = self.config_path or "configs/stopwords.json"

        try:
            # self.stopwords의 변경 사항을 self.config에 동기화.
            # '인명' 카테고리는 이름 전용 파일에서 병합해 온 단어를 포함하고 있을 수
            # 있으므로, 일반 파일에는 그 단어들을 제외하고 쓴다(DL-9 — PII 유출 방지).
            names_only = set(self._names_words)
            categories = []
            for category_name, words in self.stopwords.items():
                if category_name == NAMES_CATEGORY:
                    words = [w for w in words if w not in names_only]
                    if not words:
                        continue
                categories.append({
                    "name": category_name,
                    "words": words
                })
            self.config["categories"] = categories

            # 디렉토리 생성 (존재하지 않을 경우)
            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            # JSON 파일로 저장
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)

            self.logger.info("불용어 사전 저장 완료")
            return True
        except Exception as e:
            self.logger.error(f"불용어 사전 저장 실패: {e}")
            return False

# 싱글톤 인스턴스 저장
_stopword_manager_instance = None
_stopword_manager_lock = threading.Lock()

def get_stopword_manager(config_path: Optional[str] = None) -> StopwordManager:
    """
    싱글톤 인스턴스 반환 (Thread-safe)

    Args:
        config_path: 설정 파일 경로. None 이면 settings.STOPWORDS_CONFIG_PATH 사용 —
                     실행 디렉터리(os.getcwd())와 무관하게 항상 같은 파일을 가리킨다.

    Returns:
        StopwordManager 인스턴스
    """
    global _stopword_manager_instance
    if _stopword_manager_instance is None:
        with _stopword_manager_lock:
            if _stopword_manager_instance is None:
                if config_path is None:
                    from src.config.settings import STOPWORDS_CONFIG_PATH
                    config_path = STOPWORDS_CONFIG_PATH
                _stopword_manager_instance = StopwordManager(config_path)
    return _stopword_manager_instance

def filter_stopwords(text: str, config_path: Optional[str] = None) -> str:
    """
    불용어 필터링 편의 함수

    Args:
        text: 필터링할 텍스트
        config_path: 설정 파일 경로 (None 이면 settings.STOPWORDS_CONFIG_PATH)

    Returns:
        불용어가 제거된 텍스트
    """
    manager = get_stopword_manager(config_path)
    return manager.filter_stopwords(text)

def is_stopword(word: str, config_path: Optional[str] = None) -> bool:
    """
    불용어 확인 편의 함수

    Args:
        word: 확인할 단어
        config_path: 설정 파일 경로 (None 이면 settings.STOPWORDS_CONFIG_PATH)

    Returns:
        불용어 여부 (True/False)
    """
    manager = get_stopword_manager(config_path)
    return manager.is_stopword(word)
