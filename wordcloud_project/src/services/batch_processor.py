"""Batch processor module - handles batch metadata processing."""

import os
import json
from datetime import datetime


# 체크포인트 관련 상수
CHECKPOINT_INTERVAL = 1000  # 1000건마다 체크포인트 저장


def save_checkpoint(batch_dir, processed_count, total_count, last_employee_id, employee_results):
    """
    체크포인트 저장 (배치 처리 중 중간 저장)
    
    Args:
        batch_dir: 배치 디렉토리 경로
        processed_count: 처리 완료 수
        total_count: 전체 수
        last_employee_id: 마지막 처리된 직원 ID
        employee_results: 처리 결과 리스트
    """
    checkpoint_dir = os.path.join(batch_dir, "checkpoints")
    os.makedirs(checkpoint_dir, exist_ok=True)
    
    checkpoint_data = {
        'processed_count': processed_count,
        'total_count': total_count,
        'last_employee_id': last_employee_id,
        'timestamp': datetime.now().isoformat(),
        'completed_employees': [r['employee_id'] for r in employee_results if r.get('success')]
    }
    
    checkpoint_file = os.path.join(checkpoint_dir, "latest_checkpoint.json")
    with open(checkpoint_file, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
    
    return checkpoint_file


def load_checkpoint(batch_dir):
    """
    체크포인트 로드 (재개 시 사용)
    
    Args:
        batch_dir: 배치 디렉토리 경로
    
    Returns:
        dict or None: 체크포인트 데이터
    """
    checkpoint_file = os.path.join(batch_dir, "checkpoints", "latest_checkpoint.json")
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def initialize_batch_directory(processed_data_dir):
    """
    Create batch directory with incremented number.

    Args:
        processed_data_dir: Base directory for processed data

    Returns:
        tuple: (batch_dir, batch_num)
    """
    current_date = datetime.now().strftime('%Y%m%d')
    batch_num = 0

    def _in_db(batch_name):
        # 디렉토리가 삭제돼도 DB 레코드가 남아있으면 같은 batch_id 재사용 방지
        try:
            from src.services.batch_work_order_service import get_work_order_by_batch_id
            return get_work_order_by_batch_id(batch_name) is not None
        except Exception:
            return False

    while True:
        batch_name = f"batch_{current_date}_{batch_num}"
        batch_dir = os.path.abspath(os.path.join(processed_data_dir, "batch", batch_name))
        if not os.path.exists(batch_dir) and not _in_db(batch_name):
            break
        batch_num += 1

    os.makedirs(batch_dir, exist_ok=True)
    return batch_dir, batch_num


def group_data_by_employee(df, target_id_column, mappings):
    """
    Group DataFrame rows by employee ID.
    
    Args:
        df: pandas DataFrame
        target_id_column: Column name for employee ID
        mappings: Field to column mappings
        
    Returns:
        dict: {employee_id: [evaluation_data, ...]}
    """
    grouped_data = {}
    
    for _, row in df.iterrows():
        target_id = row[target_id_column]
        if target_id not in grouped_data:
            grouped_data[target_id] = []
        
        evaluation = {}
        for field, column in mappings.items():
            if field != 'target_employee_id' and column in row:
                value = row[column]
                # 문자열 앞뒤 공백 제거
                if isinstance(value, str):
                    value = value.strip()
                evaluation[field] = value
        
        # evaluator_id가 없으면 evaluation_date에서 생성
        if 'evaluator_id' not in evaluation and 'evaluation_date' in evaluation:
            date_str = str(evaluation.get('evaluation_date', '')).replace('-', '')
            evaluation['evaluator_id'] = f"eval-{target_id}-{date_str}"
        
        # evaluator_hierarchy_level 기본값 설정
        if 'evaluator_hierarchy_level' not in evaluation:
            position = evaluation.get('evaluator_position', '')
            if any(p in position for p in ['과장', '팀장', '관리자', '总监', 'manager']):
                evaluation['evaluator_hierarchy_level'] = 'manager'
            else:
                evaluation['evaluator_hierarchy_level'] = 'staff'
        
        grouped_data[target_id].append(evaluation)
    
    return grouped_data


def process_employee_metadata(metadata_manager, employee_id, evaluations, batch_dir, 
                              department, position, mappings, df):
    """
    Process metadata for a single employee.
    
    Args:
        metadata_manager: MetadataManager instance
        employee_id: Employee ID
        evaluations: List of evaluation data
        batch_dir: Batch directory path
        department: Department name
        position: Position title
        mappings: Field mappings
        df: Original DataFrame
        
    Returns:
        tuple: (metadata, success, error_message)
    """
    try:
        metadata = metadata_manager.create_employee_metadata(
            employee_id=employee_id,
            evaluations=evaluations,
            department=department,
            position=position
        )
        
        # Add additional fields from mappings
        if 'target_employee_department' in mappings and mappings['target_employee_department'] in df.columns:
            metadata['target_employee_department'] = df.iloc[0].get(mappings['target_employee_department'], '생산부')

        if 'target_employee_position' in mappings and mappings['target_employee_position'] in df.columns:
            metadata['target_employee_position'] = df.iloc[0].get(mappings['target_employee_position'], '사원')

        # 원래 이름(이름 컬럼이 매핑된 경우) - 가명화 대상이 아니므로 evaluations에서 직접 추출
        if 'target_employee_name' in mappings and evaluations:
            name_val = evaluations[0].get('target_employee_name', '')
            if name_val:
                metadata['target_employee_name'] = str(name_val)
        
        # Stage 2에서 Stage 3/4에서 별도로 저장하므로 여기서는 저장 안 함
        # metadata_path = metadata_manager.save_employee_metadata(metadata, batch_dir)
        
        return metadata, True, None, None
        
    except Exception as e:
        return None, False, str(e), None


def check_profanity_in_metadata(metadata, batch_state):
    """
    Check and track profanity in employee metadata.
    
    Args:
        metadata: Employee metadata dict
        batch_state: Batch processing state dictionary
        
    Returns:
        list: List of profanity words found
    """
    profanity_words = set()
    profanity_sentences = []
    total_count = 0
    
    # Check individual evaluations for detailed sentence-level info
    if 'evaluations' in metadata:
        for eval_data in metadata.get('evaluations', []):
            prof = eval_data.get('profanity_analysis_results', {})
            if not isinstance(prof, dict):
                continue
            count = prof.get('profanity_count', 0)
            detected = prof.get('detected_profanity', [])
            if not isinstance(detected, list):
                detected = []
            if count > 0 and detected:
                total_count += count
                profanity_words.update(detected)
                profanity_sentences.append({
                    'evaluator_id': eval_data.get('evaluator_id', ''),
                    'original_text': prof.get('original_text', ''),
                    'filtered_text': prof.get('filtered_text', ''),
                    'detected_words': detected,
                    'detection_details': prof.get('detection_details', []),
                })
    
    # Check consolidated analysis as fallback
    if not profanity_words and 'consolidated_analysis' in metadata:
        profanity_consolidated = metadata['consolidated_analysis'].get('profanity_consolidated', {})
        if profanity_consolidated.get('total_profanity_count', 0) > 0:
            profanity_words.update(profanity_consolidated.get('profanity_words', []))
            total_count = profanity_consolidated.get('total_profanity_count', 0)
    
    if profanity_words:
        batch_state['profanity_employees'].append({
            'employee_id': metadata.get('target_employee_id'),
            'profanity_count': total_count,
            'profanity_words': list(profanity_words),
            'profanities': list(profanity_words),
            'profanity_sentences': profanity_sentences,
        })
    
    return list(profanity_words)



def calculate_word_scores(metadata, word_freq):
    """
    Calculate sentiment scores for each word based on emotion analysis.
    
    Args:
        metadata: Employee metadata
        word_freq: Word frequency dictionary
        
    Returns:
        dict: {word: score}
    """
    word_scores = {}
    
    for word in word_freq.keys():
        total_score = 0.0
        count = 0
        
        for evaluation in metadata.get("evaluations", []):
            if "nlp_analysis_results" not in evaluation:
                continue
            
            # Get meaningful words
            nlp_result = evaluation.get("nlp_analysis_results", {})
            if "analysis" in nlp_result and "meaningful_words" in nlp_result["analysis"]:
                meaningful_words = nlp_result["analysis"]["meaningful_words"]
            elif "meaningful_words" in nlp_result:
                meaningful_words = nlp_result["meaningful_words"]
            elif "pos_tags" in nlp_result:
                meaningful_words = [w for w, pos in nlp_result["pos_tags"] 
                                   if len(w) > 1 and w not in ['이', '그', '저', '것', '수', '등']]
            else:
                continue
            
            if word not in meaningful_words:
                continue
            
            # Get sentiment scores
            emotion_result = evaluation.get("emotion_analysis_results", {})
            pos_score = 0.0
            neg_score = 0.0
            
            if "analysis" in emotion_result and "base_result" in emotion_result["analysis"]:
                base = emotion_result["analysis"]["base_result"]
                if "mapped" in base and "sentiment_scores" in base["mapped"]:
                    pos_score = base["mapped"]["sentiment_scores"].get("positive", 0.0)
                    neg_score = base["mapped"]["sentiment_scores"].get("negative", 0.0)
            elif "base_model" in emotion_result and "sentiment_scores" in emotion_result["base_model"]:
                pos_score = emotion_result["base_model"]["sentiment_scores"].get("positive", 0.0)
                neg_score = emotion_result["base_model"]["sentiment_scores"].get("negative", 0.0)
            else:
                continue
            
            score = (pos_score - neg_score) * 2.5  # Amplification factor
            total_score += score
            count += 1
        
        word_scores[word] = total_score / count if count > 0 else 0.0
    
    return word_scores


def create_batch_summary(batch_dir, grouped_data, employee_results, 
                         batch_processing_state, processing_config):
    """
    Create and save batch summary.
    
    Args:
        batch_dir: Batch directory path
        grouped_data: Grouped employee data
        employee_results: List of processing results
        batch_processing_state: Processing state dict
        processing_config: Processing configuration
         
    Returns:
        dict: Batch summary
    """
    batch_id = os.path.basename(batch_dir)
    
    batch_summary = {
        'batch_info': {
            'batch_id': batch_id,
            'created_at': datetime.now().isoformat() + 'Z',
            'processed_at': datetime.now().isoformat() + 'Z',
            'unique_employees': len(grouped_data),
            'total_evaluations': sum(len(evals) for evals in grouped_data.values()),
            'success_count': batch_processing_state.get('success_count', 0),
            'error_count': batch_processing_state.get('error_count', 0)
        },
        'metadata_info': {
            'individual_metadata_dir': 'imeta',
            'consolidated_metadata_dir': 'tmeta'
        },
        'employee_ids': list(set(
            er.get('employee_id') or er.get('metadata', {}).get('target_employee_id', '')
            for er in employee_results if er.get('success')
        )),
        'processing_config': processing_config
    }
    
    # Save summary
    summary_path = os.path.join(batch_dir, "tmeta", "batch_summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(batch_summary, f, ensure_ascii=False, indent=2)
    
    return batch_summary


def process_batch(processed_data_dir, data, session_data):
    """
    Main batch processing function.
    
    Args:
        processed_data_dir: Base directory for processed data
        data: Processing configuration dict
        session_data: Session data dict (will be modified)
        
    Returns:
        tuple: (result dict, status_code)
    """
    # Import global state FIRST (must be before any usage)
    from src.services.batch_service import batch_processing_state
    from io import StringIO
    import pandas as pd
    from src.models.metadata_manager import MetadataManager
    import os
    
    # Load data from session file path (병렬 처리)
    csv_file_path = session_data.get('csv_file_path')
    if not csv_file_path or not os.path.exists(csv_file_path):
        return {'error': '업로드된 파일이 없습니다.'}, 400
    
    # 병렬 CSV 로드 (파일 또는 폴더)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import multiprocessing
    
    # Get file count for dynamic worker allocation
    if os.path.isdir(csv_file_path):
        import glob
        csv_files = glob.glob(os.path.join(csv_file_path, "*.csv"))
        xlsx_files = glob.glob(os.path.join(csv_file_path, "*.xlsx")) + \
                    glob.glob(os.path.join(csv_file_path, "*.xls"))
        file_count = len(csv_files) + len(xlsx_files)
    else:
        file_count = 1
    
    cpu_count = min(multiprocessing.cpu_count(), 8)
    if file_count < 3:
        num_workers = 1
    elif file_count < 5:
        num_workers = min(2, cpu_count)
    else:
        num_workers = min(min(file_count, cpu_count), 8)
    
    def load_csv_chunk(args):
        path, ext = args
        try:
            if ext == '.csv':
                return pd.read_csv(path)
            elif ext in ('.xlsx', '.xls'):
                return pd.read_excel(path)
        except Exception as e:
            return None
    
    if os.path.isdir(csv_file_path):
        # 폴더 선택: 폴더 내 모든 CSV 파일 병렬 로드
        import glob
        csv_files = glob.glob(os.path.join(csv_file_path, "*.csv"))
        xlsx_files = glob.glob(os.path.join(csv_file_path, "*.xlsx")) + \
                    glob.glob(os.path.join(csv_file_path, "*.xls"))
        all_files = [(f, os.path.splitext(f)[1].lower()) for f in csv_files + xlsx_files]
        
        if not all_files:
            return {'error': '선택한 폴더에 CSV/Excel 파일이 없습니다.'}, 400
        
        batch_processing_state['current_step'] = 0
        batch_processing_state['status_message'] = f'Stage 1: 폴더에서 {len(all_files)}개 파일 병렬 로드 중...'
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            dfs = list(executor.map(load_csv_chunk, all_files))
        
        df = pd.concat([d for d in dfs if d is not None], ignore_index=True)
    
    else:
        # 단일 파일: chunk 단위로 병렬 로드
        if csv_file_path.endswith('.csv'):
            # Chunk 단위로 읽어서 병렬 처리
            chunk_size = 50000
            try:
                total_rows = sum(1 for _ in open(csv_file_path, 'r', encoding='utf-8')) - 1
            except:
                total_rows = 0
            
            if total_rows > chunk_size:
                batch_processing_state['status_message'] = f'Stage 1: 대용량 CSV ({total_rows}줄) chunk 병렬 로드 중...'
                
                chunks = []
                for chunk in pd.read_csv(csv_file_path, chunksize=chunk_size):
                    chunks.append(chunk)
                
                with ThreadPoolExecutor(max_workers=num_workers) as executor:
                    processed_chunks = list(executor.map(lambda c: c, chunks))
                
                df = pd.concat(processed_chunks, ignore_index=True)
            else:
                df = pd.read_csv(csv_file_path)
        elif csv_file_path.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(csv_file_path)
        else:
            return {'error': '지원되지 않는 파일 형식입니다.'}, 400
    
    # 파일 로드 완료: 5%
    batch_processing_state['progress'] = 5

    # Initialize batch directory (resume 시 기존 디렉토리 재사용)
    _is_resume = bool(data.get('resume'))
    if _is_resume:
        batch_dir = data.get('batch_dir')
        if not batch_dir or not os.path.isdir(batch_dir):
            return {'error': '이어서 작업할 배치 디렉토리를 찾을 수 없습니다.'}, 400
    else:
        batch_dir, batch_num = initialize_batch_directory(processed_data_dir)
        # 원본 CSV 백업 (Resume fallback용) — 단일 파일일 때만
        if os.path.isfile(csv_file_path):
            try:
                import shutil
                shutil.copy2(csv_file_path, os.path.join(batch_dir, "original.csv"))
            except Exception:
                pass

    batch_id = os.path.basename(batch_dir)
    batch_processing_state['batch_id'] = batch_id

    # Get mappings
    mappings = data.get('mappings', {})
    target_id_column = mappings.get('target_employee_id')
    
    if not target_id_column:
        return {'error': '대상자 ID 필드가 매핑되지 않았습니다.'}, 400
    
    # Group data by employee
    grouped_data = group_data_by_employee(df, target_id_column, mappings)
    
    # Always pseudonymize all PII fields (no user checkbox needed)
    pseudonym_fields = data.get('pseudonym_fields', [])
    forced_pseudo = [
        'target_employee_id', 'evaluator_id',
        'target_employee_department', 'target_employee_position',
        'evaluator_department', 'evaluator_position',
    ]
    for f in forced_pseudo:
        if f not in pseudonym_fields:
            pseudonym_fields.append(f)
    data['pseudonym_fields'] = pseudonym_fields
    _pseudo_mgr = None
    if pseudonym_fields:
        from src.config.settings import ADMIN_PASSWORD, PSEUDONYM_MAPPINGS_PATH
        from src.modules.pseudonym_manager import PseudonymManager
        _pseudo_mgr = PseudonymManager(PSEUDONYM_MAPPINGS_PATH, ADMIN_PASSWORD)
        
        # Re-key grouped_data if target_employee_id is pseudonymized
        if 'target_employee_id' in pseudonym_fields:
            new_grouped_data = {}
            for emp_id in list(grouped_data.keys()):
                pseudo_id = _pseudo_mgr.get_pseudonym(str(emp_id))
                new_grouped_data[pseudo_id] = grouped_data[emp_id]
            grouped_data = new_grouped_data
        
        # Apply pseudonyms to evaluation dicts
        for emp_id in grouped_data:
            grouped_data[emp_id] = [
                _pseudo_mgr.apply_pseudonyms_to_dict(ev, pseudonym_fields)
                for ev in grouped_data[emp_id]
            ]
    
    # 작업서(Work Order) 생성/연결 — 새 배치만 생성, resume 시 기존 작업서 재사용
    from src.services.batch_work_order_service import (
        create_work_order, update_work_order_progress, complete_work_order,
        add_completed_employees,
    )
    prior_completed = set()
    if _is_resume:
        prior_completed = set(str(e) for e in data.get('completed_employees', []))
    else:
        _settings_snapshot = {
            k: v for k, v in data.items()
            if k not in ('resume', 'batch_dir', 'completed_employees', 'batch_id')
        }
        _file_info_snapshot = {
            'csv_file_path': session_data.get('csv_file_path'),
            'csv_filename': session_data.get('csv_filename'),
            'csv_rows': session_data.get('csv_rows'),
            'input_type': session_data.get('input_type'),
        }
        try:
            create_work_order(batch_id, batch_dir, _settings_snapshot,
                              _file_info_snapshot, total_employees=len(grouped_data))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f'Work order 생성 실패: {e}')

    # Initialize metadata manager
    metadata_manager = MetadataManager(processed_data_dir)
    
    # Import concurrent.futures for parallel processing
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import multiprocessing
    
    # Get number of workers based on data amount (employee count)
    employee_count = len(grouped_data)
    cpu_count = min(multiprocessing.cpu_count(), 8)
    
    if employee_count < 10:
        num_workers = 1
    elif employee_count < 50:
        num_workers = min(2, cpu_count)
    elif employee_count < 100:
        num_workers = min(4, cpu_count)
    elif employee_count < 500:
        num_workers = min(6, cpu_count)
    else:
        num_workers = cpu_count
    
    batch_processing_state['status_message'] = f'병렬 처리 시작 (직원: {employee_count}명, workers: {num_workers})'
    
    # ============================================================
    # Stage 2: Pre-init (순차) - 분석기 사전 초기화
    # ============================================================
    batch_processing_state['status_message'] = 'Stage 2: 분석기 초기화 중...'
    batch_processing_state['current_step'] = 1
    
    try:
        from src.modules.nlp_analysis import NLPAnalysis
        from src.modules.stopword_manager import get_stopword_manager
        from src.config.settings import NLP_CONFIG_PATH, CONFIGS_DIR_PATH
        
        nlp_analyzer = NLPAnalysis.get_instance(NLP_CONFIG_PATH)
        stopword_mgr = get_stopword_manager(os.path.join(CONFIGS_DIR_PATH, 'stopwords.json'))
        
        batch_processing_state['status_message'] = 'Stage 2 완료: 분석기 초기화 성공'
        batch_processing_state['progress'] = 10
    except Exception as e:
        error_msg = f'분석기 초기화 실패: {str(e)}'
        batch_processing_state['status_message'] = f'Stage 2 실패: {error_msg}'
        batch_processing_state['progress'] = 10
        employee_results = [
            {'employee_id': emp_id, 'error': error_msg, 'success': False}
            for emp_id in grouped_data.keys()
        ]
        batch_processing_state['current_step'] = 1
        pre_init_success = False
    else:
        batch_processing_state['current_step'] = 1
        batch_processing_state['progress'] = 10
        pre_init_success = True
        employee_results = []
    
    def process_single_employee(args):
        """단일 직원 처리 함수 (병렬용)"""
        employee_id, evaluations = args
        try:
            metadata, success, error, _ = process_employee_metadata(
                metadata_manager, employee_id, evaluations, batch_dir,
                data.get('target_employee_department', '생산부'),
                data.get('target_employee_position', '사원'),
                mappings, df
            )
            if success:
                if _pseudo_mgr:
                    meta_fields = [f for f in pseudonym_fields
                                   if f in ('target_employee_department', 'target_employee_position')]
                    if meta_fields:
                        metadata = _pseudo_mgr.apply_pseudonyms_to_dict(metadata, meta_fields)
                return {
                    'employee_id': employee_id,
                    'metadata': metadata,
                    'success': True,
                    'error': None
                }
            else:
                return {
                    'employee_id': employee_id,
                    'metadata': None,
                    'success': False,
                    'error': error
                }
        except Exception as e:
            return {
                'employee_id': employee_id,
                'metadata': None,
                'success': False,
                'error': str(e)
            }
    
    # 직원별 즉시 DB 저장용 (crash-safe resume: 메타 생성 즉시 영구 저장)
    from src.services.user_data_manager import upsert

    # Prepare data for parallel processing
    employee_items = list(grouped_data.items())

    # Resume: 이미 완료된 직원 제외 (가명화 이후의 pseudo_id 기준)
    if _is_resume and prior_completed:
        employee_items = [
            item for item in employee_items if str(item[0]) not in prior_completed
        ]

    # 작업서 진행 추적: 저장 완료 직원 수(_persisted_count)와 아직 items 테이블에
    # 기록하지 않은 신규 직원 ID 델타(_pending_persisted)를 관리한다.
    _persisted_count = 0
    _pending_persisted = []

    def _flush_work_order():
        """저장된 신규 직원만 items 테이블에 append + 헤더 카운트 갱신 (O(델타))."""
        nonlocal _pending_persisted
        try:
            if _pending_persisted:
                add_completed_employees(batch_id, _pending_persisted)
                _pending_persisted = []
            update_work_order_progress(
                batch_id,
                processed_employees=len(prior_completed) + _persisted_count,
                success_count=len(prior_completed) + _persisted_count,
                error_count=sum(1 for r in employee_results if not r.get('success')),
                total_rows=len(df),
            )
        except Exception:
            pass

    if pre_init_success:
        total_employee_count = len(employee_items)
        batch_processing_state['status_message'] = f'메타데이터 생성 중 (0/{total_employee_count})'

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_employee = {
                executor.submit(process_single_employee, item): item[0] 
                for item in employee_items
            }
            
            completed = 0
            for future in as_completed(future_to_employee):
                result = future.result()
                if result['success']:
                    check_profanity_in_metadata(result['metadata'], batch_processing_state)
                    # 직원별 즉시 DB 영구 저장 — 이 직원이 완료된 즉시 저장되므로,
                    # 이후 작업서에 '완료'로 기록되는 직원은 반드시 DB에 존재한다 (crash-safe).
                    _persisted = False
                    try:
                        _meta = result['metadata'] or {}
                        _eid = result['employee_id'] or _meta.get('target_employee_id')
                        if _eid:
                            upsert(_eid, _meta, _meta.get('evaluations', []), batch_id)
                            _persisted = True
                    except Exception as _ue:
                        import logging
                        logging.getLogger(__name__).warning(
                            f'직원 DB 저장 실패({result["employee_id"]}): {_ue}'
                        )
                    if _persisted:
                        _persisted_count += 1
                        _pending_persisted.append(_eid)
                    employee_results.append({
                        'employee_id': result['employee_id'],
                        'metadata': None,   # 저장 완료 후 메모리 해제 (이후 미사용)
                        'metadata_path': None,
                        'success': True,
                        'persisted': _persisted
                    })
                else:
                    employee_results.append({
                        'employee_id': result['employee_id'],
                        'error': result['error'],
                        'success': False
                    })
                
                completed += 1
                # 10% ~ 50%: 메타데이터 생성 단계
                batch_processing_state['progress'] = int(10 + (completed / total_employee_count) * 40)
                if completed % 10 == 0 or completed == total_employee_count:
                    batch_processing_state['status_message'] = f'메타데이터 생성 중 ({completed}/{total_employee_count})'
                    # 작업서 flush (10명 단위) — 신규 저장 직원만 items 테이블에 append.
                    # 이어서 시작 시 items 테이블을 skip 대상으로 사용 (O(델타), 대용량 안전).
                    _flush_work_order()

                if completed % CHECKPOINT_INTERVAL == 0:
                    last_employee = result['employee_id']
                    save_checkpoint(
                        batch_dir, completed, len(employee_items),
                        last_employee, employee_results
                    )
                    batch_processing_state['status_message'] = f'체크포인트 저장 완료 ({completed}/{total_employee_count})'
        
        save_checkpoint(
            batch_dir, len(employee_results), len(employee_items),
            employee_results[-1]['employee_id'] if employee_results else None,
            employee_results
        )
        
        batch_processing_state['status_message'] = f'Stage 3 완료: 메타데이터 생성 ({len(employee_results)}명)'
        batch_processing_state['current_step'] = 2
        batch_processing_state['progress'] = 50
    
    # 실패한 직원 추적
    failed_employees = [r for r in employee_results if not r['success']]
    batch_processing_state['failed_employees'] = [
        {'employee_id': r['employee_id'], 'error': r.get('error', '알 수 없는 오류')}
        for r in failed_employees
    ]
    batch_processing_state['error_count'] = len(failed_employees)
    
    # 실패 데이터 저장
    if failed_employees:
        from datetime import datetime
        failed_dir_base = os.path.abspath(os.path.join(os.path.dirname(processed_data_dir), 'failed', datetime.now().strftime('%Y%m%d')))
        os.makedirs(failed_dir_base, exist_ok=True)
        
        for r in failed_employees:
            emp_id = r['employee_id']
            emp_dir = os.path.join(failed_dir_base, f'emp_{emp_id}')
            os.makedirs(emp_dir, exist_ok=True)
            
            # 실패 원인 저장
            with open(os.path.join(emp_dir, 'reason.txt'), 'w', encoding='utf-8') as f:
                f.write(r.get('error', '알 수 없는 오류'))
            
            # 원본 데이터 저장
            if emp_id in grouped_data:
                emp_df = pd.DataFrame(grouped_data[emp_id])
                emp_df.to_csv(os.path.join(emp_dir, 'data.csv'), index=False, encoding='utf-8-sig')
    
    # ============================================================
    # Stage 4: DB 저장 (employees + evaluations)
    # ============================================================
    successful_results = [r for r in employee_results if r['success']]
    total_successful = len(successful_results)

    batch_processing_state['status_message'] = f'Stage 4: DB 저장 완료 ({total_successful}명)'
    batch_processing_state['current_step'] = 3
    batch_processing_state['progress'] = 60

    # 직원별 DB 저장(upsert)은 Stage 3 루프에서 완료 즉시 수행됨 (crash-safe).
    # 여기서는 상태/카운트만 정리한다.
    batch_id = os.path.basename(batch_dir)

    batch_processing_state['total_employees'] = len(grouped_data)
    batch_processing_state['processed_employees'] = len(employee_results)
    batch_processing_state['success_count'] = total_successful
    batch_processing_state['error_count'] = sum(1 for r in employee_results if not r['success'])
    batch_processing_state['total_rows'] = len(df)
    batch_processing_state['status_message'] = f'Stage 4 완료: DB 저장 ({total_successful}명)'
    batch_processing_state['current_step'] = 4
    batch_processing_state['progress'] = 100
    batch_processing_state['completed'] = True
    batch_processing_state['batch_dir'] = batch_dir

    # Stage 5: 욕설 데이터 DB 저장
    profanity_employees = batch_processing_state.get('profanity_employees', [])
    if profanity_employees:
        try:
            from src.services.profanity_db_service import save_batch_profanity
            save_batch_profanity(batch_id, profanity_employees)
            batch_processing_state['status_message'] = f'Stage 5 완료: 욕설 데이터 저장 ({len(profanity_employees)}명)'
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f'Profanity DB save failed: {e}')

    session_data['batch_dir'] = batch_dir

    # 작업서 완료 처리 (남은 델타 flush 후 status=completed)
    try:
        _flush_work_order()
        complete_work_order(batch_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f'Work order 완료 처리 실패: {e}')

    return {
        'success': True,
        'batch_dir': batch_dir,
        'batch_id': batch_id,
    }, 200