"""Batch processing service - coordinates batch operations."""

import json
import threading
from datetime import datetime
from flask import session
from src.config.settings import PROCESSED_DATA_DIR_PATH
from src.services.file_parser import parse_uploaded_file, parse_csv_file, extract_column_info
from src.services.batch_manager import (
    get_batch_list as get_batch_list_manager,
    delete_batch_directory,
    get_sample_metadata_from_results
)
from src.services.batch_events import create_sse_response, create_batch_zip
from src.services.batch_processor import process_batch


# Global state for batch processing progress
_batch_lock = threading.Lock()
_batch_busy = False

batch_processing_state = {
    'current_step': 0,
    'progress': 0,
    'total_employees': 0,
    'processed_employees': 0,
    'success_count': 0,
    'error_count': 0,
    'profanity_employees': [],
    'failed_employees': [],
    'total_rows': 0,
    'processed_rows': 0,
    'status_message': '처리 준비 중...',
    'completed': False
}


def upload_batch_file(request_obj, session_obj):
    """Upload and validate batch file (CSV or Excel) or select inputs folder."""
    import os
    import uuid
    import glob
    import pandas as pd
    
    if 'folder' in request_obj.form and request_obj.form.get('folder'):
        inputs_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'inputs'))
        
        if os.path.isdir(inputs_dir):
            csv_files = glob.glob(os.path.join(inputs_dir, "*.csv"))
            xlsx_files = glob.glob(os.path.join(inputs_dir, "*.xlsx")) + \
                      glob.glob(os.path.join(inputs_dir, "*.xls"))
            all_files = csv_files + xlsx_files
            
            if not all_files:
                return {'error': 'inputs 폴더에 CSV/Excel 파일이 없습니다.'}, 400
            
            common_columns = None
            file_structures = []
            aggregated_preview = []
            total_rows = 0
            
            for idx, file_path in enumerate(all_files):
                try:
                    if file_path.endswith('.csv'):
                        df_sample = pd.read_csv(file_path, nrows=10)
                        df_full = pd.read_csv(file_path)
                    else:
                        df_sample = pd.read_excel(file_path, nrows=10)
                        df_full = pd.read_excel(file_path)
                    
                    total_rows += len(df_full)
                    file_cols = list(df_sample.columns)
                    file_structures.append({
                        'index': idx,
                        'filename': os.path.basename(file_path),
                        'columns': file_cols,
                        'row_count': len(df_full)
                    })
                    
                    if common_columns is None:
                        common_columns = set(file_cols)
                    else:
                        common_columns &= set(file_cols)
                    
                    for _, row in df_sample.head(5).iterrows():
                        row_data = row.replace({float('nan'): None, float('inf'): None, float('-inf'): None}).to_dict()
                        row_data['_source_file'] = os.path.basename(file_path)
                        aggregated_preview.append(row_data)
                except Exception as e:
                    file_structures.append({
                        'index': idx,
                        'filename': os.path.basename(file_path),
                        'error': str(e)
                    })
            
            common_columns = sorted(list(common_columns)) if common_columns else []
            
            if not common_columns:
                return {'error': '파일들 간 공통 컬럼이 없습니다.'}, 400
            
            columns = []
            first_df = None
            for fp in all_files:
                try:
                    if fp.endswith('.csv'):
                        first_df = pd.read_csv(fp)
                    else:
                        first_df = pd.read_excel(fp)
                    break
                except Exception:
                    pass
            
            if first_df is not None:
                for col in common_columns:
                    sample = 'N/A'
                    for val in first_df[col].dropna().head(1):
                        sample = str(val)[:50] if pd.notna(val) else 'N/A'
                        break
                    dtype = str(first_df[col].dtype)
                    if dtype == 'object':
                        col_type = '텍스트'
                    elif 'int' in dtype:
                        col_type = '정수'
                    elif 'float' in dtype:
                        col_type = '실수'
                    else:
                        col_type = '기타'
                    columns.append({'name': col, 'type': col_type, 'sample': sample})
            
            temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../temp'))
            os.makedirs(temp_dir, exist_ok=True)
            
            all_dfs = []
            for file_path in all_files:
                try:
                    if file_path.endswith('.csv'):
                        df = pd.read_csv(file_path)
                    else:
                        df = pd.read_excel(file_path)

                    missing_cols = set(common_columns) - set(df.columns)
                    for col in missing_cols:
                        df[col] = None

                    df = df[common_columns]
                    all_dfs.append(df)
                except Exception:
                    pass
            
            if not all_dfs:
                return {'error': '파일을 읽을 수 없습니다.'}, 400
            
            merged_df = pd.concat(all_dfs, ignore_index=True)
            
            unique_id = str(uuid.uuid4())[:8]
            merged_file_path = os.path.join(temp_dir, f'batch_folder_{unique_id}.csv')
            merged_df.to_csv(merged_file_path, index=False, encoding='utf-8-sig')
            
            if common_columns:
                columns = extract_column_info(merged_df)
            else:
                columns = []
            
            session_obj['csv_file_path'] = merged_file_path
            session_obj['input_type'] = 'folder'
            session_obj['csv_filename'] = os.path.basename(inputs_dir)
            session_obj['csv_rows'] = total_rows
            session_obj['file_structures'] = file_structures
            session_obj['source_files'] = all_files
            
            return {
                'success': True,
                'filename': os.path.basename(inputs_dir),
                'rows': total_rows,
                'input_type': 'folder',
                'columns': columns,
                'file_structures': file_structures,
                'preview_data': aggregated_preview,
                'preview_rows': aggregated_preview[:10]
            }, 200
        else:
            return {'error': '유효한 경로를 선택해주세요.'}, 400
    
    if 'file' not in request_obj.files:
        return {'error': '파일을 선택해주세요.'}, 400
    
    file = request_obj.files['file']
    result, status = parse_uploaded_file(file)
    
    if status == 200:
        unique_id = str(uuid.uuid4())[:8]
        temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../temp'))
        os.makedirs(temp_dir, exist_ok=True)
        
        file_ext = os.path.splitext(file.filename)[1].lower()
        temp_file_path = os.path.join(temp_dir, f'batch_upload_{unique_id}{file_ext}')
        
        file.seek(0)
        file.save(temp_file_path)
        
        session_obj['csv_file_path'] = temp_file_path
        session_obj['input_type'] = 'file'
        session_obj['csv_filename'] = result.get('filename')
        session_obj['csv_rows'] = result.get('rows')
        if 'csv_data' in session_obj:
            del session_obj['csv_data']
    
    return result, status


def upload_csv(request_obj, session_obj):
    """Upload CSV file for analysis."""
    if 'csvFile' not in request_obj.files:
        return {'error': '파일이 없습니다.'}, 400
    
    file = request_obj.files['csvFile']
    result, status = parse_csv_file(file)
    
    if status == 200:
        session_obj['uploaded_csv'] = file.filename
        session_obj['csv_data'] = result.get('df_json')
        session_obj['csv_encoding'] = result.get('encoding')
    
    return result, status


def start_preprocessing(data, session_obj):
    """Start data preprocessing."""
    import os
    
    csv_file_path = session_obj.get('csv_file_path')
    if not csv_file_path or not os.path.exists(csv_file_path):
        return {'error': '업로드된 파일이 없습니다.'}, 400
    
    try:
        import pandas as pd
        from src.modules.data_preprocessing import preprocess_data
        
        df = pd.read_csv(csv_file_path)
        
        user_id_column = data.get('user_id_column')
        if user_id_column is None:
            return {'error': '사용자 ID 열이 선택되지 않았습니다.'}, 400
        
        success = preprocess_data(csv_file_path, user_id_column, PROCESSED_DATA_DIR_PATH)
        
        if success:
            return {'message': '데이터 정제가 완료되었습니다.'}, 200
        else:
            return {'error': '데이터 정제 실패'}, 500
            
    except Exception as e:
        return {'error': f'정제 실패: {str(e)}'}, 500


def get_batch_list():
    """Get list of available batches."""
    return get_batch_list_manager(PROCESSED_DATA_DIR_PATH)


def delete_batch(batch_path):
    """Delete a batch directory."""
    return delete_batch_directory(batch_path)


def _run_batch_process(data, session_data):
    """Run batch processing in background thread.
    
    session_data is a plain dict (not Flask session object)
    to avoid thread-safety issues.
    """
    global batch_processing_state, _batch_busy
    
    try:
        result, status = process_batch(PROCESSED_DATA_DIR_PATH, data, session_data)
        
        if status == 200:
            batch_processing_state['status_message'] = '완료'
            batch_processing_state['progress'] = 100
            batch_processing_state['completed'] = True
    except Exception as e:
        batch_processing_state['status_message'] = f'오류: {str(e)}'
        batch_processing_state['error'] = str(e)
        # 전체 배치 중단 → 작업서 failed 처리
        bid = batch_processing_state.get('batch_id')
        if bid:
            try:
                from src.services.batch_work_order_service import fail_work_order
                fail_work_order(bid)
            except Exception:
                pass
    finally:
        with _batch_lock:
            _batch_busy = False


def process_batch_metadata(data, session_obj):
    """Process batch metadata - coordinates the full batch processing.
    
    Returns immediately with {'success': True, 'status': 'started'}
    and runs the actual processing in a background thread.
    """
    global batch_processing_state, _batch_busy
    
    with _batch_lock:
        if _batch_busy:
            return {'error': '다른 배치 처리가 이미 실행 중입니다.'}, 429
        _batch_busy = True
    
    try:
        batch_processing_state['current_step'] = 0
        batch_processing_state['progress'] = 0
        batch_processing_state['total_employees'] = 0
        batch_processing_state['processed_employees'] = 0
        batch_processing_state['success_count'] = 0
        batch_processing_state['error_count'] = 0
        batch_processing_state['profanity_employees'] = []
        batch_processing_state['failed_employees'] = []
        batch_processing_state['total_rows'] = 0
        batch_processing_state['processed_rows'] = 0
        batch_processing_state['status_message'] = '데이터 로딩 중...'
        batch_processing_state['completed'] = False
        if 'error' in batch_processing_state:
            del batch_processing_state['error']
        if 'batch_dir' in batch_processing_state:
            del batch_processing_state['batch_dir']
        if 'batch_id' in batch_processing_state:
            del batch_processing_state['batch_id']

        # Extract plain dict from Flask session to avoid thread-safety issues
        session_data = {
            'csv_file_path': session_obj.get('csv_file_path'),
            'input_type': session_obj.get('input_type'),
            'csv_filename': session_obj.get('csv_filename'),
            'csv_rows': session_obj.get('csv_rows'),
        }

        # Start background thread for actual processing
        thread = threading.Thread(
            target=_run_batch_process,
            args=(data, session_data),
            daemon=True
        )
        thread.start()

        return {'success': True, 'status': 'started'}, 200
    except Exception as e:
        with _batch_lock:
            _batch_busy = False
        return {'error': str(e)}, 500


def resume_batch_metadata(batch_id, session_obj):
    """작업서 기반으로 중단된 배치를 이어서 처리한다.

    작업서에서 settings/file_info/completed_employees를 로드하여 data와 session을
    재구성한 뒤, 기존 process_batch_metadata 진입점을 재사용한다(별도 스레드 생성 없음).
    """
    import os
    from src.services.batch_work_order_service import (
        get_work_order_by_batch_id, get_completed_employee_ids,
    )

    wo = get_work_order_by_batch_id(batch_id)
    if not wo:
        return {'success': False, 'error': '작업서를 찾을 수 없습니다.'}, 404
    status = wo.get('status')
    if status == 'completed':
        return {'success': False, 'error': '이미 완료된 작업입니다.'}, 400
    if status == 'running':
        return {'success': False, 'error': '현재 처리 중인 작업입니다. 서버가 재시작된 후 다시 시도해주세요.'}, 400

    try:
        settings = json.loads(wo.get('settings') or '{}')
        file_info = json.loads(wo.get('file_info') or '{}')
        completed_employees = get_completed_employee_ids(batch_id)
    except Exception:
        return {'success': False, 'error': '작업서 데이터가 손상되었습니다.'}, 500

    batch_dir = wo.get('batch_dir')

    # CSV 파일 확인: 원본 경로 → batch_dir/original.csv fallback
    csv_path = file_info.get('csv_file_path')
    if not csv_path or not os.path.exists(csv_path):
        fallback = os.path.join(batch_dir, 'original.csv') if batch_dir else None
        if fallback and os.path.exists(fallback):
            csv_path = fallback
        else:
            return {'success': False, 'error': '원본 파일을 찾을 수 없습니다. 데이터를 다시 업로드해주세요.'}, 400

    # session 재구성 (process_batch_metadata가 여기서 session_data를 추출)
    session_obj['csv_file_path'] = csv_path
    session_obj['input_type'] = file_info.get('input_type', 'file')
    session_obj['csv_filename'] = file_info.get('csv_filename')
    session_obj['csv_rows'] = file_info.get('csv_rows')
    session_obj['batch_id'] = batch_id

    # data 재구성 (settings 스냅샷 + resume 플래그)
    data = dict(settings)
    data['resume'] = True
    data['batch_id'] = batch_id
    data['batch_dir'] = batch_dir
    data['completed_employees'] = completed_employees

    return process_batch_metadata(data, session_obj)


def get_sample_metadata(session_obj):
    """Get sample metadata from batch processing results."""
    return get_sample_metadata_from_results(
        None,
        session_obj.get('batch_dir'),
        PROCESSED_DATA_DIR_PATH
    )


def download_batch_results(session_obj):
    """Download batch results as ZIP file."""
    return create_batch_zip(
        session_obj.get('batch_dir'),
        None
    )


def get_processing_events():
    """Get batch processing events via SSE."""
    return create_sse_response(batch_processing_state)


def get_failed_list():
    """Get list of failed employees from failed directory."""
    import os
    import glob

    failed_base = os.path.abspath(os.path.join(os.path.dirname(PROCESSED_DATA_DIR_PATH), 'failed'))
    if not os.path.exists(failed_base):
        return {'success': True, 'data': []}

    result = []
    for date_dir in sorted(os.listdir(failed_base), reverse=True):
        date_path = os.path.join(failed_base, date_dir)
        if not os.path.isdir(date_path):
            continue
        for emp_dir in sorted(os.listdir(date_path)):
            emp_path = os.path.join(date_path, emp_dir)
            if not os.path.isdir(emp_path):
                continue
            reason_file = os.path.join(emp_path, 'reason.txt')
            data_file = os.path.join(emp_path, 'data.csv')
            reason = ''
            if os.path.exists(reason_file):
                with open(reason_file, 'r', encoding='utf-8') as f:
                    reason = f.read().strip()
            result.append({
                'date': date_dir,
                'employee_id': emp_dir.replace('emp_', ''),
                'reason': reason,
                'has_data': os.path.exists(data_file)
            })
    return {'success': True, 'data': result}


def retry_failed_employees(data, session_obj):
    """Retry processing for selected failed employees."""
    global _batch_busy
    
    with _batch_lock:
        if _batch_busy:
            return {'error': '다른 배치 처리가 이미 실행 중입니다.'}, 429
        _batch_busy = True
    
    try:
        import os
        import pandas as pd
        from src.services.batch_processor import process_batch

        batch_processing_state['current_step'] = 0
        batch_processing_state['progress'] = 0
        batch_processing_state['total_employees'] = 0
        batch_processing_state['processed_employees'] = 0
        batch_processing_state['success_count'] = 0
        batch_processing_state['error_count'] = 0
        batch_processing_state['profanity_employees'] = []
        batch_processing_state['total_rows'] = 0
        batch_processing_state['processed_rows'] = 0
        batch_processing_state['status_message'] = '재배치 준비 중...'
        batch_processing_state['completed'] = False

        employee_ids = data.get('employee_ids', [])
        if not employee_ids:
            return {'error': '재처리할 직원 ID가 없습니다.'}, 400

        failed_base = os.path.abspath(os.path.join(os.path.dirname(PROCESSED_DATA_DIR_PATH), 'failed'))
        all_dfs = []

        for emp_id in employee_ids:
            date_dir = data.get('date', '')
            if date_dir:
                emp_dir = os.path.join(failed_base, date_dir, f'emp_{emp_id}')
            else:
                import glob
                matches = glob.glob(os.path.join(failed_base, '*', f'emp_{emp_id}', 'data.csv'))
                if not matches:
                    continue
                emp_dir = os.path.dirname(matches[-1])

            data_file = os.path.join(emp_dir, 'data.csv')
            if os.path.exists(data_file):
                df = pd.read_csv(data_file)
                df['target_employee_id'] = emp_id
                all_dfs.append(df)

        if not all_dfs:
            return {'error': '재처리할 데이터를 찾을 수 없습니다.'}, 400

        merged_df = pd.concat(all_dfs, ignore_index=True)

        import uuid
        temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../temp'))
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f'retry_{uuid.uuid4().hex[:8]}.csv')
        merged_df.to_csv(temp_path, index=False, encoding='utf-8-sig')

        session_obj['csv_file_path'] = temp_path
        session_obj['input_type'] = 'file'
        session_obj['csv_filename'] = f'retry_{"_".join(employee_ids)}'

        mappings = data.get('mappings', {})
        # Retry CSV columns are field names, not original column names.
        # Auto-detect field-to-field mapping from actual CSV columns.
        auto_mappings = {'target_employee_id': 'target_employee_id'}
        for col in merged_df.columns:
            if col != 'target_employee_id':
                auto_mappings[col] = col
        if not mappings:
            mappings = auto_mappings
        else:
            # Ensure at minimum the columns that exist in the retry CSV are mapped
            for col in merged_df.columns:
                if col not in mappings:
                    mappings[col] = col

        retry_data = {
            'mappings': mappings,
            'enableWordcloud': data.get('enableWordcloud', True),
            'background_color': data.get('background_color', 'white'),
            'apply_emotion_colors': data.get('apply_emotion_colors', True),
            'remove_profanity': data.get('remove_profanity', False),
            'enablePreprocessing': data.get('enablePreprocessing', True),
            'target_employee_department': data.get('target_employee_department', '생산부'),
            'target_employee_position': data.get('target_employee_position', '사원'),
        }

        result, status = process_batch(PROCESSED_DATA_DIR_PATH, retry_data, session_obj)

        if status == 200 and result.get('success'):
            import shutil
            for emp_id in employee_ids:
                date_dir = data.get('date', '')
                if date_dir:
                    emp_path = os.path.join(failed_base, date_dir, f'emp_{emp_id}')
                    if os.path.exists(emp_path):
                        shutil.rmtree(emp_path)

        return result, status
    finally:
        with _batch_lock:
            _batch_busy = False