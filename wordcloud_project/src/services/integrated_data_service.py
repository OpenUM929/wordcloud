"""Metadata service - handles metadata generation and management."""

import os
import json
import uuid
import hashlib
from datetime import datetime
from src.config.settings import (
    PROCESSED_DATA_DIR_PATH,
    SENTIMENT_CONFIG_PATH,
    EMOTION_NAMES,
    SENTIMENT_MAP
)
from src.models.integrated_data_manager import IntegratedDataManager
from src.modules.integrated_analysis import calculate_consolidated_analysis
from utils.date_normalize import normalize_eval_date


def load_config():
    """Load sentiment configuration from file."""
    try:
        if os.path.exists(SENTIMENT_CONFIG_PATH):
            with open(SENTIMENT_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}


def save_config(config):
    """Save sentiment configuration to file."""
    try:
        with open(SENTIMENT_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def generate_integrated_data(data):
    """Generate metadata from evaluation data."""
    integrated_data_manager = IntegratedDataManager(PROCESSED_DATA_DIR_PATH)
    
    # Extract data from request
    target_employee_id = data.get('target_employee_id')
    evaluation_document = data.get('evaluation_document')
    evaluator_id = data.get('evaluator_id')
    # 다양한 입력 형식(int 2025, '2025-06-01', '20250601', '250105' 등)을 표준형으로
    # 정규화해 저장한다. DB 컬럼·JSON blob이 동일 값에서 파생되므로 한 곳에서 통일된다.
    evaluation_date = normalize_eval_date(data.get('evaluation_date'))
    remove_profanity = data.get('remove_profanity', True)
    remove_stop_words = data.get('remove_stop_words', True)
    remove_unhealthy = data.get('remove_unhealthy', True)
    remove_special_chars = data.get('remove_special_chars', True)
    enable_wordcloud = data.get('enable_wordcloud', True)
    
    if not target_employee_id or not evaluation_document:
        raise ValueError('대상자 ID와 평가 문서는 필수입니다.')
    
    # Session ID generation
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
    
    # Initial metadata structure
    metadata = {
        "evaluation_id": f"eval-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8]}",
        "session_id": session_id,
        "created_at": datetime.now().isoformat() + 'Z',
        "version": "1.2.0-1to1",
        "target_employee_id": target_employee_id,
        "target_employee_department": data.get('target_employee_department', 'Unknown'),
        "target_employee_position": data.get('target_employee_position', 'Unknown'),
        "target_hierarchy_level": data.get('target_hierarchy_level', 'staff'),
        "evaluation_document": evaluation_document,
        "evaluator_id": evaluator_id,
        "evaluator_department": data.get('evaluator_department', 'Unknown'),
        "evaluator_position": data.get('evaluator_position', 'Unknown'),
        "evaluator_hierarchy_level": data.get('evaluator_hierarchy_level', 'staff'),
        "evaluation_date": evaluation_date,
        "processing_status": {
            "current_step": "input_validation",
            "completed_steps": ["input_validation"],
            "next_step": "data_preprocessing"
        }
    }
    
    # Processing steps will be added here
    
    return metadata


def get_batch_list():
    """Get list of available batches from processed data directory."""
    processed_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../processed_data'))
    batches = []

    if os.path.exists(processed_data_dir):
        batch_dir = os.path.join(processed_data_dir, 'batch')
        if os.path.exists(batch_dir):
            for item in os.listdir(batch_dir):
                item_path = os.path.join(batch_dir, item)
                if os.path.isdir(item_path) and item.startswith('batch_'):
                    summary_path = os.path.join(item_path, 'tmeta', 'batch_summary.json')

                    batch_name = item
                    display_name = batch_name
                    year, month, day, time_str = '', '', '', ''
                    saved_display_name = ''
                    employee_count = 0
                    created_at = ''

                    if len(batch_name) > len('batch_'):
                        date_part = batch_name[len('batch_'):]
                        if len(date_part) >= 8:
                            year = date_part[:4]
                            month = date_part[4:6]
                            day = date_part[6:8]
                            if len(date_part) > 8:
                                time_part = date_part[9:]
                                if len(time_part) == 6:
                                    time_str = f"{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}"

                    if year and month and day:
                        display_name = f"{year}-{month}-{day} {batch_name}"
                        if time_str:
                            display_name += f" ({time_str})"

                    if os.path.exists(summary_path):
                        try:
                            with open(summary_path, 'r', encoding='utf-8') as f:
                                summary = json.load(f)
                            saved_display_name = summary.get('batch_info', {}).get('display_name', '') or ''
                            employee_count = summary.get('batch_info', {}).get('unique_employees', 0)
                            created_at = summary.get('batch_info', {}).get('created_at', '').replace('Z', '').split('T')[0]
                        except Exception as e:
                            print(f"Error loading summary for batch {item}: {e}")

                    batches.append({
                        'name': saved_display_name if saved_display_name else display_name,
                        'original_name': batch_name,
                        'path': item_path,
                        'employee_count': employee_count,
                        'created_at': created_at,
                    })

    # 배치 번호를 기준으로 정렬 (동일 날짜 내에서 큰 번호가 먼저 오도록)
    def batch_sort_key(batch):
        # batch_YYYYMMDD_X 형식에서 날짜와 번호 추출
        original_name = batch['original_name']
        try:
            # batch_YYYYMMDD_X 형식 분석
            parts = original_name.split('_')
            if len(parts) >= 3:
                date_str = parts[1]
                batch_num = int(parts[2])
            else:
                date_str = batch['created_at']
                batch_num = 0
        except:
            date_str = batch['created_at']
            batch_num = 0
        return (date_str, batch_num)

    # 동일 날짜 내에서 배치 번호가 큰 순서대로 정렬
    batches.sort(key=lambda x: (
        x['created_at'], 
        -int(x['original_name'].split('_')[2]) if len(x['original_name'].split('_')) >= 3 else 0
    ), reverse=True)

    # 동일 날짜 내에서 배치 번호가 큰 순서로 정렬된 리스트 생성
    sorted_batches = []
    date_groups = {}
    for batch in batches:
        date = batch['created_at']
        if date not in date_groups:
            date_groups[date] = []
        date_groups[date].append(batch)
    
    # 각 날짜 그룹 내에서 배치 번호 역순으로 정렬
    for date in sorted(date_groups.keys(), reverse=True):
        group = date_groups[date]
        group_sorted = sorted(group, key=lambda x: int(x['original_name'].split('_')[2]) if len(x['original_name'].split('_')) >= 3 else 0, reverse=True)
        sorted_batches.extend(group_sorted)
    
    return sorted_batches


def get_batch_integrated_data(batch_path):
    """Get metadata for a specific batch."""
    integrated_data_manager = IntegratedDataManager(PROCESSED_DATA_DIR_PATH)
    metadata_list = []
    
    tmeta_path = os.path.join(batch_path, 'tmeta')
    if os.path.exists(tmeta_path) and os.path.isdir(tmeta_path):
        for file in os.listdir(tmeta_path):
            if file.startswith('employee_') and file.endswith('.json'):
                try:
                    employee_id = file.split('_')[1].split('.')[0]
                    metadata = integrated_data_manager.load_employee_metadata(employee_id, batch_path)
                    
                    # Process metadata for API response
                    wordcloud_path = metadata.get('wordcloud_path')
                    wordcloud_url = None
                    if wordcloud_path:
                        if wordcloud_path.startswith('word/'):
                            wordcloud_url = f'/api/wordcloud/batch/{os.path.basename(batch_path)}/{wordcloud_path}'
                        elif wordcloud_path.startswith('/outputs/'):
                            wordcloud_url = wordcloud_path
                        elif wordcloud_path.startswith('outputs/'):
                            wordcloud_url = '/' + wordcloud_path
                        else:
                            wordcloud_url = '/outputs/' + os.path.basename(wordcloud_path)
                    
                    profanity_consolidated = metadata.get('consolidated_analysis', {}).get('profanity_consolidated', {})
                    total_profanity = profanity_consolidated.get('total_profanity_count', 0)
                    evaluations_with_profanity = profanity_consolidated.get('evaluations_with_profanity', 0)
                    
                    wordcloud_status = '있음' if wordcloud_url else '없음'
                    
                    overall_sentiment = metadata.get('consolidated_analysis', {}).get('overall_sentiment')
                    if overall_sentiment in SENTIMENT_MAP:
                        overall_sentiment = SENTIMENT_MAP[overall_sentiment]
                    elif overall_sentiment and '?' in overall_sentiment:
                        overall_sentiment = 'neutral'
                    
                    metadata_list.append({
                        'line1': f'직원 ID: {metadata.get("target_employee_id", "Unknown")} | 평가 수: {metadata.get("total_evaluations", 0)} | 감정: {overall_sentiment or "N/A"}',
                        'line2': f'신뢰도: {metadata.get("consolidated_analysis", {}).get("confidence_score", 0):.1%} | 욕설 수: {total_profanity} | 워드클라우드: {wordcloud_status}',
                        'employee_id': metadata.get('target_employee_id', 'Unknown'),
                        'evaluations_count': metadata.get('total_evaluations', 0),
                        'overall_sentiment': overall_sentiment,
                        'confidence_score': metadata.get('consolidated_analysis', {}).get('confidence_score'),
                        'wordcloud_url': wordcloud_url,
                        'wordcloud_info': metadata.get('wordcloud_generation_info'),
                        'nlp_info': metadata.get('consolidated_analysis', {}).get('consolidated_nlp_words'),
                        'created_at': metadata.get('created_at', ''),
                        'file_path': os.path.join(batch_path, file),
                        'metadata': metadata
                    })
                except Exception as e:
                    print(f"Error loading metadata for file {file}: {e}")
                    continue
    
    # Sort by employee ID
    metadata_list.sort(key=lambda x: x['employee_id'])
    
    return metadata_list