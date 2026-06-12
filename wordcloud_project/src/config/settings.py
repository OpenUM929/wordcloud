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