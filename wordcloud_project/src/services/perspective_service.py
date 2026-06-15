"""Perspective analysis service - multi-filter grouping engine with X/Y matrix."""
import matplotlib
matplotlib.use('Agg')
import os
import json
import re
import logging

logger = logging.getLogger(__name__)
import hashlib
import uuid
from collections import Counter
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from src.config.settings import (
    OUTPUTS_DIR_PATH, WORDCLOUD_CONFIG_PATH, ADMIN_PASSWORD,
    PSEUDONYM_MAPPINGS_PATH, PROCESSED_DATA_DIR_PATH,
    POSITION_HIERARCHY_PATH, PROJECT_ROOT
)
import sqlite3
import threading
from collections import defaultdict
from src.modules.wordcloud_generator import WordCloudGenerator
from src.modules.pseudonym_manager import PseudonymManager
from src.modules.text_preprocessing import split_sentences  # 정의는 text_preprocessing로 이전(경량)

_EVAL_DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '.sessions')
_EVAL_DB_PATH = os.path.join(_EVAL_DB_DIR, 'deploy_sessions.db')


def _get_eval_conn():
    os.makedirs(_EVAL_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_EVAL_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

SKIP_COLUMNS = {
    'evaluation_id', 'session_id', 'evaluator_id',
    'evaluation_document', 'evaluation_document_original',
    'version', 'data_integrity_hash',
    'target_employee_id',
    'evaluator_hierarchy_level', 'target_hierarchy_level',
}

ROW_FIELDS = {
    'evaluation_date__year': {'label': '평가 연도', 'field': 'evaluation_date', 'modifier': 'year'},
    'evaluation_date__month': {'label': '평가 월', 'field': 'evaluation_date', 'modifier': 'month'},
    'batch_id': {'label': '배치(회차)', 'field': 'batch_id', 'modifier': None},
    'evaluation_date': {'label': '평가 일자', 'field': 'evaluation_date', 'modifier': None},
}

COL_MODES = {
    'department': {'label': '부서별', 'type': 'evaluator', 'field': 'evaluator_department'},
    'position_detail': {'label': '직책별(세부)', 'type': 'evaluator', 'field': 'evaluator_position'},
    'position_3tier': {'label': '직책별(3등분)', 'type': 'evaluator', 'field': 'position_3tier'},
    'all': {'label': '전체', 'type': 'evaluator', 'field': None},
}

ANALYSIS_TYPES = {
    'nlp': {'label': 'NLP 단어 분석', 'type': 'analysis'},
    'emotion': {'label': '감정 분석', 'type': 'analysis'},
    'leadership': {'label': '리더십 분석', 'type': 'analysis'},
    'profanity': {'label': '욕설 분석', 'type': 'analysis'},
    'sarcasm': {'label': '비꼼 분석', 'type': 'analysis'},
}

USER_OUTPUT_DIR = os.path.join(OUTPUTS_DIR_PATH, '유저')
DEPLOY_OUTPUT_DIR = os.path.join(OUTPUTS_DIR_PATH, '배포')
DEPLOY_MANIFEST_PATH = os.path.join(OUTPUTS_DIR_PATH, 'deploy_manifest.json')

FileLock = None  # legacy — manifest 파일 락 불필요 (DB 전환 완료)

# ── 반전(역접) 표지어 목록 ────────────────────────────────────────────────────
# 한국어 국어 문법 체계 기반으로 정리한 역접·양보·대조 표지어 목록.
# KoTE는 문장의 통사 구조(어디서 뒤집히는지)를 판단하지 못하므로
# 이 사전은 모델 외부에서 반드시 관리해야 하는 도메인 지식임.
# ※ 추가 시 CLAUDE.md "반전 표지어 체계" 섹션도 함께 갱신할 것.
CONTRASTIVE_MARKERS = {
    # ── 강한 역접 접속 부사 ──────────────────────────────────────────────────
    # 앞 내용을 완전히 부정하거나 뒤집는 독립 접속어
    # 출처: 표준국어대사전 접속 부사 분류 (역접·전환)
    'strong': [
        '그러나',       # 하지만, 그럼에도 (가장 일반적인 역접)
        '그렇지만',     # 그러나보다 구어적
        '하지만',       # 구어체 역접, 가장 빈도 높음
        '다만',         # 단서·제한을 추가하는 약한 역접
        '단 ',          # "다만"의 짧은 형태 (공문서·규정체). 공백 포함으로 "단순/단계" 오탐 방지
        '반면',         # 대조를 명시하는 역접
        '그래도',       # 양보 후 역접 ("그럼에도 불구하고"와 유사)
        '그럼에도',     # "그럼에도 불구하고"의 줄임
        '그렇더라도',   # 가정·양보 후 역접
        '그렇다 해도',  # 구어체 양보 역접
    ],

    # ── 중간·방향전환 접속 부사 ──────────────────────────────────────────────
    # 앞 내용에서 부드럽게 전환하거나 예상과 반대 결과를 제시
    # 출처: 표준국어대사전 접속 부사 분류 (전환·반전)
    'medium': [
        '그런데',   # 화제 전환 또는 약한 역접
        '오히려',   # 예상과 반대되는 결과 (역설적 반전)
        '도리어',   # "오히려"의 문어체
        '되레',     # "도리어"의 구어체 축약형
        '반면에',   # "반면" + 조사, 대조 강조
    ],

    # ── 역접·양보 연결 어미 (suffix) ─────────────────────────────────────────
    # 용언 어간에 붙어 앞 절과 뒷 절을 대조·양보로 연결하는 어미.
    # substring 매칭이므로 2자 이상이며 평가 문체에서 고빈도인 형태만 수록.
    # 출처: 국립국어원 한국어 문법 - 연결어미 역접·양보 분류
    'suffix': [
        # -지만 계열 (역접): "성실하지만", "부족하지만"
        '지만', '이지만',
        # -(으)나 계열 (역접): "뛰어나나", "부족하나", "소극적이나"
        '으나', '이나',
        # -건만 계열 (유감·역접): "노력했건만", "기대했건만"
        '건만',
        # -(아/어)도 계열 (양보): "노력해도", "잘해도"
        '아도', '어도',
        # -더라도 계열 (가정·양보): "잘하더라도", "우수하더라도"
        '더라도',
        # -면서도 계열 (동시·대조): "노력하면서도 결과가 없다"
        '면서도',
        # -는데/-은데 계열 (배경·대조): "성실한데 결과가 아쉽다"
        '는데', '은데',
        # -기는 계열 (인정·역접): "잘하기는 하나 아쉽다"
        '기는',
    ],

    # ── 관용 고정 표현 ────────────────────────────────────────────────────────
    # 2어절 이상의 관용적 역접·대조 표현. 공백 포함이므로 오탐 위험 낮음.
    # 출처: 표준국어대사전 관용구 / 국립국어원 문법 자료
    'idiomatic': [
        # 대조 관용구
        '에 반해',          # "A에 반해 B는 우수하다"
        '는 한편',          # "능력은 탁월한 한편 태도가 아쉽다"
        '인 반면',          # "성실한 반면 속도가 느리다"
        '은 반면',          # "능력은 좋은 반면 소통이 부족하다"
        '는 반면',          # "일은 잘하는 반면 보고가 미흡하다"
        '에도 불구하고',    # "노력에도 불구하고 성과가 없다"
        # -기는 관용 표현
        '기는 하지만',      # "잘하기는 하지만 아쉽다"
        '기는 하나',        # "우수하기는 하나 부족함이 있다"
        '기는 하되',        # "인정하기는 하되 개선이 필요하다"
        '기는 했지만',      # "노력하기는 했지만 결과가 미흡하다"
    ],
}
ALL_CONTRASTIVE = (
    CONTRASTIVE_MARKERS['strong'] +
    CONTRASTIVE_MARKERS['medium'] +
    CONTRASTIVE_MARKERS['suffix'] +
    CONTRASTIVE_MARKERS['idiomatic']
)

# ── 50개 단문 테스트 문장 (추정값 포함) ──────────────────────────────────────────
TEST_SENTENCES_100 = [
    # [단문-긍정] 1-15
    {"id": 1,  "category": "단문-긍정", "text": "업무 능력이 매우 뛰어납니다.", "expected": "positive", "est_pos": 0.85, "est_neg": 0.10},
    {"id": 2,  "category": "단문-긍정", "text": "팀 내에서 항상 긍정적인 영향을 줍니다.", "expected": "positive", "est_pos": 0.82, "est_neg": 0.08},
    {"id": 3,  "category": "단문-긍정", "text": "책임감이 강하여 맡은 일을 완수합니다.", "expected": "positive", "est_pos": 0.80, "est_neg": 0.12},
    {"id": 4,  "category": "단문-긍정", "text": "동료와의 협업이 원활합니다.", "expected": "positive", "est_pos": 0.78, "est_neg": 0.10},
    {"id": 5,  "category": "단문-긍정", "text": "새로운 업무에도 빠르게 적응합니다.", "expected": "positive", "est_pos": 0.76, "est_neg": 0.10},
    {"id": 6,  "category": "단문-긍정", "text": "보고 체계가 정확하고 신뢰할 수 있습니다.", "expected": "positive", "est_pos": 0.75, "est_neg": 0.12},
    {"id": 7,  "category": "단문-긍정", "text": "고객 대응이 매우 우수합니다.", "expected": "positive", "est_pos": 0.83, "est_neg": 0.08},
    {"id": 8,  "category": "단문-긍정", "text": "분석력이 탁월하여 문제 해결에 기여합니다.", "expected": "positive", "est_pos": 0.80, "est_neg": 0.10},
    {"id": 9,  "category": "단문-긍정", "text": "시간 약속을 철저히 지킵니다.", "expected": "positive", "est_pos": 0.77, "est_neg": 0.10},
    {"id": 10, "category": "단문-긍정", "text": "리더십이 있어 팀을 이끄는 데 적합합니다.", "expected": "positive", "est_pos": 0.81, "est_neg": 0.09},
    {"id": 11, "category": "단문-긍정", "text": "문서 정리가 깔끔하고 체계적입니다.", "expected": "positive", "est_pos": 0.74, "est_neg": 0.12},
    {"id": 12, "category": "단문-긍정", "text": "피드백을 겸허히 받아들입니다.", "expected": "positive", "est_pos": 0.79, "est_neg": 0.10},
    {"id": 13, "category": "단문-긍정", "text": "성실하게 업무에 임합니다.", "expected": "positive", "est_pos": 0.78, "est_neg": 0.10},
    {"id": 14, "category": "단문-긍정", "text": "전문 지식이 깊어 업무 품질이 높습니다.", "expected": "positive", "est_pos": 0.82, "est_neg": 0.08},
    {"id": 15, "category": "단문-긍정", "text": "위기 상황에서도 침착하게 대처합니다.", "expected": "positive", "est_pos": 0.80, "est_neg": 0.10},
    # [단문-부정] 16-30
    {"id": 16, "category": "단문-부정", "text": "업무 처리 속도가 매우 느립니다.", "expected": "negative", "est_pos": 0.12, "est_neg": 0.78},
    {"id": 17, "category": "단문-부정", "text": "동료와의 소통이 원활하지 않습니다.", "expected": "negative", "est_pos": 0.15, "est_neg": 0.75},
    {"id": 18, "category": "단문-부정", "text": "맡은 일을 미루는 경향이 있습니다.", "expected": "negative", "est_pos": 0.18, "est_neg": 0.72},
    {"id": 19, "category": "단문-부정", "text": "보고가 자주 누락되거나 지연됩니다.", "expected": "negative", "est_pos": 0.15, "est_neg": 0.76},
    {"id": 20, "category": "단문-부정", "text": "책임감이 부족하여 대응이 소극적입니다.", "expected": "negative", "est_pos": 0.14, "est_neg": 0.80},
    {"id": 21, "category": "단문-부정", "text": "팀워크가 부족하여 협업에 어려움이 있습니다.", "expected": "negative", "est_pos": 0.16, "est_neg": 0.74},
    {"id": 22, "category": "단문-부정", "text": "시간 관리가 되지 않아 마감을 지키지 못합니다.", "expected": "negative", "est_pos": 0.13, "est_neg": 0.79},
    {"id": 23, "category": "단문-부정", "text": "고객 민원 대응이 미흡합니다.", "expected": "negative", "est_pos": 0.15, "est_neg": 0.75},
    {"id": 24, "category": "단문-부정", "text": "업무 이해도가 낮아 실수가 잦습니다.", "expected": "negative", "est_pos": 0.14, "est_neg": 0.77},
    {"id": 25, "category": "단문-부정", "text": "피드백을 수용하는 태도가 부족합니다.", "expected": "negative", "est_pos": 0.18, "est_neg": 0.72},
    {"id": 26, "category": "단문-부정", "text": "문서 정리가 엉망이라 파악이 어렵습니다.", "expected": "negative", "est_pos": 0.12, "est_neg": 0.80},
    {"id": 27, "category": "단문-부정", "text": "지각이 잦아 업무 분위기를 해칩니다.", "expected": "negative", "est_pos": 0.14, "est_neg": 0.76},
    {"id": 28, "category": "단문-부정", "text": "전문성이 부족하여 업무 품질이 떨어집니다.", "expected": "negative", "est_pos": 0.13, "est_neg": 0.78},
    {"id": 29, "category": "단문-부정", "text": "위기 상황에서 당황하여 대처가 미흡합니다.", "expected": "negative", "est_pos": 0.15, "est_neg": 0.75},
    {"id": 30, "category": "단문-부정", "text": "의사결정이 너무 느려 업무 진행이 지연됩니다.", "expected": "negative", "est_pos": 0.16, "est_neg": 0.74},
    # [단문-모호] 31-40
    {"id": 31, "category": "단문-모호", "text": "커뮤니케이션에 개선의 여지가 있습니다.", "expected": "negative", "est_pos": 0.52, "est_neg": 0.43},
    {"id": 32, "category": "단문-모호", "text": "보완이 필요한 부분이 일부 있습니다.", "expected": "negative", "est_pos": 0.50, "est_neg": 0.42},
    {"id": 33, "category": "단문-모호", "text": "업무 능력이 보통 수준입니다.", "expected": "neutral", "est_pos": 0.30, "est_neg": 0.25},
    {"id": 34, "category": "단문-모호", "text": "전반적으로 무난하게 업무를 수행합니다.", "expected": "neutral", "est_pos": 0.35, "est_neg": 0.20},
    {"id": 35, "category": "단문-모호", "text": "개선 여지가 있는 편입니다.", "expected": "negative", "est_pos": 0.48, "est_neg": 0.45},
    {"id": 36, "category": "단문-모호", "text": "소통 방식에 다소 아쉬운 점이 있습니다.", "expected": "negative", "est_pos": 0.55, "est_neg": 0.40},
    {"id": 37, "category": "단문-모호", "text": "일 처리가 조금 느린 편입니다.", "expected": "negative", "est_pos": 0.45, "est_neg": 0.48},
    {"id": 38, "category": "단문-모호", "text": "역량 개발이 필요해 보입니다.", "expected": "negative", "est_pos": 0.50, "est_neg": 0.42},
    {"id": 39, "category": "단문-모호", "text": "보고 체계에 정비가 필요합니다.", "expected": "negative", "est_pos": 0.53, "est_neg": 0.41},
    {"id": 40, "category": "단문-모호", "text": "팀 내 기여도가 다소 낮은 편입니다.", "expected": "negative", "est_pos": 0.51, "est_neg": 0.44},
    # [단문-부정(기존 다문 반전)] 41-60
    {"id": 41,  "category": "단문-부정", "text": "업무 능력은 뛰어나나 커뮤니케이션이 부족합니다.", "expected": "negative", "est_pos": 0.52, "est_neg": 0.43},
    {"id": 42,  "category": "단문-부정", "text": "성실하게 임하나 결과물의 품질이 아쉽습니다.", "expected": "negative", "est_pos": 0.48, "est_neg": 0.46},
    {"id": 43,  "category": "단문-부정", "text": "협업은 원활하나 보고 체계에 정비가 필요합니다.", "expected": "negative", "est_pos": 0.50, "est_neg": 0.44},
    {"id": 44,  "category": "단문-부정", "text": "전반적으로 우수하나 시간 관리가 부족합니다.", "expected": "negative", "est_pos": 0.46, "est_neg": 0.48},
    {"id": 45,  "category": "단문-부정", "text": "책임감은 강하나 의사결정 속도가 느립니다.", "expected": "negative", "est_pos": 0.47, "est_neg": 0.47},
    {"id": 46,  "category": "단문-부정", "text": "고객 대응은 좋으나 내부 문서 정리가 미흡합니다.", "expected": "negative", "est_pos": 0.49, "est_neg": 0.45},
    {"id": 47,  "category": "단문-부정", "text": "전문 지식은 깊으나 팀 내 소통이 원활하지 않습니다.", "expected": "negative", "est_pos": 0.51, "est_neg": 0.43},
    {"id": 48,  "category": "단문-부정", "text": "업무 이해도는 높으나 실행력이 부족합니다.", "expected": "negative", "est_pos": 0.48, "est_neg": 0.46},
    {"id": 49,  "category": "단문-부정", "text": "새로운 업무에 적응하나 꼼꼼함이 부족합니다.", "expected": "negative", "est_pos": 0.50, "est_neg": 0.44},
    {"id": 50,  "category": "단문-부정", "text": "시간 약속은 지키나 업무의 깊이가 부족합니다.", "expected": "negative", "est_pos": 0.47, "est_neg": 0.47},
    {"id": 51,  "category": "단문-부정", "text": "분석력은 탁월하나 실행 계획 수립이 미흡합니다.", "expected": "negative", "est_pos": 0.48, "est_neg": 0.46},
    {"id": 52,  "category": "단문-부정", "text": "문서 정리는 체계적이나 의사소통이 부족합니다.", "expected": "negative", "est_pos": 0.50, "est_neg": 0.44},
    {"id": 53,  "category": "단문-부정", "text": "위기 상황에서 침착하나 예방 능력은 부족합니다.", "expected": "negative", "est_pos": 0.49, "est_neg": 0.45},
    {"id": 54,  "category": "단문-부정", "text": "리더십은 있으나 팀원 관리가 미흡합니다.", "expected": "negative", "est_pos": 0.47, "est_neg": 0.47},
    {"id": 55,  "category": "단문-부정", "text": "성실하지만 결과가 아쉽습니다.", "expected": "negative", "est_pos": 0.45, "est_neg": 0.48},
    {"id": 56,  "category": "단문-부정", "text": "열심인데 능력이 부족합니다.", "expected": "negative", "est_pos": 0.43, "est_neg": 0.50},
    {"id": 57,  "category": "단문-부정", "text": "능력은 있는 한편 태도가 부족합니다.", "expected": "negative", "est_pos": 0.46, "est_neg": 0.47},
    {"id": 58,  "category": "단문-부정", "text": "좋기는 한데 성과가 미흡합니다.", "expected": "negative", "est_pos": 0.44, "est_neg": 0.49},
    {"id": 59,  "category": "단문-부정", "text": "노력해도 결과가 나오지 않습니다.", "expected": "negative", "est_pos": 0.42, "est_neg": 0.52},
    {"id": 60,  "category": "단문-부정", "text": "있기는 하지만 활용이 부족합니다.", "expected": "negative", "est_pos": 0.45, "est_neg": 0.48},
    # [단문-긍정(기존 다문 반전)] 61-75
    {"id": 61,  "category": "단문-긍정", "text": "업무 처리는 느리나 책임감은 매우 강합니다.", "expected": "positive", "est_pos": 0.65, "est_neg": 0.30},
    {"id": 62,  "category": "단문-긍정", "text": "보고는 미흡하나 성실성은 인정할 만합니다.", "expected": "positive", "est_pos": 0.62, "est_neg": 0.32},
    {"id": 63,  "category": "단문-긍정", "text": "팀워크는 부족하나 전문 지식은 탁월합니다.", "expected": "positive", "est_pos": 0.68, "est_neg": 0.28},
    {"id": 64,  "category": "단문-긍정", "text": "시간 관리는 되지 않으나 업무 이해도는 높습니다.", "expected": "positive", "est_pos": 0.60, "est_neg": 0.35},
    {"id": 65,  "category": "단문-긍정", "text": "고객 대응은 아쉬우나 동료 관계는 원활합니다.", "expected": "positive", "est_pos": 0.63, "est_neg": 0.33},
    {"id": 66,  "category": "단문-긍정", "text": "문서 정리는 엉망이나 분석력은 뛰어납니다.", "expected": "positive", "est_pos": 0.66, "est_neg": 0.30},
    {"id": 67,  "category": "단문-긍정", "text": "지각은 잦으나 업무 품질은 우수합니다.", "expected": "positive", "est_pos": 0.64, "est_neg": 0.32},
    {"id": 68,  "category": "단문-긍정", "text": "의사소통은 부족하나 실행력은 강합니다.", "expected": "positive", "est_pos": 0.67, "est_neg": 0.29},
    {"id": 69,  "category": "단문-긍정", "text": "전문성은 부족하나 성장 속도는 빠릅니다.", "expected": "positive", "est_pos": 0.65, "est_neg": 0.31},
    {"id": 70,  "category": "단문-긍정", "text": "책임감은 부족하나 팀 내 분위기는 긍정적입니다.", "expected": "positive", "est_pos": 0.61, "est_neg": 0.34},
    {"id": 71,  "category": "단문-긍정", "text": "실수는 잦으나 학습 의지는 강합니다.", "expected": "positive", "est_pos": 0.63, "est_neg": 0.32},
    {"id": 72,  "category": "단문-긍정", "text": "보고는 늦으나 내용의 정확도는 높습니다.", "expected": "positive", "est_pos": 0.62, "est_neg": 0.33},
    {"id": 73,  "category": "단문-긍정", "text": "업무 속도는 느리나 꼼꼼함은 장점입니다.", "expected": "positive", "est_pos": 0.64, "est_neg": 0.31},
    {"id": 74,  "category": "단문-긍정", "text": "협업은 어려우나 독립 업무 수행력은 우수합니다.", "expected": "positive", "est_pos": 0.66, "est_neg": 0.30},
    {"id": 75,  "category": "단문-긍정", "text": "대응은 소극적이나 문제 해결 능력은 있습니다.", "expected": "positive", "est_pos": 0.65, "est_neg": 0.31},
    # [단문-부정(기존 다문 샌드위치)] 76-90
    {"id": 76,  "category": "단문-부정", "text": "보고 체계가 미흡하여 업무에 지장이 있습니다.", "expected": "negative", "est_pos": 0.48, "est_neg": 0.46},
    {"id": 77,  "category": "단문-부정", "text": "소통이 부족하여 협업에 어려움이 있습니다.", "expected": "negative", "est_pos": 0.47, "est_neg": 0.47},
    {"id": 78,  "category": "단문-부정", "text": "팀워크가 아쉬워 협업 의지가 부족합니다.", "expected": "negative", "est_pos": 0.49, "est_neg": 0.45},
    {"id": 79,  "category": "단문-부정", "text": "내부 정리가 부족하여 전반적인 관리가 어렵습니다.", "expected": "negative", "est_pos": 0.46, "est_neg": 0.48},
    {"id": 80,  "category": "단문-부정", "text": "실행력이 부족하여 결과 도출이 지연됩니다.", "expected": "negative", "est_pos": 0.47, "est_neg": 0.47},
    {"id": 81,  "category": "단문-부정", "text": "판단이 느려 업무 진행이 지연됩니다.", "expected": "negative", "est_pos": 0.48, "est_neg": 0.46},
    {"id": 82,  "category": "단문-부정", "text": "상사 보고가 미흡하여 체계적 관리가 안 됩니다.", "expected": "negative", "est_pos": 0.50, "est_neg": 0.44},
    {"id": 83,  "category": "단문-부정", "text": "의사결정이 느려 업무 효율이 떨어집니다.", "expected": "negative", "est_pos": 0.49, "est_neg": 0.45},
    {"id": 84,  "category": "단문-부정", "text": "기본 업무가 미흡하여 실수가 잦습니다.", "expected": "negative", "est_pos": 0.48, "est_neg": 0.46},
    {"id": 85,  "category": "단문-부정", "text": "예방 능력이 부족하여 위기가 반복됩니다.", "expected": "negative", "est_pos": 0.47, "est_neg": 0.47},
    {"id": 86,  "category": "단문-부정", "text": "업무의 깊이가 부족하여 결과물의 품질이 낮습니다.", "expected": "negative", "est_pos": 0.46, "est_neg": 0.48},
    {"id": 87,  "category": "단문-부정", "text": "팀원 관리가 미흡하여 조직력이 부족합니다.", "expected": "negative", "est_pos": 0.47, "est_neg": 0.47},
    {"id": 88,  "category": "단문-부정", "text": "성실하지만 결과가 여전히 아쉬운 편입니다.", "expected": "negative", "est_pos": 0.45, "est_neg": 0.48},
    {"id": 89,  "category": "단문-부정", "text": "열심인데 능력이 아직 부족한 편입니다.", "expected": "negative", "est_pos": 0.44, "est_neg": 0.49},
    {"id": 90,  "category": "단문-부정", "text": "태도가 문제여서 협업에 어려움이 있습니다.", "expected": "negative", "est_pos": 0.46, "est_neg": 0.47},
    # [특수-경계값] 91-100
    {"id": 91, "category": "경계값", "text": "업무는 잘하지만 소통이 부족합니다.", "expected": "negative", "est_pos": 0.48, "est_neg": 0.46},
    {"id": 92, "category": "경계값", "text": "능력은 있으나 성실성이 부족합니다.", "expected": "negative", "est_pos": 0.46, "est_neg": 0.48},
    {"id": 93, "category": "경계값", "text": "전반적으로 좋습니다. 다만 조금 아쉽습니다.", "expected": "negative", "est_pos": 0.49, "est_neg": 0.45},
    {"id": 94, "category": "경계값", "text": "성실합니다. 그런데 결과가 미흡합니다.", "expected": "negative", "est_pos": 0.47, "est_neg": 0.47},
    {"id": 95, "category": "경계값", "text": "우수합니다. 단 보완이 필요합니다.", "expected": "negative", "est_pos": 0.50, "est_neg": 0.44},
    {"id": 96, "category": "경계값", "text": "잘합니다. 하지만 느립니다.", "expected": "negative", "est_pos": 0.52, "est_neg": 0.42},
    {"id": 97, "category": "경계값", "text": "괜찮습니다. 반면 문제가 있습니다.", "expected": "negative", "est_pos": 0.51, "est_neg": 0.43},
    {"id": 98, "category": "경계값", "text": "좋습니다. 그러나 아쉽습니다.", "expected": "negative", "est_pos": 0.53, "est_neg": 0.41},
    {"id": 99, "category": "경계값", "text": "만족합니다. 다만 부족합니다.", "expected": "negative", "est_pos": 0.50, "est_neg": 0.44},
    {"id": 100, "category": "경계값", "text": "인정합니다. 단 개선이 필요합니다.", "expected": "negative", "est_pos": 0.49, "est_neg": 0.45},
]


def has_contrastive(sentence):
    """문장에 반전 표지어가 포함되는지 확인."""
    if not sentence:
        return False
    return any(marker in sentence for marker in ALL_CONTRASTIVE)


# 부정을 암시하는 의미적 단어들 (완곡 표현 포함)
# ※ 주의: 단어 단위 substring 매칭이므로 반전 표지어가 있는 문장(has_contrast=True)에서는
#   Rule 0/완곡부정 규칙이 발동하지 않도록 설계되어 있음.
NEGATIVE_IMPLYING_WORDS = [
    '여지',          # 개선의 여지가 있습니다
    '부족',          # 소통이 부족합니다
    '미흡',          # 보고가 미흡합니다
    '아쉽',          # 팀워크가 아쉽습니다
    '문제가 있',      # 문제가 있습니다
    '문제가 많',      # 문제가 많습니다
    '문제가 심각',    # 문제가 심각합니다
    '늦',            # 보고가 늦습니다
    '엉망',          # 문서 정리가 엉망입니다
    '지각',          # 지각이 잦습니다
    '소극',          # 대응이 소극적입니다
    '개선 필요',      # 개선이 필요합니다
    '보완 필요',      # 보완이 필요합니다
    '노력 필요',      # 노력이 필요합니다
    '부진',          # 성과가 부진합니다
    '미흡하',        # ~이 미흡합니다
    '부족하',        # ~이 부족합니다
    '안 되',         # ~이 안 됩니다
    '못 하',         # ~을 못 합니다
]

# 인사평가 도메인에서 긍정처럼 보이나 명확히 부정 함의인 구문 (phrase-level, 2어절 이상)
# NEGATIVE_IMPLYING_WORDS와 달리 구문 단위라 오탐 위험이 낮음.
# Rule 0 대신 이 목록으로 완곡 부정 표현을 처리.
STRONG_NEGATIVE_PHRASES = [
    '개선의 여지',      # "개선의 여지가 있습니다" = 개선이 필요함
    '개선 여지',        # "개선 여지가 있는 편"
    '여지가 있',        # "~의 여지가 있습니다"
    '보완이 필요',      # "보완이 필요합니다"
    '개선이 필요',      # "개선이 필요합니다"
    '노력이 필요',      # "노력이 필요합니다"
    '역량 개발이 필요',  # "역량 개발이 필요해 보입니다"
    '정비가 필요',      # "보고 체계에 정비가 필요합니다"
]


# 인사평가 도메인에서 KoTE가 극단적으로 오분류하는 중립 표현들 (단어 단위)
# 목적: 중립 문장이 부정으로 오분류되는 극단 케이스 방지 (confidence > 0.9)
# 중립 → 긍정 오분류는 허용 가능하므로 별도 구문 목록은 불필요.
NEUTRAL_KEYWORDS = ['보통', '무난', '평범']


def has_negative_implying_words(sentence):
    """문장에 부정을 암시하는 단어가 포함되는지 확인."""
    if not sentence:
        return False
    return any(word in sentence for word in NEGATIVE_IMPLYING_WORDS)


def sentence_sentiment_override(pos, neg, sentence, is_last, total_sentences,
                                  threshold=0.20, weight=2.0, neutral=0.0):
    """문장별 독립 감정 교정.

    핵심 가치: 긍정↔부정 오분류만 방지. 중립→긍정은 허용.

    규칙:
      중립) NEUTRAL_KEYWORDS + confidence>0.9 + pos/neg>0.9 → 중립 강제 (중립→부정 극단 케이스 방지)
      완곡부정) is_last + not has_contrast + KoTE 긍정 + STRONG_NEGATIVE_PHRASES → 부정 반전
      1) has_contrast + is_last + 저신뢰(confidence<threshold) + strength>0.5 → 모델 방향 기반 가중
      2) has_contrast + is_last + 고신뢰(confidence>=threshold) → 모델 방향 기반 가중
      3) is_last + 저신뢰(confidence<threshold) + strength>0.5 → 부정 전환
      4) 기본 → 모델 판단 그대로
    """
    confidence = abs(pos - neg)
    strength = pos + neg
    has_contrast = has_contrastive(sentence)

    # KoTE neutral 우세 또는 근접 우세(±0.05) → 중립 강제
    if neutral > pos and neutral >= neg - 0.05:
        return 0.0

    # 중립 규칙: 중립 문장이 부정으로 극단 오분류되는 케이스 방지
    # 중립→긍정은 허용이므로 긍정 방향 오분류는 교정하지 않음
    if any(word in sentence for word in NEUTRAL_KEYWORDS):
        if confidence > 0.9 and (pos > 0.9 or neg > 0.9):
            return 0.0

    # 완곡 부정 구문 규칙: KoTE가 긍정으로 오분류하는 인사평가 완곡 표현 → 부정 반전
    # NEGATIVE_IMPLYING_WORDS(단어 단위) 대신 구문 단위 정밀 매칭으로 오탐 방지.
    # has_contrast인 경우 규칙1/2에서 방향을 판단하므로 제외.
    if (is_last and pos > neg and not has_contrast and strength > 0.5
            and any(phrase in sentence for phrase in STRONG_NEGATIVE_PHRASES)):
        return -strength

    # 규칙 1: 반전 + 마지막 + 저신뢰도 + strength>0.5 → 모델 방향 기반 가중
    if (has_contrast and is_last and confidence < threshold
            and strength > 0.5):
        return (pos - neg) * weight

    # 규칙 2: 반전 + 마지막 + 고신뢰도 → 모델 방향 기반 가중
    if (has_contrast and is_last and confidence >= threshold):
        return (pos - neg) * weight

    # 규칙 3: 반전 없이 마지막 + 저신뢰도 + strength>0.5 → 부정 전환
    if (is_last and confidence < threshold and strength > 0.5):
        return -strength

    # 규칙 4: 기본
    return pos - neg


_pseudo_mgr_instance = None
_pseudo_mgr_lock = threading.Lock()


def _get_pseudo_mgr():
    global _pseudo_mgr_instance
    if _pseudo_mgr_instance is None:
        with _pseudo_mgr_lock:
            if _pseudo_mgr_instance is None:
                _pseudo_mgr_instance = PseudonymManager(PSEUDONYM_MAPPINGS_PATH, ADMIN_PASSWORD)
    return _pseudo_mgr_instance


def _resolve_to_pseudo(input_id, pseudo_mgr):
    """원본 ID를 저장된 가명으로 변환. 매핑이 없으면 input_id 그대로 반환.
    get_pseudonym()과 달리 새 가명을 생성하지 않음."""
    if not input_id or not pseudo_mgr:
        return input_id
    data = pseudo_mgr._load_mappings()
    return data['real_to_pseudo'].get(str(input_id), input_id)


def load_position_hierarchy(hierarchy_path=None):
    if hierarchy_path is None:
        hierarchy_path = POSITION_HIERARCHY_PATH
    if not os.path.exists(hierarchy_path):
        return []
    with open(hierarchy_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('hierarchy', [])


def save_position_hierarchy(hierarchy, hierarchy_path=None):
    if hierarchy_path is None:
        hierarchy_path = POSITION_HIERARCHY_PATH
    os.makedirs(os.path.dirname(hierarchy_path), exist_ok=True)
    with open(hierarchy_path, 'w', encoding='utf-8') as f:
        json.dump({'hierarchy': hierarchy}, f, ensure_ascii=False, indent=2)


def get_position_level(name, hierarchy):
    for entry in hierarchy:
        if entry['name'] == name:
            return entry['level']
    return None


def get_position_grade(name, hierarchy):
    for entry in hierarchy:
        if entry['name'] == name:
            return entry.get('grade', entry.get('level'))
    return None


def get_relative_groups(name, hierarchy):
    target_grade = get_position_grade(name, hierarchy)
    if target_grade is None:
        return {'junior': [], 'peer': [], 'senior': []}
    junior = []
    peer = []
    senior = []
    for entry in hierarchy:
        entry_grade = entry.get('grade', entry.get('level'))
        if entry_grade < target_grade:
            junior.append(entry['name'])
        elif entry_grade == target_grade:
            peer.append(entry['name'])
        else:
            senior.append(entry['name'])
    return {'junior': junior, 'peer': peer, 'senior': senior}


def _get_pseudonym_fields(batch_summary):
    fields = batch_summary.get('processing_config', {}).get('pseudonym_fields', [])
    return fields if isinstance(fields, list) else []


def _enrich_with_real_ids(results, pseudonym_fields, enrich=False):
    if not enrich:
        return results
    mgr = _get_pseudo_mgr()
    RESULT_LEVEL_MAP = {
        'target_employee_id': 'employee_id',
        'target_employee_department': 'employee_department',
        'target_employee_position': 'employee_position',
    }
    if not pseudonym_fields:
        pseudonym_fields = list(RESULT_LEVEL_MAP.keys())
    for item in results:
        ev = item.get('evaluation', {})
        for field in pseudonym_fields:
            if field in ev and isinstance(ev[field], str):
                ev[f"{field}_real"] = mgr.get_real_id(ev[field])
            result_key = RESULT_LEVEL_MAP.get(field)
            if result_key and result_key in item and isinstance(item[result_key], str):
                item[f"{result_key}_real"] = mgr.get_real_id(item[result_key])
    return results


def _build_column_label_map(batch_summary):
    label_map = {}
    mappings = batch_summary.get('processing_config', {}).get('mappings', {})
    for field, csv_col in mappings.items():
        if isinstance(csv_col, str) and csv_col.strip():
            label_map[field] = csv_col.strip()
    return label_map


def _field_to_label(field_name):
    KNOWN_LABELS = {
        'evaluator_position': '평가자 직책',
        'evaluator_department': '평가자 부서',
        'evaluation_date': '평가 실시 일',
        'evaluation_date__year': '평가 연도',
        'evaluation_date__month': '평가 월',
        'target_employee_department': '대상자 부서',
        'target_employee_position': '대상자 직책',
        'preprocessing_results': '전처리 결과',
    }
    return KNOWN_LABELS.get(field_name, field_name.replace('_', ' '))


def _get_eval_field_value(ev, raw_field):
    parts = raw_field.split('__', 1)
    base_field = parts[0]
    modifier = parts[1] if len(parts) > 1 else None
    raw_val = ev.get(base_field)
    if raw_val is None:
        return None
    if modifier == 'year':
        if isinstance(raw_val, str) and len(raw_val) >= 4:
            return raw_val[:4]
        return None
    elif modifier == 'month':
        if isinstance(raw_val, str) and len(raw_val) >= 7:
            parts = raw_val.split('-')
            if len(parts) >= 2:
                return parts[1]
        return None
    return raw_val


def _resolve_field_name(raw_field):
    return raw_field.split('__')[0]


def load_batch_summary(batch_path):
    summary_path = os.path.join(batch_path, "tmeta", "batch_summary.json")
    if not os.path.exists(summary_path):
        return None
    with open(summary_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _load_batch_list(processed_data_dir):
    """DB에서 배치 목록 로드 (batches 키용)."""
    from src.services.user_data_manager import _get_eval_conn
    conn = _get_eval_conn()
    try:
        rows = conn.execute("""
            SELECT batch_id,
                   COUNT(DISTINCT employee_id) AS employee_count,
                   COUNT(*) AS total_evaluations,
                   MIN(created_at) AS created_at
            FROM evaluations
            GROUP BY batch_id
            ORDER BY MIN(created_at) DESC
        """).fetchall()
    finally:
        conn.close()

    batches = []
    for row in rows:
        batch_id = row['batch_id']
        batch_path = os.path.join(processed_data_dir, 'batch', batch_id)
        display_name = ''
        summary_path = os.path.join(batch_path, "tmeta", "batch_summary.json")
        if os.path.exists(summary_path):
            try:
                with open(summary_path, 'r', encoding='utf-8') as _sf:
                    _summary = json.load(_sf)
                display_name = _summary.get('batch_info', {}).get('display_name', '') or ''
            except Exception:
                pass
        batches.append({
            'batch_id': batch_id,
            'path': batch_path,
            'display_name': display_name,
            'created_at': (row['created_at'] or '')[:10],
            'employee_count': row['employee_count'],
            'total_evaluations': row['total_evaluations'],
        })
    return batches


def _count_batches(processed_data_dir):
    """DB의 배치 수 반환."""
    from src.services.user_data_manager import _get_eval_conn
    conn = _get_eval_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(DISTINCT batch_id) FROM evaluations"
        ).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
    finally:
        conn.close()


def load_all_batches(processed_data_dir=None):
    if processed_data_dir is None:
        processed_data_dir = PROCESSED_DATA_DIR_PATH

    conn = _get_eval_conn()
    try:
        rows = conn.execute("""
            SELECT e.employee_id, e.name, e.department, e.position, ev.data, ev.id
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            ORDER BY e.employee_id, ev.id
        """).fetchall()
    finally:
        conn.close()

    emp_evals = defaultdict(list)
    emp_meta = {}
    for emp_id, name, dept, pos, data, ev_db_id in rows:
        if emp_id not in emp_meta:
            # target_employee_id는 가명 ID(emp_id)를 매칭 키로 사용한다.
            # 실명 복원은 상위 enrich 계층(get_matrix_meta) 및 'real' 출력 모드
            # (generate_perspective_matrix / save_to_deploy)에서 수행한다.
            emp_meta[emp_id] = {
                'target_employee_name': name or '',
                'target_employee_department': dept or '',
                'target_employee_position': pos or '',
            }
        if data:
            ev_obj = json.loads(data)
            # evaluation_id는 중복될 수 있으므로 고유한 DB row id를 보정값 키로 사용
            ev_obj['_db_id'] = ev_db_id
            emp_evals[emp_id].append(ev_obj)

    employee_results = []
    total_evals = 0
    for emp_id, meta in emp_meta.items():
        evals = emp_evals[emp_id]
        total_evals += len(evals)
        employee_results.append({
            'metadata': {
                'target_employee_id': emp_id,
                'target_employee_name': meta['target_employee_name'],
                'target_employee_department': meta['target_employee_department'],
                'target_employee_position': meta['target_employee_position'],
                'evaluations': evals,
            }
        })

    return {
        'batch_info': {
            'total_evaluations': total_evals,
            'unique_employees': len(emp_meta),
            'batch_count': _count_batches(processed_data_dir),
        },
        'employee_results': employee_results,
        'batches': _load_batch_list(processed_data_dir),
    }


def filter_evaluations(batch_summary, filters, employee_id=None, enrich=False):
    if not filters:
        return []
    results = []
    for er in batch_summary.get('employee_results', []):
        meta = er.get('metadata', {})
        emp_id = meta.get('target_employee_id')
        if employee_id and emp_id != employee_id:
            continue
        for ev in meta.get('evaluations', []):
            conds = []
            for f in filters:
                col = f.get('column', f.get('column_name'))
                vals = f.get('values', [f.get('value', f.get('column_value'))])
                ev_val = _get_eval_field_value(ev, col)
                conds.append(ev_val in vals)
            if not conds:
                continue
            groups = [[0]]
            for i in range(1, len(conds)):
                connector = filters[i].get('connector', 'and')
                if connector == 'or':
                    groups[-1].append(i)
                else:
                    groups.append([i])
            group_results = [any(conds[j] for j in g) for g in groups]
            if all(group_results):
                results.append({
                    'evaluation': ev,
                    'employee_id': emp_id,
                    'employee_department': meta.get('target_employee_department'),
                    'employee_position': meta.get('target_employee_position'),
                })
    pseudonym_fields = _get_pseudonym_fields(batch_summary)
    results = _enrich_with_real_ids(results, pseudonym_fields, enrich)
    return results


def extract_words(filtered_evaluations, wordcloud_pos=None, remove_profanity=False):
    if wordcloud_pos is None:
        wordcloud_pos = ['Noun']
    all_words = []
    profanity_set = set()
    employee_ids = set()
    for item in filtered_evaluations:
        ev = item['evaluation']
        employee_ids.add(item['employee_id'])
        nlp = ev.get('nlp_analysis_results', {})
        pos_data = None
        if isinstance(nlp, dict):
            analysis = nlp.get('analysis', {})
            if isinstance(analysis, dict):
                pos_data = analysis.get('meaningful_words_with_pos')
        if pos_data and isinstance(pos_data, list):
            for entry in pos_data:
                if isinstance(entry, list) and len(entry) == 2:
                    word, pos = entry
                    if pos in wordcloud_pos:
                        all_words.append(word)
                elif isinstance(entry, str):
                    all_words.append(entry)
        else:
            meaningful = None
            if isinstance(nlp, dict):
                analysis = nlp.get('analysis', {})
                if isinstance(analysis, dict):
                    meaningful = analysis.get('meaningful_words')
                if not meaningful:
                    meaningful = nlp.get('meaningful_words')
            if meaningful and isinstance(meaningful, list):
                all_words.extend(meaningful)
        if remove_profanity:
            prof = ev.get('profanity_analysis_results', {})
            if isinstance(prof, dict):
                detected = prof.get('detected_profanity', [])
                if isinstance(detected, list):
                    profanity_set.update(detected)
    word_freq = dict(Counter(all_words))
    if remove_profanity and profanity_set:
        for pw in profanity_set:
            pw_clean = pw.replace('legacy:', '')
            if pw_clean in word_freq:
                del word_freq[pw_clean]
    return {
        'word_frequency': word_freq,
        'total_evaluations': len(filtered_evaluations),
        'total_employees': len(employee_ids),
        'profanity_removed': list(profanity_set) if remove_profanity else [],
    }


def _load_corrections_map(employee_id):
    """DB에서 해당 직원의 모든 evaluation에 대한 sentiment_corrections를 로드.

    evaluation_id는 중복될 수 있으므로 고유한 DB row id(int)를 키로 사용한다.
    """
    conn = _get_eval_conn()
    try:
        rows = conn.execute(
            "SELECT id, sentiment_corrections FROM evaluations WHERE employee_id = ?",
            (employee_id,)
        ).fetchall()
        corrections_map = {}
        for row in rows:
            db_id = row[0]
            corrections_str = row[1] or '{}'
            try:
                corrections = json.loads(corrections_str)
            except (json.JSONDecodeError, TypeError):
                corrections = {}
            if corrections:
                corrections_map[db_id] = corrections
        return corrections_map
    finally:
        conn.close()


def _get_sentence_level_scores(doc, threshold=0.20, weight=2.0, corrections=None, sentence_cache=None):
    """문장별 감정 점수(반전 규칙·사용자 교정 적용 후)를 계산.

    Returns list of (sent, score, pos, neg) 4-tuples.
    corrections: {sentence_index: "positive"|"negative"|"neutral"}
    sentence_cache: 배치 시 저장된 문장 단위 KoTE 원시 점수 리스트
                    [{"sentence"(optional), "pos", "neg", "neutral"}, ...].
                    제공되면 KoTE 재실행 없이 캐시 사용. 없으면 공유 헬퍼로 fallback.
    """
    if sentence_cache and isinstance(sentence_cache, list):
        # 캐시 경로: KoTE 재실행 없음. sentence 누락(점수-only) 시 split로 재도출
        derived = None
        sentences = []
        for idx, e in enumerate(sentence_cache):
            sent = e.get('sentence')
            if sent is None:
                if derived is None:
                    derived = split_sentences(doc)
                sent = derived[idx] if idx < len(derived) else ''
            sentences.append(sent)
        sent_scores_raw = [
            (e.get('pos', 0.0) or 0.0, e.get('neg', 0.0) or 0.0, e.get('neutral', 0.0) or 0.0)
            for e in sentence_cache
        ]
    else:
        # fallback: 캐시 없는 기존 배치 — 공유 헬퍼로 즉석 계산 (기존과 동일 결과)
        from src.modules.sentence_emotion import compute_sentence_raw_scores
        cache = compute_sentence_raw_scores(doc)
        if not cache:
            return [(None, 0.0, 0.0, 0.0)]
        sentences = [e['sentence'] for e in cache]
        sent_scores_raw = [(e['pos'], e['neg'], e['neutral']) for e in cache]

    total = len(sentences)
    result = []
    for i, (pos, neg, neutral) in enumerate(sent_scores_raw):
        sent = sentences[i]
        is_last = (i == total - 1)
        # KoTE 원점수 항상 계산 (보정 여부 무관)
        original_score = sentence_sentiment_override(
            pos, neg, sent, is_last, total,
            threshold=threshold, weight=weight, neutral=neutral
        )
        if corrections and str(i) in corrections:
            corr_val = corrections[str(i)]
            if corr_val == 'positive':
                # 긍정 강제: 원래 강도 보존, 원래 중립(≈0)이면 +1.0
                score = abs(original_score) if abs(original_score) > 0.01 else 1.0
            elif corr_val == 'negative':
                # 부정 강제: 원래 강도 보존(×-1), 원래 중립이면 -1.0
                score = -abs(original_score) if abs(original_score) > 0.01 else -1.0
            else:  # neutral
                score = 0.0
        else:
            score = original_score
        result.append((sent, score, pos, neg))
    return result


def calculate_word_scores(filtered_evaluations, word_frequency, threshold=0.20, weight=2.0, corrections_map=None):
    """단어별 감정 점수를 문장 단위로 계산."""
    word_scores = {}
    for word in word_frequency.keys():
        total_score = 0.0
        count = 0
        for item in filtered_evaluations:
            ev = item['evaluation']
            nlp = ev.get('nlp_analysis_results', {})
            meaningful_words = []
            if isinstance(nlp, dict):
                analysis = nlp.get('analysis', {})
                if isinstance(analysis, dict):
                    meaningful_words = analysis.get('meaningful_words', [])
                if not meaningful_words:
                    meaningful_words = nlp.get('meaningful_words', [])
            if word not in meaningful_words:
                continue
            doc = ev.get('evaluation_document', '') or ev.get('evaluation_document_original', '')
            eval_corrections = corrections_map.get(ev.get('_db_id')) if corrections_map else None
            sent_scores = _get_sentence_level_scores(doc, threshold, weight, corrections=eval_corrections, sentence_cache=ev.get('sentence_emotion_cache'))
            # 단어가 속한 문장의 점수 찾기
            word_sent_score = None
            for sent, score, _, _ in sent_scores:
                if sent and word in sent:
                    word_sent_score = score
                    break
            # 속한 문장을 찾지 못하면 첫 번째(보통 가장 중요한) 문장 점수 사용
            if word_sent_score is None and sent_scores:
                word_sent_score = sent_scores[0][1]
            if word_sent_score is not None:
                total_score += word_sent_score
                count += 1
        word_scores[word] = round(total_score / count, 4) if count > 0 else 0.0
    return word_scores


def _get_emotion_color_rgb(score):
    score = max(-1.0, min(1.0, score))
    if score > 0.5:    return (100, 190, 145)
    elif score > 0.0:  return (145, 210, 165)
    elif score > -0.5: return (172, 178, 200)
    elif score > -1.0: return (230, 150, 150)
    else:              return (215, 120, 130)


def _highlight_words_in_sentence(sentence, top_words_set, word_scores):
    if not top_words_set or not sentence:
        return sentence
    pattern = '|'.join(re.escape(w) for w in sorted(top_words_set, key=len, reverse=True))
    def replacer(m):
        word = m.group(0)
        score = word_scores.get(word, 0.0)
        r, g, b = _get_emotion_color_rgb(score)
        return f'<span style="color:rgb({r},{g},{b})">{word}</span>'
    return re.sub(pattern, replacer, sentence)


def _extract_sentences_for_words(items, top_words, word_scores, top_k=20):
    top_list = [w for w, _ in sorted(top_words.items(), key=lambda x: -x[1])[:top_k]]
    if not top_list:
        return []
    top_set = set(top_list)
    sentences = []
    seen = set()
    for item in items:
        ev = item['evaluation']
        doc = ev.get('evaluation_document', '') or ev.get('evaluation_document_original', '')
        if not doc:
            continue
        for sep in ('\n', '. ', '! ', '? '):
            for part in doc.split(sep):
                part = part.strip()
                if not part or len(part) < 5:
                    continue
                if any(w in part for w in top_set):
                    key = part[:80]
                    if key not in seen:
                        seen.add(key)
                        sentences.append(_highlight_words_in_sentence(part, top_set, word_scores))
    return sentences


def _save_wordcloud_to_path(word_freq, word_scores, output_path, options):
    from src.modules.word_boost_manager import get_word_boost_manager
    word_freq = get_word_boost_manager().apply_to_frequency(word_freq)
    generator = WordCloudGenerator(config_path=WORDCLOUD_CONFIG_PATH)
    success = generator.generate_with_colors_and_options(
        word_freq, word_scores, output_path,
        background_color=options.get('background_color', 'white'),
        max_words=options.get('max_words', 100),
        width=options.get('width', 400),
        height=options.get('height', 300),
        apply_emotion_colors=options.get('apply_emotion_colors', True),
        word_color=options.get('word_color'),
    )
    return success


def _filters_to_desc(filters):
    parts = []
    for f in filters:
        col = f.get('column', '')
        vals = f.get('values', [f.get('value', '')])
        col_short = col.replace('evaluation_date', 'date').replace('evaluator_', '').replace('__', '_')
        parts.append(f"{col_short}_{'_'.join(str(v) for v in vals)}")
    return '_'.join(parts) if parts else 'all'


def _get_employee_metadata(unified_data, employee_id):
    for er in unified_data.get('employee_results', []):
        meta = er.get('metadata', {})
        if meta.get('target_employee_id') == employee_id:
            return meta
    return None


def _extract_row_values(ev, row_field):
    if row_field == 'batch_id':
        return [ev.get('batch_id', '?')]
    val = _get_eval_field_value(ev, row_field)
    return [str(val)] if val is not None else []


def _filter_items_by_row(all_items, row_field, row_values):
    """row_values 필터를 적용해 매칭되는 아이템만 반환한다."""
    if not row_values:
        return list(all_items)
    result = []
    for item in all_items:
        vals = _extract_row_values(item['evaluation'], row_field)
        if any(v in row_values for v in vals):
            result.append(item)
    return result


def _extract_col_group(evaluator_ev, col_mode, hierarchy, target_employee_meta, pseudo_mgr=None, output_mode='pseudonym'):
    def _resolve(val):
        if not val:
            return val
        if output_mode == 'real' and pseudo_mgr:
            resolved = pseudo_mgr.get_real_id(str(val))
            return resolved if resolved and resolved != str(val) else val
        return val

    if col_mode == 'all':
        return ['전체']
    if col_mode == 'department':
        val = evaluator_ev.get('evaluator_department', '')
        if val:
            val = _resolve(val)
        return [str(val)] if val else ['알수없음']
    if col_mode == 'position_detail':
        val = evaluator_ev.get('evaluator_position', '')
        if val:
            val = _resolve(val)
        return [str(val)] if val else ['알수없음']
    if col_mode == 'position_3tier':
        target_pos = target_employee_meta.get('target_employee_position', '') if target_employee_meta else ''
        if not target_pos:
            target_pos = evaluator_ev.get('target_employee_position', '')
        if target_pos:
            target_pos = _resolve(target_pos)
        eval_pos = evaluator_ev.get('evaluator_position', '')
        if eval_pos:
            eval_pos = _resolve(eval_pos)
        groups = get_relative_groups(target_pos, hierarchy)
        if eval_pos in groups['junior']:
            return ['부하']
        elif eval_pos in groups['peer']:
            return ['동료']
        elif eval_pos in groups['senior']:
            return ['상위직책']
        return ['알수없음']
    return ['알수없음']


def _aggregate_emotion(filtered_items, threshold=0.20, weight=2.0, corrections_map=None):
    """평가 문서를 문장 단위로 분할하여 감정 점수를 교정 후 문장별로 독립 집계."""
    pos_sum = 0.0
    neg_sum = 0.0
    count = 0
    for item in filtered_items:
        ev = item['evaluation']
        emotion = ev.get('emotion_analysis_results', {})
        scores = {}
        if isinstance(emotion, dict):
            analysis = emotion.get('analysis', {})
            if isinstance(analysis, dict):
                br = analysis.get('base_result', {})
                if isinstance(br, dict):
                    mp = br.get('mapped', {})
                    if isinstance(mp, dict):
                        scores = mp.get('sentiment_scores', {})
        if not isinstance(scores, dict):
            scores = {}
        doc = ev.get('evaluation_document', '') or ev.get('evaluation_document_original', '')
        eval_corrections = corrections_map.get(ev.get('_db_id')) if corrections_map else None
        sent_scores = _get_sentence_level_scores(doc, threshold, weight, corrections=eval_corrections, sentence_cache=ev.get('sentence_emotion_cache'))
        for sent, score, _, _ in sent_scores:
            pos_sum += max(0, score)
            neg_sum += max(0, -score)
            count += 1
    return {
        'positive': round(pos_sum / count, 4) if count > 0 else 0,
        'negative': round(neg_sum / count, 4) if count > 0 else 0,
    }


def _generate_nlp_cell(filtered_items, options, save_path, corrections_map=None):
    word_data = extract_words(filtered_items, wordcloud_pos=options.get('wordcloud_pos', ['Noun']),
                              remove_profanity=options.get('remove_profanity', False))
    wf = word_data['word_frequency']
    result = {
        'evaluation_count': word_data['total_evaluations'],
        'total_words': len(wf),
        'top_words': dict(Counter(wf).most_common(20)),
    }
    if not wf:
        result['warning'] = '추출된 단어 없음'
        return result

    word_scores = calculate_word_scores(filtered_items, wf, corrections_map=corrections_map)
    emotion_agg = _aggregate_emotion(filtered_items, corrections_map=corrections_map)
    result['avg_sentiment'] = emotion_agg

    if save_path:
        success = _save_wordcloud_to_path(wf, word_scores, save_path, options)
        if success:
            rel_path = os.path.relpath(save_path, OUTPUTS_DIR_PATH).replace('\\', '/')
            result['wordcloud_url'] = f"/outputs/{rel_path}"

    return result


def _generate_emotion_cell(filtered_items, threshold=0.20, weight=2.0, corrections_map=None):
    emotion_agg = _aggregate_emotion(filtered_items, threshold, weight, corrections_map)
    all_labels = []
    positive_docs = []
    negative_docs = []
    positive_details = []
    negative_details = []
    for item in filtered_items:
        ev = item['evaluation']
        emotion = ev.get('emotion_analysis_results', {})
        pos_score = 0.0
        neg_score = 0.0
        scores = {}
        if isinstance(emotion, dict):
            an = emotion.get('analysis', {})
            if isinstance(an, dict):
                br = an.get('base_result', {})
                if isinstance(br, dict):
                    raw = br.get('raw', {})
                    if isinstance(raw, dict):
                        label = raw.get('label', '')
                        if label:
                            all_labels.append(label)
                    mp = br.get('mapped', {})
                    if isinstance(mp, dict):
                        scores = mp.get('sentiment_scores', {})
                        if isinstance(scores, dict):
                            pos_score = scores.get('positive', 0.0) or 0.0
                            neg_score = scores.get('negative', 0.0) or 0.0
        doc = ev.get('evaluation_document', '') or ev.get('evaluation_document_original', '')
        eval_id = ev.get('evaluation_id', '')
        db_id = ev.get('_db_id')
        eval_corrections = corrections_map.get(db_id) if corrections_map else None
        sent_scores = _get_sentence_level_scores(doc, threshold, weight, corrections=eval_corrections, sentence_cache=ev.get('sentence_emotion_cache'))
        for i, (sent, score, pos, neg) in enumerate(sent_scores):
            if not sent:
                continue
            confidence = abs(pos - neg)
            batch_id = ev.get('batch_id', '')
            if score > 0:
                positive_docs.append(sent)
                positive_details.append({
                    'text': sent,
                    'evaluation_id': eval_id,
                    'db_id': db_id,
                    'sentence_index': i,
                    'sentiment': 'positive',
                    'confidence': confidence,
                    'batch_id': batch_id,
                    'context': doc,
                })
            elif score < 0:
                negative_docs.append(sent)
                negative_details.append({
                    'text': sent,
                    'evaluation_id': eval_id,
                    'db_id': db_id,
                    'sentence_index': i,
                    'sentiment': 'negative',
                    'confidence': confidence,
                    'batch_id': batch_id,
                    'context': doc,
                })
    return {
        'evaluation_count': len(filtered_items),
        'avg_sentiment': emotion_agg,
        'emotion_labels': dict(Counter(all_labels).most_common(10)),
        'positive_sentences': positive_docs[:5],
        'negative_sentences': negative_docs[:5],
        'positive_sentence_details': positive_details,
        'negative_sentence_details': negative_details,
    }


def _generate_leadership_cell(filtered_items):
    total_leadership = 0.0
    count = 0
    competencies_sum = {}
    for item in filtered_items:
        ev = item['evaluation']
        ldr = ev.get('leadership_analysis_results', {})
        if isinstance(ldr, dict):
            score = ldr.get('leadership_score') or ldr.get('overall_leadership_score')
            if score is not None:
                total_leadership += float(score)
                count += 1
            comps = ldr.get('leadership_competencies', {})
            for k, v in comps.items():
                if isinstance(v, (int, float)):
                    competencies_sum[k] = competencies_sum.get(k, 0) + v
    return {
        'evaluation_count': len(filtered_items),
        'avg_leadership_score': round(total_leadership / count, 4) if count > 0 else 0,
        'competencies': {k: round(v / count, 4) for k, v in competencies_sum.items()} if count > 0 else {},
    }


def _generate_profanity_cell(filtered_items):
    from src.services.profanity_db_service import _get_pseudo_mgr
    pseudo_mgr = _get_pseudo_mgr()

    total_count = 0
    profanity_words = set()
    profanity_sentences = []
    for item in filtered_items:
        ev = item['evaluation']
        prof = ev.get('profanity_analysis_results', {})
        if not isinstance(prof, dict):
            continue
        count = prof.get('profanity_count', 0)
        detected = prof.get('detected_profanity', [])
        if not isinstance(detected, list):
            detected = []
        total_count += count
        profanity_words.update(detected)
        if count > 0 and detected:
            raw_eval_id = ev.get('evaluator_id', '')
            real_eval_id = pseudo_mgr.get_real_id(raw_eval_id) if raw_eval_id else ''
            display_eval_id = real_eval_id if real_eval_id and real_eval_id != raw_eval_id else raw_eval_id
            profanity_sentences.append({
                'evaluator_id': display_eval_id,
                'original_text': prof.get('original_text', ''),
                'filtered_text': prof.get('filtered_text', ''),
                'detected_words': detected,
                'detection_details': prof.get('detection_details', []),
            })
    return {
        'evaluation_count': len(filtered_items),
        'total_profanity_count': total_count,
        'profanity_ratio': round(total_count / max(len(filtered_items), 1), 4),
        'profanity_words': list(profanity_words),
        'profanity_sentences': profanity_sentences,
    }


def build_profanity_summary(unified, employee_id):
    """직원의 전체 평가에서 욕설 감지 요약 반환 (스트리밍 done 이벤트용)."""
    from src.services.profanity_db_service import _get_pseudo_mgr
    pseudo_mgr = _get_pseudo_mgr()

    profanity_sentences = []
    total_count = 0
    for er in unified.get('employee_results', []):
        meta = er.get('metadata', {})
        if meta.get('target_employee_id') != employee_id:
            continue
        for ev in meta.get('evaluations', []):
            prof = ev.get('profanity_analysis_results', {})
            if not isinstance(prof, dict):
                continue
            count = prof.get('profanity_count', 0)
            detected = prof.get('detected_profanity', [])
            if not isinstance(detected, list):
                detected = []
            if count > 0 and detected:
                total_count += count

                raw_eval_id = ev.get('evaluator_id', '')
                real_eval_id = pseudo_mgr.get_real_id(raw_eval_id) if raw_eval_id else ''
                display_eval_id = real_eval_id if real_eval_id and real_eval_id != raw_eval_id else raw_eval_id

                profanity_sentences.append({
                    'evaluator_id': display_eval_id,
                    'original_text': prof.get('original_text', ''),
                    'filtered_text': prof.get('filtered_text', ''),
                    'detected_words': detected,
                    'detection_details': prof.get('detection_details', []),
                })
        break
    return {'total_count': total_count, 'profanity_sentences': profanity_sentences}


def build_all_profanity_summary(search=None, department=None, min_count=1,
                                sort='count', order='desc', page=1, limit=50,
                                include_sentences=False):
    """전사 욕설 리스트 조회 (DB 기반)."""
    from src.services.profanity_db_service import get_all_profanity_employees
    return get_all_profanity_employees(
        search=search, department=department, min_count=min_count,
        sort=sort, order=order, page=page, limit=limit,
        include_sentences=include_sentences,
    )


def _generate_sarcasm_cell(filtered_items):
    sarcasm_count = 0
    for item in filtered_items:
        ev = item['evaluation']
        sar = ev.get('sarcasm_analysis_results', {})
        if isinstance(sar, dict):
            an = sar.get('analysis', {})
            if isinstance(an, dict):
                for result_key in ['fine_tuned_result', 'sklearn_result']:
                    res = an.get(result_key, {})
                    if isinstance(res, dict):
                        mp = res.get('mapped', {})
                        if isinstance(mp, dict) and mp.get('label') == 'Sarcasm':
                            sarcasm_count += 1
                            break
    return {
        'evaluation_count': len(filtered_items),
        'sarcasm_count': sarcasm_count,
        'non_sarcasm_count': len(filtered_items) - sarcasm_count,
        'sarcasm_ratio': round(sarcasm_count / max(len(filtered_items), 1), 4),
    }


def _generate_cell_content(filtered_items, analysis_types, options, save_path=None, corrections_map=None):
    if not filtered_items:
        return {'evaluation_count': 0, 'warning': '평가 없음'}
    if isinstance(analysis_types, str):
        analysis_types = [analysis_types]
    _dispatch = {
        'nlp':        lambda: _generate_nlp_cell(filtered_items, options, save_path, corrections_map=corrections_map),
        'emotion':    lambda: _generate_emotion_cell(filtered_items, corrections_map=corrections_map),
        'leadership': lambda: _generate_leadership_cell(filtered_items),
        'profanity':  lambda: _generate_profanity_cell(filtered_items),
        'sarcasm':    lambda: _generate_sarcasm_cell(filtered_items),
    }
    result = {'evaluation_count': len(filtered_items)}
    for atype in analysis_types:
        if atype in _dispatch:
            result[atype] = _dispatch[atype]()
    return result


def _build_save_path(user_or_deploy, employee_id, row_field, col_mode, analysis_type, row_val, col_val, pseudo_mgr=None, output_mode='pseudonym'):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    if user_or_deploy == 'user':
        pseudo = employee_id
        if output_mode == 'real' and pseudo_mgr:
            real_id = pseudo_mgr.get_real_id(employee_id)
            if real_id and real_id != employee_id:
                pseudo = employee_id
        safe_pseudo = re.sub(r'[\\/*?:"<>|]', '_', str(pseudo))
        safe_rv = re.sub(r'[\\/*?:"<>|]', '_', str(row_val))
        safe_cv = re.sub(r'[\\/*?:"<>|]', '_', str(col_val))
        subdir = f"{row_field}_{col_mode}_{analysis_type}"
        filename = f"{safe_rv}_{safe_cv}.png"
        full_dir = os.path.join(USER_OUTPUT_DIR, safe_pseudo, subdir)
        os.makedirs(full_dir, exist_ok=True)
        return os.path.join(full_dir, filename)
    else:
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', str(employee_id))
        filename = f"{safe_name}_{row_field}_{col_mode}_{analysis_type}_{ts}.png"
        return filename


def _get_row_value_counts(unified_data, row_field, employee_id=None):
    counts = {}
    for er in unified_data.get('employee_results', []):
        meta = er.get('metadata', {})
        if employee_id and meta.get('target_employee_id') != employee_id:
            continue
        for ev in meta.get('evaluations', []):
            vals = _extract_row_values(ev, row_field)
            for v in vals:
                counts[v] = counts.get(v, 0) + 1
    return counts


def get_matrix_meta(unified_data, employee_id=None, enrich=False):
    hierarchy = load_position_hierarchy()
    row_options = []
    for key, info in ROW_FIELDS.items():
        vals = _get_row_value_counts(unified_data, key, employee_id)
        if vals:
            vals_sorted = sorted(vals.items(), key=lambda x: (-x[1], x[0]))
            row_options.append({
                'field': key,
                'label': info['label'],
                'values': [{'value': v, 'count': c} for v, c in vals_sorted],
            })
    col_modes = [{'mode': k, 'label': v['label'], 'type': v['type']} for k, v in COL_MODES.items()]
    analysis_types = [{'mode': k, 'label': v['label'], 'type': v['type']} for k, v in ANALYSIS_TYPES.items()]
    pseudo_mgr = _get_pseudo_mgr() if enrich else None
    employees = []
    seen = set()
    for er in unified_data.get('employee_results', []):
        meta = er.get('metadata', {})
        emp_id = meta.get('target_employee_id')
        if emp_id and emp_id not in seen:
            seen.add(emp_id)
            entry = {
                'employee_id': emp_id,
                'department': meta.get('target_employee_department'),
                'position': meta.get('target_employee_position'),
                'evaluation_count': len(meta.get('evaluations', [])),
                'employee_name': meta.get('target_employee_name'),
            }
            if enrich and pseudo_mgr:
                def _dr(v):
                    if not v:
                        return v
                    r = pseudo_mgr.get_real_id(str(v))
                    return r if r != v else v
                real_id = _dr(emp_id)
                entry['employee_id'] = real_id           # 원본 ID로 교체 (호출=원본 정책)
                entry['employee_id_real'] = real_id if real_id != emp_id else None
                raw_name = meta.get('target_employee_name')
                entry['employee_name'] = _dr(raw_name) if raw_name else None
                entry['department'] = _dr(entry.get('department')) if entry.get('department') else entry.get('department')
                entry['position'] = _dr(entry.get('position')) if entry.get('position') else entry.get('position')
            employees.append(entry)
    employees.sort(key=lambda e: e['employee_id'] or '')

    return {
        'row_options': row_options,
        'col_modes': col_modes,
        'analysis_types': analysis_types,
        'employees': employees,
        'position_hierarchy': hierarchy,
        'batch_count': unified_data.get('batch_info', {}).get('batch_count', 0),
        'total_evaluations': unified_data.get('batch_info', {}).get('total_evaluations', 0),
    }


def _get_evaluations_for_employee(unified_data, employee_id):
    items = []
    for er in unified_data.get('employee_results', []):
        meta = er.get('metadata', {})
        if meta.get('target_employee_id') != employee_id:
            continue
        for ev in meta.get('evaluations', []):
            items.append({
                'evaluation': ev,
                'employee_id': employee_id,
                'employee_department': meta.get('target_employee_department'),
                'employee_position': meta.get('target_employee_position'),
            })
    return items


def _sort_keys(keys, row_field):
    if row_field == 'evaluation_date':
        return sorted(keys)
    elif row_field == 'evaluation_date__year':
        return sorted(keys)
    elif row_field == 'evaluation_date__month':
        return sorted(keys, key=lambda x: int(x) if x.isdigit() else x)
    elif row_field == 'batch_id':
        return sorted(keys)
    return sorted(keys)


def _sort_col_keys(keys, col_mode, hierarchy):
    if col_mode == 'position_detail':
        order = [e['name'] for e in hierarchy]
        order.append('알수없음')
        return [k for k in order if k in keys] + [k for k in keys if k not in order]
    if col_mode == 'position_3tier':
        order = ['부하', '동료', '상위직책', '알수없음', '전체']
        return [k for k in order if k in keys] + [k for k in keys if k not in order]
    return sorted(keys)


def generate_perspective_matrix(unified_data, employee_id, row_field, col_mode, analysis_type, options, corrections_map=None):
    hierarchy = load_position_hierarchy()
    # 원본 ID가 입력된 경우 저장된 가명으로 resolve (새 가명 생성 없음)
    resolved_id = _resolve_to_pseudo(employee_id, _get_pseudo_mgr())
    target_meta = _get_employee_metadata(unified_data, resolved_id)
    all_items = _get_evaluations_for_employee(unified_data, resolved_id)
    if not all_items:
        return None

    output_mode = options.get('output_mode', 'pseudonym')
    pseudo_mgr = _get_pseudo_mgr() if output_mode == 'real' else None

    row_values = options.get('row_values')
    row_combine_all = options.get('row_combine_all', False)

    row_cells = {}
    col_cells = {}

    for item in all_items:
        ev = item['evaluation']
        row_vals = _extract_row_values(ev, row_field)
        if row_values and not row_combine_all:
            row_vals = [v for v in row_vals if v in row_values]
            if not row_vals:
                continue
        elif row_combine_all:
            if row_values and not any(v in row_values for v in row_vals):
                continue
            row_vals = ['선택 통합']
        col_vals = _extract_col_group(ev, col_mode, hierarchy, target_meta, pseudo_mgr, output_mode)
        for rv in row_vals:
            if rv not in row_cells:
                row_cells[rv] = {}
            for cv in col_vals:
                if cv not in col_cells:
                    col_cells[cv] = True
                if cv not in row_cells[rv]:
                    row_cells[rv][cv] = []
                row_cells[rv][cv].append(item)

    row_keys_sorted = _sort_keys(row_cells.keys(), row_field)
    col_keys_sorted = _sort_col_keys(col_cells.keys(), col_mode, hierarchy)

    analysis_types = options.get('analysis_types') or [analysis_type]

    matrix = {}
    for rk in row_keys_sorted:
        matrix[rk] = {}
        for ck in col_keys_sorted:
            cell_items = row_cells.get(rk, {}).get(ck, [])
            save_path = _build_save_path(
                'user', resolved_id, row_field, col_mode, analysis_types[0],
                rk, ck, pseudo_mgr, options.get('output_mode', 'pseudonym')
            ) if cell_items else None
            matrix[rk][ck] = _generate_cell_content(cell_items, analysis_types, options, save_path, corrections_map)

    def _deref(val):
        if not val or not pseudo_mgr:
            return val
        resolved = pseudo_mgr.get_real_id(str(val))
        return resolved if resolved != val else val

    real_id = _deref(resolved_id) if output_mode == 'real' else resolved_id

    raw_name = (target_meta or {}).get('target_employee_name') or ''
    raw_dept = (target_meta or {}).get('target_employee_department') or ''
    # 실제 이름은 원데이터 모드(관리자 인증 완료 후 매트릭스 생성/저장 시)에만 노출
    employee_name = _deref(raw_name) if output_mode == 'real' else None
    employee_department = _deref(raw_dept) if output_mode == 'real' else raw_dept

    result = {
        'employee_id': real_id if output_mode == 'real' else resolved_id,
        'employee_id_real': real_id if (output_mode == 'real' and real_id != resolved_id) else None,
        'employee_name': employee_name or None,
        'employee_department': employee_department or None,
        'row_field': row_field,
        'row_label': ROW_FIELDS.get(row_field, {}).get('label', row_field),
        'col_mode': col_mode,
        'col_label': COL_MODES.get(col_mode, {}).get('label', col_mode),
        'analysis_type': analysis_types[0] if analysis_types else analysis_type,
        'analysis_types': analysis_types,
        'rows': row_keys_sorted,
        'columns': col_keys_sorted,
        'matrix': matrix,
        'profanity_summary': build_profanity_summary(unified_data, resolved_id),
    }

    # 매트릭스 결과 자동 인덱싱 (단일 직원 호출 시)
    if result.get('matrix') and result.get('rows'):
        _index_matrix_to_manifest(result, resolved_id, row_field, col_mode, analysis_type, options)

    return result


def _setup_korean_font():
    try:
        import matplotlib.font_manager as fm
        import matplotlib.pyplot as plt
        import platform
        system = platform.system()
        if system == 'Windows':
            candidates = [
                'C:/Windows/Fonts/malgun.ttf',
                'C:/Windows/Fonts/malgunsl.ttf',
                'C:/Windows/Fonts/gulim.ttc',
            ]
            for font_path in candidates:
                if os.path.exists(font_path):
                    fm.fontManager.addfont(font_path)
                    font_name = fm.FontProperties(fname=font_path).get_name()
                    plt.rcParams['font.family'] = font_name
                    break
    except Exception:
        pass


def _save_cell_wordcloud(cell_items, sentiment_filter, options, cell_path):
    """셀 워드클라우드를 PIL Image로 생성하고 파일 저장 후 Image 객체 반환."""
    from PIL import Image
    word_data = extract_words(cell_items, wordcloud_pos=options.get('wordcloud_pos', ['Noun']),
                              remove_profanity=options.get('remove_profanity', False))
    wf = word_data['word_frequency']
    if sentiment_filter == 'positive':
        word_scores = calculate_word_scores(cell_items, wf)
        wf = {w: c for w, c in wf.items() if word_scores.get(w, 0) > 0}
    elif sentiment_filter == 'negative':
        word_scores = calculate_word_scores(cell_items, wf)
        wf = {w: c for w, c in wf.items() if word_scores.get(w, 0) < 0}
    if wf:
        word_scores = calculate_word_scores(cell_items, wf)
        _save_wordcloud_to_path(wf, word_scores, cell_path, options)
        return Image.open(cell_path).convert('RGB')
    return None


def _append_to_deploy_manifest(result, employee_id, row_field, analysis_type, options):
    """배포 결과를 gallery_entries DB에 저장."""
    row_results = {}
    for row_key, row_val in result.get('row_results', {}).items():
        row_results[row_key] = {
            "combined": row_val.get('combined'),
            "positive": row_val.get('positive'),
            "negative": row_val.get('negative'),
        }

    entry = {
        "id": str(uuid.uuid4()),
        "employee_id": employee_id,
        "deploy_name": result.get('name', ''),
        "batch_title": options.get('batch_title') or None,
        "timestamp": result.get('timestamp', ''),
        "output_mode": options.get('output_mode', 'real'),
        "source": "deploy",
        "row_field": row_field,
        "row_values": options.get('row_values'),
        "row_combine_all": options.get('row_combine_all', False),
        "analysis_type": analysis_type,
        "options": {
            "wordcloud_pos": options.get('wordcloud_pos', ['Noun']),
            "background_color": options.get('background_color', 'white'),
            "width": options.get('width', 800),
            "height": options.get('height', 600),
            "max_words": options.get('max_words', 100),
            "apply_emotion_colors": options.get('apply_emotion_colors', True),
            "remove_profanity": options.get('remove_profanity', False),
            "word_color": options.get('word_color'),
        },
        "images": {
            "combined": result.get('combined'),
            "positive": result.get('positive'),
            "negative": result.get('negative'),
        },
        "row_results": row_results,
    }

    try:
        from src.services.gallery_db_service import upsert_entry
        upsert_entry(entry)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Gallery DB write failed: {e}")


def _index_matrix_to_manifest(matrix_result, employee_id, row_field, col_mode, analysis_type, options):
    """매트릭스 결과를 gallery_entries DB에 저장."""
    matrix = matrix_result.get('matrix', {})
    rows = matrix_result.get('rows', [])
    columns = matrix_result.get('columns', [])

    first_col = columns[0] if columns else None
    if not first_col:
        return

    row_results = {}
    for row_key in rows:
        cell = matrix.get(row_key, {}).get(first_col, {})
        nlp_data = cell.get('nlp') or cell.get(analysis_type, {})
        combined_url = nlp_data.get('wordcloud_url') if isinstance(nlp_data, dict) else None
        if combined_url:
            row_results[row_key] = {'combined': combined_url, 'positive': None, 'negative': None}

    thumbnail = next((v['combined'] for v in row_results.values() if v['combined']), None)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    entry = {
        "id": str(uuid.uuid4()),
        "employee_id": employee_id,
        "deploy_name": employee_id,
        "batch_title": options.get('batch_title') or None,
        "timestamp": ts,
        "output_mode": options.get('output_mode', 'real'),
        "source": "matrix",
        "row_field": row_field,
        "analysis_type": analysis_type,
        "options": {
            "wordcloud_pos": options.get('wordcloud_pos', ['Noun']),
            "background_color": options.get('background_color', 'white'),
            "width": options.get('width', 400),
            "height": options.get('height', 300),
            "max_words": options.get('max_words', 80),
            "apply_emotion_colors": options.get('apply_emotion_colors', True),
            "remove_profanity": options.get('remove_profanity', False),
            "word_color": options.get('word_color'),
        },
        "images": {"combined": thumbnail, "positive": None, "negative": None},
        "row_results": row_results,
    }

    try:
        from src.services.gallery_db_service import upsert_entry
        upsert_entry(entry)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Gallery DB write (matrix) failed: {e}")


def save_to_deploy(unified_data, employee_id, row_field, col_mode, analysis_type, options, request=None):
    _setup_korean_font()
    output_mode = options.get('output_mode', 'pseudonym')

    # 원본 ID가 입력될 수 있으므로 내부 저장 가명으로 변환
    pseudo_mgr = _get_pseudo_mgr()
    resolved_id = _resolve_to_pseudo(employee_id, pseudo_mgr)

    target_meta = _get_employee_metadata(unified_data, resolved_id)

    include_name = options.get('include_name', True)
    include_id   = options.get('include_id', True)

    if output_mode == 'real' and (include_name or include_id):
        # 사번: resolved_id(가명) → 원본 역변환
        real_id = pseudo_mgr.get_real_id(resolved_id)
        real_id = real_id if (real_id and real_id != resolved_id) else None
        # 이름: target_employee_name도 가명화 대상이므로 역변환
        raw_name = (target_meta or {}).get('target_employee_name', '') or ''
        real_name = pseudo_mgr.get_real_id(raw_name) if raw_name else ''
        if not real_name or real_name == resolved_id or real_name == raw_name:
            real_name = ''

        parts = []
        if include_name and real_name:
            parts.append(real_name)
        if include_id and real_id and real_id not in parts:
            parts.append(real_id)
        deploy_name = '_'.join(parts) if parts else (real_id or employee_id)
    else:
        deploy_name = employee_id

    all_items = _get_evaluations_for_employee(unified_data, resolved_id)
    if not all_items:
        return None

    row_values = options.get('row_values')
    row_combine_all = options.get('row_combine_all', False)

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = re.sub(r'[\\/*?:"<>|]', '_', str(deploy_name))

    wordcloud_pos = options.get('wordcloud_pos', ['Noun'])
    os.makedirs(DEPLOY_OUTPUT_DIR, exist_ok=True)

    wc_options = {
        'background_color': options.get('background_color', 'white'),
        'max_words': options.get('max_words', 100),
        'width': options.get('width', 800),
        'height': options.get('height', 600),
        'apply_emotion_colors': options.get('apply_emotion_colors', True),
        'word_color': options.get('word_color'),
    }

    def _save_wc(wf, scores, suffix, filename):
        if not wf:
            return None
        sub_dir = os.path.join(DEPLOY_OUTPUT_DIR, suffix)
        os.makedirs(sub_dir, exist_ok=True)
        path = os.path.join(sub_dir, f"{filename}.png")
        ok = _save_wordcloud_to_path(wf, scores, path, wc_options)
        if ok and os.path.exists(path):
            rel = os.path.relpath(path, OUTPUTS_DIR_PATH).replace('\\', '/')
            return f"/outputs/{rel}?v={ts}"
        return None

    deploy_corrections_map = _load_corrections_map(resolved_id)
    logger.info(f"[deploy] employee={resolved_id} corrections_map keys={list(deploy_corrections_map.keys()) if deploy_corrections_map else []}")

    def _generate_wc_for_items(items, label_suffix):
        word_data = extract_words(items, wordcloud_pos=wordcloud_pos,
                                  remove_profanity=options.get('remove_profanity', False))
        wf_all = word_data['word_frequency']
        if not wf_all:
            return None, None, None, [], [], [], [], [], []
        word_scores = calculate_word_scores(items, wf_all, corrections_map=deploy_corrections_map)
        wf_positive = {w: c for w, c in wf_all.items() if word_scores.get(w, 0) >= 0}
        wf_negative = {w: c for w, c in wf_all.items() if word_scores.get(w, 0) < 0}
        filename = f"{safe_name}_{label_suffix}" if label_suffix else safe_name
        combined_url = _save_wc(wf_all, word_scores, '통합', filename)
        positive_url = _save_wc(wf_positive, {w: s for w, s in word_scores.items() if w in wf_positive}, '긍정', filename)
        negative_url = _save_wc(wf_negative, {w: s for w, s in word_scores.items() if w in wf_negative}, '부정', filename)
        combined_sent = _extract_sentences_for_words(items, wf_all, word_scores)
        positive_sent = _extract_sentences_for_words(items, wf_positive, word_scores)
        negative_sent = _extract_sentences_for_words(items, wf_negative, word_scores)
        top_pos = set([w for w, _ in sorted(wf_positive.items(), key=lambda x: -x[1])[:20]])
        top_neg = set([w for w, _ in sorted(wf_negative.items(), key=lambda x: -x[1])[:20]])
        pos_details, neg_details, neutral_details = [], [], []
        all_seen = set()
        for item_idx, item in enumerate(items):
            ev = item['evaluation']
            eval_id = ev.get('evaluation_id', '')
            db_id = ev.get('_db_id')
            doc = ev.get('evaluation_document', '') or ev.get('evaluation_document_original', '')
            if not doc:
                continue
            eval_corr = deploy_corrections_map.get(db_id, {}) if deploy_corrections_map else {}
            if eval_corr:
                logger.info(f"[deploy][{label_suffix}] db_id={db_id} eval_id={eval_id} corrections={eval_corr}")
            sent_scores_list = _get_sentence_level_scores(doc, corrections=eval_corr, sentence_cache=ev.get('sentence_emotion_cache'))
            sent_score_map = {}
            confidence_map = {}
            for idx, (_, sc, pos, neg) in enumerate(sent_scores_list):
                sent_score_map[idx] = sc
                confidence_map[idx] = abs(pos - neg)
            for i, sent in enumerate(split_sentences(doc)):
                if not sent:
                    continue
                text_key = sent[:80]
                if text_key in all_seen:
                    continue
                all_seen.add(text_key)
                sent_score = sent_score_map.get(i, 0.0)
                confidence = confidence_map.get(i, 0.0)
                base = {'text': sent, 'evaluation_id': eval_id, 'db_id': db_id, 'item_index': item_idx, 'sentence_index': i, 'confidence': confidence, 'batch_id': ev.get('batch_id', ''), 'context': doc}
                if sent_score > 0:
                    base['text_html'] = _highlight_words_in_sentence(sent, top_pos, word_scores)
                    pos_details.append({**base, 'sentiment': 'positive', 'score': round(sent_score, 3)})
                elif sent_score < 0:
                    base['text_html'] = _highlight_words_in_sentence(sent, top_neg, word_scores)
                    neg_details.append({**base, 'sentiment': 'negative', 'score': round(sent_score, 3)})
                else:
                    neutral_details.append({**base, 'sentiment': 'neutral', 'score': 0.0})
        logger.info(f"[deploy][{label_suffix}] pos_details={len(pos_details)}건 neg_details={len(neg_details)}건 neutral_details={len(neutral_details)}건 top_pos={len(top_pos)}단어 top_neg={len(top_neg)}단어")
        if pos_details:
            logger.info(f"[deploy][{label_suffix}] pos_details 샘플: {[d['text'][:20] for d in pos_details[:3]]}")
        if neg_details:
            logger.info(f"[deploy][{label_suffix}] neg_details 샘플: {[d['text'][:20] for d in neg_details[:3]]}")
        return combined_url, positive_url, negative_url, combined_sent, positive_sent, negative_sent, pos_details, neg_details, neutral_details

    filtered_items = _filter_items_by_row(all_items, row_field, row_values)
    if not filtered_items:
        return None
    combined_url, positive_url, negative_url, combined_sent, positive_sent, negative_sent, pos_det, neg_det, neu_det = _generate_wc_for_items(filtered_items, '통합')
    result = {
        'name': deploy_name,
        'timestamp': ts,
        'combined': combined_url,
        'positive': positive_url,
        'negative': negative_url,
        '통합': combined_url,
        '긍정': positive_url,
        '부정': negative_url,
        'combined_sentences': combined_sent,
        'positive_sentences': positive_sent,
        'negative_sentences': negative_sent,
        '통합_문장': combined_sent,
        '긍정_문장': positive_sent,
        '부정_문장': negative_sent,
        'positive_sentence_details': pos_det,
        'negative_sentence_details': neg_det,
        'neutral_sentence_details': neu_det,
        'profanity_summary': build_profanity_summary(unified_data, resolved_id),
    }
    _append_to_deploy_manifest(result, employee_id, row_field, analysis_type, options)
    return result


def parse_csv_employee_ids(content):
    import csv, io
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return []

    header = rows[0]
    id_col_idx = None
    possible_names = ['employee_id', '사번', 'ID', 'emp_id', '직원ID', '대상자ID', '아이디', '직원번호', 'id', 'employeeid', 'empno']
    for name in possible_names:
        for i, col in enumerate(header):
            if col.strip().lower() == name.lower():
                id_col_idx = i
                break
        if id_col_idx is not None:
            break

    if id_col_idx is not None:
        ids = [row[id_col_idx].strip() for row in rows[1:] if len(row) > id_col_idx and row[id_col_idx].strip()]
    else:
        ids = [row[0].strip() for row in rows if row and row[0].strip()]

    return ids


def generate_all_employee_matrix(unified_data, row_field, col_mode, analysis_type, options, employee_ids=None):
    hierarchy = load_position_hierarchy()
    # employee_ids가 원본 ID를 포함할 수 있으므로 가명으로 resolve하여 필터 집합 구성
    resolved_filter = None
    if employee_ids is not None:
        _pm = _get_pseudo_mgr()
        resolved_filter = {_resolve_to_pseudo(eid, _pm) for eid in employee_ids}

    employees = []
    seen = set()
    for er in unified_data.get('employee_results', []):
        meta = er.get('metadata', {})
        emp_id = meta.get('target_employee_id')
        if emp_id and emp_id not in seen:
            seen.add(emp_id)
            if resolved_filter is None or emp_id in resolved_filter:
                employees.append({
                    'employee_id': emp_id,
                    'department': meta.get('target_employee_department'),
                    'position': meta.get('target_employee_position'),
                })

    def process_emp(emp):
        emp_id = emp['employee_id']
        try:
            result = generate_perspective_matrix(unified_data, emp_id, row_field, col_mode, analysis_type, options)
            return emp_id, result
        except Exception as e:
            return emp_id, {'error': str(e)}

    results = {}
    num_workers = min(multiprocessing.cpu_count(), 4)
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(process_emp, emp): emp['employee_id'] for emp in employees}
        for future in as_completed(futures):
            emp_id = futures[future]
            try:
                emp_result = future.result()
                if isinstance(emp_result, tuple):
                    emp_id, emp_result = emp_result
                results[emp_id] = emp_result
            except Exception as e:
                results[emp_id] = {'error': str(e)}
    return results


def _get_acq_conn():
    from src.services.deploy_session_service import _get_conn
    return _get_conn()


def save_acquired_sentence(data):
    conn = _get_acq_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO acquired_sentences
                (sentence_text, user_label, model_label, confidence,
                 source_employee_id, source_evaluation_id, source_batch_id,
                 sentence_index, db_id, context)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['sentence_text'],
            data.get('user_label', 'neutral'),
            data.get('model_label', 'neutral'),
            data.get('confidence', 0.0),
            data.get('source_employee_id', ''),
            data.get('source_evaluation_id', ''),
            data.get('source_batch_id', ''),
            data.get('sentence_index', 0),
            data.get('db_id', 0),
            data.get('context', ''),
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"[acquired] save error: {e}")
        return False
    finally:
        conn.close()


def list_acquired_sentences(page=1, per_page=50, mismatch_only=False, label=None, date_from=None, date_to=None):
    conn = _get_acq_conn()
    try:
        where_clauses = []
        params = []
        if mismatch_only:
            where_clauses.append("user_label != model_label")
        if label:
            where_clauses.append("(user_label = ? OR model_label = ?)")
            params.extend([label, label])
        if date_from:
            where_clauses.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            where_clauses.append("created_at <= ?")
            params.append(date_to + ' 23:59:59')
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        total = conn.execute(f"SELECT COUNT(*) FROM acquired_sentences WHERE {where_sql}", params).fetchone()[0]
        offset = (page - 1) * per_page
        rows = conn.execute(f"""
            SELECT * FROM acquired_sentences
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, params + [per_page, offset]).fetchall()
        return {
            'total': total,
            'page': page,
            'per_page': per_page,
            'items': [dict(r) for r in rows],
        }
    finally:
        conn.close()


def delete_acquired_sentence(sentence_id):
    conn = _get_acq_conn()
    try:
        conn.execute("DELETE FROM acquired_sentences WHERE id = ?", (sentence_id,))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"[acquired] delete error: {e}")
        return False
    finally:
        conn.close()


def analyze_acquired_sentences(sentence_ids, analysis_types=None):
    if analysis_types is None:
        analysis_types = ['emotion', 'profanity', 'sarcasm']
    from src.modules.emotion_analysis import analyze_emotion
    from src.modules.profanity_filter import advanced_filter_profanity
    from src.modules.sarcasm_analysis import analyze_sarcasm
    conn = _get_acq_conn()
    try:
        results = []
        for sid in sentence_ids:
            row = conn.execute("SELECT * FROM acquired_sentences WHERE id = ?", (sid,)).fetchone()
            if not row:
                continue
            sent_data = dict(row)
            text = sent_data['sentence_text']
            analysis = {}
            if 'emotion' in analysis_types:
                try:
                    er = analyze_emotion(text)
                    scores = er.get('analysis', {}).get('base_result', {}).get('mapped', {}).get('sentiment_scores', {})
                    pos = scores.get('positive', 0.0) or 0.0
                    neg = scores.get('negative', 0.0) or 0.0
                    neu = scores.get('neutral', 0.0) or 0.0
                    result_label = 'positive' if pos > neg else 'negative' if neg > pos else 'neutral'
                    analysis['emotion'] = {
                        'positive': round(pos, 4),
                        'negative': round(neg, 4),
                        'neutral': round(neu, 4),
                        'result': result_label,
                    }
                except Exception as e:
                    analysis['emotion'] = {'error': str(e)}
            if 'profanity' in analysis_types:
                try:
                    pr = advanced_filter_profanity(text)
                    analysis['profanity'] = {
                        'detected': pr.get('profanity_count', 0) > 0,
                        'count': pr.get('profanity_count', 0),
                    }
                except Exception as e:
                    analysis['profanity'] = {'error': str(e)}
            if 'sarcasm' in analysis_types:
                try:
                    sr = analyze_sarcasm(text)
                    analysis['sarcasm'] = {
                        'detected': sr.get('detected', False),
                        'score': sr.get('score', 0.0),
                    }
                except Exception as e:
                    analysis['sarcasm'] = {'error': str(e)}
            conn.execute(
                "UPDATE acquired_sentences SET analysis_results = ?, updated_at = datetime('now','localtime') WHERE id = ?",
                (json.dumps(analysis, ensure_ascii=False), sid)
            )
            results.append({
                'id': sid,
                'sentence_text': text,
                'user_label': sent_data.get('user_label'),
                'model_label': sent_data.get('model_label'),
                **analysis,
            })
        conn.commit()
        return results
    except Exception as e:
        logger.error(f"[acquired] analyze error: {e}")
        return []
    finally:
        conn.close()


def export_acquired_sentences_csv(mismatch_only=False):
    import csv, io
    data = list_acquired_sentences(page=1, per_page=999999, mismatch_only=mismatch_only)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'sentence_text', 'user_label', 'model_label', 'confidence',
                     'source_employee_id', 'source_evaluation_id', 'source_batch_id',
                     'sentence_index', 'context', 'created_at'])
    for item in data['items']:
        writer.writerow([
            item['id'], item['sentence_text'], item['user_label'], item['model_label'],
            item['confidence'], item['source_employee_id'], item['source_evaluation_id'],
            item['source_batch_id'], item['sentence_index'], item['context'], item['created_at'],
        ])
    return output.getvalue()
