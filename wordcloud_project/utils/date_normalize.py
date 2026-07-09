"""평가 일자(evaluation_date) 정규화 유틸.

입력 데이터는 출처마다 날짜 형식이 제각각이다(예: 2025, '2025-06-01', '2025/6/1',
'20250601', '250105'(YYMMDD), '202506'(YYYYMM), int/str 혼재). 이를 한 군데서
표준형으로 정규화해 저장·조회 양쪽이 같은 값을 보게 한다.

표준형(확보된 정밀도만큼만):
    'YYYY-MM-DD'  (연·월·일)
    'YYYY-MM'     (연·월)
    'YYYY'        (연도만)
파싱이 불확실하면 데이터 훼손을 피하기 위해 **원본 문자열을 그대로** 둔다
(연도 추출은 앞 4자리 폴백으로 여전히 동작). 빈값/None은 None.
"""

import re

__all__ = ["normalize_eval_date"]


def normalize_eval_date(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    # 1) 구분자(-, /, ., 공백)가 있는 경우: 분해 후 재조립
    parts = re.split(r"[-/.\s]+", s)
    if len(parts) >= 2 and all(p.isdigit() for p in parts[:3] if p):
        y = parts[0]
        if len(y) == 2:          # 2자리 연도 → 20xx 가정(인사평가 도메인)
            y = "20" + y
        if len(y) != 4:
            return s             # 비정형 연도 → 원본 유지(폴백)
        out = y
        if len(parts) >= 2 and parts[1]:
            out += "-" + parts[1].zfill(2)
        if len(parts) >= 3 and parts[2]:
            out += "-" + parts[2].zfill(2)
        return out

    # 2) 구분자 없는 순수 숫자 덩어리
    if s.isdigit():
        n = len(s)
        if n == 4:               # YYYY
            return s
        if n == 8:               # YYYYMMDD
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        if n == 6:
            # YYYYMM vs YYMMDD 모호 → 앞 4자리가 그럴듯한 연도면 YYYYMM, 아니면 YYMMDD
            head = int(s[:4])
            if 1900 <= head <= 2100:
                return f"{s[:4]}-{s[4:6]}"          # YYYYMM
            return f"20{s[:2]}-{s[2:4]}-{s[4:6]}"   # YYMMDD
        # 그 외 길이(5·7 등)는 안전하게 원본 유지
        return s

    # 3) 숫자가 아닌 기타 형식은 손대지 않는다
    return s
