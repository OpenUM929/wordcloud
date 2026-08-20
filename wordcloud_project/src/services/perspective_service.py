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
from utils.perf import perf_span  # 20_09: 구간 소요시간 계측(로그만, 동작 불변)
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
        # -(으)나 계열 (역접): "뛰어나나", "부족하나", "소극적이나". '이나'는 양보('초임차장이나
        #   뛰어남')를 지켜 positive_rescue/rule2가 긍정 보존하므로 전역에선 유지. 단 개선요청
        #   차단용에선 제외(_IMPROVE_BLOCK_CONTRAST) — "소통이나 공감능력 필요"의 명사나열 오인 교정(0703).
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
# 개선요청 부정화 차단 전용 대조어(0703) — '이나'(명사 나열=or, "소통이나 공감능력 필요") 제외.
#   '이나'는 양보('초임차장이나 뛰어남')로 긍정 보존해야 해 전역 대조엔 남기되, 개선요청이
#   '이나' 하나 때문에 중립화되지 않도록 이 목록으로만 차단 여부를 판단한다.
_IMPROVE_BLOCK_CONTRAST = tuple(m for m in ALL_CONTRASTIVE if m != '이나')


def _has_improve_blocking_contrast(sentence):
    """개선요청 부정화를 막아야 할 '진짜' 대조어가 있으면 True('이나' 단독 나열은 불차단)."""
    return bool(sentence) and any(m in sentence for m in _IMPROVE_BLOCK_CONTRAST)

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
    # 0702_03 시도·폐기: "배울 점이 많음"(칭찬) 위해 '배울' 추가했으나 "배울 점이 없는 사람"(부정)에서
    #   positive_rescue의 direct-negation 게이트가 원거리 '없'을 못 잡아 부→긍 유발 → revert.
    #   "보완 필요한 부분보다 배울점이 더 많음"류 비교급 칭찬은 파인튜닝 몫(KoTE 부정+비교구조 규칙불가).
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
_POS_SUFFIX_NEG_WINDOW = 14  # 0709: 8→14 — "협업[능력이 뛰어나]지 않고"처럼 명사표지와 '지 않' 사이
                             #   어간이 긴 부정 칭찬 128건이 창 밖이라 구제되던 것 차단(A/B 실측 채택)


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
                if tail.startswith('도록'):
                    continue  # 목적형 부정("~않도록 배려")=칭찬 → 차단하지 않음(0709)
                return True
            # 접미 부정형 '~지 않/~지 못/~지 아니'(예: "열성적이지 않습니다", "우수하지 못함").
            #   window-3 직접 negator로는 표지와 '않' 사이 어간('적이지')이 끼어 놓친다.
            #   넓은 창에서 '지 않/지 못/지 아니'를 잡되, 재부정·양보는 제외(긍→부 안전).
            sfx = sentence[after:after + _POS_SUFFIX_NEG_WINDOW]
            for snt in _POS_SUFFIX_NEGATORS:
                k = sfx.find(snt)
                if k == -1:
                    continue
                # 꼬리는 원문 기준으로 읽는다 — 창(sfx) 끝에 걸친 '지 않[도록…]'의 후속 확인 누락 방지(0709)
                stail = sentence[after + k + len(snt):after + k + len(snt) + 5]
                if any(r in stail for r in _RENEGATION_TOKENS):
                    continue  # "않지 않" 류 이중부정 → 차단 안 함
                if any(c in stail for c in _CONCESSIVE_TOKENS):
                    continue
                if stail.startswith('도록'):
                    continue  # 목적형 부정("불편해하지 않도록 배려")=칭찬 → 차단 안 함(0709 A/B)
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
_NEED_NEG_WINDOW = 8    # '필요' 뒤 negation 탐색창(필요하지 않/필요 없 = 불요=긍정 → 제외)
# 0702: 5→8. "보완 필요점 딱히 없습니다"처럼 '필요'와 부정 '없' 사이에 부사('딱히')·명사꼬리('점')가
#   끼면 5자 창을 벗어나 '필요'를 건설적필요로 오판 → 무결점 선언이 improvement_request_neg(부)로
#   새던 것을 교정. 확대는 '불요(必要없음)=중립/긍정' 인식을 넓혀 부→중 방향이라 긍↔부 안전.
# '필요 [인물/인재/존재…]' = 불가결한 사람(긍정) → 건설적 비판 아님.
#   배경(0630 재감사·PoC): "강원본부에 절대적 필요 인물"이 '필요'로 has_constructive_need=True가 되어
#   positive_rescue를 막던 긍→중 트랩. 직후 토큰이 사람명사면 제외(긍정 보존).
#   ⚠️ '필요 이상'(과도)은 비판("필요이상의 일에 시달려")이라 가드에 넣지 않는다(부→긍 교차 방지, 전수검증).
_NEED_POSITIVE_TAILS = ('인물', '인재', '존재', '인력', '자원')
# 0702 폐기: '필요'+명사복합('사항·성·시·업무'…) 제외를 시도했으나 "필요성이 있다"·"소통이 더
#   필요할 것 같음"(진짜 개선요청)까지 풀어 부→긍 113건 유발 → revert. 공유 게이트는 안 건드리고,
#   강긍정 보호는 improvement_request_neg 분기의 pos 가드로만 처리(양방향 안전).


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
        # 0702: negation 창이 절 경계(쉼표·마침표 등)를 넘지 않게 절단 — "자세 필요, 말이 없음"의
        #   '없'은 다른 절(말이 없음) 소속인데 창 확대(8)로 잘못 '불요'로 봐 개선요청(부)이 긍정
        #   구제되던 부→긍 1건 교정. 같은 절 안의 "필요점 딱히 없"만 불요로 인정(무결점 유지).
        for _sep in (',', '.', '·', ';', '/', '\n', '。', '，'):
            _ci = window.find(_sep)
            if _ci != -1:
                window = window[:_ci]
        before = sentence[max(0, p - 1):p]
        tail = sentence[p + 2:p + 2 + 6].lstrip()         # '필요' 직후(선행 공백 제거) 토큰
        # 0702_03 시도·폐기: '필요시/필요할 경우/때' 조건형을 개선요청에서 제외하려 했으나,
        #   "X가 필요할 때가 있음"(개선요청=부)과 "필요시 X를 잘 해줌"(조력=긍)이 동일 표면형이라
        #   양방향 전수에서 부→긍 72 유발(113 revert와 동형) → 공유게이트 불가침 재확인, 이 폴리세미는
        #   파인튜닝 몫([[project_field_signal_for_finetune]]). 관형 '필요한'만 기존 유지.
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
    # 0702_03: 관형 '필요한'([명사] 수식)만 요청에서 제외 — has_constructive_need(a1=='한' 제외)와
    #   일관. "보완이 필요한 부분보다 배울점이 더 많음"·"보완이 필요한 부분에 조언 제공"(칭찬)이
    #   부정/중립화되던 긍 훼손 차단. ⚠️ 조건형 '필요할/필요시'는 제외 안 함 — 이전에 "X 필요할 때가
    #   있음"(개선요청)까지 풀어 부→긍 72 유발했기 때문(파인튜닝 몫). '필요한'만 좁게 제외.
    for w in ('보완', '개선'):
        j = sentence.find(w)
        while j != -1:
            tail = sentence[j + len(w):j + len(w) + 8]
            if not any(neg in tail for neg in ('없', '않', '아니')):
                for v in _IMPROVE_REQ_VERBS:
                    vi = tail.find(v)
                    if vi == -1:
                        continue
                    if v == '필요' and tail[vi + 2:vi + 3] == '한':
                        continue                          # 보완이 필요한 [명사] = 관형 수식 → 요청 아님
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
                 '결점', '지적사항', '지적 사항', '미흡한 점', '아쉬운 점', '부족한 점',
                 # 0702_03: '보안'은 '보완'의 잦은 IME 오타(사용자 제보). "보안점 필요없음"·
                 #   "보안필요상황없음"류 무결점 선언이 미인식되어 남던 것 흡수. 이 리스트는
                 #   negation 창이 있을 때만 →중립을 내므로 진짜 보안(security)+없음("보안 문제
                 #   없음"=긍)도 긍→중(핵심가치 안전)일 뿐 긍↔부 오분류 불가.
                 '보안', '보안점', '보안 점', '보안사항', '보안 사항', '보안필요',
                 # 0703: 오타 변형(사용자 제보) — 모완(보완)·단덤(단점)·미비한 점.
                 '모완', '모완점', '모완사항', '단덤', '미비한 점', '미비점', '미흡점',
                 # 0702: '특별한 장점 없음'류 무언급 선언 — 강점 부재 서술은 비평가(중립).
                 #   '장점' 단독은 "장점을 못 살림"(소홀 등 결함어가 상위 가드에서 부정 보존)이라
                 #   여기 중립화는 순수 "장점 없음" 선언에만 걸림(→중립, 긍↔부 무관).
                 '장점', '특별한 점', '특이점']
_NOWEAK_NEG = ('없', '않', '아니')
# 0702: 8→12. "보완 필요점은 별도로 없습니다"·"부족함 점을 발견할 수 없음"처럼 명사와 '없'
#   사이에 부사구('별도로'·'발견할 수')가 끼면 8자 창을 벗어나 중립화를 놓치던 부70 케이스 교정.
#   중립만 산출하므로 창 확대가 긍↔부 오분류를 만들 수 없다.
_NOWEAK_WINDOW = 12
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


# 약점-못찾음/미발견/오타없음 선언 — "보완필요점 찾지 못함"·"단점 발견하지 못함"·"보완필요사항 업음".
#   0702_03: 실측 15,782건(약점명사 ∧ 표준 negation('없/않/아니') 없음 ∧ 부정라벨)의 지배 패턴.
#   부정 표지가 '못(찾지 못/느끼지 못)'·'미발견'·'찾기 어려움'·오타 없음('업음/업슴')이라 기존
#   negation('없/않/아니')·개선요청 core가 이를 부정으로 인식 못 해 "약점을 못 찾음"(=무결점, 중립)이
#   improvement_request로 부정화되던 것을 교정. 약점 '찾는 행위'의 부정 = 약점 부재 선언 = 중립.
#   방향이 오직 →중립이라 긍↔부 오분류를 만들 수 없다(부→중, 사용자 라벨원칙 무결점=중립).
_NOWEAK_NOTFOUND = ('찾지 못', '찾지못', '못 찾', '못찾', '찾기 어려', '찾기어려', '찾기 힘',
                    '느끼지 못', '느끼지못', '못 느', '못느', '발견하지 못', '발견하지못',
                    '발견 못', '발견못', '미발견', '못 발견', '모르겠',
                    # 0702_03: '확인하지 못/확인 못/확인되지 않' — "보완이 필요한 점은 확인하지
                    #   못하였습니다"(약점 확인행위의 부정=무결점 선언)를 not-found로 포착.
                    #   약점명사 동시 요구라 순수 '확인'문(성과 확인 등)은 미발동.
                    '확인하지 못', '확인하지못', '확인 못', '확인못', '확인되지 않', '확인되지않',
                    # 오타 '없음'(사용자 제보 10~20%) — 표준 '없'으로 안 잡히는 변형만.
                    '업음', '업슴', '업습니', '업ㅅ', '읎', '엄슴', '엄음',
                    # 0715 확장(사용자 감사 카테고리7): 무결점 선언 변형 — 생각해본 적 없음/두드러진 점
                    #   없음/특별히 없음/느까지 못함(느끼지 오타)/칮지 못함(찾지 오타). 약점명사 동시
                    #   요구라 안전(→중립만). '두드러지'는 약점명사 게이트로 "장점 두드러짐"(긍정) 미발동.
                    '생각해본 적', '생각해본적', '생각해 본 적', '생각 안', '생각나지 않',
                    '두드러지', '특별히 없', '특별히없', '느까지', '칮지')
# not-found 전용 약점명사 — '장점/특별한 점/특이점'(무언급) 제외. "느끼지 못함이 장점"(칭찬)이나
#   "장점 못 찾음"(모호)에 not-found가 걸려 진짜 칭찬을 긍→중 하지 않게, 순수 약점명사만 사용.
_NOWEAK_NOTFOUND_NOUNS = ('보완', '단점', '개선점', '개선 사항', '개선사항', '보완점', '보완 점',
                          '보완사항', '보완 사항', '보완필요', '문제점', '특이사항', '특이 사항',
                          '결점', '지적사항', '지적 사항', '미흡한 점', '아쉬운 점', '부족한 점',
                          # 0702_03: 무공백 관형 변형("부족한점을 발견하지 못했습니다") — 공백형만
                          #   있어 못 잡던 것 보강(순수 약점명사).
                          '부족한점', '미흡한점', '아쉬운점',
                          # 0702_03: '보안'(보완 오타) 무결점 not-found도 흡수 — 순수 약점명사만.
                          '보안', '보안점', '보안 점', '보안사항', '보안 사항', '보안필요')


def _has_unnegated_other_negative_strict(sentence):
    """_has_unnegated_other_negative와 동일하나 관형 '부족한/미흡한'(not-found 대상)은 제외.

    0702_03: "아직 부족한 점을 발견하지 못했습니다"의 '부족'은 찾지 못한 *대상*(부족한 점)이라
    실제 결핍 서술이 아니다. _is_weakness_not_found 내부 혼합판정 전용 — →중립만 산출하므로
    관형 제외가 긍↔부 오분류를 만들 수 없다. 진짜 혼합("단점 못찾으나 소통 미흡함")의 '미흡함'은
    관형이 아니라 계속 True로 부정 보존.
    """
    for w in _NOWEAK_OTHER_NEG:
        i = sentence.find(w)
        while i != -1:
            tail = sentence[i + len(w):i + len(w) + 5]
            # 관형('한'/'운' 시작) = 약점명사 수식(부족한 점) → not-found 대상, 결핍 서술 아님.
            if not tail.lstrip().startswith(('한', '운')) \
                    and not any(n in tail for n in ('없', '않', '아니')):
                return True
            i = sentence.find(w, i + len(w))
    return False


def _has_strong_negative_nonadnominal(sentence):
    """has_unnegated_strong_negative와 동일하나 관형 '필요한'(예: '보완이 필요한')은 강부정에서 제외.

    0702_03: "보완이 필요한 점은 확인하지 못하였습니다"는 '보완이 필요'가 관형으로 not-found의
    *대상*(찾지 못한 그 점)이라 실제 결핍 서술이 아니다. 이 판정은 →중립만 내므로 관형 제외가
    긍↔부 오분류를 만들 수 없다(진짜 혼합 결핍은 _has_unnegated_other_negative가 계속 보존).
    """
    if not sentence:
        return False
    for phrase in STRONG_NEGATIVE_PHRASES:
        p = sentence.find(phrase)
        while p != -1:
            tail = sentence[p + len(phrase):p + len(phrase) + 6]
            if not tail.lstrip().startswith('한') and not any(r in tail for r in _RENEGATION_TOKENS):
                return True
            p = sentence.find(phrase, p + len(phrase))
    return False


def _is_weakness_not_found(sentence):
    """약점 명사가 있고 그 약점을 '못 찾음/미발견/오타 없음'으로 부재 선언하면 True(무결점=중립).

    고정밀: 약점명사 + not-found 표지 동시 요구 → "보완 필요"(negation 없는 순수 개선요청)는 미매치.
    혼합("보완점 못찾았지만 소통 미흡")은 미부정 결핍/강부정이 섞이면 False로 부정 보존.
    """
    if not any(n in sentence for n in _NOWEAK_NOTFOUND_NOUNS):
        return False
    if not any(v in sentence for v in _NOWEAK_NOTFOUND):
        return False
    # 혼합 방지 — 다른 미부정 결핍어(부족·미흡…)나 강부정이 섞이면 무결점 단정 보류(부정 보존).
    #   단 관형 '보완이 필요한'류는 not-found 대상이라 강부정에서 제외(→중립만, 긍↔부 안전).
    if _has_unnegated_other_negative_strict(sentence) or _has_strong_negative_nonadnominal(sentence):
        return False
    return True


def is_no_weakness_declaration(sentence):
    """약점 명사(보완/단점/개선점…) 직후 창에 negation이 와 '약점 없음'을 선언하면 True → 중립.

    다른 진짜 부정 신호(결함술어·건설적필요·강조부정·미부정 결핍어)가 섞이면 혼합이므로
    False(부정 보존). 중립만 산출하므로 긍↔부 오분류를 만들 수 없다.
    """
    if not sentence:
        return False
    # 약점-못찾음/미발견/오타없음 선언은 개선요청 가드보다 우선 인식 — "보완필요점 찾지 못함"류가
    #   has_constructive_need('필요')에 걸려 부정으로 새던 것을 무결점(중립)으로 확정(0702_03).
    if _is_weakness_not_found(sentence):
        return True
    # 혼합("보완점은 없으나 소통이 부족") → 진짜 부정 우선, 약점선언 미발동
    # NOTE: has_improvement_request 는 여기 넣지 않는다. 그 게이트는 후행 '없음'을 negation-aware로
    #   완전 처리하지 못해("개선 및 보완필요점 없음") 약점-없음 선언을 부정으로 밀 수 있다.
    #   positive_rescue 게이트에서만 사용하고, 약점-없음 중립화는 기존 negation-aware 로직에 맡긴다.
    if (has_unnegated_deficiency(sentence) or has_constructive_need(sentence)
            or has_unnegated_strong_negative(sentence)
            or _has_unnegated_other_negative(sentence)):
        return False
    # 메타-부재 선언("특별한 사항/별다른 것/딱히 ... 없음") — 특정 약점명사가 없어도 "특별히
    #   없다"류 무언급=무결점(중립). 위 결핍 가드를 통과했으므로 진짜 결핍(부족·미흡·역량없음)은
    #   이미 걸러졌다. 방향 →중립뿐이라 긍↔부 안전.
    if _is_meta_nothing(sentence):
        return True
    for noun in _NOWEAK_NOUNS:
        i = sentence.find(noun)
        while i != -1:
            window = sentence[i + len(noun):i + len(noun) + _NOWEAK_WINDOW]
            if any(neg in window for neg in _NOWEAK_NEG):
                return True
            i = sentence.find(noun, i + len(noun))
    return False


# 메타-부재 선언(0703, 사용자 제보 "보완/개선 필요없음 유사어 다수") — 특정 약점명사 없이 "특별한
#   사항/별다른 것/딱히/그외 ... 없음"으로 무언급을 선언. 명사구 표지는 어디에 있어도 되지만, 부사
#   표지(딱히/별로/그외 등)는 competency 결핍("열의가 딱히 없음")과 구분하려 문두에서만 인정한다.
_META_NOTHING_PHRASE = ('특별한 사항', '특별한 점', '특별한것', '특별한 것', '특별한 부분',
                        '특별한 내용', '특이사항', '특이 사항', '특이점', '특이한 점', '별다른',
                        '해당사항', '해당 사항', '기재사항', '기재 사항', '느낀 점', '느낀점',
                        '느낀 적', '느낀적', '언급할', '작성할', '적을 내용', '적을 것', '적을게',
                        '생각나는', '생각해본', '기타 특별', '지적할', '언급 사항')
_META_NOTHING_LEAD = ('딱히', '특별히', '그외', '그 외', '이외', '별로', '그런거', '그런 것',
                      '그런것', '별 다른', '별거', '별 거', '없음', '없습니다')
_META_ABSENT = ('없', '않', '아님', '아니', '업음', '업슴', '읎', '엄슴')


def _is_meta_nothing(sentence):
    """메타-부재 선언이면 True(무결점=중립). 부사표지는 문두에서만 인정(competency 결핍 오포착 방지)."""
    if not sentence or not any(a in sentence for a in _META_ABSENT):
        return False
    if any(p in sentence for p in _META_NOTHING_PHRASE):
        return True
    head = sentence.lstrip()
    return any(head.startswith(l) for l in _META_NOTHING_LEAD)


# 0702 구조규칙 — 명시적 강긍정 술어. 무결점 선언에 실제 칭찬이 붙으면("보완필요점 없을 정도로
#   완벽함") 중립화하지 않고 긍정 보존. 폴리세미 명사(노력·전문성 등)는 제외하고, 극성이 명확한
#   평가 형용사만 수록 → 무결점 중립화 확대가 진짜 칭찬을 삼키지 않게 한다.
_EXPLICIT_POSITIVE = ('완벽', '뛰어', '우수', '훌륭', '탁월', '최고', '출중', '탄탄', '모범',
                      '남다른', '타의 추종', '더할 나위',
                      # 0709: "높은 평가를 드리고 싶음"류 명시 상찬 — 무보완+칭찬어=긍정(4R 재정 원칙).
                      #   '높은' 단독은 폴리세미(눈높이·연령대 높은)라 '평가' 결합구만 수록.
                      '높은 평가', '높이 평가', '높게 평가')


def has_explicit_strong_positive(sentence):
    """명시적 강긍정 평가어가 있으면 True(무결점 중립화에서 진짜 칭찬 보존용)."""
    return bool(sentence) and any(w in sentence for w in _EXPLICIT_POSITIVE)


# 건강/사생활 관련 조언 — 사용자 정책(0702_03): 개인 건강(건강관리·음주·체력 등) 조언·개선 언급은
#   업무 평가가 아니므로 중립. "건강관리가 필요함"·"술을 줄이면 좋겠음"·"건강에 유의". 방향 →중립뿐
#   이라 긍↔부 무관. 건강 term + 조언/결핍 marker 동시 요구 → "체력이 좋아 업무를 잘함"(건강이
#   업무역량을 뒷받침하는 칭찬, marker 없음)은 미발동으로 칭찬 보존.
_HEALTH_TERMS = ('건강관리', '건강 관리', '건강에', '건강을', '건강상', '건강히', '건강관련',
                 '건강도', '건강까지', '건겅', '건강유지', '몸건강', '몸 건강', '체력', '음주',
                 '술을', '술자리', '과음', '흡연', '담배', '금연', '금주', '지병', '컨디션',
                 '다이어트', '운동',  # 0715 확장: 운동/몸건강(사용자 감사 카테고리1)
                 '과로의', '과로로', '과로가', '과로를', '과로에')  # 과로(성과로/결과로 substring 회피 위해 조사 결합형만)
_HEALTH_ADVICE = ('필요', '보완', '유의', '좋겠', '조심', '신경', '챙기', '해야', '줄이',
                  '주의', '바랍', '바람', '했으면', '하였으면', '관리가', '관리도')


def is_health_advice(sentence):
    """개인 건강/사생활 조언·개선 언급이면 True → 중립(업무 평가 아님, 사용자 정책)."""
    if not sentence:
        return False
    return (any(t in sentence for t in _HEALTH_TERMS)
            and any(a in sentence for a in _HEALTH_ADVICE))


# ── 개인 심신 안녕(업무 무관) → 중립 (0706 사용자 정책) ────────────────────────────
# 배경: 건강뿐 아니라 스트레스·상처·휴식·사기 등 개인 안녕에 대한 '바람/염려/조언'은 업무역량
#   평가가 아니다(사용자: "쉬어가면서 일했으면", "스트레스 받지 않았으면", "상처 덜 받으셨으면").
#   그런데 이들이 '필요/해야/좋겠'을 포함해 improvement_request·rule3_last_low로 부정화되고 있었다
#   (검토 코퍼스 실측: 건강 부정 68·개인안녕 부정 32, 대부분 rule3/improvement).
# 안전: 도메인 명사 AND 염려/바람/조언 마커를 *동시* 요구 → 단순 언급("체력이 좋아 잘함")·역량서술
#   ("스트레스에 내성이 강함")·업무귀결 부정("음주로 잦은 지각")은 마커가 없어 미발동 → 칭찬/부정 보존.
#   반환은 중립뿐이라 긍↔부 오분류 불가(방향 →중립만). is_health_advice의 상위집합(건강+마커도 포함).
# 다의 명사(사기=morale/scam, 마음이=care) 제외 — 긴 문장서 무관 마커와 AND 오발동(강부정 오중립).
# substring 충돌 명사도 제외: '술을'(→기술을/전술을/예술을), '과로'(→성과로/결과로).
_PERSONAL_DOMAIN_NOUNS = tuple(t for t in _HEALTH_TERMS if t != '술을') + (
    '건강이', '건강과', '스트레스', '상처', '휴식', '쉬어', '쉬엄', '쉬면서', '쉬셨',
    '번아웃', '멘탈', '정신적', '몸이', '몸을', '몸 챙', '몸도',
    # 0715 확장(사용자 감사 카테고리1·3): 휴가/휴무/휴직/경력단절/시달림/마음아픔 = 개인 안녕
    '휴가', '휴무', '연차', '휴직', '경력단절', '경력 단절', '가정에', '가정을',
    '시달', '마음이 아', '마음 아', '마음이아',
)
# 칭찬형 마커(관리·해소·받지 않·신경) 제외 — "자기관리로 컨디션 유지"·"스트레스 잘 해소"·"스트레스
#   받지 않는다"(회복력=긍정)·"멘탈케어 신경 써주심"(칭찬)을 오중립하던 것 차단. '생각하'는 명령형
#   (생각하세/셔/해야)만 — "남을 먼저 생각하고"(칭찬) 오발동 방지. 위시/염려/조언형만 유지.
_PERSONAL_CONCERN_MARK = (
    '좋겠', '좋을', '했으면', '하였으면', '하셨으면', '바람', '바랍', '우려', '염려', '안쓰',
    '조심', '유의', '챙기', '하셔야', '하세요', '드립니다', '드림', '필요', '줄이',
    '주의', '무리하지', '덜 받', '받지 마', '끊어야', '끊으', '끊고',
    '생각하세', '생각하셔', '생각해야', '생각하시',
    '풀었으면', '당부', '기원', '응원', '힘내', '해야', '있어야',
    '았으면', '었으면',   # 위시 어미("쉬었으면", "안받었으면") — 명사 게이트로 오탐 방지
    # 0715 확장(사용자 감사): 건강/안녕 명사 + 결핍/아쉬움/고통 마커도 중립(업무 아닌 개인 안녕).
    #   도메인 명사 게이트가 있어 "업무능력 부족"엔 미발동(업무능력=도메인 아님).
    '부족', '떨어', '아쉽', '아쉬움', '단절', '아프', '아픕', '아팠', '힘들', '힘듬', '힘듦',
)


def is_personal_wellbeing_neutral(sentence):
    """개인 건강·심신 안녕(업무 무관)에 대한 조언·바람·염려면 True → 중립(사용자 정책).

    도메인 명사 + 염려/바람/조언 마커 동시 필요(단순 언급·역량서술·업무귀결 부정은 미발동).
    방향은 →중립뿐이라 긍↔부 안전. is_health_advice보다 도메인·마커가 넓다.
    """
    if not sentence:
        return False
    if not any(n in sentence for n in _PERSONAL_DOMAIN_NOUNS):
        return False
    return any(m in sentence for m in _PERSONAL_CONCERN_MARK)


# ── 비평가 메타 코멘트(0715 사용자 감사 카테고리4) → 중립 ──────────────────────
#   평가 대상이 '사람 역량'이 아니라 제도/설문/근무일정 자체. "다면평가 없어졌으면", "근무시간
#   조정해 오전 퇴근했으면", "보완필요성 적는게 힘듬". 방향 →중립뿐이라 긍↔부 안전.
_META_COMMENT = ('다면평가', '다면 평가', '평가제도', '평가 제도', '설문조사', '평가서 작성',
                 '평가 항목', '근무시간 조정', '근무 시간 조정', '퇴근했으면', '출근했으면')
_META_SURVEY_HARD = ('적는게', '적는 게', '적기가', '작성이', '쓰는게', '쓰는 게', '적을게')
_META_HARD = ('힘', '어렵', '곤란')


def is_meta_comment(sentence):
    """평가 제도/설문/근무일정 등 비역량 메타 코멘트면 True → 중립(사용자 정책 0715)."""
    if not sentence:
        return False
    if any(m in sentence for m in _META_COMMENT):
        return True
    return (any(s in sentence for s in _META_SURVEY_HARD)
            and any(h in sentence for h in _META_HARD))


# ── 평가 불가(상호작용/관찰 부재, 카테고리2) → 중립 ─────────────────────────────
#   평가자가 교류/대면 부재로 판단 불가. ⚠ '업무 불가시성 비판'("무슨 일 하는지 모르겠")과 구분:
#   여기선 상호작용·관찰 부재 표지만 본다 → 비판(부정)은 보존.
_CANNOT_ASSESS = ('교류가 없', '교류가 전혀', '교류한 적', '교류할 일이 없', '말도 안해',
                  '말 한번 안', '말 한마디', '어케 아', '어떻게 아나', '어찌 아',
                  '평가를 못', '평가하기 어렵', '평가하기 힘', '알 도리가 없',
                  '함께 일한 적이 없', '같이 일한 적이 없', '함께 근무한 적이 없')


def is_cannot_assess(sentence):
    """평가자의 상호작용/관찰 부재로 평가 불가면 True → 중립(사용자 카테고리2)."""
    return bool(sentence) and any(p in sentence for p in _CANNOT_ASSESS)


def is_mixed_pos_neg(sentence):
    """긍정 대조술어(뛰어나나·우수하나…) + 부정신호(없음/부족/아쉬움/못/단절) 공존 = 긍부혼재 → 중립.
    개선요청 짝에 국한하지 않는 광의 혼합(0715 사용자 카테고리3). 방향 →중립뿐 긍↔부 안전."""
    if not sentence or not _MIXED_POS_CONTRAST.search(sentence):
        return False
    return (has_negative_implying_words(sentence)
            or any(m in sentence for m in ('없', '부족', '아쉽', '단절', '떨어', '시달', '못함', '못하')))


def _is_effort_needed(sentence):
    """'노력'이 직후 창(8자)에 '필요'와 함께 오면 True(불요 제외) → 명백한 개선요청.

    0702_03: 코퍼스 실측 '노력+필요' 3,640건(2,300 distinct) 중 칭찬 반례 0 — "노력이 필요함"은
    노력이 *결여*됐다는 뜻(칭찬은 "노력함/노력이 대단함/아끼지 않음"). 폴리세미 아니므로 KoTE
    강긍정(pos≥0.75)이어도 pos가드를 무시하고 부정 확정(긍↔부 안전, 방향 편향 없음).
    """
    if not sentence:
        return False
    p = sentence.find('노력')
    while p != -1:
        seg = sentence[p:p + 8]
        fi = seg.find('필요')
        if fi != -1 and '필요없' not in seg and '필요 없' not in seg:
            # 0703: 노력~필요 사이 절 경계(쉼표 등)면 다른 절("노력, 필요한 네트워크 보유"=칭찬) → 제외.
            if not any(sep in seg[:fi] for sep in (',', '·', '/', '。', '，', ';', '.')):
                return True
        p = sentence.find('노력', p + 2)
    return False


# 추측형 필요 — "X가 필요한 것 같음/필요한듯/필요해 보임" = 화자가 결핍을 추정 단언 = 개선요청(부정).
#   0702_03: 코퍼스 실측 2,932건, KoTE-긍 표본조차 전부 개선요청("적극적 참여가 필요해보인다"·
#   "챙기는 노력도 필요한 것 같") — 칭찬 반례 0. 관형 '필요한 [실명사]'(필요한 부분/조언=칭찬맥락,
#   부→긍 72 트랩)와 표면형이 분리(것 같/듯/해 보임 종결)돼 재발 없음. 불가결('필요한 인재/인물')·
#   불요(필요없)·부정('필요해 보이지 않')은 제외 → 긍↔부 안전.
_SPEC_NEED = ('필요한 것 같', '필요한것 같', '필요한 듯', '필요한듯', '필요할 듯', '필요할듯',
              '필요해 보', '필요해보', '필요할 것 같', '필요할것 같', '필요하다고 보',
              '필요해 지', '필요하지 않나')
_SPEC_NEED_STOP = ('인재', '인물', '존재', '인력')          # 필요한 인재인 것 같다 = 칭찬 → 제외


def _is_speculative_need(sentence):
    """추측형 필요(결핍 추정) = 개선요청이면 True. 불가결·불요·부정은 제외(긍→부 보호)."""
    if not sentence:
        return False
    for form in _SPEC_NEED:
        i = sentence.find(form)
        while i != -1:
            back = sentence[max(0, i - 4):i]                 # '필요' 앞 4자(인재/인물 수식 확인)
            if any(s in back for s in _SPEC_NEED_STOP):
                i = sentence.find(form, i + len(form))
                continue
            tail = sentence[i:i + len(form) + 6]
            if '않' in tail or '없' in tail:                  # 필요해 보이지 않/필요한 것 같지 않 = 제외
                i = sentence.find(form, i + len(form))
                continue
            return True
    return False


# 요청표지 화행 — 사용자 재정 원칙(4R·0630): 요청표지(~해야/~바람/~좋겠/~주세요/자제/지양/보완)가
#   있으면 개선요청 = 부정. 0709 적대검증 실측: 내부망 부→dev 긍 16,031건 중 positive_rescue 12,275건이
#   전부 이 화행("협업을 위해 노력해야한다"·"적극적인 업무처리 바랍니다"·"업무열의 및 협업능력 보완")
#   인데 기존 검출기(improvement_core/constructive/effort/speculative) 전원 미탐 → 긍정 구제돼 긍↔부
#   위반 위험. 칭찬 트랩은 표면형으로 제외: '바람직'(≠바람), '본받아야'(칭찬), '~어야 할 일을 처리함'
#   (문말 아님 → regex가 처방형 종결만 매칭), '아쉬움이 없다'(negation), '했으면서도'(양보 연결어미).
_REQ_PRESCRIPTIVE = re.compile(
    r'(?:어|아|여|해|되어|돼|져)\s?야\s?(?:함|한다(?!는)|합니다|됨|됩니다|겠(?!다는))')
# '될' 제외(260709 A/B): "체크해야될 사항들을 제시함"의 관형절(해야 될+명사)이 칭찬문을 오탐.
_REQ_WISH = re.compile(r'(?:었|았)으면(?!서)')
# A/B 실측 트랩 제외(260709): '자제'(전자제어 substring)·bare '지양/삼가'("불필요한 업무 지양"=
#   행위서술 칭찬)·bare '요함'(중요함)·문말 '노력'("조직목표 달성을 위해 노력"=장점 행위서술 1,616건
#   긍→부 유발) — 처방형 어미/바람/요망 래퍼가 있을 때만 요청으로 본다.
_REQ_TOKENS = ('좋겠', '좋겟', '면 좋을', '면좋을', '면 좋음', '면 좋다', '면 좋습',
               '면 될 것', '시면 될', '바랍', '주세요', '주시기 바', '주시길', '주십시오',
               '해주길', '해 주길', '요망', ' 요함',
               '이 요구됨', '가 요구됨', '보완한다면', '보완하면', '보완하시면', '보완이 요',
               '보완 요')
_REQ_FINAL_BARE = re.compile(r'보완[\s\.\!\?~]*$')            # 문말 bare 명사 요청("협업능력 보완")
# 문말 '보완'이라도 행위서술(칭찬)인 형태 제외(260709 A/B 실측): ① 수단("중간점검을 통하여 보완"),
#   ② 부정명사 목적어("문제점을 보완"·"어려움 보완" = 결함을 고쳐준다는 칭찬), ③ 목적/수단 연결
#   ("효율적 업무처리를 위해 개선보완"·"온화한 성격으로 보완"·"발견하여 보완").
_REQ_FINAL_BARE_EXCL = ('통하여', '통해', '통한', '바탕으로',
                        '문제점', '문제를', '어려움', '단점', '약점', '미비점',
                        '하여', '위해', '위한', '으로')
# 서술형 칭찬 술어 — 요청표지 *단독* 문장에 동반되면 긍부혼재("업무열의가 매우 좋으며 좀더
#   노력바랍니다") → 원칙(긍부혼재=중립)대로 부정 대신 중립. 결핍 core 표지가 있으면 부정 유지.
_PRED_PRAISE = ('좋으며', '좋고', '좋으나', '매우 좋', '아주 좋', '능숙', '잘함', '잘 함')

# 긍부혼재 대조 술어(0715 사용자 규칙 "긍정+부정 공존→중립"): 긍정 용언 + 역접 대조어미
#   (뛰어나나·우수하나·좋으나). 이게 있으면 core 개선요청("개선 필요")이어도 혼합으로 보고 중립.
#   ⚠ 병렬어미(고/며)·관형형(뛰어난)은 제외 — "적극적이고 성실함 필요"(순수 개선요청)·
#     "뛰어난 능력 필요"(관형=결여지적) 오탐 방지. "-나" 역접은 has_contrastive가 누구나/언제나
#     모호성으로 미인식하므로 여기서 연결어미를 직접 매칭한다. 방향 →중립뿐이라 긍↔부 안전.
_MIXED_POS_CONTRAST = re.compile(
    r'(뛰어나|우수하|탁월하|훌륭하|능숙하|좋으|성실하|원활하|풍부하|강하|많으|높으|넓으)'
    r'(나|지만|으나|은데|는데|나마|음에도|는데도)')


def _has_request_marker(sentence):
    """요청표지 화행(개선요청=부정, 사용자 재정)이면 True. 칭찬 트랩은 표면형으로 제외."""
    if not sentence:
        return False
    m = _REQ_PRESCRIPTIVE.search(sentence)
    if m and sentence[max(0, m.start() - 2):m.start()] != '본받':
        return True
    if _REQ_WISH.search(sentence):
        return True
    for tok in _REQ_TOKENS:
        i = sentence.find(tok)
        if i != -1:
            return True
    # '바람'은 '바람직'·'예의 바람'(=예의 바름, 칭찬 표기변이) 제외("소통 노력 바람"류만)
    i = sentence.find('바람')
    while i != -1:
        if sentence[i:i + 3] != '바람직' and '예의' not in sentence[max(0, i - 5):i]:
            return True
        i = sentence.find('바람', i + 2)
    # '아쉬'는 negation('아쉬움이 없다') 제외
    i = sentence.find('아쉬')
    while i != -1:
        if not any(n in sentence[i:i + 10] for n in ('없', '않')):
            return True
        i = sentence.find('아쉬', i + 2)
    m = _REQ_FINAL_BARE.search(sentence)
    if m:
        win = sentence[max(0, m.start() - 8):m.start()]      # 직전 창만 — 문두 '적극적으로'는 무관
        if not any(e in win for e in _REQ_FINAL_BARE_EXCL):
            return True
    return False


# 과잉 호소 — "너무/지나치게 X해서 [부정 귀결]" = 과함이 문제를 낳음 = 부정. '너무' 폴리세미
#   ("너무 좋음"=칭찬)를 블랭킷 부정화하지 않고, 오직 부정 *귀결* 마커가 붙을 때만 발동.
#   0702_03: 코퍼스 실측으로 칭찬 오염 0인 마커만 채택(오해·못따라·과함·피로·버거·힘듬·곤란…).
#   제외(칭찬 오염 有): 부담·눈치·힘들·따라오기힘·'문제해결'. → 긍↔부 안전(실측 pos=0 마커).
_EXCESS_MARK = ('너무', '지나치게', '지나칠', '과도')
# 실측 칭찬오염 0 귀결마커만(SCAN2 2026-07-02). '부담/눈치/힘들/문제(bare)'는 칭찬혼입 있어 제외.
_EXCESS_CONSEQ = ('오해', '못 따라', '못따라', '따라가기 힘', '따라가지 못', '따라오지 못',
                  '과함', '과하게', '피로', '버거', '벅차', '힘듬', '힘듦', '곤란', '눈치보', '부담스')
# '문제'는 폴리세미(문제해결/어떠한 문제든=칭찬)라 bare 금지 — 명시적 '문제' 프레이밍 구만.
_EXCESS_PROBLEM = ('문제입니다', '문제 입니다', '문제임', '문제가 됩', '문제가 된', '문제가 되기',
                   '문제가 있', '문제점이 됩', '해서 문제', '라서 문제', '문제를 일으', '문제를 야기')
_CLAUSE_SEP = (',', '.', '·', ';', '/', '\n', '。', '，', '지만', '으나', '나 ', '며', '고 ')


def _clause_after(sentence, pos):
    """pos 이후 같은 절(절 경계 전까지) 텍스트."""
    seg = sentence[pos:]
    cut = len(seg)
    for sep in _CLAUSE_SEP:
        c = seg.find(sep, 1)
        if c != -1:
            cut = min(cut, c)
    return seg[:cut]


def _is_excess_complaint(sentence):
    """과잉('너무/지나치게') + 부정 귀결 마커면 True → 부정. 마커는 실측 칭찬오염 0만 사용.

    0702_03: '너무'는 강조사라 블랭킷 금지. '지나치게 X하지 않음'(과하지 않음=칭찬)·'어떠한 문제든
    긍정적'(칭찬)에서 긍→부 위반이 나와, 지나치=같은 절 내 negation('않/없') 확인·문제=명시 프레이밍
    구로 좁힘(전수 재검증 긍→부 0 확인).
    """
    if not sentence:
        return False
    if not any(m in sentence for m in _EXCESS_MARK):
        return False
    # 칭찬 보존 가드(전수 재검증에서 발굴한 긍→부 위반 차단):
    #   ① 명시적 강긍정("지나치게 업무능력이 뛰어남")·② 무결점 선언("단점을 찾기가 힘듦"=찾기 어려움)은
    #   과잉호소가 아니다 → 제외. (has_contrast 혼합문은 호출측에서 제외해 대조규칙에 위임.)
    if has_explicit_strong_positive(sentence) or _is_weakness_not_found(sentence):
        return False
    if any(c in sentence for c in _EXCESS_CONSEQ):
        return True
    if any(pf in sentence for pf in _EXCESS_PROBLEM):
        return True
    # '지나치'(과도) — 같은 절 안에 negation('않/없')이 있으면 '지나치지 않음'류 칭찬 → 제외.
    j = sentence.find('지나치')
    while j != -1:
        cl = _clause_after(sentence, j)
        if '않' not in cl and '없' not in cl:
            return True
        j = sentence.find('지나치', j + 3)
    return False


# 내용 문자(한글 자모·음절, 영숫자) — 하나도 없으면 구분선('-----')·기호 나열 = 쓰레기 행.
_CONTENT_CHAR_RE = re.compile(r'[0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]')


def _sentence_sentiment_override_explain(pos, neg, sentence, is_last, total_sentences,
                                          threshold=0.20, weight=2.0, neutral=0.0):
    """sentence_sentiment_override와 동일한 분기를 수행하되 (score, rule_id)를 반환.

    규칙 마이닝/정제 패스에서 "어떤 규칙이 발동했는가"를 기록하기 위한 설명 가능 버전.
    분기 조건·반환 점수는 sentence_sentiment_override와 완전히 동일해야 한다(동작 보존).
    """
    confidence = abs(pos - neg)
    strength = pos + neg

    # 구분선/기호-only 쓰레기 행 → 중립 (0709, q.txt ③). '-----' 류에 KoTE가 pos 0.7+를 주어
    #   rule4_default가 긍정 처리하던 269건 차단. 한글·영숫자가 하나도 없으면 평가 텍스트가 아님.
    #   방향 →중립뿐이라 긍↔부 무관.
    if not _CONTENT_CHAR_RE.search(sentence or ''):
        return 0.0, 'garbage_line_neutral'

    has_contrast = has_contrastive(sentence)

    # 개인 심신 안녕(업무 무관) → 중립 (도메인 게이트, 최우선). 0706 사용자 정책: 건강·스트레스·
    #   휴식·상처 등 개인 안녕에 대한 바람/염려/조언은 업무역량 평가가 아니므로 중립. improvement_request·
    #   excess·rule3_last_low가 '필요/해야/좋겠'을 부정화하기 전에 선점해 차단한다. 도메인명사+마커
    #   동시 요구라 칭찬("체력 좋아 잘함")·역량서술("스트레스 내성 강함")·업무귀결 부정은 미발동.
    #   반환 중립뿐 → 긍↔부 안전(긍→중·부→중만 발생, 전수회귀로 확인).
    if is_personal_wellbeing_neutral(sentence):
        return 0.0, 'personal_wellbeing_neutral'

    # 0715(사용자 카테고리6b): '역량명사, 잘 모르겠음'(그 항목 평가불가) → 중립. positive_rescue가
    #   긍정명사(소통능력)에 끌려 긍정 선점하던 것 차단. '잘 모르겠'만(비판 '무슨일 하는지 모르겠'과
    #   달리 상호작용/판단불가 표지). 방향 →중립뿐 긍↔부 안전.
    if ('잘 모르겠' in sentence or '잘모르겠' in sentence) and not has_explicit_strong_positive(sentence):
        return 0.0, 'no_response_neutral'

    # 0715 사용자 감사 반영 — positive_rescue·excess·개선요청보다 먼저 중립 확정(전부 →중립, 긍↔부
    #   안전): ② 상호작용/관찰 부재=평가불가 · ③ 긍부혼재(광의) · ④ 비평가 메타(제도/설문/근무일정).
    if is_cannot_assess(sentence):
        return 0.0, 'cannot_assess_neutral'
    if is_mixed_pos_neg(sentence):
        return 0.0, 'mixed_pos_neg_neutral'
    if is_meta_comment(sentence) and not has_explicit_strong_positive(sentence):
        return 0.0, 'meta_comment_neutral'

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
            # 0702_03: 무결점 선언("개선사항 없음"·"개선점 발견 못함")·추측형 필요·과잉호소는
            #   긍정 구제에서 제외 — 아래 전용 분기(no_weakness/improvement/excess)로 보내
            #   각각 중립/부정 확정. positive_rescue가 선점해 긍정으로 올리던 것 차단(긍→중·긍 미상향).
            and not is_no_weakness_declaration(sentence)
            and not _is_speculative_need(sentence)
            and not _is_effort_needed(sentence)
            # 0709 적대검증: 요청표지 화행("노력해야한다"·"바랍니다"·"~ 보완")이 긍정명사(열의·협업)
            #   때문에 구제되던 부→긍 축(12,275건) 차단 — 아래 improvement_request 분기로 보낸다.
            and not _has_request_marker(sentence)
            and not _is_excess_complaint(sentence)
            and not any(ph in sentence for ph in STRONG_NEGATIVE_PHRASES)
            and not any(nc in sentence for nc in NEGATIVE_CONTEXT_FOR_RESCUE)
            and neg < 0.85):
        # A-1(0702) 시도·폐기: "neg≥0.6·neg>pos면 긍정구제 보류"는 weak_export 전수에서
        #   긍→부 5,445건 유발, 표본 판정 결과 "학구열이 매우 높음"(n0.63)·"동료의식이 강함"(n0.62)·
        #   "상대방 배려 커뮤니케이션"(n0.70) 등 진짜 긍정 + 역량 단편 중립→부 다수 → 긍↔부 위반.
        #   KoTE가 짧은 역량구에 부정 과다예측 → neg 임계 차단은 부적합. 근본해법=필드(A-2). revert.
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

    # 과잉 호소(excess_complaint) → 부정. "너무 친절해서 오해를 삼"·"너무 적극적이라 못 따라감".
    #   0702_03: '너무'는 강조사라 블랭킷 부정화 불가(긍→부 위반). 부정 *귀결* 마커(실측 칭찬오염 0:
    #   오해·못따라·과함·피로·힘듬·곤란·문제)가 붙을 때만 발동 → "너무 좋음/열정적"(마커 없음)은
    #   positive_rescue로 긍정 유지. negation_praise('지나치지 않음' 칭찬) 뒤에 둬 칭찬 우선.
    if not has_contrast and _is_excess_complaint(sentence):
        return (-strength if strength > 1e-6 else -0.3), 'excess_complaint_neg'

    # ── 비평가/무결점 선언 우선 중립화 (개선요청 부정화·neutral_dominant보다 먼저) ──────
    # 0702_03: no_response·no_weakness를 neutral_dominant·improvement_request보다 앞으로 이동.
    #   "보완 필요점은 별도로 없습니다"류 무결점 선언은 '보완/필요' 표지 때문에 improvement_request의
    #   짧은 negation 창(8자)이 뒤쪽 '없'(별도로 없…)을 놓쳐 부정화되던 것을, is_no_weakness_declaration
    #   (원거리 '없' 인식)이 먼저 중립화해 차단한다(실측 16,154건 오부정 제거). 방향 →중립뿐, 긍↔부 안전.
    #   위치 이동 자체는 회귀 무해: neutral_dominant 문장이면 no_resp/no_weak도 중립을 반환(동일 결과),
    #   비(非)neutral_dominant면 순서 불변. 달라지는 건 improvement_request 선점을 막는 것뿐.
    if is_no_response(sentence) and not (pos >= 0.6 and pos > neg):
        return 0.0, 'no_response_neutral'
    if is_no_weakness_declaration(sentence):
        # 0703: 명시적 강긍정(완벽/뛰어남)이 붙은 무결점 선언은 중립화 대신 **긍정 확정**. 이전엔
        #   중립화만 건너뛰고 fall-through시켜 rule4_default가 KoTE neg를 따라 부정으로 뒤집던
        #   버그("완벽한 업무처리로 보완사항 없습니다"·"보완필요점 없고 역량 뛰어남"→부) 교정.
        #   무결점+강긍정은 진짜 칭찬이라 긍정 반환이 긍↔부 안전.
        if has_explicit_strong_positive(sentence):
            return (strength if strength > 1e-6 else 0.3), 'no_weakness_positive'
        return 0.0, 'no_weakness_neutral'

    # 건강/사생활 조언 → 중립 (개선요청 부정화보다 먼저). 사용자 정책(0702_03): 개인 건강 코멘트는
    #   업무 평가가 아니므로 중립. "건강관리가 필요함"·"술을 잘 드셔서 건강관리 보완 필요"가
    #   improvement_request로 부정화되던 것을 차단. 방향 →중립뿐이라 긍↔부 안전.
    if is_health_advice(sentence) and not has_explicit_strong_positive(sentence):
        return 0.0, 'health_advice_neutral'

    # 개선요청/결핍 프레이밍 → 부정 (neutral_dominant 선행·무결점 선언 뒤). 사용자 정책: 요청형=결여=부정.
    #   neutral_dominant가 'KoTE 중립우세'라는 이유만으로 "X 필요·소통 부족·소홀"류 개선요청을
    #   선점·중립화하던 것을 교정(polysemy 큐 실측 1,683건). 요청 core 검출기(_has_improvement_request_core/
    #   has_constructive_need/has_unnegated_deficiency — 모두 내장 가드 有: 관형 '필요한'·불요·
    #   '필요 인물/인재'·부정의부정)가 참일 때만 발동 → 무술어 단편("업무 열의 및 노력",
    #   "협업을 통한 성과제고 노력")은 미발동 → 아래 neutral_dominant로 중립 유지(사용자 점3).
    #   강긍정 보호(pos>=0.75): '필요'가 명사복합(필요사항·필요지식)·부수적 칭찬일 개연이 커 중립 유지
    #   (긍→부 차단). positive_rescue·negation_praise가 앞서 진짜 긍정을 상향했으므로 여기 도달하는 건
    #   긍정 표지가 약하거나 없는 개선요청 → 강긍정→중립·그 외→부정. neutral→부정은 핵심가치(긍↔부)
    #   무관·허용, 긍↔부 0은 장점/단점 양방향 회귀로 확인 후 채택(0702_03).
    _core_improve = (_has_improvement_request_core(sentence)
                     or has_constructive_need(sentence)
                     or has_unnegated_deficiency(sentence)
                     or _is_speculative_need(sentence)
                     or _is_effort_needed(sentence))
    # 0709: 요청표지 화행 편입(부→긍 적대검증). 강긍정(pos>=0.75) 가드는 존중 —
    #   유지형 위시("지금처럼 하기를 바랍니다")의 긍→부 반전을 막기 위해 중립으로.
    if (not _has_improve_blocking_contrast(sentence)
            and (_core_improve or _has_request_marker(sentence))):
        # 요청표지 *단독* + 서술형 칭찬 동반은 긍부혼재 → 중립(원칙). core 결핍 표지면 부정 유지.
        # 0715 확장(사용자 규칙): 긍정 용언+역접 대조어미(_MIXED_POS_CONTRAST: 뛰어나나·우수하나)로
        #   긍정 절이 명확히 선행하면 core 개선요청("개선 필요")이어도 혼합→중립. 기존 분기는 그대로
        #   두고 대조술어 케이스만 추가(strictly additive). 방향 →중립뿐이라 긍↔부 안전
        #   (40만 표본 flip 3건 전수 혼합 확인). "직원간 의사소통이 뛰어나나 개선 필요" 부정→중립 교정.
        if (_MIXED_POS_CONTRAST.search(sentence)
                or (not _core_improve
                    and (has_explicit_strong_positive(sentence)
                         or any(pp in sentence for pp in _PRED_PRAISE)))):
            return 0.0, 'improvement_request_neutral'
        # 노력+필요·추측형필요(불요 제외)는 실측 개선요청(반례 0) → pos가드 무시하고 부정 확정.
        if pos >= 0.75 and not _is_effort_needed(sentence) and not _is_speculative_need(sentence):
            return 0.0, 'improvement_request_neutral'
        return (-strength if strength > 1e-6 else -0.3), 'improvement_request_neg'

    # KoTE neutral 우세 또는 근접 우세(±0.05) → 중립 강제
    if neutral > pos and neutral >= neg - 0.05:
        return 0.0, 'neutral_dominant'

    # (no_response_neutral·no_weakness_neutral은 0702_03 reorder로 neutral_dominant/improvement_request
    #  앞으로 이동함 — 무결점·무응답 선언이 개선요청 부정화보다 먼저 중립화되도록.)

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

    # (개선요청/결핍 프레이밍 → 부정 분기는 0702_03 reorder로 neutral_dominant 앞으로 이동함.
    #  euphemistic_negative까지 통과한 잔여는 rule1~4가 처리.)

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


def apply_model_label_override(model_label, sentence, field=None):
    """파인튜닝 모델 라벨 위에 얹는 **좁은 고정밀** override (13_03 Track2).

    설계 원칙(핵심가치 불가침): 이 레이어는 **긍↔부를 새로 만들지 않는다**. 그래서 모델
    라벨 조건부로, 오류를 제거하는 방향으로만 보정한다. 반환: 보정된 라벨 문자열.

    R1 (요청표지 거짓긍정 제거): model=='positive' 인데 요청표지 화행(~해주세요·~바랍니다·
        희망형, `_has_request_marker` — 트랩가드 내장)이면 → 'neutral'. 긍→중만(긍→부 아님)이라
        긍↔부 생성 불가. 개선요청=부정 정책([[feedback_improvement_request_is_negative_gold]])의
        결정론적 안전망. 명시 강긍정·차단반전 있으면 미발동(진짜 칭찬 보호).

    설계·검증 근거(2026-07-13 실증, plans/2026/07/13_03_rule-alignment/):
      - 필드신호 override(무서술어 단편→필드극성)는 **폐기**: 모델이 필드 프리픽스로 이미
        필드신호 내장(train/serve 정합) → 재적용 시 이중계산, 4슬라이스 긍↔부 신규 +2·정확도 급락.
      - '요함' substring core(_has_improvement_request_core)는 '집요함'(끈기=긍정) 트랩 재도입 →
        제외. `_has_request_marker`만 사용 → 4슬라이스 발동 0·긍↔부 신규 0(청정) 확인.
      - 부→긍(모델이 명백 긍정을 부정으로) 케이스는 override로 안전 교정 불가 → 재학습(Track1) 몫.
    """
    if not sentence or model_label != 'positive':
        return model_label
    if (_has_request_marker(sentence)
            and not _has_improve_blocking_contrast(sentence)
            and not has_explicit_strong_positive(sentence)):
        return 'neutral'
    return model_label


_pseudo_mgr_instance = None
_pseudo_mgr_lock = threading.Lock()


def _get_pseudo_mgr():
    global _pseudo_mgr_instance
    if _pseudo_mgr_instance is None:
        with _pseudo_mgr_lock:
            if _pseudo_mgr_instance is None:
                _pseudo_mgr_instance = PseudonymManager(PSEUDONYM_MAPPINGS_PATH, ADMIN_PASSWORD)
    return _pseudo_mgr_instance


def _make_real_id_resolver(pseudo_mgr):
    """목록 응답용 대량 역변환기 — get_real_id()와 같은 의미를 로컬 dict 조회로 수행.

    20_09 §3.2. 반환 규칙은 get_real_id()(pseudonym_manager.py)와 1:1로 맞춘다:
      - 비었거나 공백뿐이면 원값 그대로 반환
      - 그 외에는 strip 후 조회, 매핑이 없으면 strip 된 값을 반환
    다른 점은 매핑 dict를 매 호출 락으로 얻지 않고 시작 시 스냅샷 1회로 얻는 것뿐이다.
    (가명 매핑 규칙 문서 §2 "조회 시 원본 복원"의 의무는 그대로 지킨다 — 복원을
    생략하는 게 아니라 같은 복원을 더 적은 오버헤드로 한다.)
    """
    mapping = pseudo_mgr.get_real_id_map() if pseudo_mgr else {}

    def _resolve(value):
        if not value or not str(value).strip():
            return value
        s = str(value).strip()
        return mapping.get(s, s)

    return _resolve


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
    summary_path = os.path.join(batch_path, "tdata", "batch_summary.json")
    if not os.path.exists(summary_path):
        return None
    with open(summary_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _batch_display_name(processed_data_dir, batch_id):
    """배치 디렉토리의 batch_summary.json에서 표시 명칭을 읽는다."""
    summary_path = os.path.join(processed_data_dir, 'batch', batch_id, "tdata", "batch_summary.json")
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

    병합(batch_merge_service)으로 status='merged'가 된 원본 배치는 목록에서
    숨긴다(데이터는 살아있고 statistics만 숨김 — batch_merges 테이블로 이력 보존).
    """
    from src.services.user_data_manager import _get_eval_conn
    conn = _get_eval_conn()
    try:
        wo_rows = conn.execute("""
            SELECT batch_id, success_count, total_rows, created_at
            FROM batch_work_orders
            WHERE status != 'merged'
            ORDER BY created_at DESC, id DESC
        """).fetchall()
        merged_rows = conn.execute("""
            SELECT batch_id FROM batch_work_orders WHERE status = 'merged'
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
    # 병합돼 숨겨야 할 원본 배치를 먼저 seen에 넣어, evaluations 보강 루프에서
    # 되살아나지 않도록 한다(방어적 처리 — 정상 병합 후엔 evaluations 행이 0건이 됨).
    seen = {row['batch_id'] for row in merged_rows}
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
            SELECT e.employee_id, e.name, e.department, e.position, ev.data, ev.id, ev.batch_id
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            ORDER BY e.employee_id, ev.id
        """).fetchall()
    finally:
        conn.close()

    emp_evals = defaultdict(list)
    emp_meta = {}
    for emp_id, name, dept, pos, data, ev_db_id, ev_batch_id in rows:
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
            # batch_id 정본은 DB 컬럼이다 — data 블롭에 적재 시점 값이 그대로 남아 있어
            # 병합(batch_merge_service: 컬럼만 재라벨) 이후 블롭 값이 낡는다.
            # /meta·배치이력 패널·배치 범위 필터가 모두 컬럼 기준이므로 여기서 정본으로 덮어쓴다.
            ev_obj['batch_id'] = ev_batch_id
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
        # 20_09 1.2: 배치 이력 지연은 원인 미확정 상태다 — 집계 SQL과 목록 조립을
        # 나눠 재서 어느 쪽인지(혹은 둘 다 빠른지) 실행 즉시 드러나게 한다.
        with perf_span('batch_history.count_sql'):
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

    with perf_span('batch_history.count_batches'):
        batch_count = _count_batches(processed_data_dir)
    with perf_span('batch_history.list'):
        batch_list = _load_batch_list(processed_data_dir)

    return {
        'batch_info': {
            'total_evaluations': total,
            'unique_employees': uniq,
            'batch_count': batch_count,
        },
        'batches': batch_list,
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
            SELECT e.employee_id, e.name, e.department, e.position, ev.data, ev.id, ev.batch_id
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
    for _emp_id, nm, dp, ps, data, ev_db_id, ev_batch_id in rows:
        name, dept, pos = nm or '', dp or '', ps or ''
        if data:
            try:
                ev_obj = json.loads(data)
            except json.JSONDecodeError as e:
                logger.error("json_parse_error row=%s error=%s", ev_db_id, e, extra={'request_id': request_id, 'stage': 'DB_LOAD'})
                continue
            # evaluation_id는 중복될 수 있으므로 고유한 DB row id를 보정값 키로 사용
            ev_obj['_db_id'] = ev_db_id
            # batch_id 정본은 DB 컬럼(병합 시 컬럼만 재라벨됨) — load_all_batches 동일 주석 참조
            ev_obj['batch_id'] = ev_batch_id
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


def load_employees_batch(employee_ids, request_id=''):
    """선택한 소수 직원의 평가만 담은 unified 형태 dict 반환(load_employee_batch의 다건판).

    소수 직원 매트릭스 생성(generate_all_employee_matrix)은 employee_ids 필터로
    선택분만 처리하므로 전 직원(load_all_batches)을 적재할 필요가 없다. 입력 ID는
    원본/가명 혼재를 허용하며 가명으로 resolve 후 IN 절 단일 쿼리로 조회한다.
    반환 구조·매칭 키(target_employee_id=가명)는 load_all_batches와 동일하다(0714).
    """
    pseudo_mgr = _get_pseudo_mgr()
    resolved_ids = []
    seen = set()
    for eid in employee_ids:
        rid = _resolve_to_pseudo(eid, pseudo_mgr)
        if rid and rid not in seen:
            seen.add(rid)
            resolved_ids.append(rid)
    if not resolved_ids:
        return {'batch_info': {}, 'employee_results': [], 'batches': []}

    placeholders = ','.join('?' for _ in resolved_ids)
    conn = _get_eval_conn()
    try:
        rows = conn.execute(f"""
            SELECT e.employee_id, e.name, e.department, e.position, ev.data, ev.id, ev.batch_id
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            WHERE e.employee_id IN ({placeholders})
            ORDER BY e.employee_id, ev.id
        """, resolved_ids).fetchall()
    finally:
        conn.close()

    emp_evals = defaultdict(list)
    emp_meta = {}
    for emp_id, name, dept, pos, data, ev_db_id, ev_batch_id in rows:
        if emp_id not in emp_meta:
            emp_meta[emp_id] = {
                'target_employee_name': name or '',
                'target_employee_department': dept or '',
                'target_employee_position': pos or '',
            }
        if data:
            try:
                ev_obj = json.loads(data)
            except json.JSONDecodeError as e:
                logger.error("json_parse_error row=%s error=%s", ev_db_id, e, extra={'request_id': request_id, 'stage': 'DB_LOAD'})
                continue
            # evaluation_id는 중복될 수 있으므로 고유한 DB row id를 보정값 키로 사용
            ev_obj['_db_id'] = ev_db_id
            # batch_id 정본은 DB 컬럼(병합 시 컬럼만 재라벨됨) — load_all_batches 동일 주석 참조
            ev_obj['batch_id'] = ev_batch_id
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

    logger.info("requested=%s loaded_employees=%s total_evals=%s", len(resolved_ids), len(emp_meta), total_evals, extra={'request_id': request_id, 'stage': 'DB_LOAD'})

    return {
        'batch_info': {'total_evaluations': total_evals, 'unique_employees': len(emp_meta)},
        'employee_results': employee_results,
        'batches': [],
    }


def list_employee_roster():
    """전 직원 명부(id/이름/부서/직급/평가건수)만 반환 — 평가 본문(data blob) 미적재.

    ID 매칭 경로(/csv-parse·/parse-ids)는 직원 명부와 평가 건수만 사용하므로
    load_all_batches()의 1.9만건 json.loads가 불필요하다. get_matrix_meta_light의
    emp_rows 집계와 동일 패턴(0714).
    """
    conn = _get_eval_conn()
    try:
        rows = conn.execute("""
            SELECT e.employee_id, e.name, e.department, e.position, COUNT(ev.id) AS cnt
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            GROUP BY e.employee_id
        """).fetchall()
    finally:
        conn.close()
    return [
        {
            'employee_id': r[0],
            'name': r[1] or '',
            'department': r[2] or '',
            'position': r[3] or '',
            'evaluation_count': r[4] or 0,
        }
        for r in rows
    ]


def list_users_with_batch_counts():
    """직원별 평가 총건수 + 배치별 건수를 SQL 집계로 반환 — 평가 본문(data blob) 미적재.

    /users는 직원 명부와 배치별 카운트만 쓴다. batch_id는 evaluations의 인덱스
    컬럼이므로(get_matrix_meta_light 참조) json.loads 없이 GROUP BY로 동일 결과를
    산출한다. 반환 구조는 기존 api_get_users 출력과 동일(employee_id/department/
    position/name/total_evaluations/batches[{batch_id,evaluation_count}]). 정렬도
    동일(직원=employee_id, batches=batch_id). load_all_batches()의 1.9만건
    json.loads 제거(0714). total_evaluations는 batch_id가 빈/NULL인 평가도 포함한다.
    """
    conn = _get_eval_conn()
    try:
        rows = conn.execute("""
            SELECT e.employee_id, e.name, e.department, e.position,
                   ev.batch_id, COUNT(ev.id) AS cnt
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            GROUP BY e.employee_id, ev.batch_id
        """).fetchall()
    finally:
        conn.close()

    users = {}
    for emp_id, name, dept, pos, batch_id, cnt in rows:
        if not emp_id:
            continue
        info = users.get(emp_id)
        if info is None:
            info = users[emp_id] = {
                'employee_id': emp_id,
                'department': dept or '',
                'position': pos or '',
                'name': name or '',
                'total_evaluations': 0,
                'batches': {},
            }
        info['total_evaluations'] += cnt
        # batch_id가 빈 문자열/NULL인 그룹은 총건수에는 포함하되 배치 목록에서는 제외
        if batch_id:
            info['batches'][batch_id] = info['batches'].get(batch_id, 0) + cnt

    result = []
    for emp_id in sorted(users):
        info = users[emp_id]
        info['batches'] = [
            {'batch_id': bid, 'evaluation_count': cnt}
            for bid, cnt in sorted(info['batches'].items())
        ]
        result.append(info)
    return result


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


def _get_sentence_level_scores(doc, threshold=0.20, weight=2.0, corrections=None, sentence_cache=None, field=None):
    """문장별 감정 점수(반전 규칙·사용자 교정 적용 후)를 계산.

    Returns list of (sent, score, pos, neg) 4-tuples.
    corrections: {sentence_index: "positive"|"negative"|"neutral"}
    sentence_cache: 배치 시 저장된 문장 단위 KoTE 원시 점수 리스트
                    [{"sentence"(optional), "pos", "neg", "neutral"}, ...].
                    제공되면 KoTE 재실행 없이 캐시 사용. 없으면 공유 헬퍼로 fallback.
    field: 문서 단위 극성 필드('장점'/'단점' 등, 0707_01). HR 감정모델 추론 시 학습과 동일
           프리픽스로 전달(train/serve 정합). None/빈값이면 무프리픽스(하위호환·기존 동작).
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
            # 필드(장점/단점)가 있으면 문서 전 문장에 상속(문서 단위 단일극성, 0707_01) → 학습과 동일
            # 프리픽스로 추론. field는 신 파이프라인(0707_01 극성매핑) 데이터에만 존재하고 그 데이터는
            # seed45 배포 세계에서만 생기므로, field 존재 자체가 train/serve 정합의 표식(별도 플래그 불요).
            # 구 데이터·미매핑은 field 없음 → 원문 추론(하위호환·어느 모델에서도 안전).
            fields = [field] * total if field else None
            model_labels = predict_sentiments(sentences, fields=fields)
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
            # 13_03 Track2: 모델 라벨 위 좁은 고정밀 override(요청표지 거짓긍정→중립). 긍↔부 불생성.
            lab = apply_model_label_override(model_labels[i], sent, field)
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
            sent_scores = _get_sentence_level_scores(doc, threshold, weight, corrections=eval_corrections, sentence_cache=ev.get('sentence_emotion_cache'), field=ev.get('evaluation_document_field'))
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
        sent_scores = _get_sentence_level_scores(doc, threshold, weight, corrections=eval_corrections, sentence_cache=ev.get('sentence_emotion_cache'), field=ev.get('evaluation_document_field'))
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
        sent_scores = _get_sentence_level_scores(doc, threshold, weight, corrections=eval_corrections, sentence_cache=ev.get('sentence_emotion_cache'), field=ev.get('evaluation_document_field'))
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


def search_employees(query, limit=20, batch_ids=None, enrich=False):
    """사번/이름 부분일치 직원 검색 (20_10). 최대 limit건만 반환한다.

    /meta 는 전 직원을 한 번에 돌려주지만, 대상 직원 입력창은 타이핑마다 소수 후보만
    필요하다. 전 직원 적재·전 직원 가명 역변환 없이 SQL LIKE + LIMIT 으로 끝낸다.

    DB의 employee_id·name 은 가명이므로, 관리자(enrich)일 때는 원본 사번으로도 찾을 수
    있도록 매핑(real→pseudo)을 함께 훑는다. 비관리자에게는 원본 값을 노출하지 않는다.
    배치 범위(batch_ids)가 주어지면 그 배치에 평가가 있는 직원만 반환한다(13_05와 동일 규칙).
    """
    q = (query or '').strip()
    if not q:
        return []
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 100))

    # 관리자 한정: 입력값이 원본 사번(부분일치)일 수 있으므로 매핑에서 가명 후보를 모은다.
    pseudo_hits = []
    if enrich:
        q_lower = q.lower()
        try:
            for real_id, pseudo in _get_pseudo_mgr().get_all_mappings():
                if q_lower in str(real_id).lower():
                    pseudo_hits.append(pseudo)
                    if len(pseudo_hits) >= limit * 5:
                        break
        except Exception:
            pseudo_hits = []

    like = f'%{q}%'
    match_sql = 'e.employee_id LIKE ? OR e.name LIKE ?'
    params = [like, like]
    if pseudo_hits:
        match_sql += f" OR e.employee_id IN ({','.join('?' * len(pseudo_hits))})"
        params.extend(pseudo_hits)

    batch_sql = ''
    if batch_ids:
        batch_sql = f" AND ev.batch_id IN ({','.join('?' * len(batch_ids))})"
        params.extend(batch_ids)
    params.append(limit)

    conn = _get_eval_conn()
    try:
        rows = conn.execute(f"""
            SELECT e.employee_id, e.name, e.department, e.position, COUNT(ev.id) AS cnt
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            WHERE ({match_sql}){batch_sql}
            GROUP BY e.employee_id
            ORDER BY e.employee_id
            LIMIT ?
        """, params).fetchall()
    finally:
        conn.close()

    # 20_09 §3.2와 동일 방식 — 매핑 스냅샷 1회 후 로컬 조회(결과 동일).
    _dr = _make_real_id_resolver(_get_pseudo_mgr()) if enrich else None
    results = []
    for emp_id, name, dept, pos, cnt in rows:
        entry = {
            'employee_id': emp_id,
            'employee_name': name,
            'department': dept,
            'position': pos,
            'evaluation_count': cnt,
        }
        if _dr:
            real_id = _dr(emp_id)
            entry['employee_id'] = real_id
            entry['employee_id_real'] = real_id if real_id != emp_id else None
            entry['employee_name'] = _dr(name) if name else None
            entry['department'] = _dr(dept) if dept else dept
        results.append(entry)
    return results


def get_matrix_meta_light(employee_id=None, batch_ids=None, enrich=False, processed_data_dir=None):
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

    # 13_05: 배치 범위 필터 — 축(row_field) 선택과 독립적인 사전 필터.
    # 미지정 시(None/빈 리스트) 기존과 100% 동일한 SQL(원자 질문 1.7, 하위 호환).
    batch_clause = ''
    batch_params = ()
    if batch_ids:
        placeholders = ','.join('?' * len(batch_ids))
        batch_clause = f' AND ev.batch_id IN ({placeholders})'
        batch_params = tuple(batch_ids)

    conn = _get_eval_conn()
    try:
        # 1) X축 facet — 평가일자 × 배치 그룹 카운트 (data blob 미적재)
        # 20_09: SQL·가명역변환·조립을 각각 재서 느린 구간을 특정한다(로그만, 동작 불변).
        with perf_span('meta.sql.facet'):
            if resolved_id:
                facet_rows = conn.execute(f"""
                    SELECT evaluation_date, batch_id, COUNT(*) AS c
                    FROM evaluations ev
                    WHERE employee_id = ?{batch_clause}
                    GROUP BY evaluation_date, batch_id
                """, (resolved_id,) + batch_params).fetchall()
            else:
                where = f'WHERE 1=1{batch_clause}' if batch_clause else ''
                facet_rows = conn.execute(f"""
                    SELECT evaluation_date, batch_id, COUNT(*) AS c
                    FROM evaluations ev
                    {where}
                    GROUP BY evaluation_date, batch_id
                """, batch_params).fetchall()

        # 2) 직원 목록 + 평가 건수 (data blob 미적재) — get_matrix_meta와 동일하게 전체 기준
        with perf_span('meta.sql.employees'):
            emp_where = f'WHERE 1=1{batch_clause}' if batch_clause else ''
            emp_rows = conn.execute(f"""
                SELECT e.employee_id, e.name, e.department, e.position, COUNT(ev.id) AS cnt
                FROM employees e
                INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
                {emp_where}
                GROUP BY e.employee_id
            """, batch_params).fetchall()

            total_evals = conn.execute(
                f"SELECT COUNT(*) FROM evaluations ev{(' WHERE 1=1' + batch_clause) if batch_clause else ''}",
                batch_params
            ).fetchone()[0]
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

    # 20_09 §3.2: 직원 1명당 최대 4회 get_real_id()(락+로깅) → 매핑 스냅샷 1회 + 로컬 조회.
    # 결과값은 동일하다(_make_real_id_resolver 주석 참조).
    _dr = _make_real_id_resolver(_get_pseudo_mgr()) if enrich else None
    with perf_span('meta.employees', enrich=bool(enrich), rows=len(emp_rows)):
        employees = []
        for emp_id, name, dept, pos, cnt in emp_rows:
            entry = {
                'employee_id': emp_id,
                'department': dept,
                'position': pos,
                'evaluation_count': cnt,
                'employee_name': name,
            }
            if _dr:
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
    batch_ids = options.get('batch_ids')

    row_cells = {}
    col_cells = {}

    for item in all_items:
        ev = item['evaluation']
        if batch_ids and ev.get('batch_id') not in batch_ids:
            continue
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
    batch_ids = options.get('batch_ids')
    if batch_ids:
        all_items = [it for it in all_items if it['evaluation'].get('batch_id') in batch_ids]
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
            sent_scores_list = _get_sentence_level_scores(doc, corrections=eval_corr, sentence_cache=ev.get('sentence_emotion_cache'), field=ev.get('evaluation_document_field'))
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


# ─────────────────────────────────────────────────────────────────────────────
# 연도별 긍정/부정 추이 그래프 (계획서 plans/2026/08/12_01_sentiment-trend)
# ─────────────────────────────────────────────────────────────────────────────

TREND_GRAPH_DIR_NAME = '그래프'

# metric 키 → (화면 표기, 집계 기준). '단어' 기준은 워드클라우드와 동일하게
# score >= 0 을 긍정으로 묶는다(중립 단어가 긍정에 포함) — save_to_deploy 의
# wf_positive/wf_negative 와 같은 경계를 쓰지 않으면 그래프와 이미지가 어긋난다.
TREND_METRICS = {
    'sentence_cnt':   {'label': '문장 수',        'unit_suffix': '건',   'basis': 'sentence'},
    'word_freq':      {'label': '단어 수(빈도)',  'unit_suffix': '회',   'basis': 'word'},
    'word_uniq':      {'label': '단어 종류 수',   'unit_suffix': '종',   'basis': 'word'},
    'word_weighted':  {'label': '감정 가중 단어량', 'unit_suffix': '',   'basis': 'word'},
    'sentence_power': {'label': '감정 강도 합',   'unit_suffix': '',     'basis': 'sentence'},
}

TREND_POSITIVE_COLOR = '#28a745'
TREND_NEGATIVE_COLOR = '#dc3545'

# 차트 디자인 토큰 — Material Tailwind 라인 차트 규격
# (grid #dddddd strokeDashArray:5, 축 라벨 #616161 12px, 흰 카드 위 회색 캔버스)
TREND_CANVAS_COLOR = '#f1f5f9'
TREND_CARD_COLOR = '#ffffff'
TREND_GRID_COLOR = '#dddddd'
TREND_LABEL_COLOR = '#616161'
TREND_TITLE_COLOR = '#1e293b'


def _trend_sentence_counts(items, corrections_map=None):
    """items 안의 문장을 극성별로 집계한다.

    반환: (긍정 문장 수, 부정 문장 수, 긍정 강도 합, 부정 강도 합)
    중복 문장은 save_to_deploy 와 동일하게 앞 80자 기준으로 1회만 센다.
    점수 0(중립)은 어느 쪽에도 넣지 않는다.
    """
    pos_cnt = neg_cnt = 0
    pos_power = neg_power = 0.0
    seen = set()
    for item in items:
        ev = item['evaluation']
        doc = ev.get('evaluation_document', '') or ev.get('evaluation_document_original', '')
        if not doc:
            continue
        eval_corr = corrections_map.get(ev.get('_db_id'), {}) if corrections_map else {}
        sent_scores_list = _get_sentence_level_scores(
            doc, corrections=eval_corr,
            sentence_cache=ev.get('sentence_emotion_cache'),
            field=ev.get('evaluation_document_field'))
        for sent, sent_score, _pos, _neg, _neutral in sent_scores_list:
            if not sent:
                continue
            text_key = sent[:80]
            if text_key in seen:
                continue
            seen.add(text_key)
            if sent_score > 0:
                pos_cnt += 1
                pos_power += abs(sent_score)
            elif sent_score < 0:
                neg_cnt += 1
                neg_power += abs(sent_score)
    return pos_cnt, neg_cnt, round(pos_power, 4), round(neg_power, 4)


def _trend_word_counts(items, options, corrections_map=None):
    """items 안의 단어를 극성별로 집계한다.

    반환: dict(freq/uniq/weighted 각각 (긍정, 부정))
    극성 경계는 save_to_deploy 와 동일(>= 0 긍정 / < 0 부정) — 중립 단어는 긍정에 포함된다.
    """
    options = options or {}
    word_data = extract_words(items,
                              wordcloud_pos=options.get('wordcloud_pos', ['Noun']),
                              remove_profanity=options.get('remove_profanity', False))
    wf_all = word_data['word_frequency']
    empty = {'freq': (0, 0), 'uniq': (0, 0), 'weighted': (0.0, 0.0)}
    if not wf_all:
        return empty
    word_scores = calculate_word_scores(items, wf_all, corrections_map=corrections_map)
    pos_freq = neg_freq = 0
    pos_uniq = neg_uniq = 0
    pos_w = neg_w = 0.0
    for word, freq in wf_all.items():
        score = word_scores.get(word, 0)
        if score >= 0:
            pos_freq += freq
            pos_uniq += 1
            pos_w += freq * abs(score)
        else:
            neg_freq += freq
            neg_uniq += 1
            neg_w += freq * abs(score)
    return {
        'freq': (pos_freq, neg_freq),
        'uniq': (pos_uniq, neg_uniq),
        'weighted': (round(pos_w, 4), round(neg_w, 4)),
    }


def aggregate_sentiment_trend(items, row_field, row_values, metric='sentence_cnt',
                              options=None, corrections_map=None):
    """연도(row_value)별 긍정/부정 집계값을 반환한다.

    반환: {'rows': ['2024','2026'], 'positive': [...], 'negative': [...],
           'metric': metric, 'metric_label': '문장 수', 'skipped_rows': [...]}
    데이터가 없는 연도의 계열값은 None(선 끊김)이며 skipped_rows 에 기록된다.
    """
    if metric not in TREND_METRICS:
        metric = 'sentence_cnt'
    options = options or {}

    rows = [str(v) for v in (row_values or []) if str(v)]
    if not rows:
        collected = set()
        for item in items:
            for v in _extract_row_values(item['evaluation'], row_field):
                if v:
                    collected.add(str(v))
        rows = sorted(collected)
    else:
        rows = sorted(dict.fromkeys(rows))

    basis = TREND_METRICS[metric]['basis']
    positive, negative, skipped = [], [], []

    for row in rows:
        subset = _filter_items_by_row(items, row_field, [row])
        if not subset:
            positive.append(None)
            negative.append(None)
            skipped.append({'row': row, 'reason': '해당 연도 평가 없음'})
            continue
        if basis == 'sentence':
            p_cnt, n_cnt, p_pow, n_pow = _trend_sentence_counts(subset, corrections_map)
            if metric == 'sentence_cnt':
                p, n = p_cnt, n_cnt
            else:
                p, n = p_pow, n_pow
        else:
            wc = _trend_word_counts(subset, options, corrections_map)
            if metric == 'word_freq':
                p, n = wc['freq']
            elif metric == 'word_uniq':
                p, n = wc['uniq']
            else:
                p, n = wc['weighted']
        positive.append(p)
        negative.append(n)
        if not p and not n:
            skipped.append({'row': row, 'reason': '긍정·부정 집계값 0'})

    return {
        'rows': rows,
        'positive': positive,
        'negative': negative,
        'metric': metric,
        'metric_label': TREND_METRICS[metric]['label'],
        'basis': basis,
        'skipped_rows': skipped,
    }


def _trend_series(trend, unit):
    """추이 집계를 표시 단위로 변환한다.

    unit='pct' 는 분모를 (긍정+부정)로 잡는다 — 중립은 분모에서 제외된다.
    분모가 0이거나 데이터가 없는 연도는 None(선 끊김)으로 둔다.
    """
    pos_out, neg_out = [], []
    for p, n in zip(trend['positive'], trend['negative']):
        if p is None or n is None:
            pos_out.append(None)
            neg_out.append(None)
            continue
        if unit == 'pct':
            total = (p or 0) + (n or 0)
            if not total:
                pos_out.append(None)
                neg_out.append(None)
                continue
            pos_out.append(round(p / total * 100, 1))
            neg_out.append(round(n / total * 100, 1))
        else:
            pos_out.append(round(p, 2) if isinstance(p, float) else p)
            neg_out.append(round(n, 2) if isinstance(n, float) else n)
    return pos_out, neg_out


def _save_trend_chart_to_path(trend, output_path, options):
    """aggregate_sentiment_trend 결과를 라인 차트 PNG로 저장. 성공 시 True.

    디자인은 Material Tailwind 라인 차트 규격을 따른다 — 흰 카드, 축선·눈금 제거,
    점선 그리드(#dddddd), 회색 12px 라벨, 부드러운 곡선. 다만 값 라벨과 마커는
    MT 원본(dataLabels:false, markers.size:0)과 달리 유지한다 — 인사처 납품물은
    수치를 읽는 문서라 그래프에 값이 찍혀 있어야 한다(2026-08-12 사용자 결정).

    한글 폰트는 호출부(라우트)에서 _setup_korean_font() 를 1회 실행해 둔다.
    """
    import numpy as np
    import matplotlib.pyplot as plt
    import matplotlib.patheffects as patheffects
    from matplotlib.patches import FancyBboxPatch

    options = options or {}
    unit = options.get('unit', 'pct')
    rows = trend.get('rows') or []
    if not rows:
        return False

    pos_series, neg_series = _trend_series(trend, unit)
    width = int(options.get('width', 800) or 800)
    height = int(options.get('height', 600) or 600)
    metric_label = trend.get('metric_label', '')
    unit_label = '백분율(%)' if unit == 'pct' else '수량'

    def _runs(series):
        """값이 이어지는 구간(인덱스 묶음). 결측 연도에서 끊긴다."""
        out, cur = [], []
        for i, v in enumerate(series):
            if v is None:
                if cur:
                    out.append(cur)
                cur = []
            else:
                cur.append(i)
        if cur:
            out.append(cur)
        return out

    def _smooth(xs, ys):
        """PCHIP 단조 보존 보간 — 점 사이가 실제 값 범위를 넘지 않는다(오버슈트 없음)."""
        if len(xs) < 3:
            return xs, ys
        try:
            from scipy.interpolate import PchipInterpolator
            fx = np.linspace(xs[0], xs[-1], 200)
            return fx, PchipInterpolator(xs, ys)(fx)
        except Exception:
            return xs, ys

    fig = None
    try:
        fig = plt.figure(figsize=(width / 100.0, height / 100.0), dpi=100,
                         facecolor=TREND_CANVAS_COLOR)

        # 흰 카드(둥근 모서리 + 옅은 그림자) — MT 카드 래퍼
        card = FancyBboxPatch(
            (0.03, 0.04), 0.94, 0.92, transform=fig.transFigure,
            boxstyle='round,pad=0,rounding_size=0.018',
            facecolor=TREND_CARD_COLOR, edgecolor='#ececec', linewidth=1, zorder=0)
        card.set_path_effects([patheffects.withSimplePatchShadow(
            offset=(2, -2), alpha=0.10, shadow_rgbFace='#94a3b8')])
        fig.add_artist(card)

        ax = fig.add_axes([0.10, 0.22, 0.86, 0.55])
        ax.set_facecolor(TREND_CARD_COLOR)
        x = list(range(len(rows)))

        def _plot_series(series, color, label, marker):
            labeled = False
            runs = _runs(series)
            # 실선(곡선): 결측 연도에서 끊긴다 — 값이 없다는 사실을 숨기지 않는다
            for run in runs:
                if len(run) < 2:
                    continue
                sx, sy = _smooth(run, [series[i] for i in run])
                ax.plot(sx, sy, color=color, linewidth=3, solid_capstyle='round',
                        label=(None if labeled else label), zorder=3)
                labeled = True
            # 점선: 값이 없는 구간만 이어 준다 — 흐름은 보이되 실선과 겹치지 않게
            for prev_run, next_run in zip(runs, runs[1:]):
                i, j = prev_run[-1], next_run[0]
                ax.plot([i, j], [series[i], series[j]], color=color, linewidth=1.4,
                        alpha=0.5, linestyle=(0, (4, 4)), zorder=2)
            pts = [(i, series[i]) for i in x if series[i] is not None]
            # 마커: 실제 측정 지점(연도)을 표시
            ax.plot([p[0] for p in pts], [p[1] for p in pts], linestyle='none',
                    marker=marker, markersize=8, color=color, markeredgecolor='white',
                    markeredgewidth=1.6, zorder=4, label=(None if labeled else label))

        _plot_series(pos_series, TREND_POSITIVE_COLOR, '긍정', 'o')
        _plot_series(neg_series, TREND_NEGATIVE_COLOR, '부정', '^')

        fmt = (lambda v: f"{v}%") if unit == 'pct' else (lambda v: f"{v}")

        def _label(value, xi, above, color):
            if value is None:
                return
            ax.annotate(fmt(value), (xi, value), textcoords='offset points',
                        xytext=(0, 12 if above else -19), ha='center',
                        fontsize=11, color=color, zorder=5)

        for xi in x:
            vp, vn = pos_series[xi], neg_series[xi]
            # 두 계열이 교차하는 지점에서 라벨이 겹치지 않도록, 위에 있는 쪽 값은
            # 위에 / 아래에 있는 쪽 값은 아래에 붙인다(같으면 긍정을 위로)
            pos_above = True if (vp is None or vn is None) else (vp >= vn)
            _label(vp, xi, pos_above, TREND_POSITIVE_COLOR)
            _label(vn, xi, not pos_above, TREND_NEGATIVE_COLOR)

        ax.set_xticks(x)
        ax.set_xticklabels([str(r) for r in rows])
        ax.set_xlim(-0.35, len(rows) - 0.65)
        if unit == 'pct':
            ax.set_ylim(-8, 114)
            ax.set_yticks([0, 25, 50, 75, 100])
            ax.set_yticklabels(['0%', '25%', '50%', '75%', '100%'])
        else:
            vals = [v for v in list(pos_series) + list(neg_series) if v is not None]
            top = max(vals) if vals else 0
            if top <= 0:
                top = 1
            ax.set_ylim(-top * 0.14, top * 1.30)
            # 건수·종류 수는 정수 지표 — 0.25 같은 눈금이 나오지 않게 한다
            if trend.get('metric') in ('sentence_cnt', 'word_freq', 'word_uniq'):
                from matplotlib.ticker import MaxNLocator
                ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
            # 아래쪽 여백은 값 라벨 자리일 뿐이므로 음수 눈금은 지운다
            ax.set_yticks([t for t in ax.get_yticks() if 0 <= t <= ax.get_ylim()[1]])

        # MT: 축선·눈금 없음, 가로·세로 점선 그리드, 회색 12px 라벨
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.grid(True, which='major', color=TREND_GRID_COLOR,
                linestyle=(0, (5, 5)), linewidth=1)
        ax.set_axisbelow(True)
        ax.tick_params(axis='both', length=0, colors=TREND_LABEL_COLOR,
                       labelsize=12, pad=8)

        ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.13), ncol=2,
                  frameon=False, fontsize=12, handlelength=1.8,
                  handletextpad=0.6, columnspacing=2.4, labelcolor=TREND_LABEL_COLOR)

        title = options.get('title') or '연도별 긍정/부정 추이'
        fig.text(0.07, 0.885, title, fontsize=16, fontweight='bold',
                 color=TREND_TITLE_COLOR, va='center')
        fig.text(0.07, 0.833, f"지표: {metric_label} · 단위: {unit_label}",
                 fontsize=11, color=TREND_LABEL_COLOR, va='center')

        notes = []
        if unit == 'pct':
            notes.append('분모 = 긍정+부정 (중립 제외)')
        if trend.get('basis') == 'word':
            notes.append('단어 기준은 중립 단어를 긍정에 포함(워드클라우드와 동일 기준)')
        if len(rows) >= 3:
            notes.append('연도 사이 곡선은 시각 표현 (실측값 아님)')
        if trend.get('skipped_rows'):
            skipped_names = ', '.join(str(s.get('row')) for s in trend['skipped_rows'])
            notes.append(f'값 없음: {skipped_names}')
        if notes:
            fig.text(0.07, 0.062, ' | '.join(notes), fontsize=8.5,
                     color='#9e9e9e', va='center')

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        fig.savefig(output_path, dpi=100, facecolor=fig.get_facecolor())
        return True
    except Exception as e:
        logger.error("trend_chart_failed error=%s", e, extra={'stage': 'TREND_GRAPH'})
        return False
    finally:
        if fig is not None:
            plt.close(fig)


def save_trend_graph_to_deploy(unified_data, employee_id, row_field, row_values,
                               metric='sentence_cnt', unit='pct', options=None, request_id=''):
    """직원 1명의 연도별 긍정/부정 추이 그래프를 outputs/배포/그래프/ 에 저장한다.

    파일명 앞부분은 save_to_deploy 와 동일한 규칙(safe_name)을 써서 같은 직원의
    워드클라우드 파일과 짝이 맞도록 한다.
    """
    options = dict(options or {})
    output_mode = options.get('output_mode', 'pseudonym')

    logger.info("employee_id=%s metric=%s unit=%s",
                _mask_real_id(str(employee_id)) if employee_id else '', metric, unit,
                extra={'request_id': request_id, 'stage': 'TREND_GRAPH'})

    pseudo_mgr = _get_pseudo_mgr()
    resolved_id = _resolve_to_pseudo(employee_id, pseudo_mgr)
    target_meta = _get_employee_metadata(unified_data, resolved_id)

    include_name = options.get('include_name', True)
    include_id = options.get('include_id', True)

    if output_mode == 'real' and (include_name or include_id):
        real_id = pseudo_mgr.get_real_id(resolved_id)
        real_id = real_id if (real_id and real_id != resolved_id) else None
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
    batch_ids = options.get('batch_ids')
    if batch_ids:
        all_items = [it for it in all_items if it['evaluation'].get('batch_id') in batch_ids]
    if not all_items:
        logger.warning("no_evaluations_for_employee", extra={'request_id': request_id, 'stage': 'TREND_GRAPH'})
        return None

    corrections_map = _load_corrections_map(resolved_id)
    trend = aggregate_sentiment_trend(all_items, row_field, row_values,
                                      metric=metric, options=options,
                                      corrections_map=corrections_map)
    if not trend.get('rows'):
        logger.warning("trend_rows_empty row_field=%s row_values=%s", row_field, row_values,
                       extra={'request_id': request_id, 'stage': 'TREND_GRAPH'})
        return None
    if all(v is None for v in trend['positive']):
        logger.warning("trend_all_empty row_values=%s", row_values,
                       extra={'request_id': request_id, 'stage': 'TREND_GRAPH'})
        return None

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = re.sub(r'[\\/*?:"<>|]', '_', str(deploy_name))
    sub_dir = os.path.join(DEPLOY_OUTPUT_DIR, TREND_GRAPH_DIR_NAME)
    os.makedirs(sub_dir, exist_ok=True)
    path = os.path.join(sub_dir, f"{safe_name}_긍부정그래프.png")

    chart_options = dict(options)
    chart_options['unit'] = unit
    chart_options['title'] = f"{deploy_name} — 연도별 긍정/부정 비율"
    ok = _save_trend_chart_to_path(trend, path, chart_options)
    if not ok or not os.path.exists(path):
        logger.error("trend_graph_failed name=%s", safe_name,
                     extra={'request_id': request_id, 'stage': 'TREND_GRAPH'})
        return None

    rel = os.path.relpath(path, OUTPUTS_DIR_PATH).replace('\\', '/')
    graph_url = f"/outputs/{rel}?v={ts}"
    pos_series, neg_series = _trend_series(trend, unit)

    result = {
        'name': deploy_name,
        'timestamp': ts,
        'graph': graph_url,
        '긍부정그래프': graph_url,
        'metric': trend['metric'],
        'metric_label': trend['metric_label'],
        'unit': unit,
        'rows': trend['rows'],
        'positive': pos_series,
        'negative': neg_series,
        'positive_raw': trend['positive'],
        'negative_raw': trend['negative'],
        'skipped_rows': trend['skipped_rows'],
    }

    _append_trend_graph_to_manifest(result, employee_id, row_field, options)
    logger.info("done graph=%s rows=%s", graph_url, trend['rows'],
                extra={'request_id': request_id, 'stage': 'TREND_GRAPH'})
    return result


def _append_trend_graph_to_manifest(result, employee_id, row_field, options):
    """추이 그래프 결과를 gallery_entries DB에 저장(source='graph')."""
    entry = {
        "id": str(uuid.uuid4()),
        "employee_id": employee_id,
        "deploy_name": result.get('name', ''),
        "batch_title": options.get('batch_title') or None,
        "timestamp": result.get('timestamp', ''),
        "output_mode": options.get('output_mode', 'real'),
        "source": "graph",
        "row_field": row_field,
        "row_values": result.get('rows'),
        "row_combine_all": False,
        "analysis_type": 'trend',
        "options": {
            "metric": result.get('metric'),
            "unit": result.get('unit'),
            "width": options.get('width', 800),
            "height": options.get('height', 600),
        },
        "images": {
            "graph": result.get('graph'),
        },
        "row_results": {},
    }
    try:
        from src.services.gallery_db_service import upsert_entry
        upsert_entry(entry)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Gallery DB write (graph) failed: {e}")


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
