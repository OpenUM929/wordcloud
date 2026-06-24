#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
from datetime import datetime

def setup_logger(name: str, log_file: str = None, level: int = logging.INFO) -> logging.Logger:
    """
    로거 설정 함수

    Args:
        name: 로거 이름
        log_file: 로그 파일 경로 (None이면 파일 로깅 안함)
        level: 로깅 레벨

    Returns:
        설정된 로거 객체
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # getLogger(name)은 이름이 같으면 동일 싱글톤을 반환한다.
    # 핸들러가 이미 붙어 있으면 재사용한다 — 매 호출마다 FileHandler를 중복
    # 추가하면 열린 로그 파일이 누적되어 'Too many open files'(Errno 24)가
    # 발생한다(그룹/매트릭스 저장처럼 WordCloudGenerator를 루프로 생성할 때).
    if logger.handlers:
        return logger

    # 포맷터 설정
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러 (선택적)
    if log_file:
        # 로그 디렉토리 생성
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

def get_timestamp() -> str:
    """현재 타임스탬프 반환"""
    return datetime.now().strftime('%Y%m%d_%H%M%S')

def get_log_file_path(module_name: str, timestamp: str = None) -> str:
    """모듈별 로그 파일 경로 생성"""
    if timestamp is None:
        timestamp = get_timestamp()
    return f"logs/{module_name}_{timestamp}.log"
