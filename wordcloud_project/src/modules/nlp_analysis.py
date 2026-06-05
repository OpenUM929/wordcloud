#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import threading
from typing import Dict, Any, Optional
from kiwipiepy import Kiwi
from konlpy.tag import Okt
from utils.logger import setup_logger, get_log_file_path, get_timestamp

# wordcloud_pos 레이블 → Kiwi 품사 태그 매핑 (NNB 의존명사 제외)
_KIWI_POS_MAP = {
    'Noun':      ['NNG', 'NNP', 'SL'],   # SL: 영어/외래어
    'Verb':      ['VV'],
    'Adjective': ['VA'],
}

# Kiwi 태그 → wordcloud_pos 레이블 역매핑 (저장 시 기존 형식 유지)
_KIWI_TAG_TO_POS = {
    'NNG': 'Noun',
    'NNP': 'Noun',
    'SL':  'Noun',   # 영어/외래어 → Noun으로 분류
    'VV':  'Verb',
    'VA':  'Adjective',
}

# meaningful_words_with_pos 저장 시 항상 추출할 전체 품사 목록
_ALL_KIWI_POS_LABELS = ['Noun', 'Verb', 'Adjective']
_ALL_OKT_POS_LABELS  = ['Noun', 'Verb', 'Adjective']

class NLPAnalysis:
    """자연어 형태소 분석 모듈"""

    _instances = {}
    _lock = threading.Lock()

    def __init__(self, config_path: str = "configs/nlp_config.json"):
        """
        NLP 분석기 초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.timestamp = get_timestamp()

        # 로거 설정
        log_file = get_log_file_path(self.config["module_name"], self.timestamp)
        self.logger = setup_logger(self.config["module_name"], log_file)

        # 분석기 초기화
        self.kiwi = Kiwi() if self.config["kiwi"]["enabled"] else None
        self.okt = Okt() if self.config["okt"]["enabled"] else None

        self.logger.info("NLP 분석기 초기화 완료")

    @classmethod
    def get_instance(cls, config_path: str = "configs/nlp_config.json"):
        """싱글톤 인스턴스 반환 (Thread-safe)"""
        if config_path not in cls._instances:
            with cls._lock:
                if config_path not in cls._instances:
                    cls._instances[config_path] = cls(config_path)
        return cls._instances[config_path]

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """설정 파일 로드"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def analyze(self, text: str, output_path: Optional[str] = None, context: str = None) -> Dict[str, Any]:
        """
        텍스트 형태소 분석

        Args:
            text: 분석할 텍스트
            output_path: 결과 저장 경로 (None이면 저장 안함)
            context: 처리 상황 컨텍스트 (예: "👤 대상자 ID: U002, 평가 ID: 1")

        Returns:
            분석 결과 딕셔너리
        """
        log_prefix = context if context else ""
        if log_prefix:
            log_prefix = f"{log_prefix} | "
            
        self.logger.info(f"{log_prefix}텍스트 분석 시작: {len(text)}자")

        results = {
            "input_text": text,
            "analysis": {}
        }

        # Kiwi 분석
        if self.kiwi:
            try:
                kiwi_result = self.kiwi.analyze(text)
                # Kiwi 결과는 (tokens, score) 튜플 형태
                if isinstance(kiwi_result, tuple) and len(kiwi_result) >= 1:
                    tokens = kiwi_result[0]
                    kiwi_results = []
                    for token in tokens:
                        kiwi_results.append({
                            "form": token.form,
                            "tag": token.tag,
                            "start": token.start,
                            "len": token.len
                        })
                    results["analysis"]["kiwi_tokens"] = kiwi_results
                    self.logger.info(f"{log_prefix}Kiwi 분석 완료")
                else:
                    results["analysis"]["kiwi_tokens"] = {"error": "Unexpected result format"}
            except Exception as e:
                self.logger.error(f"{log_prefix}Kiwi 분석 실패: {e}")
                results["analysis"]["kiwi_tokens"] = {"error": str(e)}

        # Okt 분석 (형태소 태깅 결과 보존)
        okt_pos = None
        if self.okt:
            try:
                okt_pos = self.okt.pos(text)
                results["analysis"]["okt_morphemes"] = okt_pos
                self.logger.info(f"{log_prefix}Okt 분석 완료")
            except Exception as e:
                self.logger.error(f"{log_prefix}Okt 분석 실패: {e}")
                results["analysis"]["okt_morphemes"] = {"error": str(e)}

        # 의미 단어 추출 (Kiwi 우선 → NNB 의존명사 제외, fallback Okt)
        # meaningful_words_with_pos: 모든 품사 저장 (재생성 시 품사 옵션 변경 가능하도록)
        # meaningful_words: wordcloud_pos 필터 적용 (word_frequency 계산용)
        wordcloud_pos = self.config.get('wordcloud_pos', ['Noun', 'Verb', 'Adjective'])
        from src.modules.stopword_manager import get_stopword_manager
        manager = get_stopword_manager()
        try:
            if self.kiwi:
                all_with_pos = self._extract_meaningful_words_kiwi(text, _ALL_KIWI_POS_LABELS, manager)
                filtered_words = [w for w, pos in all_with_pos if pos in wordcloud_pos]
            elif okt_pos is not None:
                all_with_pos = self._extract_meaningful_words_okt(okt_pos, _ALL_OKT_POS_LABELS, manager)
                filtered_words = [w for w, pos in all_with_pos if pos in wordcloud_pos]
            else:
                all_with_pos = []
                filtered_words = []

            sentence_boundaries = self._extract_sentence_boundaries(text)
            results["analysis"]["meaningful_words"] = filtered_words
            results["analysis"]["meaningful_words_with_pos"] = all_with_pos
            results["analysis"]["sentence_boundaries"] = sentence_boundaries
            self.logger.info(f"{log_prefix}의미 단어 추출 완료: 전체 {len(all_with_pos)}개, 필터 {len(filtered_words)}개 (품사: {wordcloud_pos})")
        except Exception as e:
            self.logger.error(f"{log_prefix}의미 단어 추출 실패: {e}")
            results["analysis"]["meaningful_words"] = {"error": str(e)}
            results["analysis"]["meaningful_words_with_pos"] = {"error": str(e)}
            results["analysis"]["sentence_boundaries"] = {"error": str(e)}

        # 결과 저장
        if output_path and self.config["output"]["save_results"]:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            self.logger.info(f"{log_prefix}결과 저장 완료: {output_path}")

        self.logger.info(f"{log_prefix}텍스트 분석 완료")
        results["config"] = self.config
        return results

    def _extract_meaningful_words_kiwi(self, text: str, pos_labels: list, manager) -> list:
        """Kiwi 기반 의미 단어 추출 — NNB(의존명사) 제외.

        pos_labels: 추출할 품사 레이블 목록 ('Noun', 'Verb', 'Adjective')
        kiwipiepy 버전에 따라 token.tag가 str 또는 IntEnum일 수 있어 양쪽 처리.
        """
        allowed_tags = set()
        for label in pos_labels:
            allowed_tags.update(_KIWI_POS_MAP.get(label, []))

        try:
            tokens = self.kiwi.tokenize(text)
        except Exception as e:
            self.logger.warning(f"Kiwi tokenize 실패, 빈 목록 반환: {e}")
            return []

        result = []
        for token in tokens:
            tag = token.tag
            # kiwipiepy 버전에 따라 tag가 str이거나 IntEnum
            tag_str = tag if isinstance(tag, str) else (tag.name if hasattr(tag, 'name') else str(tag).split('.')[-1])
            word = token.form
            pos_label = _KIWI_TAG_TO_POS.get(tag_str)
            if pos_label and pos_label in pos_labels and len(word) > 1 and not manager.is_stopword(word):
                result.append((word, pos_label))
        return result

    def _extract_meaningful_words_okt(self, okt_pos: list, pos_labels: list, manager) -> list:
        """Okt 기반 의미 단어 추출 (Kiwi 미사용 시 fallback)."""
        result = []
        for word, pos in okt_pos:
            if pos in pos_labels and len(word) > 1 and not manager.is_stopword(word):
                result.append((word, pos))
        return result

    def analyze_word_pos(self, word: str) -> str:
        """
        단어의 품사 분석 (Okt 사용)

        Args:
            word: 분석할 단어

        Returns:
            품사 태그
        """
        try:
            if self.okt:
                pos_result = self.okt.pos(word)
                if pos_result:
                    print(f"품사 분석 결과 (Okt): {pos_result}")  # 디버그 로그
                    return pos_result[0][1]  # (word, pos) 튜플에서 pos 반환
            else:
                print("Okt 분석기가 활성화되지 않았습니다.")
        except Exception as e:
            print(f"단어 품사 분석 실패: {word} - {e}")
            import traceback
            print(f"스택 트레이스: {traceback.format_exc()}")
            self.logger.error(f"단어 품사 분석 실패: {word} - {e}")
        
        return 'Unknown'

    def _extract_sentence_boundaries(self, text: str) -> list:
        """
        문장 경계 추출

        Args:
            text: 분석할 텍스트

        Returns:
            문장 경계 위치 리스트
        """
        boundaries = []
        current_pos = 0

        # 문장 구분자 패턴
        sentence_end_patterns = ['.', '!', '?', '。', '！', '？']

        for i, char in enumerate(text):
            if char in sentence_end_patterns:
                boundaries.append(current_pos)
                current_pos = i + 1

        # 마지막 문장 추가
        if current_pos < len(text):
            boundaries.append(current_pos)

        return boundaries

def analyze_text(text: str, config_path: str = None,
                output_path: Optional[str] = None, context: str = None) -> Dict[str, Any]:
    """
    편의 함수: 텍스트 분석

    Args:
        text: 분석할 텍스트
        config_path: 설정 파일 경로 (기본값: 프로젝트 루트의 configs/nlp_config.json)
        output_path: 결과 저장 경로
        context: 처리 상황 컨텍스트 (예: "👤 대상자 ID: U002, 평가 ID: 1")

    Returns:
        분석 결과
    """
    if config_path is None:
        from src.config.settings import NLP_CONFIG_PATH
        config_path = NLP_CONFIG_PATH
    
    analyzer = NLPAnalysis.get_instance(config_path)
    return analyzer.analyze(text, output_path, context)
