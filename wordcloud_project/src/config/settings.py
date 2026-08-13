"""Configuration settings for the WordCloud application."""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project root directory (wordcloud_project 폴더)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Environment variables
BASE_ROOT = os.getenv('BASE_ROOT', os.getcwd())
MODEL_DIR = os.getenv('MODEL_DIR', 'model')
CONFIGS_DIR = os.getenv('CONFIGS_DIR', 'configs')
OUTPUTS_DIR = os.getenv('OUTPUTS_DIR', 'outputs')
PROCESSED_DATA_DIR = os.getenv('PROCESSED_DATA_DIR', 'processed_data')

# Model paths (PROJECT_ROOT 기준으로 고정 — os.getcwd() 의존 제거)
MODEL_PATH = os.path.abspath(os.path.join(PROJECT_ROOT, '..', '..', 'model', 'kote_for_easygoing_people'))

# HR 도메인 파인튜닝 감정모델(3분류 극성) — 0624 파인튜닝 산출.
# 베이스 KoTE(44감정)는 그대로 두고, 문장 극성 결정만 이 모델로 대체(플래그).
# 안전: 로드/추론 실패 시 자동으로 기존 규칙(override)으로 폴백 → production 무중단.
# 끄려면 USE_HR_SENTIMENT_MODEL=0 (또는 아래 기본값 False로). 켜기 전 dev 실서버 검증 권장.
HR_SENTIMENT_MODEL_PATH = os.path.abspath(os.path.join(PROJECT_ROOT, '..', '..', 'model', 'hr_sentiment_finetuned'))
USE_HR_SENTIMENT_MODEL = os.getenv('USE_HR_SENTIMENT_MODEL', '1') not in ('0', 'false', 'False', '')
# 감정모델 추론 시 장/단점 field 프리픽스는 field 존재 여부로 자동 적용(0707_01·0708_01). field는 신
# 파이프라인 데이터에만 붙어 seed45 배포 세계의 표식이므로 별도 on/off 플래그 불요(perspective_service).

# Configuration file paths
CONFIGS_DIR_PATH = os.path.abspath(os.path.join(PROJECT_ROOT, CONFIGS_DIR))
SENTIMENT_CONFIG_PATH = os.path.join(CONFIGS_DIR_PATH, "sentiment_config.json")
NLP_CONFIG_PATH = os.path.join(CONFIGS_DIR_PATH, "nlp_config.json")
WORDCLOUD_CONFIG_PATH = os.path.join(CONFIGS_DIR_PATH, "wordcloud_config.json")
SARCASM_CONFIG_PATH = os.path.join(CONFIGS_DIR_PATH, "sarcasm_config.json")
PROFANITY_CONFIG_PATH = os.path.join(CONFIGS_DIR_PATH, "profanity_config.json")
EMOTION_CONFIG_PATH = os.path.join(CONFIGS_DIR_PATH, "emotion_config.json")
LEADERSHIP_CONFIG_PATH = os.path.join(CONFIGS_DIR_PATH, "leadership_config.json")
WORD_BOOST_CONFIG_PATH = os.path.join(CONFIGS_DIR_PATH, "word_boost.json")
STOPWORDS_CONFIG_PATH = os.path.join(CONFIGS_DIR_PATH, "stopwords.json")
# 직원 실명 전용 불용어 파일 — PII 이므로 stopwords.json 과 분리, 배포 패키지 제외
# 대상(deploy/build_deploy.ps1 $ExcludeFiles). 카테고리는 항상 '인명' 1개만 담는다.
STOPWORDS_NAMES_CONFIG_PATH = os.path.join(CONFIGS_DIR_PATH, "stopwords_names.json")

# Output directories (PROJECT_ROOT is src/, go up one more level to wordcloud_project/)
OUTPUTS_DIR_PATH = os.path.abspath(os.path.join(PROJECT_ROOT, '..', OUTPUTS_DIR))
PROCESSED_DATA_DIR_PATH = os.path.abspath(os.path.join(PROJECT_ROOT, '..', PROCESSED_DATA_DIR))

# Flask app configuration
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
FLASK_PORT = int(os.getenv('FLASK_PORT', 5001))
FLASK_HOST = os.getenv('FLASK_HOST', '127.0.0.1')

# Application settings
SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key_here')

# Admin settings
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin1234')
PSEUDONYM_MAPPINGS_PATH = os.path.abspath(os.path.join(CONFIGS_DIR_PATH, 'pseudonym_mappings.enc'))
POSITION_HIERARCHY_PATH = os.path.abspath(os.path.join(CONFIGS_DIR_PATH, 'position_hierarchy.json'))

# Plans directory (칸반보드 대상, 다중 프로젝트 지원)
PROJECT_ROOT_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, '..'))
PLANS_DIR = os.getenv('PLANS_DIR', os.path.join(PROJECT_ROOT_DIR, 'plans', '2026'))
PLANS_ROOTS = os.getenv('PLANS_ROOTS', '')
PLANS_ROOTS_LIST = [p.strip() for p in PLANS_ROOTS.split(',') if p.strip()] if PLANS_ROOTS else []

# Processing settings
DEFAULT_WORDCLOUD_POS = ['Noun']
DEFAULT_BACKGROUND_COLOR = 'white'
DEFAULT_WIDTH = 800
DEFAULT_HEIGHT = 600
DEFAULT_MAX_WORDS = 100

# Emotion analysis settings
EMOTION_NAMES = [
    "불평/불만", "환영/호의", "감동/감탄", "지긋지긋", "고마움", "슬픔", "화남/분노", "존경", "기대감", "우쭐댐/무시함",
    "안타까움/실망", "비장함", "의심/불신", "뿌듯함", "편안/쾌적", "신기함/관심", "아껴주는", "부끄러움", "공포/무서움", "절망",
    "한심함", "역겨움/징그러움", "짜증", "어이없음", "없음", "패배/자기혐오", "귀찮음", "힘듦/지침", "즐거움/신남", "깨달음",
    "죄책감", "증오/혐오", "흐뭇함(귀여움/예쁨)", "당황/난처", "경악", "부담/안_내킴", "서러움", "재미없음", "불쌍함/연민", "놀람",
    "행복", "불안/걱정", "기쁨", "안심/신뢰"
]

# Sentiment mapping
SENTIMENT_MAP = {
    '긍정': 'positive',
    '부정': 'negative',
    '중립': 'neutral'
}