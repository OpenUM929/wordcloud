"""텍스트 전처리 모듈 — split_sentences 정의 (경량, 무거운 의존 없음)."""

import re


def split_sentences(text):
    """문서를 문장 단위로 분할. 인사말 제외."""
    if not text:
        return []
    # 기본 분할: . ! ? \n
    raw = re.split(r'[.!?\n]+', text)
    sentences = [s.strip() for s in raw if s.strip()]
    # 인사말 필터
    greetings = {'감사합니다', '수고하셨습니다', '좋은 하루', '고맙습니다',
                 '감사드립니다', '수고 많으셨습니다'}
    filtered = []
    for s in sentences:
        if any(g in s for g in greetings):
            continue
        if len(s) < 5:  # 너무 짧은 문장 제외
            continue
        filtered.append(s)
    return filtered


__all__ = ['split_sentences']
