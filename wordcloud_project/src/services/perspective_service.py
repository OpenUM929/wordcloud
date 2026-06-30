"""Perspective analysis service - multi-filter grouping engine with X/Y matrix."""
import matplotlib
matplotlib.use('Agg')
import os
import json
import re
import uuid
import hashlib
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
from src.modules.hr_context_lexicon import is_negation_praise  # negation 칭찬(부정의 부정) 식별(순수 문자열)
from utils.logger import get_pipeline_logger, _mask_real_id
from utils.date_normalize import normalize_eval_date

# 파이프라인 전용 로거
logger = get_pipeline_logger()

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


# 인사평가 도메인 긍정 표지 (positive_rescue 규칙용, 데이터 기반 도출)
# 배경: KoTE(구어 감정모델)는 인사평가 역량 명사구의 긍정을 거의 못 잡고(긍정 미검출 91%),
#   매핑 편향(부정25/긍정16)+보정규칙으로 긍정이 부정/중립으로 강등된다.
# 핵심 가치: 긍↔부 오분류만 방지. 본 목록은 부정 신호가 없을 때만(neg 게이트+배제어) 발동하므로
#   true-negative→positive 반전은 일어나지 않는다(중립→긍정 상향은 허용 범주).
POSITIVE_IMPLYING_PHRASES = [
    '수평적', '의사소통', '소통', '리더십', '리더쉽',
    '자발적', '참여 유도', '참여를 유도', '참여유도',
    '목표', '전략', '성과', '핵심성과',
    '전문성', '전문적', '전문 지식', '전문지식', '해박',
    '업무열의', '업무 열의', '열의', '열정', '의욕',
    '자기개발', '자기 개발', '학구열', '배우고자',
    '솔선수범', '솔선', '모범', '책임감', '책임 부여',
    '청렴', '윤리의식', '윤리', '도덕',
    '안전', '무재해', '무고장',
    '공감', '경청', '존중', '배려', '화합', '조화',
    '네트워크', '협업', '협조', '협력',
    '동기부여', '동기 부여', '코칭', '인재육성', '후진 양성',
    '혁신', '창의', '도전적', '도전의식', '주도',
    '명확한 업무지시', '명확히 제시', '구체적 전략', '명확',
    '해결책', '대안 제시', '대안을 제시', '대안',
    '적극적', '적극성',
    # 데이터 검증(1차 복원율 62%)에서 미복원으로 드러난 보강 표지
    '지식', '학습', '최신', '경험', '노하우', '분석', '우선순위',
    '효율', '검토', '이해도', '이해', '관심', '업무지시',
    '신중', '근면', '성실', '격려', '양방향', '쌍방향', '경청', '청취', '수렴',
    '비전', '방향 제시', '방향성', '예측', '대처', '개선', '노력',
    '동기', '분위기 조성', '인자', '온화', '부드러운', '유연',
    '문제해결', '체계적', '준수', '책임', '의지', '동료', '조성', '청취', '역량',
    # 23년_장점 코퍼스(523,715행) 재판정에서 rule3_last_low로 긍→부 뒤집히던 역량 표지 보강.
    #   한 줄짜리 장점("보고능력 우수"/"공정한 업무 수행"/"능동적 사고")이 곧 끝문장(is_last)이라
    #   저신뢰 시 rule3가 무조건 부정화 → positive_rescue가 먼저 구제하도록 표지 append.
    #   부정형("X하지 않")·불공정 등은 아래 게이트/NEGATIVE_CONTEXT로 차단(긍↔부 0 유지).
    '우수', '탁월', '능동', '원만', '신속', '열성', '공정',
]

# positive_rescue 발동을 막는 도메인 부정 문맥어 (기존 NEGATIVE 목록에 없는 보강분)
# 긍정 표지를 포함하더라도 아래가 있으면 구제하지 않는다(진짜 부정 보존).
# 주의: '고압'·'강압'·'권위의식'·'잔소리'는 "~지 않음"형 칭찬에도 등장 → 구제만 보류(중립 유지),
#   부정으로 만들지는 않으므로 핵심 가치(긍↔부) 안전.
NEGATIVE_CONTEXT_FOR_RESCUE = [
    '강요', '수직적', '수동적', '출세', '일방적', '독단',
    '고압', '강압', '권위의식', '잔소리', '비논리',
    # '공정' 표지의 부정 동형어 — "불공정한 업무처리"가 '공정' 매칭으로 구제되는 것을 차단.
    '불공정', '편파', '불공평',
    # 반어적 비판(역량어로 포장된 부정) — "지위 우위 이용 능력 탁월"·"본인에게만 유리하도록
    #   유도하는 능력 탁월"·"갑질이 장점"·"편향적·이기적 판단이 장점" 등 실측 발굴.
    '갑질', '이기적', '편향', '우위 이용', '유리하도록', '본인에게만', '본인에게 유리',
]


# 무응답/평가불가/내용없음 구문 (no_response_neutral 규칙용, 코퍼스 26건 실측 근거)
# 배경: "잘 모르겠습니다"·"뵌 적이 없어서 모름"·"내용없음"·낙서(ㅈㅈㅈ) 등 평가를 하지
#   않은(또는 못 한) 비(非)평가 문장이 KoTE→rule4_default에서 부정으로 강등된다(중립→부정 오분류).
# 핵심 가치: 비평가 문장은 긍정도 부정도 아니므로 중립이 정답. 본 규칙은 부정으로 강등된 것을
#   중립으로 되돌릴 뿐 긍↔부 오분류를 만들지 않는다(중립→부정 오류만 제거).
NO_RESPONSE_PHRASES = [
    '잘 모르', '잘모르', '모르겠', '모름', '모르것', '모르겟',
    '알지 못', '알 수 없', '알수 없', '알수없',
    '평가 할 수 없', '평가할 수 없', '평가 할 수가 없', '평가할 수가 없',
    '평가할수없', '평가 불가', '평가불가',
    '만난 적이 없', '만난적이 없', '뵌 적이 없', '뵌적이 없', '뵙지',
    '본 적이 없', '본적이 없', '본적없', '대면한 적이 없',
    '근무를 안해', '근무한 적이 없', '일해 본적', '일해본 적', '일해본적', '일해 본 적',
    '마주할 일이 없', '마주할일이 없', '마주칠 일이 없',
    '내용없음', '내용 없음', '내용없슴',
    '의견이 없', '의견 없',
    '서술할 내용 없', '서술할내용없', '서술할 내용없', '특별히 서술',
    '해당사항 없', '해당없', '특이사항 및 해당사항 없',
    '채우라니까', '10자',
]


def is_gibberish(sentence):
    """의미 없는 낙서(자모 반복·동일토큰 반복·숫자/기호 도배)인지 확인."""
    if not sentence:
        return False
    s = re.sub(r'\s', '', sentence)
    if len(s) < 2:
        return False
    # 한글 자모(완성형 아님)만으로 구성: ㅂㅂㅂ / ㅈㅈㅈ / ㄴㅇㄹ…
    if re.fullmatch(r'[ㄱ-ㅎㅏ-ㅣ]+', s):
        return True
    # 숫자만 / 기호만 도배: 1111…, -----, …
    if re.fullmatch(r'\d+', s) or re.fullmatch(r'[^\w가-힣]+', s):
        return True
    # 동일 1~4자 토큰이 3회 이상 반복: 성실성실성실…, ㅁㄴㅇㄹㅁㄴㅇㄹ…
    for n in (1, 2, 3, 4):
        unit = s[:n]
        if len(s) >= n * 3 and unit * (len(s) // n) == s[:n * (len(s) // n)] \
                and len(s) % n == 0:
            return True
    return False


def is_no_response(sentence):
    """평가를 하지 않은(또는 못 한) 비평가 문장인지 확인 — 무응답/평가불가/내용없음/낙서.

    단, 진짜 부정 신호(부정 암시어/완곡부정 구문)가 섞인 문장은 제외해 부정 보존
    (코퍼스 26건 전부 순수 비평가라 영향 없으나, 향후 혼합 입력에서 부→중 강등 차단).
    """
    if not sentence:
        return False
    if is_gibberish(sentence):
        return True
    if any(p in sentence for p in NO_RESPONSE_PHRASES):
        if has_negative_implying_words(sentence):
            return False
        if any(ph in sentence for ph in STRONG_NEGATIVE_PHRASES):
            return False
        return True
    return False


def has_positive_implying_phrase(sentence):
    """문장에 인사평가 긍정 표지가 포함되는지 확인."""
    if not sentence:
        return False
    return any(p in sentence for p in POSITIVE_IMPLYING_PHRASES)


def has_negative_implying_words(sentence):
    """문장에 부정을 암시하는 단어가 포함되는지 확인."""
    if not sentence:
        return False
    return any(word in sentence for word in NEGATIVE_IMPLYING_WORDS)


# 긍정표지를 직접 부정하는 bare negation(NEGATIVE_IMPLYING_WORDS에 없는 '없/않/안/못'류).
# 배경(batch_20260622_0 다면평가 실측 50건): "관심이 없다"·"책임감이 없습니다"·"업무열의가 없음"은
#   '관심/책임감/업무열의'가 긍정표지라 positive_rescue가 긍정 상향(부→긍 핵심가치 위반).
#   '부족/미흡/안 되'는 이미 NEGATIVE_IMPLYING_WORDS로 막히나 bare '없'은 누락되어 샌다.
#   바로 '없'을 통째 추가하면 "부족함이 없다"(긍정)·"문제가 없다"(긍정)까지 막으므로,
#   긍정표지 직후 창에서만 + 재부정(이중부정=칭찬)·양보는 제외하여 정밀 차단한다.
# 창을 좁게(3자) 두어 표지 직후 '조사+없/않'(관심이 없다)만 잡고, 표지와 negation 사이에
# 다른 단어가 낀 긍정 강조어/상쇄명사(노하우를 아낌'없이', 안전사고도 '없음', 고집'없음')는 배제.
_POS_DIRECT_NEGATORS = ['없', '않', '안 ', '안하', '안한', '못 ', '못하']
_RENEGATION_TOKENS = ['없', '않', '아니']
_CONCESSIVE_TOKENS = ['해도', '하나', '하지만', '지만', '으나', '에도', '하더라도']
# 긍정 강조어 어간(표지 뒤에 와도 부정이 아님: 아낌없이=후하게, 끊임없이=계속, 막힘없이=원활).
_POSITIVE_INTENSIFIER_STEMS = ['아낌', '끊임', '막힘', '쉼', '쉬지', '거침', '빠짐',
                               '변함', '다름', '어김', '틀림', '흔들림', '가림']
# 양면 표지(부재가 곧 부정이 아님) — 가드에서 제외. "개선할 점이 없다/예측할 수 없는 부분까지"는 긍정,
#   "개선/예측 의지가 없음"의 진짜 부정은 '의지/관심' 등 다른 표지가 그대로 잡으므로 손실 없음.
_GUARD_EXCLUDED_MARKERS = {'개선', '예측', '효율', '대안', '해결책', '문제해결'}
_POS_NEGATION_WINDOW = 3
# 접미 부정형(표지 + 어간 + '지 않/못/아니') 감지용 — 표지~negation 사이 어간을 건너뛰는 넓은 창.
_POS_SUFFIX_NEGATORS = ['지 않', '지않', '지 못', '지못', '지 아니', '지아니']
_POS_SUFFIX_NEG_WINDOW = 8


def positive_marker_directly_negated(sentence):
    """긍정표지가 직후 창에서 bare negation으로 직접 부정되면 True(부→긍 차단용).

    재부정(이중부정=칭찬: "배려함이 없지 않다")·양보("부족하나 노력")는 제외 → 긍→부 오분류 방지.
    """
    if not sentence:
        return False
    for marker in POSITIVE_IMPLYING_PHRASES:
        if marker in _GUARD_EXCLUDED_MARKERS:
            continue
        i = 0
        while True:
            p = sentence.find(marker, i)
            if p == -1:
                break
            after = p + len(marker)
            window = sentence[after:after + _POS_NEGATION_WINDOW]
            for neg in _POS_DIRECT_NEGATORS:
                j = window.find(neg)
                if j == -1:
                    continue
                neg_at = after + j
                # negation 직전 3자가 긍정 강조어 어간이면(아낌없이/끊임없이) 부정 아님 → 제외
                if any(stem in sentence[max(0, neg_at - 3):neg_at] for stem in _POSITIVE_INTENSIFIER_STEMS):
                    continue
                tail = sentence[neg_at + len(neg):neg_at + len(neg) + 5]
                # '없이'(후하게/원활)·'없는'(관계절)·'없을'(~없을 때) = 부정 아님 → 종결형(없다/없음/없고)만 부정
                if neg == '없' and tail[:1] in ('이', '는', '을'):
                    continue
                if any(r in tail for r in _RENEGATION_TOKENS):
                    continue  # 이중부정 = 칭찬 → 차단하지 않음
                if any(c in tail for c in _CONCESSIVE_TOKENS):
                    continue  # 양보 = 혼합 → 차단하지 않음
                return True
            # 접미 부정형 '~지 않/~지 못/~지 아니'(예: "열성적이지 않습니다", "우수하지 못함").
            #   window-3 직접 negator로는 표지와 '않' 사이 어간('적이지')이 끼어 놓친다.
            #   넓은 창에서 '지 않/지 못/지 아니'를 잡되, 재부정·양보는 제외(긍→부 안전).
            sfx = sentence[after:after + _POS_SUFFIX_NEG_WINDOW]
            for snt in _POS_SUFFIX_NEGATORS:
                k = sfx.find(snt)
                if k == -1:
                    continue
                stail = sfx[k + len(snt):k + len(snt) + 5]
                if any(r in stail for r in _RENEGATION_TOKENS):
                    continue  # "않지 않" 류 이중부정 → 차단 안 함
                if any(c in stail for c in _CONCESSIVE_TOKENS):
                    continue
                return True
            i = after
    return False


def has_unnegated_strong_negative(sentence):
    """STRONG_NEGATIVE_PHRASES가 직후 negation 없이 등장하면 True.

    배경(실측): "보완이 필요하지 않으며 높은 평가"는 '보완이 필요'가 매칭되나 '하지 않으며'로
    부정되어 칭찬이다. negation을 인식해 euphemistic_negative의 긍→부 오분류를 막는다.
    """
    if not sentence:
        return False
    for phrase in STRONG_NEGATIVE_PHRASES:
        p = sentence.find(phrase)
        while p != -1:
            tail = sentence[p + len(phrase):p + len(phrase) + 6]
            if not any(r in tail for r in _RENEGATION_TOKENS):
                return True
            p = sentence.find(phrase, p + len(phrase))
    return False


# 결함 술어 — 긍정표지와 공존해도 진짜 비판인 부정 술어(batch_20260622_0 부→긍 실측 발굴).
#   고정밀·저trap만 수록. 단축 한글 substring 한계로 trap 항목은 제외:
#     '무관심' = "업**무관심**도/업무관심이"(업무+관심=긍정) 부분문자열 → 제외(긍→부 실측 4건).
#     '태만'(⊂상태만)·'약해'(⊂요약해)·'나태'(⊂거나 태도) → 제외.
#   '소홀'은 부분문자열 trap이 없어 안전(긍정어 중 '소홀' 포함 없음). 같은 "…소홀함" 문장은
#   '무관심' 없이도 '소홀'이 포착(예: "무관심하고 소홀함"). 추가 결함어는 토크나이저 후속.
_DEFICIENCY_PREDICATES = ['소홀']
_DEFICIENCY_NEG_WINDOW = 6


def has_unnegated_deficiency(sentence):
    """결함 술어가 직후 negation 없이 등장하면 True(긍정표지+결함 = 부→긍 차단용).

    negation 인식: "소홀히 하지 않음"·"무관심하지 않다"(부정의 부정=칭찬)는 제외 → 긍→부 보호.
    """
    if not sentence:
        return False
    for word in _DEFICIENCY_PREDICATES:
        p = sentence.find(word)
        while p != -1:
            tail = sentence[p + len(word):p + len(word) + _DEFICIENCY_NEG_WINDOW]
            if not any(neg in tail for neg in ('않', '없', '아니')):
                return True
            p = sentence.find(word, p + len(word))
    return False


# 건설적 필요/요구 — 다면평가 약점 섹션 "[긍정표지]+필요/요구" = "더 ~하면 좋겠다"(부정).
#   batch_2026062x 약점 배치 부→긍 지배 패턴(경청 필요·소통이 필요함·자세가 필요함·책임감 요구됨).
_NEED_NEG_WINDOW = 5    # '필요' 뒤 negation 탐색창(필요하지 않/필요 없 = 불요=긍정 → 제외)
# '필요 [인물/인재/존재…]' = 불가결한 사람(긍정) → 건설적 비판 아님.
#   배경(0630 재감사·PoC): "강원본부에 절대적 필요 인물"이 '필요'로 has_constructive_need=True가 되어
#   positive_rescue를 막던 긍→중 트랩. 직후 토큰이 사람명사면 제외(긍정 보존).
#   ⚠️ '필요 이상'(과도)은 비판("필요이상의 일에 시달려")이라 가드에 넣지 않는다(부→긍 교차 방지, 전수검증).
_NEED_POSITIVE_TAILS = ('인물', '인재', '존재', '인력', '자원')


def has_constructive_need(sentence):
    """'필요'(건설적 비판 술어)가 등장하면 True. 관형형·부정·불필요·불가결은 제외(긍→부 보호).

    포착: "경청 필요"·"소통이 필요함"·"자세가 필요하다"·"향상이 필요"·"요구됨/요구된다".
    제외(긍→부 trap): '필요한 [명사]'(관형=necessary) · '필요하지 않'/'필요 없'(불요=긍정)
                      · '불필요'(앞 글자 불) · '필요 인물/인재/이상'(불가결·과 = 긍정).
    """
    if not sentence:
        return False
    p = sentence.find('필요')
    while p != -1:
        a1 = sentence[p + 2:p + 3]
        window = sentence[p + 2:p + 2 + _NEED_NEG_WINDOW]
        before = sentence[max(0, p - 1):p]
        tail = sentence[p + 2:p + 2 + 6].lstrip()         # '필요' 직후(선행 공백 제거) 토큰
        if before == '불':
            pass                                          # 불필요 → 제외
        elif a1 == '한':
            pass                                          # 필요한 [명사] = 관형(necessary) → 제외
        elif any(neg in window for neg in ('없', '않', '아니')):
            pass                                          # 필요 없/필요하지 않 = 불요(긍정) → 제외
        elif any(tail.startswith(t) for t in _NEED_POSITIVE_TAILS):
            pass                                          # 필요 인물/인재 = 불가결(긍정) → 제외
        else:
            return True                                   # 필요/필요함/필요하다/X 필요 = 건설적 비판
        p = sentence.find('필요', p + 2)
    # 요구 수동형(요구됨/요구된다/요구되…)만 — 'X 요구' bare는 "고객 요구 반영"(긍정) trap이라 제외
    if any(m in sentence for m in ('요구됨', '요구된다', '요구되며', '요구되고', '요구되어')):
        return True
    return False


# 개선요청/곤란 프레이밍 — 긍정·역량 표지가 단점 맥락(개선 바람·요함/요망·보완요청·곤란)에 놓일 때
#   positive_rescue의 부→긍 오구제 차단. `23_단점.csv`(505,011행) 적대검증 발굴
#   (부→긍 11,039 중 클리어 프레이밍, has_constructive_need('필요'/'요구됨')의 자매 게이트).
#   trap 회피(긍↔부 양방향 0): 주어의존 모호어('별로'="보완점 별로 없음"↔"열의 별로 없음")·
#   과잉어('너무/과한'="너무 우수함"=장점 칭찬)는 제외 → 필드맥락/파서 트랙.
_WISH_FORMS = ['했으면', '하였으면', '하면 좋', '으면 좋', '길 바', '기 바', '하길', '했음 한',
               '하였음 한', '했음 좋', '하시길', '해주길', '해줬으면', '해주었으면',
               '면 좋겠', '였으면', '으면 합', '면 합니', '면 됩', '면 함']
_IMPROVE_REQ_VERBS = ['하면', '해야', '하길', '했으면', '하였으면', '필요', '요함', '요망',
                      '바람', '바랍', '하여야', '할 필요']
# '어려움' 직후에 이들이 오면 곤란 호소가 아니라 *남의* 어려움을 돕는 긍정 서술 → 제외.
#   '해결/해소'(타동 해결)·'도와/도움/살피/살펴/나서/앞장'(조력)·'지나치'(지나치지 않음=세심).
#   배경(0630 전수검증): "동료의 어려움을 해결해 주십니다"類 긍정이 중립화되던 긍→중 트랩 차단.
_DIFFICULTY_OK = ('극복', '없', '헤', '이겨', '이김', '풀', '해소', '해결', '극', '않',
                  '도와', '도움', '살피', '살펴', '나서', '앞장', '지나치')


def _has_improvement_request_core(sentence):
    """개선요청 고정밀 프레이밍(희망형·요함/요망·보완|개선 요청). 곤란(어려움) 제외.

    중립화 분기(improvement_request_neutral) 전용 — 어려움은 "남의 어려움을 돕는다"(긍정)
    트랩이 잦아 중립화 트리거에서 분리한다(positive_rescue용 has_improvement_request는 곤란 포함 보존).
    """
    if not sentence:
        return False
    # 1) 개선 바람(희망형) — "더 ~했으면"·"~하길 바람"·"~면 좋겠"
    if any(w in sentence for w in _WISH_FORMS):
        return True
    # 2) 요망(trap 없음) / 요함('중요함'·'필요함' substring 제외)
    if '요망' in sentence:
        return True
    i = sentence.find('요함')
    while i != -1:
        if sentence[max(0, i - 1):i] not in ('중', '필'):
            return True
        i = sentence.find('요함', i + 2)
    # 3) 보완/개선 '요청'(직후 창에 negation 있으면 제외 = "보완점 없음" 중립 보존)
    for w in ('보완', '개선'):
        j = sentence.find(w)
        while j != -1:
            tail = sentence[j + len(w):j + len(w) + 8]
            if (not any(neg in tail for neg in ('없', '않', '아니'))
                    and any(v in tail for v in _IMPROVE_REQ_VERBS)):
                return True
            j = sentence.find(w, j + len(w))
    return False


def _has_difficulty_complaint(sentence):
    """곤란(어려움/어렵) 호소면 True. 극복/조력 동사 근접 시 제외(남을 돕는 긍정)."""
    if not sentence:
        return False
    for w in ('어려움', '어렵'):
        k = sentence.find(w)
        while k != -1:
            tail = sentence[k + len(w):k + len(w) + 7]
            if not any(g in tail for g in _DIFFICULTY_OK):
                return True
            k = sentence.find(w, k + len(w))
    return False


def has_improvement_request(sentence):
    """개선 바람/요함·요망/보완요청/곤란 프레이밍이면 True(긍정표지+단점맥락 → 부→긍 차단).

    negation·극복 trap은 가드해 긍→부(양방향 핵심가치)를 만들지 않는다. 기존 동작 보존:
    고정밀 개선요청(core) + 곤란(어려움) 합집합. positive_rescue 게이트 전용 진입점.
    포착: "더 ~했으면"·"~하길 바람"·"~면 좋겠"·"신속성 요함"·"열의 요망"·"소통 보완해야"·"협업에 어려움".
    """
    return _has_improvement_request_core(sentence) or _has_difficulty_complaint(sentence)


# 약점-없음 선언 — "보완점 없음/단점 없습니다" 等. 약점 섹션에 "없음"이 흔해 KoTE가 '보완/단점'만
#   보고 부정 오분류하던 지배 패턴(batch 실측: 부정 라벨의 23.8%). 비평가성 = 중립(긍↔부 무관).
_NOWEAK_NOUNS = ['보완', '단점', '개선점', '개선 사항', '개선사항', '보완점', '보완 점',
                 '보완사항', '보완 사항', '보완필요', '문제점', '특이사항', '특이 사항',
                 '결점', '지적사항', '지적 사항', '미흡한 점', '아쉬운 점', '부족한 점']
_NOWEAK_NEG = ('없', '않', '아니')
_NOWEAK_WINDOW = 8
# 혼합 판정용 결핍어 — negation 인식으로 체크(약점명사 '보완 필요'와 겹치는 NEGATIVE_IMPLYING_WORDS
#   평면 매칭은 "보완 필요점 없음"을 오차단하므로 사용 불가 → 전용 negation-aware 게이트).
_NOWEAK_OTHER_NEG = ('부족', '미흡', '결여', '부재', '아쉽', '여지')


def _has_unnegated_other_negative(sentence):
    """결핍어가 직후 창에 negation 없이 등장하면 True(혼합문 판별용)."""
    for w in _NOWEAK_OTHER_NEG:
        i = sentence.find(w)
        while i != -1:
            tail = sentence[i + len(w):i + len(w) + 5]
            if not any(n in tail for n in ('없', '않', '아니')):
                return True
            i = sentence.find(w, i + len(w))
    return False


def is_no_weakness_declaration(sentence):
    """약점 명사(보완/단점/개선점…) 직후 창에 negation이 와 '약점 없음'을 선언하면 True → 중립.

    다른 진짜 부정 신호(결함술어·건설적필요·강조부정·미부정 결핍어)가 섞이면 혼합이므로
    False(부정 보존). 중립만 산출하므로 긍↔부 오분류를 만들 수 없다.
    """
    if not sentence:
        return False
    # 혼합("보완점은 없으나 소통이 부족") → 진짜 부정 우선, 약점선언 미발동
    # NOTE: has_improvement_request 는 여기 넣지 않는다. 그 게이트는 후행 '없음'을 negation-aware로
    #   완전 처리하지 못해("개선 및 보완필요점 없음") 약점-없음 선언을 부정으로 밀 수 있다.
    #   positive_rescue 게이트에서만 사용하고, 약점-없음 중립화는 기존 negation-aware 로직에 맡긴다.
    if (has_unnegated_deficiency(sentence) or has_constructive_need(sentence)
            or has_unnegated_strong_negative(sentence)
            or _has_unnegated_other_negative(sentence)):
        return False
    for noun in _NOWEAK_NOUNS:
        i = sentence.find(noun)
        while i != -1:
            window = sentence[i + len(noun):i + len(noun) + _NOWEAK_WINDOW]
            if any(neg in window for neg in _NOWEAK_NEG):
                return True
            i = sentence.find(noun, i + len(noun))
    return False


def _sentence_sentiment_override_explain(pos, neg, sentence, is_last, total_sentences,
                                          threshold=0.20, weight=2.0, neutral=0.0):
    """sentence_sentiment_override와 동일한 분기를 수행하되 (score, rule_id)를 반환.

    규칙 마이닝/정제 패스에서 "어떤 규칙이 발동했는가"를 기록하기 위한 설명 가능 버전.
    분기 조건·반환 점수는 sentence_sentiment_override와 완전히 동일해야 한다(동작 보존).
    """
    confidence = abs(pos - neg)
    strength = pos + neg
    has_contrast = has_contrastive(sentence)

    # 긍정 구제(positive_rescue): 인사평가 긍정 표지가 명확하고 부정 신호가 없으면 긍정 상향.
    # neutral_dominant/rule3/rule4보다 앞서 평가해, 긍정이 중립·부정으로 강등되는 것을 사전 차단.
    # 핵심 가치 보호 게이트: 반전 표지 없음 + 완곡부정 구문/부정 암시어/도메인 부정문맥어 없음 + KoTE neg 낮음.
    #   → true-negative(반전·강요·완곡부정 등)는 게이트에서 모두 걸러져 긍정으로 뒤집히지 않는다.
    if (has_positive_implying_phrase(sentence)
            and not has_contrast
            and not has_negative_implying_words(sentence)
            and not positive_marker_directly_negated(sentence)
            and not has_unnegated_deficiency(sentence)
            and not has_constructive_need(sentence)
            and not has_improvement_request(sentence)
            and not any(ph in sentence for ph in STRONG_NEGATIVE_PHRASES)
            and not any(nc in sentence for nc in NEGATIVE_CONTEXT_FOR_RESCUE)
            and neg < 0.85):
        return (strength if strength > 1e-6 else 0.3), 'positive_rescue'

    # negation 칭찬 구제(negation_praise): "부정어의 부정 = 칭찬"을 긍정 상향.
    #   예) '강압적이지 않음', '고압적이지 않습니다', '권위의식이 없음', '잔소리를 안한다'.
    #   이들은 부정표면어(강압/고압/권위의식/잔소리)를 가져 positive_rescue의
    #   NEGATIVE_CONTEXT_FOR_RESCUE 게이트에서 막혀 중립에 머무르고, is_last면
    #   euphemistic_negative로 부정 반전될 위험까지 있다. is_negation_praise는
    #   negation 없는 진짜 부정표지가 하나라도 있으면 False → 진짜 부정(강요·수직적)은
    #   이 분기에 들어오지 못하므로 긍↔부 오분류가 발생하지 않는다(중립→긍정만 상향).
    #   neutral_dominant·euphemistic_negative보다 앞서 평가해 부정 반전을 차단한다.
    if is_negation_praise(sentence):
        return (strength if strength > 1e-6 else 0.3), 'negation_praise'

    # KoTE neutral 우세 또는 근접 우세(±0.05) → 중립 강제
    if neutral > pos and neutral >= neg - 0.05:
        return 0.0, 'neutral_dominant'

    # 무응답 중립화(no_response_neutral): "잘 모르겠습니다"·"뵌 적 없어 모름"·"내용없음"·낙서 등
    #   평가를 하지 않은 비평가 문장이 rule3/rule4에서 부정으로 강등되는 것을 중립으로 교정.
    #   neutral_dominant 뒤·euphemistic_negative/rule3 앞에 두어, 이미 중립인 낙서(neutral_dominant)는
    #   그대로 두고(회귀 영향 0) 부정으로 떨어질 비평가 문장만 중립으로 가로챈다.
    #   is_no_response는 진짜 부정 신호(부정암시어/완곡부정)가 섞이면 False → 부→중 강등 없음
    #   (비평가는 긍정도 부정도 아니므로 중립화는 긍↔부 오분류를 만들지 않는다).
    if is_no_response(sentence):
        return 0.0, 'no_response_neutral'

    # 약점-없음 선언 중립화(no_weakness_neutral): "보완점 없음"·"단점 없습니다" 等.
    #   KoTE가 '보완/단점'만 보고 부정 오분류하던 비평가성 선언(batch 실측 부정의 23.8%).
    #   KoTE 부정 우세(neg>=pos)일 때만 — 긍정문("보완 필요없이 높은 평가")은 미발동(긍정 보존).
    #   다른 진짜 부정이 섞이면 미발동(혼합은 부정 보존) → 중립만 산출, 긍↔부 안전.
    #   추가(23년_장점 실측): 저신뢰(|pos-neg|<threshold)면 pos>neg여도 발동 — "같이 근무해보니
    #   보완할점 없음"(pos 0.5/neg 0.44)류가 rule3_last_low로 긍→부 뒤집히던 것을 중립으로 가로챈다.
    #   고신뢰 긍정("보완 필요없이 높은 평가")은 confidence가 커 미발동 → 긍정 보존(긍↔부 0).
    if (neg >= pos or confidence < threshold) and is_no_weakness_declaration(sentence):
        return 0.0, 'no_weakness_neutral'

    # 중립 규칙: 중립 문장이 부정으로 극단 오분류되는 케이스 방지
    # 중립→긍정은 허용이므로 긍정 방향 오분류는 교정하지 않음
    if any(word in sentence for word in NEUTRAL_KEYWORDS):
        if confidence > 0.9 and (pos > 0.9 or neg > 0.9):
            return 0.0, 'neutral_keyword'

    # 완곡 부정 구문 규칙: KoTE가 긍정으로 오분류하는 인사평가 완곡 표현 → 부정 반전
    # NEGATIVE_IMPLYING_WORDS(단어 단위) 대신 구문 단위 정밀 매칭으로 오탐 방지.
    # has_contrast인 경우 규칙1/2에서 방향을 판단하므로 제외.
    if (is_last and pos > neg and not has_contrast and strength > 0.5
            and has_unnegated_strong_negative(sentence)):
        return -strength, 'euphemistic_negative'

    # 개선요청/결핍 프레이밍 중립화(improvement_request_neutral):
    #   결핍·개선요청 표지("보완 필요"·"소통 부족"·"개선 바람")가 있는데 KoTE가 긍정 우세로 줘
    #   rule4_default가 그대로 긍정 통과하던 부→긍 누수를 중립으로 가로챈다.
    #   배경(batch_20260624 단점필드 실측·0630 PoC): 단점필드 30.8% positive, 그중 78%가
    #   rule4_default 무override = 구조적 구멍. 기존 개선요청 가드는 positive_rescue 전용이라 못 봄.
    #   안전성: ① pos>neg(긍정으로 갈 것)일 때만 발동 — neg≥pos 진짜 부정은 rule3/rule4가 처리.
    #          ② 부정이 아니라 *중립*으로만 강등 → 긍↔부 0 보존(부→긍 위반 제거, 긍→부 미발생).
    #          ③ has_improvement_request/has_constructive_need/has_unnegated_deficiency의 내장 가드
    #             (없/극복/양보/관형 '필요한'/'필요 인물·이상')가 긍정 trap을 제외 → 긍→중 최소화.
    #          ④ has_contrast(반전)는 rule1/2가 방향 판단 → 제외.
    if (pos > neg and not has_contrast
            and (_has_improvement_request_core(sentence)
                 or has_constructive_need(sentence)
                 or has_unnegated_deficiency(sentence))):
        return 0.0, 'improvement_request_neutral'

    # 규칙 1: 반전 + 마지막 + 저신뢰도 + strength>0.5 → 모델 방향 기반 가중
    if (has_contrast and is_last and confidence < threshold
            and strength > 0.5):
        return (pos - neg) * weight, 'rule1_contrast_lastlow'

    # 규칙 2: 반전 + 마지막 + 고신뢰도 → 모델 방향 기반 가중
    if (has_contrast and is_last and confidence >= threshold):
        return (pos - neg) * weight, 'rule2_contrast_lasthigh'

    # 규칙 3: 반전 없이 마지막 + 저신뢰도 + strength>0.5 → 부정 전환
    if (is_last and confidence < threshold and strength > 0.5):
        return -strength, 'rule3_last_low'

    # 규칙 4: 기본
    return pos - neg, 'rule4_default'


def sentence_sentiment_override(pos, neg, sentence, is_last, total_sentences,
                                  threshold=0.20, weight=2.0, neutral=0.0):
    """문장별 독립 감정 교정.

    핵심 가치: 긍정↔부정 오분류만 방지. 중립→긍정은 허용.

    규칙:
      긍정구제) POSITIVE_IMPLYING_PHRASES + not has_contrast + 부정암시어/완곡부정/부정문맥어 없음 + neg<0.85
                → 긍정 상향 (KoTE 긍정 미검출 보강; neg/어휘 게이트로 true-negative 반전 차단)
      negation칭찬) is_negation_praise(부정어의 부정, 진짜 부정 0) → 긍정 상향 (중립→긍정만, 긍↔부 안전)
      무응답) is_no_response(평가불가/내용없음/낙서, 진짜 부정 0) → 중립화 (중립→부정 오분류만 제거)
      중립) NEUTRAL_KEYWORDS + confidence>0.9 + pos/neg>0.9 → 중립 강제 (중립→부정 극단 케이스 방지)
      완곡부정) is_last + not has_contrast + KoTE 긍정 + STRONG_NEGATIVE_PHRASES → 부정 반전
      1) has_contrast + is_last + 저신뢰(confidence<threshold) + strength>0.5 → 모델 방향 기반 가중
      2) has_contrast + is_last + 고신뢰(confidence>=threshold) → 모델 방향 기반 가중
      3) is_last + 저신뢰(confidence<threshold) + strength>0.5 → 부정 전환
      4) 기본 → 모델 판단 그대로

    ※ 분기 로직은 _sentence_sentiment_override_explain에 단일 정의되며, 본 함수는
      기존 호출처 호환을 위해 score(float)만 반환한다.
    """
    score, _ = _sentence_sentiment_override_explain(
        pos, neg, sentence, is_last, total_sentences,
        threshold=threshold, weight=weight, neutral=neutral
    )
    return score


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
        logger.warning("input_id=%s mgr=%s", input_id, bool(pseudo_mgr), extra={'request_id': '', 'stage': 'PSEUDO_RESOLVE'})
        return input_id
    data = pseudo_mgr._load_mappings()
    resolved = data['real_to_pseudo'].get(str(input_id), input_id)
    if resolved == input_id:
        logger.warning("mapping_not_found returned_as_is=%s", _mask_real_id(str(input_id)), extra={'request_id': '', 'stage': 'PSEUDO_RESOLVE'})
    else:
        logger.debug("resolved_to_pseudo=%s", resolved, extra={'request_id': '', 'stage': 'PSEUDO_RESOLVE'})
    return resolved


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


def _enrich_with_real_ids(results, pseudonym_fields, enrich=False, request_id=''):
    if not enrich:
        return results
    logger.info("enrich=%s fields=%s", enrich, pseudonym_fields, extra={'request_id': request_id, 'stage': 'ENRICH'})
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
                real = mgr.get_real_id(ev[field])
                if real and real != ev[field]:
                    ev[f"{field}_real"] = real
                    logger.debug("restored field=%s from=%s to=%s", field, ev[field], _mask_real_id(real), extra={'request_id': request_id, 'stage': 'ENRICH'})
                else:
                    logger.warning("restore_failed field=%s pseudo=%s", field, ev[field], extra={'request_id': request_id, 'stage': 'ENRICH'})
            result_key = RESULT_LEVEL_MAP.get(field)
            if result_key and result_key in item and isinstance(item[result_key], str):
                real = mgr.get_real_id(item[result_key])
                if real and real != item[result_key]:
                    item[f"{result_key}_real"] = real
                    logger.debug("restored field=%s from=%s to=%s", result_key, item[result_key], _mask_real_id(real), extra={'request_id': request_id, 'stage': 'ENRICH'})
                else:
                    logger.warning("restore_failed field=%s pseudo=%s", result_key, item[result_key], extra={'request_id': request_id, 'stage': 'ENRICH'})
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
    # 날짜 modifier(year/month)는 다양한 입력 형식(int 2025, '20250601', '250105' 등)을
    # 표준형(YYYY[-MM[-DD]])으로 정규화한 뒤 추출한다. 과거엔 'YYYY-MM-DD' 문자열만 가정해
    # 정수 연도·구분자 없는 형식에서 None을 반환, row 필터가 전건 탈락하던 버그가 있었다.
    if modifier in ('year', 'month'):
        norm = normalize_eval_date(raw_val)
        if not norm:
            return None
        if modifier == 'year':
            return norm[:4] if len(norm) >= 4 else None
        # month
        parts = norm.split('-')
        return parts[1] if len(parts) >= 2 and parts[1] else None
    return raw_val


def _resolve_field_name(raw_field):
    return raw_field.split('__')[0]


def load_batch_summary(batch_path):
    summary_path = os.path.join(batch_path, "tmeta", "batch_summary.json")
    if not os.path.exists(summary_path):
        return None
    with open(summary_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _batch_display_name(processed_data_dir, batch_id):
    """배치 디렉토리의 batch_summary.json에서 표시 명칭을 읽는다."""
    summary_path = os.path.join(processed_data_dir, 'batch', batch_id, "tmeta", "batch_summary.json")
    if os.path.exists(summary_path):
        try:
            with open(summary_path, 'r', encoding='utf-8') as _sf:
                _summary = json.load(_sf)
            return _summary.get('batch_info', {}).get('display_name', '') or ''
        except Exception:
            pass
    return ''


def _load_batch_list(processed_data_dir):
    """배치 목록 로드 — 작업서(batch_work_orders) 레지스트리를 기준으로 출력한다.

    이력은 사용자가 생성한 '배치 작업 ID'를 기준으로 나열한다. 평가 중복 제거
    인덱스(idx_ev_fp: employee_id+fingerprint) 때문에 동일 데이터를 재처리한
    배치는 evaluations에 신규 행이 0건일 수 있으나, 작업서에는 남으므로 이력에서
    사라지지 않는다. 직원/평가 수는 작업서가 기록한 처리 결과(success_count/
    total_rows)를 사용한다. 작업서가 없는 레거시 평가 배치는 evaluations 집계로
    보강한다.
    """
    from src.services.user_data_manager import _get_eval_conn
    conn = _get_eval_conn()
    try:
        wo_rows = conn.execute("""
            SELECT batch_id, success_count, total_rows, created_at
            FROM batch_work_orders
            ORDER BY created_at DESC, id DESC
        """).fetchall()
        ev_rows = conn.execute("""
            SELECT batch_id,
                   COUNT(DISTINCT employee_id) AS employee_count,
                   COUNT(*) AS total_evaluations,
                   MIN(created_at) AS created_at
            FROM evaluations
            WHERE batch_id IS NOT NULL
            GROUP BY batch_id
            ORDER BY MIN(created_at) DESC
        """).fetchall()
    finally:
        conn.close()

    batches = []
    seen = set()
    for row in wo_rows:
        batch_id = row['batch_id']
        seen.add(batch_id)
        batches.append({
            'batch_id': batch_id,
            'path': os.path.join(processed_data_dir, 'batch', batch_id),
            'display_name': _batch_display_name(processed_data_dir, batch_id),
            'created_at': (row['created_at'] or '')[:10],
            'employee_count': row['success_count'] or 0,
            'total_evaluations': row['total_rows'] or 0,
        })

    # 작업서에 없는(레거시) 평가 배치 보강
    for row in ev_rows:
        batch_id = row['batch_id']
        if batch_id in seen:
            continue
        seen.add(batch_id)
        batches.append({
            'batch_id': batch_id,
            'path': os.path.join(processed_data_dir, 'batch', batch_id),
            'display_name': _batch_display_name(processed_data_dir, batch_id),
            'created_at': (row['created_at'] or '')[:10],
            'employee_count': row['employee_count'],
            'total_evaluations': row['total_evaluations'],
        })
    return batches


def _count_batches(processed_data_dir):
    """배치 수 반환 — 작업서 레지스트리와 평가 배치의 합집합(이력 목록과 일치)."""
    from src.services.user_data_manager import _get_eval_conn
    conn = _get_eval_conn()
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT batch_id FROM batch_work_orders
                UNION
                SELECT batch_id FROM evaluations WHERE batch_id IS NOT NULL
            )
        """).fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
    finally:
        conn.close()


def load_all_batches(processed_data_dir=None, request_id=''):
    if processed_data_dir is None:
        processed_data_dir = PROCESSED_DATA_DIR_PATH

    logger.info("", extra={'request_id': request_id, 'stage': 'DB_LOAD_ALL'})

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
            try:
                ev_obj = json.loads(data)
            except json.JSONDecodeError as e:
                logger.error("json_parse_error row=%s error=%s", ev_db_id, e, extra={'request_id': request_id, 'stage': 'DB_LOAD_ALL'})
                continue
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

    logger.info("total_employees=%s total_evals=%s", len(emp_meta), total_evals, extra={'request_id': request_id, 'stage': 'DB_LOAD_ALL'})

    if not emp_meta:
        logger.warning("no_data", extra={'request_id': request_id, 'stage': 'DB_LOAD_ALL'})

    return {
        'batch_info': {
            'total_evaluations': total_evals,
            'unique_employees': len(emp_meta),
            'batch_count': _count_batches(processed_data_dir),
        },
        'employee_results': employee_results,
        'batches': _load_batch_list(processed_data_dir),
    }


def load_batch_history(processed_data_dir=None):
    """이력 화면 전용 경량 로더 — 배치 목록 + 카운트만 반환(평가 본문 미적재).

    이력 조회(/api/perspective/batches)는 batches 목록과 batch_info 카운트만
    사용하므로, load_all_batches()처럼 전 직원 평가를 json.loads로 적재할 필요가
    없다. 1.7만명 규모에서 전체 적재가 수십 초·수 GB를 소모하던 병목을 제거하기
    위해 cheap aggregate COUNT만 수행한다(employee_results 키 없음). 0619_03.
    """
    if processed_data_dir is None:
        processed_data_dir = PROCESSED_DATA_DIR_PATH

    conn = _get_eval_conn()
    try:
        row = conn.execute("""
            SELECT COUNT(DISTINCT e.employee_id) AS uniq,
                   COUNT(*) AS total
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
        """).fetchone()
    finally:
        conn.close()
    uniq = (row[0] if row else 0) or 0
    total = (row[1] if row else 0) or 0

    return {
        'batch_info': {
            'total_evaluations': total,
            'unique_employees': uniq,
            'batch_count': _count_batches(processed_data_dir),
        },
        'batches': _load_batch_list(processed_data_dir),
    }


def load_employee_batch(employee_id, request_id=''):
    """단일 직원의 평가만 담은 unified 형태 dict 반환.

    load_all_batches()와 동일한 반환 구조(employee_results/batch_info/batches)를
    유지하되 employee_results에는 해당 직원 1명만 포함한다. 제출용 저장 경로의
    소비 함수(_get_evaluations_for_employee / _get_employee_metadata /
    build_profanity_summary)는 employee_results를 target_employee_id로 필터링하므로
    1명짜리 dict와 완전 호환된다. 17,000명 전체 적재로 인한 메모리 폭증을 피하기 위함(0619_02).

    input_id는 원본/가명 어느 쪽이든 받아 가명으로 변환 후 DB를 조회한다.
    (DB의 employee_id는 가명 ID이며, target_employee_id 매칭 키도 가명으로 고정 —
    REQ-2606-032/0615_06 회귀 방지.)
    """
    pseudo_mgr = _get_pseudo_mgr()
    logger.info("input_id=%s", _mask_real_id(str(employee_id)) if employee_id else '', extra={'request_id': request_id, 'stage': 'DB_LOAD'})
    resolved_id = _resolve_to_pseudo(employee_id, pseudo_mgr)
    logger.debug("resolved_to_pseudo=%s", resolved_id, extra={'request_id': request_id, 'stage': 'DB_LOAD'})

    conn = _get_eval_conn()
    try:
        rows = conn.execute("""
            SELECT e.employee_id, e.name, e.department, e.position, ev.data, ev.id
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            WHERE e.employee_id = ?
            ORDER BY ev.id
        """, (resolved_id,)).fetchall()
    finally:
        conn.close()

    if not rows:
        logger.warning("no_rows_found employee_id=%s", _mask_real_id(resolved_id), extra={'request_id': request_id, 'stage': 'DB_LOAD'})
        return {'employee_results': [], 'batch_info': {}, 'batches': []}

    name = dept = pos = ''
    evals = []
    for _emp_id, nm, dp, ps, data, ev_db_id in rows:
        name, dept, pos = nm or '', dp or '', ps or ''
        if data:
            try:
                ev_obj = json.loads(data)
            except json.JSONDecodeError as e:
                logger.error("json_parse_error row=%s error=%s", ev_db_id, e, extra={'request_id': request_id, 'stage': 'DB_LOAD'})
                continue
            # evaluation_id는 중복될 수 있으므로 고유한 DB row id를 보정값 키로 사용
            ev_obj['_db_id'] = ev_db_id
            evals.append(ev_obj)

    logger.info("row_count=%s eval_count=%s", len(rows), len(evals), extra={'request_id': request_id, 'stage': 'DB_LOAD'})

    return {
        'batch_info': {'total_evaluations': len(evals), 'unique_employees': 1},
        'employee_results': [{
            'metadata': {
                'target_employee_id': resolved_id,
                'target_employee_name': name,
                'target_employee_department': dept,
                'target_employee_position': pos,
                'evaluations': evals,
            }
        }],
        'batches': [],
    }


def list_all_employee_ids():
    """전 직원(평가 보유) ID 목록만 반환(평가 데이터 미적재). all_employees 일괄 저장용(0619_02).

    전체 unified 적재 없이 ID만 추리기 위한 경량 쿼리.
    """
    conn = _get_eval_conn()
    try:
        rows = conn.execute("""
            SELECT DISTINCT e.employee_id
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            ORDER BY e.employee_id
        """).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


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
            return [(None, 0.0, 0.0, 0.0, 0.0)]
        sentences = [e['sentence'] for e in cache]
        sent_scores_raw = [(e['pos'], e['neg'], e['neutral']) for e in cache]

    total = len(sentences)
    # HR 파인튜닝 감정모델(극성) — 플래그 on이면 문장 배치 추론(O(배치)). 실패 시 None→규칙 폴백.
    model_labels = None
    try:
        from src.config.settings import USE_HR_SENTIMENT_MODEL
        if USE_HR_SENTIMENT_MODEL:
            from src.modules.hr_sentiment import predict_sentiments
            model_labels = predict_sentiments(sentences)
            if model_labels is not None and len(model_labels) != total:
                model_labels = None
    except Exception:
        model_labels = None
    result = []
    for i, (pos, neg, neutral) in enumerate(sent_scores_raw):
        sent = sentences[i]
        is_last = (i == total - 1)
        if model_labels is not None:
            # 파인튜닝 모델 극성 → score(강도는 KoTE |pos-neg| 보존, 중립=0)
            lab = model_labels[i]
            strength = abs(pos - neg) if abs(pos - neg) > 0.01 else 1.0
            original_score = strength if lab == 'positive' else (-strength if lab == 'negative' else 0.0)
        else:
            # 기존 규칙 경로(폴백 포함): KoTE 원점수 + override
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
        result.append((sent, score, pos, neg, neutral))
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
            for sent, score, _, _, _ in sent_scores:
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
        for sent, score, _, _, _ in sent_scores:
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
        for i, (sent, score, pos, neg, neutral) in enumerate(sent_scores):
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
                    'kote_pos': round(pos, 4),
                    'kote_neg': round(neg, 4),
                    'kote_neutral': round(neutral, 4),
                    'override_score': round(score, 4),
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
                    'kote_pos': round(pos, 4),
                    'kote_neg': round(neg, 4),
                    'kote_neutral': round(neutral, 4),
                    'override_score': round(score, 4),
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


def get_matrix_meta_light(employee_id=None, enrich=False, processed_data_dir=None):
    """/meta 전용 경량 메타 빌더 — evaluations의 data blob을 적재하지 않는다.

    X축(row_options)이 실제로 쓰는 값은 batch_id·evaluation_date 둘뿐이며
    (ROW_FIELDS / _extract_row_values 참조), 두 필드는 evaluations 테이블에
    인덱스된 독립 컬럼으로 존재한다(deploy_session_service: evaluation_date,
    batch_id, idx_ev_batch). 따라서 load_all_batches()처럼 전 직원 평가
    1.9만건을 json.loads로 적재할 필요 없이 GROUP BY 집계만으로 동일한
    row_options/employees를 만든다. get_matrix_meta()의 19,000건 json.loads
    병목 제거 — 0619_03 배치 이력 경량화(load_batch_history)의 X축(/meta) 후속.

    반환 구조는 get_matrix_meta()와 동일(키·의미 보존). employees 목록과
    total_evaluations는 기존 get_matrix_meta와 동일하게 전체 기준이며,
    row_options만 employee_id가 주어지면 해당 직원으로 한정한다.
    """
    if processed_data_dir is None:
        processed_data_dir = PROCESSED_DATA_DIR_PATH

    resolved_id = None
    if employee_id:
        resolved_id = _resolve_to_pseudo(employee_id, _get_pseudo_mgr())

    conn = _get_eval_conn()
    try:
        # 1) X축 facet — 평가일자 × 배치 그룹 카운트 (data blob 미적재)
        if resolved_id:
            facet_rows = conn.execute("""
                SELECT evaluation_date, batch_id, COUNT(*) AS c
                FROM evaluations
                WHERE employee_id = ?
                GROUP BY evaluation_date, batch_id
            """, (resolved_id,)).fetchall()
        else:
            facet_rows = conn.execute("""
                SELECT evaluation_date, batch_id, COUNT(*) AS c
                FROM evaluations
                GROUP BY evaluation_date, batch_id
            """).fetchall()

        # 2) 직원 목록 + 평가 건수 (data blob 미적재) — get_matrix_meta와 동일하게 전체 기준
        emp_rows = conn.execute("""
            SELECT e.employee_id, e.name, e.department, e.position, COUNT(ev.id) AS cnt
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            GROUP BY e.employee_id
        """).fetchall()

        total_evals = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
    finally:
        conn.close()

    # facet → ROW_FIELDS 별 카운트 (_extract_row_values / _get_eval_field_value 의미 보존)
    field_counts = {key: {} for key in ROW_FIELDS}

    def _bump(d, k, c):
        d[k] = d.get(k, 0) + c

    for ev_date, batch_id, c in facet_rows:
        date_str = ev_date if ev_date is not None else ''
        # batch_id: _extract_row_values는 ev.get('batch_id', '?')
        _bump(field_counts['batch_id'], batch_id if batch_id is not None else '?', c)
        # evaluation_date(raw): val이 None이 아니면 str(val) 버킷 — 빈 문자열도 포함
        _bump(field_counts['evaluation_date'], str(date_str), c)
        # year: len>=4 → date[:4] (그 외 None → 미집계)
        if isinstance(date_str, str) and len(date_str) >= 4:
            _bump(field_counts['evaluation_date__year'], date_str[:4], c)
        # month: len>=7 & '-' 분할 2개 이상 → parts[1]
        if isinstance(date_str, str) and len(date_str) >= 7:
            parts = date_str.split('-')
            if len(parts) >= 2:
                _bump(field_counts['evaluation_date__month'], parts[1], c)

    row_options = []
    for key, info in ROW_FIELDS.items():
        vals = field_counts[key]
        if vals:
            vals_sorted = sorted(vals.items(), key=lambda x: (-x[1], x[0]))
            row_options.append({
                'field': key,
                'label': info['label'],
                'values': [{'value': v, 'count': c} for v, c in vals_sorted],
            })

    pseudo_mgr = _get_pseudo_mgr() if enrich else None
    employees = []
    for emp_id, name, dept, pos, cnt in emp_rows:
        entry = {
            'employee_id': emp_id,
            'department': dept,
            'position': pos,
            'evaluation_count': cnt,
            'employee_name': name,
        }
        if enrich and pseudo_mgr:
            def _dr(v):
                if not v:
                    return v
                r = pseudo_mgr.get_real_id(str(v))
                return r if r != v else v
            real_id = _dr(emp_id)
            entry['employee_id'] = real_id
            entry['employee_id_real'] = real_id if real_id != emp_id else None
            entry['employee_name'] = _dr(name) if name else None
            entry['department'] = _dr(dept) if dept else dept
            entry['position'] = _dr(pos) if pos else pos
        employees.append(entry)
    employees.sort(key=lambda e: e['employee_id'] or '')

    return {
        'row_options': row_options,
        'col_modes': [{'mode': k, 'label': v['label'], 'type': v['type']} for k, v in COL_MODES.items()],
        'analysis_types': [{'mode': k, 'label': v['label'], 'type': v['type']} for k, v in ANALYSIS_TYPES.items()],
        'employees': employees,
        'position_hierarchy': load_position_hierarchy(),
        'batch_count': _count_batches(processed_data_dir),
        'total_evaluations': total_evals,
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


def generate_perspective_matrix(unified_data, employee_id, row_field, col_mode, analysis_type, options, corrections_map=None, request_id=''):
    logger.info("employee_id=%s rows=%s cols=%s", _mask_real_id(str(employee_id)) if employee_id else '', len(unified_data.get('employee_results', [])), len(COL_MODES), extra={'request_id': request_id, 'stage': 'MATRIX_GEN'})
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

    logger.info("done cell_count=%s", sum(len(v) for v in matrix.values()), extra={'request_id': request_id, 'stage': 'MATRIX_GEN'})
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


def save_to_deploy(unified_data, employee_id, row_field, col_mode, analysis_type, options, request=None, request_id=''):
    # _setup_korean_font()는 호출부(라우트 진입)에서 1회 호출 — 병렬 워커마다 중복 설정 방지(작업4)
    output_mode = options.get('output_mode', 'pseudonym')
    deploy_name_val = options.get('batch_title') or employee_id

    logger.info("employee_id=%s deploy_name=%s", _mask_real_id(str(employee_id)) if employee_id else '', deploy_name_val,
                extra={'request_id': request_id, 'stage': 'DEPLOY_SAVE'})

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
        logger.warning("no_evaluations_for_employee", extra={'request_id': request_id, 'stage': 'DEPLOY_SAVE'})
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
    logger.debug("corrections keys=%s", list(deploy_corrections_map.keys()) if deploy_corrections_map else [],
                 extra={'request_id': request_id, 'stage': 'DEPLOY_SAVE'})

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
            sent_scores_list = _get_sentence_level_scores(doc, corrections=eval_corr, sentence_cache=ev.get('sentence_emotion_cache'))
            # 문장-점수 단일 출처: _get_sentence_level_scores 결과(문장 텍스트 포함)를 직접 순회한다.
            # split_sentences(doc) 재분할 + index 맵 방식은 캐시 순서/재분할이 어긋나면
            # 점수가 다른 문장에 붙어 긍↔부 오분류로 이어질 수 있어 제거(0618_01 §3-A).
            for i, (sent, sent_score, pos, neg, neutral) in enumerate(sent_scores_list):
                if not sent:
                    continue
                text_key = sent[:80]
                if text_key in all_seen:
                    continue
                all_seen.add(text_key)
                confidence = abs(pos - neg)
                base = {'text': sent, 'evaluation_id': eval_id, 'db_id': db_id, 'item_index': item_idx, 'sentence_index': i, 'confidence': confidence, 'batch_id': ev.get('batch_id', ''), 'context': doc,
                        'kote_pos': round(pos, 4), 'kote_neg': round(neg, 4),
                        'kote_neutral': round(neutral, 4), 'override_score': round(sent_score, 4)}
                if sent_score > 0:
                    base['text_html'] = _highlight_words_in_sentence(sent, top_pos, word_scores)
                    pos_details.append({**base, 'sentiment': 'positive', 'score': round(sent_score, 3)})
                elif sent_score < 0:
                    base['text_html'] = _highlight_words_in_sentence(sent, top_neg, word_scores)
                    neg_details.append({**base, 'sentiment': 'negative', 'score': round(sent_score, 3)})
                else:
                    neutral_details.append({**base, 'sentiment': 'neutral', 'score': 0.0})
        return combined_url, positive_url, negative_url, combined_sent, positive_sent, negative_sent, pos_details, neg_details, neutral_details

    filtered_items = _filter_items_by_row(all_items, row_field, row_values)
    if not filtered_items:
        logger.warning("filtered_items_empty row_field=%s row_values=%s", row_field, row_values,
                       extra={'request_id': request_id, 'stage': 'DEPLOY_SAVE'})
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

    if combined_url:
        logger.info("wc_generated type=combined path=%s", combined_url, extra={'request_id': request_id, 'stage': 'DEPLOY_SAVE'})
    else:
        logger.error("wc_failed type=combined", extra={'request_id': request_id, 'stage': 'DEPLOY_SAVE'})

    _append_to_deploy_manifest(result, employee_id, row_field, analysis_type, options)
    logger.info("done combined=%s positive=%s negative=%s", combined_url, positive_url, negative_url,
                extra={'request_id': request_id, 'stage': 'DEPLOY_SAVE'})
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
    num_workers = min(multiprocessing.cpu_count(), 8)
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
        ar = data.get('analysis_results', '')
        if isinstance(ar, (dict, list)):
            ar = json.dumps(ar, ensure_ascii=False)
        elif not ar:
            ar = '{}'

        def _num(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        conn.execute("""
            INSERT OR REPLACE INTO acquired_sentences
                (sentence_text, user_label, model_label, confidence,
                 source_employee_id, source_evaluation_id, source_batch_id,
                 sentence_index, db_id, context,
                 kote_pos, kote_neg, kote_neutral, override_score,
                 source_kind, analysis_results)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['sentence_text'],
            _normalize_acq_label(data.get('user_label')),
            _normalize_acq_label(data.get('model_label')),
            data.get('confidence', 0.0),
            data.get('source_employee_id', ''),
            data.get('source_evaluation_id', ''),
            data.get('source_batch_id', ''),
            data.get('sentence_index', 0),
            data.get('db_id', 0),
            data.get('context', ''),
            _num(data.get('kote_pos')),
            _num(data.get('kote_neg')),
            _num(data.get('kote_neutral')),
            _num(data.get('override_score')),
            str(data.get('source_kind') or ''),
            ar,
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


def delete_acquired_sentences_bulk(ids):
    """선택한 id 목록의 취득 문장을 일괄 삭제. 삭제 건수를 반환."""
    ids = [int(i) for i in (ids or []) if str(i).strip()]
    if not ids:
        return 0
    conn = _get_acq_conn()
    try:
        placeholders = ','.join('?' for _ in ids)
        cur = conn.execute(
            f"DELETE FROM acquired_sentences WHERE id IN ({placeholders})", ids
        )
        conn.commit()
        return cur.rowcount
    except Exception as e:
        logger.error(f"[acquired] bulk delete error: {e}")
        return 0
    finally:
        conn.close()


def delete_acquired_sentences_filtered(mismatch_only=False, label=None,
                                       date_from=None, date_to=None):
    """현재 필터(불일치/라벨/기간)에 해당하는 취득 문장을 전체 삭제. 삭제 건수 반환.

    list_acquired_sentences와 동일한 WHERE 조건을 사용해 화면 필터와 일치시킨다.
    필터가 하나도 없으면 전체 삭제.
    """
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
    conn = _get_acq_conn()
    try:
        cur = conn.execute(f"DELETE FROM acquired_sentences WHERE {where_sql}", params)
        conn.commit()
        return cur.rowcount
    except Exception as e:
        logger.error(f"[acquired] filtered delete error: {e}")
        return 0
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


def refine_acquired_row(row):
    """취득 코퍼스 한 행을 규칙 마이닝용으로 정제(재계산).

    캡처 시 저장된 sentence_text + context + user_label(사람 정답)만으로,
    KoTE 원시 점수 / 보정 전·후 라벨 / 발동 규칙 / 문장 위치를 사후 재현한다.
    배치·원데이터에 의존하지 않으므로 코퍼스 DB와 KoTE만 있으면 어디서든 동작한다.

    Args:
        row (dict): acquired_sentences 한 행 (sentence_text, context, user_label 필수)

    Returns:
        dict: 분석 메타 (CSV 컬럼용)
    """
    from src.modules.emotion_analysis import analyze_emotion

    text = (row.get('sentence_text') or '').strip()
    context = row.get('context') or ''
    truth = row.get('user_label') or ''

    # 1) 문장 위치 확정 — context 재분할 후 텍스트로 매칭(인덱스 드리프트 방지)
    sents = split_sentences(context) if context else []
    idx = None
    for i, s in enumerate(sents):
        if s.strip() == text:
            idx = i
            break
    if idx is None and text:
        for i, s in enumerate(sents):
            if text in s:
                idx = i
                break
    if sents:
        total = len(sents)
        if idx is None:
            # 매칭 실패: 저장된 sentence_index로 fallback
            try:
                idx = int(row.get('sentence_index') or 0)
            except (TypeError, ValueError):
                idx = 0
        is_last = (idx == total - 1)
    else:
        total = 1
        idx = 0
        is_last = True

    # 2) KoTE 원시 점수 재계산
    kote_pos = kote_neg = kote_neutral = 0.0
    try:
        res = analyze_emotion(text)
        sc = (res.get('analysis', {}).get('base_result', {})
                 .get('mapped', {}).get('sentiment_scores', {}))
        kote_pos = sc.get('positive', 0.0) or 0.0
        kote_neg = sc.get('negative', 0.0) or 0.0
        kote_neutral = sc.get('neutral', 0.0) or 0.0
    except Exception as e:
        logger.warning(f"[refine] analyze_emotion 실패 id={row.get('id')}: {e}")

    if kote_pos > kote_neg and kote_pos > kote_neutral:
        raw_model_label = 'positive'
    elif kote_neg > kote_pos and kote_neg > kote_neutral:
        raw_model_label = 'negative'
    else:
        raw_model_label = 'neutral'

    # 3) 보정 규칙 재실행 — 발동 규칙 id 포함
    score, applied_rule = _sentence_sentiment_override_explain(
        kote_pos, kote_neg, text, is_last, total, neutral=kote_neutral
    )
    if score > 0:
        corrected_label = 'positive'
    elif score < 0:
        corrected_label = 'negative'
    else:
        corrected_label = 'neutral'

    # 4) 비교 플래그
    kote_correct = (raw_model_label == truth)
    pipeline_correct = (corrected_label == truth)
    return {
        'kote_pos': round(kote_pos, 4),
        'kote_neg': round(kote_neg, 4),
        'kote_neutral': round(kote_neutral, 4),
        'raw_model_label': raw_model_label,
        'applied_rule': applied_rule,
        'corrected_label': corrected_label,
        'override_score': round(score, 4),
        'is_last': is_last,
        'total_sentences': total,
        'kote_vs_truth': 'correct' if kote_correct else 'wrong',
        'pipeline_vs_truth': 'correct' if pipeline_correct else 'wrong',
        'rule_helped': (not kote_correct) and pipeline_correct,
        'rule_hurt': kote_correct and (not pipeline_correct),
    }


def export_acquired_sentences_refined_csv(mismatch_only=False):
    """취득 코퍼스를 정제(KoTE 재계산 + 규칙 재현)하여 마이닝용 CSV로 내보낸다."""
    import csv, io
    data = list_acquired_sentences(page=1, per_page=999999, mismatch_only=mismatch_only)
    output = io.StringIO()
    # Excel 한글 깨짐 방지용 BOM
    output.write('﻿')
    writer = csv.writer(output)
    writer.writerow([
        'id', 'sentence_text', 'user_label',
        'kote_pos', 'kote_neg', 'kote_neutral', 'raw_model_label',
        'applied_rule', 'corrected_label', 'override_score',
        'kote_vs_truth', 'pipeline_vs_truth', 'rule_helped', 'rule_hurt',
        'is_last', 'total_sentences',
        'model_label_at_capture', 'confidence_at_capture',
        'source_employee_id', 'source_evaluation_id', 'source_batch_id', 'sentence_index',
        'context', 'created_at',
    ])
    for item in data['items']:
        r = refine_acquired_row(item)
        writer.writerow([
            item['id'], item['sentence_text'], item['user_label'],
            r['kote_pos'], r['kote_neg'], r['kote_neutral'], r['raw_model_label'],
            r['applied_rule'], r['corrected_label'], r['override_score'],
            r['kote_vs_truth'], r['pipeline_vs_truth'], r['rule_helped'], r['rule_hurt'],
            r['is_last'], r['total_sentences'],
            item.get('model_label'), item.get('confidence'),
            item['source_employee_id'], item['source_evaluation_id'],
            item['source_batch_id'], item['sentence_index'],
            item['context'], item['created_at'],
        ])
    return output.getvalue()


# 업로드(import) 라벨 정규화 — 한글/영문 모두 수용, 스키마 CHECK 위반 방지
_ACQ_LABEL_MAP = {
    'positive': 'positive', 'negative': 'negative', 'neutral': 'neutral',
    'pos': 'positive', 'neg': 'negative', 'neu': 'neutral',
    '긍정': 'positive', '부정': 'negative', '중립': 'neutral',
}


def _normalize_acq_label(value, default='neutral'):
    """user/model 라벨을 positive/negative/neutral로 정규화. 미지정/미인식은 default."""
    raw = (value or '').strip()
    if not raw:
        return default
    return _ACQ_LABEL_MAP.get(raw, _ACQ_LABEL_MAP.get(raw.lower(), default))


def _parse_acq_import_rows(csv_text):
    """기본/정제 CSV 텍스트를 acquired_sentences 적재용 dict 목록으로 파싱(순수함수).

    DB·KoTE에 의존하지 않으므로 단위 테스트 가능. 헤더 기반 컬럼 매핑이며
    sentence_text가 필수, user_label은 선택(없으면 neutral)이다.

    Returns:
        (rows, errors): rows=적재용 dict 목록, errors=무시/경고 메시지 목록
    """
    import csv, io
    text = (csv_text or '').lstrip('﻿')
    if not text.strip():
        return [], ['빈 파일']
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or 'sentence_text' not in reader.fieldnames:
        return [], ['필수 컬럼 sentence_text 가 없습니다']

    rows, errors = [], []
    for line_no, raw in enumerate(reader, start=2):  # 2 = 헤더 다음 줄
        text_val = (raw.get('sentence_text') or '').strip()
        if not text_val:
            errors.append(f"{line_no}행: sentence_text 비어있음 — 건너뜀")
            continue
        user_label = _normalize_acq_label(raw.get('user_label'))
        model_label = _normalize_acq_label(raw.get('model_label'), default=user_label)
        try:
            confidence = float(raw.get('confidence') or raw.get('confidence_at_capture') or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        try:
            sent_idx = int(float(raw.get('sentence_index') or 0))
        except (TypeError, ValueError):
            sent_idx = 0
        rows.append({
            'sentence_text': text_val,
            'user_label': user_label,
            'model_label': model_label,
            'confidence': confidence,
            'source_employee_id': (raw.get('source_employee_id') or '').strip(),
            'source_evaluation_id': (raw.get('source_evaluation_id') or '').strip(),
            'source_batch_id': (raw.get('source_batch_id') or '').strip(),
            'sentence_index': sent_idx,
            'context': (raw.get('context') or '').strip(),
        })
    return rows, errors


def import_acquired_sentences_csv(csv_text, overwrite=False):
    """기본/정제 CSV를 acquired_sentences에 업로드(적재).

    dev 검증용 데이터 반입 경로. 배치/원데이터·KoTE 불요(기본 컬럼만 적재).
    중복(UNIQUE: sentence_text+source_evaluation_id+sentence_index)은
    overwrite=False면 건너뛰고(INSERT OR IGNORE), True면 덮어쓴다(INSERT OR REPLACE).

    Returns: {'inserted': n, 'skipped': n, 'errors': [..]}
    """
    rows, errors = _parse_acq_import_rows(csv_text)
    if not rows:
        return {'inserted': 0, 'skipped': 0, 'errors': errors}

    verb = "INSERT OR REPLACE" if overwrite else "INSERT OR IGNORE"
    inserted = skipped = 0
    conn = _get_acq_conn()
    try:
        for r in rows:
            cur = conn.execute(f"""
                {verb} INTO acquired_sentences
                    (sentence_text, user_label, model_label, confidence,
                     source_employee_id, source_evaluation_id, source_batch_id,
                     sentence_index, db_id, context)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r['sentence_text'], r['user_label'], r['model_label'], r['confidence'],
                r['source_employee_id'], r['source_evaluation_id'], r['source_batch_id'],
                r['sentence_index'], 0, r['context'],
            ))
            if cur.rowcount and cur.rowcount > 0:
                inserted += 1
            else:
                skipped += 1  # 중복으로 무시됨
        conn.commit()
    except Exception as e:
        logger.error(f"[acquired] import error: {e}")
        errors.append(f"적재 중 오류: {e}")
    finally:
        conn.close()
    return {'inserted': inserted, 'skipped': skipped, 'errors': errors}


def save_acquired_sentences_bulk(items, overwrite=False):
    """집단 분석/제출용 배포 결과 문장을 acquired_sentences에 일괄 적재.

    items: [{sentence_text(필수), user_label, model_label, confidence,
             source_employee_id, source_evaluation_id, source_batch_id,
             sentence_index, db_id, context,
             kote_pos, kote_neg, kote_neutral, override_score,
             source_kind, analysis_results(dict|str)}, ...]
    분류 시점 KoTE 값(kote_*·override_score)을 함께 적재 → KoTE 재실행 불요.
    중복(UNIQUE: sentence_text+source_evaluation_id+sentence_index)은
    overwrite=False면 건너뛰고(INSERT OR IGNORE), True면 덮어쓴다(INSERT OR REPLACE).

    Returns: {'inserted': n, 'skipped': n, 'errors': [..]}
    """
    if not items or not isinstance(items, list):
        return {'inserted': 0, 'skipped': 0, 'errors': ['이동할 문장이 없습니다.']}

    verb = "INSERT OR REPLACE" if overwrite else "INSERT OR IGNORE"
    inserted = skipped = 0
    errors = []

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    conn = _get_acq_conn()
    try:
        for idx, it in enumerate(items):
            text = (it.get('sentence_text') or '').strip()
            if not text:
                errors.append(f"{idx+1}번째: sentence_text 비어있음")
                continue
            ar = it.get('analysis_results', '')
            if isinstance(ar, (dict, list)):
                ar = json.dumps(ar, ensure_ascii=False)
            elif not ar:
                ar = '{}'
            try:
                cur = conn.execute(f"""
                    {verb} INTO acquired_sentences
                        (sentence_text, user_label, model_label, confidence,
                         source_employee_id, source_evaluation_id, source_batch_id,
                         sentence_index, db_id, context,
                         kote_pos, kote_neg, kote_neutral, override_score,
                         source_kind, analysis_results)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    text,
                    _normalize_acq_label(it.get('user_label')),
                    _normalize_acq_label(it.get('model_label')),
                    _num(it.get('confidence')) or 0.0,
                    str(it.get('source_employee_id') or ''),
                    str(it.get('source_evaluation_id') or ''),
                    str(it.get('source_batch_id') or ''),
                    int(_num(it.get('sentence_index')) or 0),
                    int(_num(it.get('db_id')) or 0),
                    str(it.get('context') or ''),
                    _num(it.get('kote_pos')),
                    _num(it.get('kote_neg')),
                    _num(it.get('kote_neutral')),
                    _num(it.get('override_score')),
                    str(it.get('source_kind') or ''),
                    ar,
                ))
                if cur.rowcount and cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1  # 중복으로 무시됨
            except Exception as e:
                errors.append(f"{idx+1}번째 적재 오류: {e}")
        conn.commit()
    except Exception as e:
        logger.error(f"[acquired] bulk save error: {e}")
        errors.append(f"일괄 적재 중 오류: {e}")
    finally:
        conn.close()
    return {'inserted': inserted, 'skipped': skipped, 'errors': errors}
