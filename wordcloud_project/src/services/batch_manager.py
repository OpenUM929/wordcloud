"""Batch manager module - handles batch listing and management."""

import os
import json
from datetime import datetime


def get_batch_list(processed_data_dir):
    """
    Get list of available batches from processed data directory.
    
    Args:
        processed_data_dir: Base directory for processed data
        
    Returns:
        list: Batch info list
    """
    batches = []
    batch_dir = os.path.join(processed_data_dir, 'batch')
    
    if not os.path.exists(batch_dir):
        return batches
    
    for item in os.listdir(batch_dir):
        item_path = os.path.join(batch_dir, item)
        if os.path.isdir(item_path) and item.startswith('batch_'):
            summary_path = os.path.join(item_path, 'tmeta', 'batch_summary.json')
            
            if os.path.exists(summary_path):
                try:
                    with open(summary_path, 'r', encoding='utf-8') as f:
                        summary = json.load(f)
                    
                    batch_name = item
                    display_name = batch_name
                    year, month, day, time_str = '', '', '', ''
                    
                    # Parse batch name: batch_YYYYMMDD_X
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
                        
                        batches.append({
                            'name': display_name,
                            'original_name': batch_name,
                            'path': item_path,
                            'employee_count': summary.get('batch_info', {}).get('unique_employees', 0),
                            'created_at': summary.get('batch_info', {}).get('created_at', '').replace('Z', '').split('T')[0]
                        })
                except Exception as e:
                    print(f"Error loading summary for batch {item}: {e}")
                    continue
    
    batches.sort(key=lambda x: x['created_at'], reverse=True)
    return batches


def delete_batch_directory(batch_path):
    """
    Delete a batch directory.

    WARNING: This function only removes the batch directory on disk.
    It does NOT remove the batch's evaluation data from users/*.json files.
    For complete cleanup including user data, use remove_batch_from_all()
    from user_data_manager before calling this function.

    Args:
        batch_path: Path to batch directory

    Returns:
        tuple: (dict result, status_code)
    """
    try:
        if not batch_path or not os.path.exists(batch_path):
            return {'error': '배치 경로를 찾을 수 없습니다.'}, 404
        
        import shutil
        shutil.rmtree(batch_path)
        
        return {'success': True, 'message': '배치 처리 결과가 성공적으로 삭제되었습니다.'}, 200
    except Exception as e:
        return {'error': f'배치 삭제 실패: {str(e)}'}, 500


def load_batch_metadata(processed_data_dir, batch_dir):
    """
    Load metadata for all employees in a batch.
    
    Args:
        processed_data_dir: Base directory for processed data
        batch_dir: Specific batch directory path
        
    Returns:
        list: Metadata list for each employee
    """
    from src.models.metadata_manager import MetadataManager
    
    metadata_manager = MetadataManager(processed_data_dir)
    metadata_list = []
    
    tmeta_path = os.path.join(batch_dir, 'tmeta')
    if not os.path.exists(tmeta_path) or not os.path.isdir(tmeta_path):
        return metadata_list
    
    for file in os.listdir(tmeta_path):
        if file.startswith('employee_') and file.endswith('.json'):
            try:
                employee_id = file.split('_')[1].split('.')[0]
                metadata = metadata_manager.load_employee_metadata(employee_id, batch_dir)
                
                if metadata:
                    metadata_list.append({
                        'employee_id': employee_id,
                        'metadata': metadata
                    })
            except Exception as e:
                print(f"Error loading metadata for file {file}: {e}")
                continue
    
    metadata_list.sort(key=lambda x: x['employee_id'])
    return metadata_list


def get_batch_summary(processed_data_dir, batch_path):
    """
    Get batch summary information.
    
    Args:
        processed_data_dir: Base directory for processed data
        batch_path: Path to batch directory
        
    Returns:
        dict or None: Batch summary
    """
    from src.models.metadata_manager import MetadataManager
    
    metadata_manager = MetadataManager(processed_data_dir)
    return metadata_manager.get_batch_summary(batch_path)


def get_sample_metadata_from_results(session_results, batch_dir, processed_data_dir):
    """
    Get sample metadata from batch processing results.
    
    Args:
        session_results: JSON string of batch results from session (unused, kept for compat)
        batch_dir: Batch directory path
        processed_data_dir: Base directory for processed data
        
    Returns:
        tuple: (dict result, status_code)
    """
    try:
        summary_path = os.path.join(batch_dir, "tmeta", "batch_summary.json")
        if not os.path.exists(summary_path):
            return {'error': 'batch_summary.json을 찾을 수 없습니다.'}, 400
        
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        employee_results = summary.get('employee_results', [])
        
        if not employee_results:
            return {'error': '처리된 직원이 없습니다.'}, 400
        
        from src.models.metadata_manager import MetadataManager
        metadata_manager = MetadataManager(processed_data_dir)
        
        for result in employee_results:
            if result.get('success'):
                metadata = metadata_manager.load_employee_metadata(result['employee_id'], batch_dir)
                
                if metadata:
                    return {
                        'employee_id': result['employee_id'],
                        'metadata': metadata
                    }, 200
        
        return {'error': '성공적으로 처리된 직원이 없습니다.'}, 400
        
    except Exception as e:
        return {'error': str(e)}, 500