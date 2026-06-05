#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import time
from typing import Dict, Any, Optional, List
from utils.logger import setup_logger, get_log_file_path, get_timestamp

# Kiwi 형태소 분석기 (1계층 탐지)
try:
    from kiwipiepy import Kiwi
    KIWI_AVAILABLE = True
except ImportError:
    KIWI_AVAILABLE = False

# 외부 라이브러리 import (선택적)
try:
    from profanity_check import predict_prob  # 영어 욕설 필터링
    PROFANITY_CHECK_AVAILABLE = True
except ImportError:
    PROFANITY_CHECK_AVAILABLE = False


class ProfanityFilter:
    """비속어 및 불용어 필터링 모듈 — 2계층 탐지 구조"""

    def __init__(self, config_path: str = "configs/profanity_config.json"):
        """
        비속어 필터 초기화

        Args:
            config_path: 설정 파일 경로
        """
        self.config = self._load_config(config_path)
        self.timestamp = get_timestamp()

        # 로거 설정
        log_file = get_log_file_path(self.config["module_name"], self.timestamp)
        self.logger = setup_logger(self.config["module_name"], log_file)

        # 필터 리스트 로드
        self.profanity_words = self.config.get("profanity_words", [])
        self.stop_words = self.config.get("stop_words", [])
        self.unhealthy_words = self.config.get("unhealthy_words", [])
        # 영어 욕설만 캐싱 (한글 없는 단어) — advanced_filter_text에서 반복 필터링 방지
        self.english_profanity_words = [w for w in self.profanity_words if not re.search(r'[가-힣]', w)]
        self.logger.info(f"영어 욕설 단어 {len(self.english_profanity_words)}개 캐싱")

        # ── 2계층 탐지 초기화 ──────────────────────────────────────────────────
        # 1계층: Kiwi 형태소 분석기
        self.kiwi = None
        if KIWI_AVAILABLE:
            try:
                self.kiwi = Kiwi()
                self.logger.info("Kiwi 형태소 분석기 로드됨")
            except Exception as e:
                self.logger.warning(f"Kiwi 초기화 실패: {e}")
        else:
            self.logger.warning("kiwipiepy 미설치 — 1계층 탐지 비활성화, substring fallback 사용")

        # 2계층: 음절 간격 regex 패턴 사전
        self._gap_patterns = self._build_gap_patterns()
        self.logger.info(f"음절 간격 패턴 {len(self._gap_patterns)}개 컴파일 완료")

        # 영어 필터링
        self.profanity_check_available = PROFANITY_CHECK_AVAILABLE
        if PROFANITY_CHECK_AVAILABLE:
            self.logger.info("profanity-check 라이브러리 로드됨")

        self.logger.info("비속어 필터 초기화 완료 (2계층 탐지)")

    # ── 내부 유틸리티 ────────────────────────────────────────────────────────

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """설정 파일 로드"""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # 기본 설정
            return {
                "module_name": "profanity_filter",
                "profanity_words": [
                    "시발", "씨발", "병신", "개새끼", "좆", "좃", "씹", "쌍놈", "쌍년", "새끼", "년", "놈",
                    "미친", "미친놈", "미친년", "개년", "개놈", "지랄", "지랄놈", "지랄년", "fuck", "shit",
                    "damn", "bitch", "asshole", "bastard", "cunt", "dick", "pussy"
                ],
                "stop_words": [
                    "이", "그", "저", "것", "수", "등", "에서", "에게", "으로", "에서", "이다", "하다",
                    "있다", "없다", "되다", "아니다", "이다", "것이다", "수 있다", "할 수 있다"
                ],
                "unhealthy_words": [
                    "섹스", "성관계", "포르노", "야동", "자위", "오르가즘", "사정", "음경", "보지",
                    "가슴", "젖", "엉덩이", "sex", "porn", "masturbate", "orgasm", "penis", "vagina",
                    "breast", "butt", "ass"
                ],
                "remove_special_chars": True,
                "output": {
                    "save_results": True
                }
            }

    def _build_gap_patterns(self) -> Dict[str, List[re.Pattern]]:
        """2계층: 각 욕설 단어의 '적어도 한 쌍 간격' regex 사전 컴파일.

        2음절:  시발 → [시[^가-힣]+발]
        3음절:  개새끼 → [개[^가-힣]+새[^가-힣]*끼, 개[^가-힣]*새[^가-힣]+끼]
        """
        patterns: Dict[str, List[re.Pattern]] = {}
        for word in self.profanity_words:
            syllables = list(word)
            n = len(syllables)
            if n < 2:
                continue
            word_patterns = []
            for forced_gap_idx in range(n - 1):
                parts = []
                for i in range(n - 1):
                    if i == forced_gap_idx:
                        parts.append(re.escape(syllables[i]) + r'[^가-힣]+')
                    else:
                        parts.append(re.escape(syllables[i]) + r'[^가-힣]*')
                parts.append(re.escape(syllables[-1]) + r'(?![가-힣])')
                pattern_str = ''.join(parts)
                try:
                    word_patterns.append(re.compile(pattern_str))
                except re.error:
                    continue
            if word_patterns:
                patterns[word] = word_patterns
        return patterns

    # ── 2계층 탐지 메서드 ──────────────────────────────────────────────────

    def _detect_by_morpheme(self, text: str) -> List[tuple]:
        """1계층: Kiwi 형태소 단위 완전 일치 탐지.

        원본 텍스트의 정확한 슬라이스(text[start:end])와 span을 함께 반환.
        반환: [(word: str, start: int, end: int), ...]
        """
        if not self.kiwi:
            return []
        try:
            tokens = self.kiwi.tokenize(text)
            return [(text[t.start:t.end], t.start, t.end) for t in tokens if t.form.lower() in self.profanity_words or t.form in self.profanity_words]
        except Exception as e:
            self.logger.warning(f"Kiwi tokenize 실패: {e}")
            return []

    def _detect_by_gap_pattern(self, text: str) -> List[tuple]:
        """2계층: 음절 사이 비한글 문자 허용 regex 탐지.

        '시. 발' → '시'와 '발' 사이 '. ' (한글 아님) → 매칭
        '개 새 끼' → '개'-'새'-'끼' 사이 공백 → 매칭
        '개!새끼' → '개'-'새' 사이 '!' (한글 아님) → 매칭
        '시스템 발전' → '시' 뒤 '스템 ' (한글 포함) → 미매칭

        반환: [(word, start, end), ...]
        """
        found = []
        for word, pattern_list in self._gap_patterns.items():
            for pattern in pattern_list:
                m = pattern.search(text)
                if m:
                    found.append((word, m.start(), m.end()))
                    break
        return found

    def _apply_filter(self, text: str, morpheme_detected: List[str], gap_detected: List[str]) -> str:
        """탐지된 욕설을 *** 로 치환.

        2계층 먼저 → 1계층 나중.
        (1계층 먼저 시 일부 음절만 치환되면 2계층 패턴이 깨질 수 있음)
        """
        # 2계층: 간격 패턴 치환 (먼저)
        for word in gap_detected:
            if word in self._gap_patterns:
                for pattern in self._gap_patterns[word]:
                    text = pattern.sub('***', text)

        # 1계층: 정확한 위치 치환 (나중)
        for exact_word in morpheme_detected:
            text = text.replace(exact_word, '***')

        return text

    def _detect_profanity(self, text: str) -> tuple:
        """2계층 탐지 통합 실행.

        반환: (morpheme_words, gap_words, morpheme_spans, gap_spans)
              각 spans 항목: (word: str, start: int, end: int)
        """
        morpheme_spans = []
        gap_spans = []
        # 1계층
        if self.kiwi:
            morpheme_spans = self._detect_by_morpheme(text)
        # 2계층 (1계층과 병행)
        gap_spans = self._detect_by_gap_pattern(text)
        morpheme_words = [m[0] for m in morpheme_spans]
        gap_words = [g[0] for g in gap_spans]
        return morpheme_words, gap_words, morpheme_spans, gap_spans

    # ── 공개 API ───────────────────────────────────────────────────────────

    def filter_text(self, text: str, remove_profanity: bool = True,
                   remove_stop_words: bool = True, remove_unhealthy: bool = True,
                   remove_special_chars: bool = True) -> Dict[str, Any]:
        """
        텍스트 필터링 — 2계층 탐지 구조 적용.

        Args:
            text: 필터링할 텍스트
            remove_profanity: 욕설 제거 여부
            remove_stop_words: 불용어 제거 여부
            remove_unhealthy: 비건전 단어 제거 여부
            remove_special_chars: 특수문자 제거 여부

        Returns:
            필터링 결과 딕셔너리
        """
        self.logger.info(f"텍스트 필터링 시작: {len(text)}자")

        start_time = time.time()
        original_text = text
        removed_items = []

        # 특수문자 제거
        if remove_special_chars:
            text = re.sub(r'[^\w\s가-힣]', '', text)
            if text != original_text:
                removed_items.append("특수문자")

        # 욕설 제거 — 2계층 탐지
        if remove_profanity:
            morpheme_detected, gap_detected = self._detect_profanity(text)
            if morpheme_detected or gap_detected:
                text = self._apply_filter(text, morpheme_detected, gap_detected)
                for word in set(morpheme_detected + gap_detected):
                    removed_items.append(f"욕설:{word}")

        # 비건전 단어 제거 — substring 유지 (복합어 오탐 위험 낮음)
        if remove_unhealthy:
            for word in self.unhealthy_words:
                if word in text:
                    text = text.replace(word, "***")
                    removed_items.append(f"비건전:{word}")

        # 불용어 제거 (단어 단위로 처리)
        if remove_stop_words:
            words = text.split()
            filtered_words = []
            for word in words:
                if word not in self.stop_words:
                    filtered_words.append(word)
                else:
                    removed_items.append(f"불용어:{word}")
            text = ' '.join(filtered_words)

        processing_time = int((time.time() - start_time) * 1000)

        result = {
            "original_text": original_text,
            "filtered_text": text,
            "original_length": len(original_text),
            "filtered_length": len(text),
            "removed_items": list(set(removed_items)),  # 중복 제거
            "processing_time_ms": processing_time
        }

        self.logger.info(f"텍스트 필터링 완료: {len(removed_items)}개 항목 제거, {processing_time}ms 소요")

        return result

    def detect_language(self, text: str) -> str:
        """
        텍스트 언어 감지

        Args:
            text: 분석할 텍스트

        Returns:
            언어 코드 ("ko": 한국어, "en": 영어, "mixed": 혼합, "unknown": 알 수 없음)
        """
        korean_chars = len(re.findall(r'[가-힣]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        total_chars = len(text.replace(' ', ''))

        if total_chars == 0:
            return "unknown"

        korean_ratio = korean_chars / total_chars
        english_ratio = english_chars / total_chars

        if korean_ratio > 0.7:
            return "ko"
        elif english_ratio > 0.7:
            return "en"
        elif korean_chars > 0 and english_chars > 0:
            return "mixed"
        else:
            return "unknown"

    def advanced_filter_text(self, text: str, context: str = None) -> Dict[str, Any]:
        """
        고급 필터링 — 2계층 탐지 + 영어 profanity-check 통합.

        korcen 의존성 제거. Kiwi 기반 1/2계층으로 대체.

        Args:
            text: 필터링할 텍스트
            context: 처리 상황 컨텍스트 (예: "👤 대상자 ID: U002, 평가 ID: 1")

        Returns:
            고급 필터링 결과
        """
        log_prefix = context if context else ""
        if log_prefix:
            log_prefix = f"{log_prefix} | "

        self.logger.info(f"{log_prefix}고급 텍스트 필터링 시작: {len(text)}자")

        start_time = time.time()
        original_text = text
        detected_profanity = []
        filtered_text = text
        methods_used = []
        morpheme_spans = []
        gap_spans = []

        # 언어 감지
        language = self.detect_language(text)
        self.logger.info(f"{log_prefix}감지된 언어: {language}")

        # ── 한국어 텍스트 필터링 (2계층 탐지) ─────────────────────────────────
        # 짧은 텍스트/특수문자 포함 시 detect_language가 'unknown'으로 분류할 수 있음
        # 한글 문자라도 포함되어 있으면 2계층 탐지 실행
        has_korean = bool(re.search(r'[가-힣]', text))
        if language in ["ko", "mixed"] or (language == "unknown" and has_korean):
            morpheme_detected, gap_detected, morpheme_spans, gap_spans = self._detect_profanity(text)
            if morpheme_detected or gap_detected:
                filtered_text = self._apply_filter(filtered_text, morpheme_detected, gap_detected)
                detected_profanity.extend(morpheme_detected)
                detected_profanity.extend(gap_detected)
                if morpheme_detected:
                    methods_used.append("kiwi_morpheme")
                if gap_detected:
                    methods_used.append("gap_pattern")
                self.logger.info(f"{log_prefix}한국어 욕설 탐지: {set(morpheme_detected + gap_detected)}")

        # ── 영어 욕설 직접 탐지 (언어 구분 무관, 캐싱 목록 사용) ───────────────
        # morpheme_spans 항목: (word: str, start: int, end: int)
        existing_spans = {(s, e) for _, s, e in morpheme_spans}
        english_found = []
        for word in self.english_profanity_words:
            for m in re.finditer(re.escape(word), text, re.IGNORECASE):
                if (m.start(), m.end()) not in existing_spans:
                    morpheme_spans.append((m.group(), m.start(), m.end()))
                    existing_spans.add((m.start(), m.end()))
                    w_lower = m.group().lower()
                    if w_lower not in detected_profanity:
                        detected_profanity.append(w_lower)
                        english_found.append(w_lower)
        if english_found:
            filtered_text = self._apply_filter(filtered_text, english_found, [])
            methods_used.append("direct_match")
            self.logger.info(f"{log_prefix}영어 욕설 직접 탐지: {set(english_found)}")

        # ── 영어 텍스트 필터링 (profanity-check) ─────────────────────────────
        if language in ["en", "mixed"] and self.profanity_check_available:
            try:
                prob = predict_prob([text])[0]
                if prob > 0.8:
                    words = text.split()
                    for i, word in enumerate(words):
                        if len(word) > 3:
                            word_prob = predict_prob([word])[0]
                            if word_prob > 0.9:
                                words[i] = "***"
                                detected_profanity.append(word)
                    filtered_text = ' '.join(words)
                    methods_used.append("profanity_check")
                    self.logger.info(f"{log_prefix}profanity-check 필터링 적용됨")
            except Exception as e:
                self.logger.warning(f"{log_prefix}profanity-check 필터링 실패: {e}")

        # ── 비건전 단어 (한글/영어 공통) ─────────────────────────────────────
        for word in self.unhealthy_words:
            if word in original_text:
                filtered_text = filtered_text.replace(word, "***")
                detected_profanity.append(word)

        processing_time = int((time.time() - start_time) * 1000)

        # 탐지 상세 정보 조립 (span 포함)
        detection_details = [
            {"word": w, "layer": "morpheme", "method": "kiwi_morpheme", "span": [s, e]}
            for w, s, e in morpheme_spans
        ] + [
            {"word": w, "layer": "gap", "method": "gap_pattern", "span": [s, e]}
            for w, s, e in gap_spans
        ]

        result = {
            "original_text": original_text,
            "filtered_text": filtered_text,
            "language": language,
            "detected_profanity": list(set(detected_profanity)),
            "methods_used": methods_used,
            "profanity_count": len(set(detected_profanity)),
            "processing_time_ms": processing_time,
            "detection_details": detection_details,
        }

        self.logger.info(f"{log_prefix}고급 필터링 완료: {len(set(detected_profanity))}개 욕설 검출, {processing_time}ms 소요")

        return result


# ── 싱글톤 인스턴스 저장 ───────────────────────────────────────────────────
_profanity_filter_instance = None

def filter_profanity(text: str, remove_profanity: bool = True,
                    remove_stop_words: bool = True, remove_unhealthy: bool = True,
                    remove_special_chars: bool = True,
                    config_path: str = "configs/profanity_config.json") -> Dict[str, Any]:
    """
    편의 함수: 기본 텍스트 필터링
    """
    global _profanity_filter_instance
    if _profanity_filter_instance is None:
        _profanity_filter_instance = ProfanityFilter(config_path)
    return _profanity_filter_instance.filter_text(text, remove_profanity, remove_stop_words,
                                                  remove_unhealthy, remove_special_chars)


def advanced_filter_profanity(text: str, config_path: str = "configs/profanity_config.json", context: str = None) -> Dict[str, Any]:
    """
    편의 함수: 고급 텍스트 필터링 (2계층 탐지 통합)
    """
    global _profanity_filter_instance
    if _profanity_filter_instance is None:
        _profanity_filter_instance = ProfanityFilter(config_path)
    return _profanity_filter_instance.advanced_filter_text(text, context)
