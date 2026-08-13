# -*- coding: utf-8 -*-
"""13_03 Track2 — 모델 라벨 조건부 고정밀 override 레이어(프로토타입).

설계 원칙(§4-3 불가침): override는 **긍↔부를 새로 만들면 안 된다**. 그래서 규칙을
모델 라벨 조건부로, "오류를 제거하는 방향으로만" 건다.

R1 (요청표지 거짓긍정 제거): model=='positive' 이고 개선요청/요청표지(트랩가드된 기존
    검출기)가 참이면 → 'neutral'. 긍→중만(긍→부 아님) → 긍↔부 생성 불가. case11 교정.
R2 (무서술어 단편 필드신호): model=='neutral' 이고 서술어 없는 단편 + field∈{장점,단점}
    이면 → 필드극성(장점→positive/단점→negative). 중립에서만 출발 → 모델부정을 긍정으로
    뒤집지 않음. case1 교정. (중→부 방향이 gold긍정과 충돌 가능 → 슬라이스로 검증)

프로토타입: 이 함수를 4슬라이스+11case로 검증 후 perspective_service.py 에 이식한다.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WP = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '..'))
if WP not in sys.path:
    sys.path.insert(0, WP)

from src.services.perspective_service import (
    _has_improvement_request_core, has_constructive_need, _has_request_marker,
    _has_improve_blocking_contrast, has_explicit_strong_positive,
)

FIELD_POL = {'장점': 'positive', '단점': 'negative'}

# 서술어 종결 어미(있으면 완결문 = 무서술어 단편 아님). 한국어 용언 종결형.
_PRED_END = re.compile(
    r'(다|요|까|죠|네|군|함|됨|김|음|슴|임|짐|침|킴|힘|봄|옴|줌|섬|람|씀|담|맘|남)'
    r'[.!?)\'"”’\s]*$'
)


def is_predicate_less_fragment(sentence):
    """서술어(용언 종결) 없이 명사/명사구로 끝나는 단편이면 True.

    '관리감독없이 업무수행'(수행)·'전문성 향상 노력'(노력) → True.
    '업무를 진행합니다'(니다)·'행동을 유발한다'(다) → False.
    보수적: 종결어미가 하나라도 보이면 False(단편 아님 → 필드신호 미적용, 안전).
    """
    if not sentence:
        return False
    s = sentence.strip()
    if not s:
        return False
    # 마지막 어절 기준 — 문장 전체 끝이 용언 종결형이면 완결문
    return _PRED_END.search(s) is None


def apply_override(model_label, sentence, field):
    """(final_label, rule_id) 반환. rule 미발동 시 (model_label, None).

    KoTE 점수 불요 — 순수 lexical + 모델라벨 조건부(결정론적·설명가능).
    """
    if not sentence:
        return model_label, None

    # R1: 모델 긍정인데 요청표지 화행 → 중립화(거짓 긍정 제거, 긍→중만).
    #   ⚠ core('요함' substring)는 '집요함'(끈기=긍정) 트랩 재도입 → 제외. 고정밀 _has_request_marker
    #   (~해주세요·~바랍니다·희망형)만 사용(트랩가드 내장). 명시 강긍정·차단반전 있으면 미발동.
    if model_label == 'positive':
        if _has_request_marker(sentence) \
                and not _has_improve_blocking_contrast(sentence) \
                and not has_explicit_strong_positive(sentence):
            return 'neutral', 'R1_request_falsepos_to_neutral'

    # R2: 폐기(2026-07-13 실측) — 모델이 필드 프리픽스로 이미 필드신호 내장(train/serve 정합).
    #   override로 필드극성 재적용 시 이중계산 → 슬라이스 긍↔부 신규 +2·정확도 급락(8c -27).
    #   무서술어 단편의 중립 미스(예: case1)는 중립→긍정 허용(핵심가치)이라 잔존 무방. Track1 몫.
    _ = FIELD_POL  # (R2 폐기로 미사용 — is_predicate_less_fragment는 문서/테스트용 보존)

    return model_label, None
