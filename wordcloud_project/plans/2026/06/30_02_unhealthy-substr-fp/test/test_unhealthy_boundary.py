#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""0630_02 회귀: 비건전 단어 substring 오탐 수정.

복합어 내부 부분 문자열(회사정책의 '사정', assessment의 'ass')이 더는
욕설/비건전으로 검출되지 않음을 검증한다. 실제 비건전어 단독 사용은 정탐 유지.

실행: cwd=wordcloud_project 에서
    python plans/2026/0630_02_unhealthy-substr-fp/test/test_unhealthy_boundary.py
"""
import os
import sys

try:  # 한글 출력이 콘솔 인코딩(cp949)에서 깨지지 않도록
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# wordcloud_project 루트를 import 경로에 추가
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.modules.profanity_filter import advanced_filter_profanity


# 복합어 내부 부분 문자열 오탐 — 본 수정(형태소/단어경계)이 해결하는 클래스.
# (입력, 검출되면 안 되는 단어)
NO_FALSE_POSITIVE = [
    ('대내외 소통을 통한 회사정책 홍보 능력 탁월', '사정'),   # 원 버그: 회사정책의 '사정'
    ('Strong performance in the assessment', 'ass'),         # assessment의 'ass'
    ('He leads the class with passion', 'ass'),              # class/passion의 'ass'
    ('Press the button to submit', 'butt'),                  # button의 'butt'
    # 동음이의어 — 사정/가슴/젖 리스트 제외(2026-06-30 결정)로 검출 0
    ('회사 사정으로 일정이 지연되었습니다', '사정'),
    ('사정상 참석이 어렵습니다', '사정'),
    ('가슴 벅찬 성과를 달성함', '가슴'),
    ('비에 젖은 자료를 복구함', '젖'),
]

# 실제 비건전어가 단독 형태소/단어로 등장 → 정탐 유지(검출 1)
TRUE_POSITIVE = [
    ('sex offender', 'sex'),
]


def run():
    failures = []

    for text, forbidden in NO_FALSE_POSITIVE:
        det = advanced_filter_profanity(text)['detected_profanity']
        if forbidden in det:
            failures.append(f"[오탐] {text!r} → '{forbidden}' 검출됨 (detected={det})")
        elif det:
            # 다른 단어가 잡혔다면 참고용으로 표시(실패는 아님)
            print(f"  (참고) {text!r} → 비대상 검출 {det}")

    for text, expected in TRUE_POSITIVE:
        det = advanced_filter_profanity(text)['detected_profanity']
        if expected not in det:
            failures.append(f"[미탐] {text!r} → '{expected}' 검출 안 됨 (detected={det})")

    if failures:
        print("FAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print(f"PASS — 오탐 {len(NO_FALSE_POSITIVE)}건 0 / 정탐 {len(TRUE_POSITIVE)}건 유지")
    return 0


if __name__ == '__main__':
    sys.exit(run())
