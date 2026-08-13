"""
재현 스크립트: extra 미전달 로깅 호출로 KeyError 발생 확인
"""
import sys
import os

# 경로 설정
sys.path.insert(0, os.path.dirname(__file__))

from utils.logger import get_pipeline_logger

if __name__ == '__main__':
    logger = get_pipeline_logger()

    print("=== 재현 테스트: extra 미전달 호출 ===")
    print("logger.info('[batch] stage6 start batch_id=test') 호출...\n")

    # extra 없이 호출 (이전엔 KeyError: 'request_id' 발생)
    logger.info('[batch] stage6 start batch_id=test')

    print("\n✓ 에러 없이 출력됨 (필터가 기본값 주입)")
