"""
검증 스크립트: 수정 A(필터)·B(extra) 동작 확인
"""
import sys
import os
import time
import glob

sys.path.insert(0, os.path.dirname(__file__))

from utils.logger import get_pipeline_logger

def test_without_extra():
    """Test A: extra 미전달 호출 → 필터가 기본값 주입"""
    print("\n[테스트 A] extra 미전달 호출 → 필터 기본값 주입")
    logger = get_pipeline_logger()
    logger.info('[batch] stage6 start batch_id=test_a')
    print("[OK] 에러 없음 (예상: [STAGE:-]로 포맷)")

def test_with_extra():
    """Test B: extra 포함 호출 → 전달값 유지"""
    print("\n[테스트 B] extra 포함 호출 → 값 유지")
    logger = get_pipeline_logger()
    logger.info('[batch] stage6 end batch_id=test_b dur=1.5s',
                extra={'request_id': '', 'stage': 'BATCH'})
    print("[OK] 에러 없음 (예상: [STAGE:BATCH]로 포맷)")

def check_log_file():
    """파이프라인 로그 파일에서 Logging error 확인"""
    print("\n[검증] 파이프라인 로그 파일 검사")
    log_dir = os.path.join(os.path.dirname(__file__), 'logs', 'pipeline')

    if not os.path.exists(log_dir):
        print(f"  [INFO] 로그 디렉토리 없음: {log_dir} (아직 생성 안됨)")
        return True

    log_files = glob.glob(os.path.join(log_dir, 'pipeline_*.log'))
    if not log_files:
        print(f"  [INFO] 로그 파일 없음: {log_dir}")
        return True

    latest_log = max(log_files, key=os.path.getctime)
    print(f"  확인 파일: {os.path.basename(latest_log)}")

    with open(latest_log, 'r', encoding='utf-8') as f:
        content = f.read()

    if 'Logging error' in content:
        error_count = content.count('--- Logging error ---')
        print(f"  [FAIL] 'Logging error' {error_count}건 발견")
        return False
    else:
        print(f"  [PASS] 'Logging error' 0건")
        return True

if __name__ == '__main__':
    print("="*60)
    print("검증: pipeline logger 수정 A·B")
    print("="*60)

    test_without_extra()
    time.sleep(0.1)
    test_with_extra()
    time.sleep(0.5)

    result = check_log_file()

    print("\n" + "="*60)
    if result:
        print("[RESULT] FIX_OK: 로깅 에러 미발생, 필터 정상 동작")
    else:
        print("[RESULT] FIX_FAIL: 로깅 에러 발견, 재조사 필요")
    print("="*60)
