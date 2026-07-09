"""Batch processor module - handles batch metadata processing."""

import os
import json
import multiprocessing
import psutil
import threading
import time
from datetime import datetime


# 체크포인트 관련 상수
CHECKPOINT_INTERVAL = 1000  # 1000건마다 체크포인트 저장
SKIP_DETAIL_CAP = 10        # 중복 스킵 상세 목록 보존 상한(총계는 전수 집계)

# 워커 산정 상수 (모델 메모리 크기는 PC 무관, GPU 용량은 매 실행 시 실측)
MODEL_VRAM_RESERVE_MB = 2300   # KoTE 공유 1개(~1.8GB) + Sarcasm(~0.5GB)
VRAM_PER_WORKER_MB = 250       # 워커 1개당 배치 추론 텐서 예상치
GPU_OS_RESERVE_MB = 1024       # GPU OS/디스플레이 예약
GPU_SAFETY_RATIO = 0.20        # 전체 VRAM의 20% 추가 예비


class VRAMMonitor:
    """배치 처리 중 GPU VRAM 사용량 자동 모니터링 및 로깅"""

    def __init__(self, batch_dir):
        self.batch_dir = batch_dir
        self.log_path = os.path.join(batch_dir, "vram_monitor.log")
        self.vram_records = []
        self.monitoring = False
        self.monitor_thread = None

    def start(self):
        """배경 모니터링 시작"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop(self):
        """배경 모니터링 종료"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        self._write_summary()

    def _monitor_loop(self):
        """1초마다 VRAM 사용량 기록"""
        try:
            import torch
            if not torch.cuda.is_available():
                return

            start_time = time.time()
            while self.monitoring:
                try:
                    free_mb, total_mb = (x / (1024 ** 2) for x in torch.cuda.mem_get_info())
                    used_mb = total_mb - free_mb
                    elapsed_sec = time.time() - start_time
                    self.vram_records.append({
                        "elapsed_sec": elapsed_sec,
                        "used_mb": used_mb,
                        "total_mb": total_mb,
                        "free_mb": free_mb
                    })
                except Exception:
                    pass
                time.sleep(1)
        except ImportError:
            pass

    def _write_summary(self):
        """모니터링 결과를 로그 파일에 저장"""
        if not self.vram_records:
            return

        max_used = max(r["used_mb"] for r in self.vram_records)
        min_used = min(r["used_mb"] for r in self.vram_records)
        avg_used = sum(r["used_mb"] for r in self.vram_records) / len(self.vram_records)
        total_vram = self.vram_records[0]["total_mb"]

        with open(self.log_path, 'w', encoding='utf-8') as f:
            f.write("=== GPU VRAM 모니터링 결과 ===\n\n")
            f.write(f"총 VRAM: {total_vram:.0f}MB\n")
            f.write(f"피크 사용량: {max_used:.0f}MB ({max_used/total_vram*100:.1f}%)\n")
            f.write(f"평균 사용량: {avg_used:.0f}MB ({avg_used/total_vram*100:.1f}%)\n")
            f.write(f"최소 사용량: {min_used:.0f}MB ({min_used/total_vram*100:.1f}%)\n")
            f.write(f"모니터링 구간: {self.vram_records[-1]['elapsed_sec']:.1f}초\n\n")

            f.write("--- 시계열 데이터 (1초 간격) ---\n")
            f.write("경과시간(초) | 사용량(MB) | 여유(MB) | 사용률(%)\n")
            f.write("-" * 50 + "\n")
            for r in self.vram_records:
                pct = r["used_mb"] / total_vram * 100
                f.write(f"{r['elapsed_sec']:>8.1f}s | {r['used_mb']:>8.0f}   | {r['free_mb']:>7.0f}  | {pct:>6.1f}%\n")


def _calc_adaptive_workers(employee_count=0):
    """CPU/RAM/VRAM 실측값 기반 워커 수 동적 계산 (PC마다 자동으로 달라짐)"""
    cpu_cores = multiprocessing.cpu_count()
    ram_gb = psutil.virtual_memory().available / (1024 ** 3)
    gpu_ok = False
    vram_worker_cap = 0
    try:
        import torch
        if torch.cuda.is_available():
            free_vram_mb, total_vram_mb = (x / (1024 ** 2) for x in torch.cuda.mem_get_info())
            safety_available_mb = total_vram_mb - GPU_OS_RESERVE_MB - (total_vram_mb * GPU_SAFETY_RATIO)
            available_for_workers_mb = safety_available_mb - MODEL_VRAM_RESERVE_MB
            if available_for_workers_mb >= VRAM_PER_WORKER_MB:
                gpu_ok = True
                vram_worker_cap = max(2, int(available_for_workers_mb // VRAM_PER_WORKER_MB))
    except ImportError:
        pass

    if gpu_ok:
        # GPU가 실제 병목 → VRAM 여유에서 도출한 상한이 결정
        cpu_worker_cap = max(2, int(cpu_cores * 0.5))
        max_workers = min(cpu_worker_cap, vram_worker_cap)
    else:
        # CPU-only: GIL 제약, 4개 초과는 실익 없음
        max_workers = max(1, int(cpu_cores * 0.15))
        max_workers = min(max_workers, 4)

    if ram_gb < 4:
        max_workers = 1

    if employee_count < 10:
        return min(1, max_workers)
    return max_workers


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


def _extract_rows_from_chunk(chunk, target_id_column, mappings,
                             _pseudo_mgr, pseudonym_fields):
    """청크 DataFrame → [(pseudo_emp_id, json(evaluation)), ...]

    기존 group_data_by_employee의 값 처리(문자열 strip, NaN 보존)를 동일하게 유지하되,
    iterrows 전수 순회 대신 청크 단위 groupby로 그룹핑하고 가명화를 여기서 1회 적용한다.
    """
    out = []
    for raw_id, group in chunk.groupby(target_id_column):
        emp_id = str(raw_id)
        if _pseudo_mgr and 'target_employee_id' in pseudonym_fields:
            emp_id = _pseudo_mgr.get_pseudonym(emp_id)

        for _, row in group.iterrows():  # 소규모 그룹 내부만 iterrows
            evaluation = {}
            for field, column in mappings.items():
                if field != 'target_employee_id' and column in row.index:
                    value = row[column]
                    # pandas NaN/inf 처리 (float('nan') → None, 유효 float → str)
                    if isinstance(value, float):
                        if value != value or value == float('inf') or value == float('-inf'):
                            value = None
                        else:
                            value = str(value)
                    # 문자열 앞뒤 공백 제거
                    if isinstance(value, str):
                        value = value.strip()
                    if value is not None:
                        evaluation[field] = value

            # evaluator_id가 없으면 evaluation_date에서 생성
            if 'evaluator_id' not in evaluation and 'evaluation_date' in evaluation:
                date_str = str(evaluation.get('evaluation_date', '')).replace('-', '')
                evaluation['evaluator_id'] = f"eval-{emp_id}-{date_str}"

            # evaluator_hierarchy_level 기본값 설정
            if 'evaluator_hierarchy_level' not in evaluation:
                position = evaluation.get('evaluator_position', '')
                if any(p in position for p in ['과장', '팀장', '관리자', '总监', 'manager']):
                    evaluation['evaluator_hierarchy_level'] = 'manager'
                else:
                    evaluation['evaluator_hierarchy_level'] = 'staff'

            # 가명화 1회 적용 (이후 metadata dept/pos 후처리 가명화는 삭제됨 — 이중 적용 방지)
            if _pseudo_mgr:
                evaluation = _pseudo_mgr.apply_pseudonyms_to_dict(evaluation, pseudonym_fields)

            out.append((emp_id, json.dumps(evaluation, ensure_ascii=False)))

    return out


def process_employee_metadata(integrated_data_manager, employee_id, evaluations, batch_dir,
                              department, position, mappings):
    """
    Process metadata for a single employee.

    Args:
        integrated_data_manager: IntegratedDataManager instance
        employee_id: Employee ID
        evaluations: List of evaluation data
        batch_dir: Batch directory path
        department: Department name
        position: Position title
        mappings: Field mappings

    Returns:
        tuple: (metadata, success, error_message)
    """
    try:
        metadata = integrated_data_manager.create_employee_integrated_data(
            employee_id=employee_id,
            evaluations=evaluations,
            department=department,
            position=position
        )

        # Add additional fields from this employee's own evaluations
        # (기존 df.iloc[0]은 전체 첫 행을 모든 직원에 적용하는 잠재 버그였음 → 직원별 값으로 교정)
        if evaluations and 'target_employee_department' in evaluations[0]:
            dept = evaluations[0].get('target_employee_department')
            if dept and isinstance(dept, str):
                metadata['target_employee_department'] = dept

        if evaluations and 'target_employee_position' in evaluations[0]:
            pos = evaluations[0].get('target_employee_position')
            if pos and isinstance(pos, str):
                metadata['target_employee_position'] = pos

        # 원래 이름(이름 컬럼이 매핑된 경우) - 가명화 대상이 아니므로 evaluations에서 직접 추출
        if 'target_employee_name' in mappings and evaluations:
            name_val = evaluations[0].get('target_employee_name')
            if name_val and isinstance(name_val, str):
                metadata['target_employee_name'] = name_val
        
        # Stage 2에서 Stage 3/4에서 별도로 저장하므로 여기서는 저장 안 함
        # metadata_path = integrated_data_manager.save_employee_integrated_data(metadata, batch_dir)

        return metadata, True, None, None

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        # evaluations 샘플 추출 (최대 3개)
        eval_samples = []
        for i, ev in enumerate(evaluations[:3]):
            doc = ev.get('evaluation_document', '')[:200]
            eval_id = ev.get('evaluation_id', f'#{i}')
            eval_samples.append(f"  eval_id={eval_id}: document={doc!r}")
        eval_str = '\n'.join(eval_samples)
        error_msg = (
            f"{type(e).__name__}: {e}\n"
            f"Traceback:\n{tb}\n"
            f"Employee ID: {employee_id}\n"
            f"Evaluations count: {len(evaluations)}\n"
            f"Evaluation samples:\n{eval_str}"
        )
        return None, False, error_msg, None


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
            'individual_metadata_dir': 'idata',
            'consolidated_metadata_dir': 'tdata'
        },
        'employee_ids': list(set(
            er.get('employee_id') or er.get('metadata', {}).get('target_employee_id', '')
            for er in employee_results if er.get('success')
        )),
        'processing_config': processing_config
    }
    
    # Save summary
    summary_path = os.path.join(batch_dir, "tdata", "batch_summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(batch_summary, f, ensure_ascii=False, indent=2)
    
    return batch_summary


def _ensure_batch_summary(batch_dir, batch_processing_state, display_name='',
                          skipped_count=0, skipped_detail=None):
    """batch_summary.json 생성 또는 갱신 (display_name 저장용)."""
    summary_path = os.path.join(batch_dir, "tdata", "batch_summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)

    summary = {
        'batch_info': {
            'batch_id': os.path.basename(batch_dir),
            'display_name': display_name if display_name else '',
            'created_at': batch_processing_state.get('created_at', ''),
            'processed_at': datetime.now().isoformat() + 'Z',
            'unique_employees': batch_processing_state.get('total_employees', 0),
            'total_evaluations': batch_processing_state.get('total_rows', 0),
            'success_count': batch_processing_state.get('success_count', 0),
            'error_count': batch_processing_state.get('error_count', 0),
            'skipped_count': skipped_count
        },
        'skipped_evaluations': skipped_detail or [],
        'processing_config': {}
    }

    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return summary


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
    from src.models.integrated_data_manager import IntegratedDataManager
    import os
    
    # Load data from session file path
    csv_file_path = session_data.get('csv_file_path')
    if not csv_file_path or not os.path.exists(csv_file_path):
        return {'error': '업로드된 파일이 없습니다.'}, 400

    from src.services import batch_staging
    CHUNK_SIZE = 10000

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

    # Always pseudonymize all PII fields (no user checkbox needed)
    # 가명화 매니저는 Phase 1 ingest 중 1회 적용되므로 여기서 먼저 준비한다.
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

    # ============================================================
    # Phase 1: CSV 청크 스트리밍 → staging.db ingest (라인 기반 진행, 0~40%)
    # 전체 df를 RAM에 올리지 않고 청크 단위로 읽어 원문 평가를 디스크에 누적한다.
    # ============================================================
    def _count_total_lines(path):
        """단일 CSV의 총 레코드 수(헤더 제외). 1패스, 메모리 미사용."""
        if os.path.isfile(path) and path.endswith('.csv'):
            try:
                with open(path, 'r', encoding='utf-8') as _f:
                    return sum(1 for _ in _f) - 1
            except Exception:
                return 0
        return 0

    def _chunk_iter(path):
        """파일/폴더를 청크 DataFrame으로 순회한다(Excel은 1회 로드 후 슬라이스)."""
        if os.path.isfile(path):
            if path.endswith('.csv'):
                yield from pd.read_csv(path, chunksize=CHUNK_SIZE)
            elif path.endswith(('.xlsx', '.xls')):
                xl = pd.read_excel(path)
                for i in range(0, len(xl), CHUNK_SIZE):
                    yield xl.iloc[i:i + CHUNK_SIZE]
            else:
                raise ValueError('지원되지 않는 파일 형식입니다.')
        else:
            import glob
            files = (glob.glob(os.path.join(path, '*.csv'))
                     + glob.glob(os.path.join(path, '*.xlsx'))
                     + glob.glob(os.path.join(path, '*.xls')))
            if not files:
                raise ValueError('선택한 폴더에 CSV/Excel 파일이 없습니다.')
            for fp in files:
                if fp.endswith('.csv'):
                    yield from pd.read_csv(fp, chunksize=CHUNK_SIZE)
                else:
                    xl = pd.read_excel(fp)
                    for i in range(0, len(xl), CHUNK_SIZE):
                        yield xl.iloc[i:i + CHUNK_SIZE]

    # 파일 분석(라인 수 카운트)도 대용량에선 수 초 소요 → 카운트 전 진행 문구 선설정
    batch_processing_state['current_step'] = 0
    batch_processing_state['progress'] = 3
    batch_processing_state['status_message'] = '데이터 수집 시작 — 파일 분석 중...'

    # GPU VRAM 모니터링 시작
    vram_monitor = VRAMMonitor(batch_dir)
    vram_monitor.start()

    _total_lines = _count_total_lines(csv_file_path)

    staging_conn = batch_staging.open_staging(batch_dir)
    # 처리 중 예외로 종료될 경우 _run_batch_process except 블록이 staging을 정리하도록 경로 기록
    batch_processing_state['_active_staging_dir'] = batch_dir
    emp_id_set = set()          # Phase 2 직원 ID 집합 (문자열만 보관 = 경량)
    _ingested_rows = 0

    from contextlib import nullcontext

    batch_processing_state['current_step'] = 0
    batch_processing_state['progress'] = 5
    if _total_lines:
        batch_processing_state['total_rows'] = _total_lines
        batch_processing_state['status_message'] = f'데이터 수집 중 (0 / {_total_lines:,} 라인)'
    else:
        batch_processing_state['status_message'] = '데이터 수집 중...'

    # 가명화 매핑을 새 ID마다 파일 전체로 재기록하면 O(n²) → 1.9만+ 직원/수백만 행에서
    # Phase 1이 사실상 정지한다. ingest 동안 메모리에만 누적하고 블록 종료 시 1회 저장한다.
    _pseudo_bulk = _pseudo_mgr.bulk_mode() if _pseudo_mgr else nullcontext()

    try:
        with _pseudo_bulk:
            for chunk in _chunk_iter(csv_file_path):
                rows = _extract_rows_from_chunk(chunk, target_id_column, mappings,
                                                _pseudo_mgr, pseudonym_fields)
                if rows:
                    batch_staging.insert_evaluations(staging_conn, rows)
                    for _emp_id, _ in rows:
                        emp_id_set.add(_emp_id)
                _ingested_rows += len(chunk)

                if _total_lines:
                    batch_processing_state['total_rows'] = _total_lines
                    pct = min(_ingested_rows / max(_total_lines, 1), 1.0)
                    batch_processing_state['progress'] = int(5 + pct * 35)
                    batch_processing_state['status_message'] = (
                        f'데이터 수집 중 ({_ingested_rows:,} / {_total_lines:,} 라인)'
                    )
                else:
                    # Excel/폴더: 총량 미상 → 누적 카운트만 표시
                    batch_processing_state['status_message'] = f'데이터 수집 중 ({_ingested_rows:,} 라인)'
                batch_processing_state['processed_rows'] = _ingested_rows  # 기존 필드 재사용
        # with 블록 종료 시 가명화 매핑이 디스크에 1회 flush 된다 (Phase 2/복원이 최신 매핑 사용)
    except Exception as e:
        batch_staging.close_and_remove(staging_conn, batch_dir)
        batch_processing_state.pop('_active_staging_dir', None)
        return {'error': f'데이터 수집 실패: {str(e)}'}, 500

    if _ingested_rows == 0:
        batch_staging.close_and_remove(staging_conn, batch_dir)
        batch_processing_state.pop('_active_staging_dir', None)
        return {'error': '처리할 데이터가 없습니다.'}, 400

    batch_processing_state['progress'] = 40
    batch_processing_state['total_rows'] = _ingested_rows  # 완료 시 실제값 확정
    batch_processing_state['status_message'] = f'데이터 수집 완료: {len(emp_id_set):,}명'

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
                              _file_info_snapshot, total_employees=len(emp_id_set))
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f'Work order 생성 실패: {e}')

    # Initialize metadata manager
    integrated_data_manager = IntegratedDataManager(processed_data_dir)
    
    # Import concurrent.futures for parallel processing
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Get number of workers based on hardware (CPU/RAM/VRAM 실측) and data amount
    employee_count = len(emp_id_set)
    num_workers = _calc_adaptive_workers(employee_count)

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
        batch_processing_state['progress'] = 45
    except Exception as e:
        error_msg = f'분석기 초기화 실패: {str(e)}'
        batch_processing_state['status_message'] = f'Stage 2 실패: {error_msg}'
        batch_processing_state['progress'] = 45
        employee_results = [
            {'employee_id': emp_id, 'error': error_msg, 'success': False}
            for emp_id in emp_id_set
        ]
        batch_processing_state['current_step'] = 1
        pre_init_success = False
    else:
        batch_processing_state['current_step'] = 1
        batch_processing_state['progress'] = 45
        pre_init_success = True
        employee_results = []
        # 조기 batch_summary.json 생성: display_name을 DB 기반 목록보다 먼저 사용 가능하게 함
        _display_name_early = (data.get('batch_display_name') or '').strip()
        _ensure_batch_summary(batch_dir, batch_processing_state, _display_name_early)
    
    def process_single_employee(employee_id):
        """단일 직원 처리 함수 (병렬용) — staging.db에서 원문 평가를 로드한다."""
        try:
            # 워커 스레드당 read 커넥션 1개 재사용 (open/close 반복 제거)
            conn = batch_staging.get_reader(batch_dir)
            evaluations = batch_staging.load_employee_evaluations(conn, employee_id)
            metadata, success, error, _ = process_employee_metadata(
                integrated_data_manager, employee_id, evaluations, batch_dir,
                data.get('target_employee_department', '생산부'),
                data.get('target_employee_position', '사원'),
                mappings
            )
            if success:
                # dept/pos 가명화는 Phase 1 ingest에서 이미 적용됨 → 후처리 가명화 삭제(이중 적용 방지)
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
            import traceback
            tb = traceback.format_exc()
            error_msg = (
                f"process_single_employee failed: {type(e).__name__}: {e}\n"
                f"Traceback:\n{tb}\n"
                f"Employee ID: {employee_id}"
            )
            return {
                'employee_id': employee_id,
                'metadata': None,
                'success': False,
                'error': error_msg
            }
    
    # 직원별 즉시 DB 저장용 (crash-safe resume: 메타 생성 즉시 영구 저장)
    from src.services.user_data_manager import upsert

    # Prepare data for parallel processing (staging에 적재된 직원 ID 집합)
    employee_items = sorted(emp_id_set)

    # Resume: 이미 완료된 직원 제외 (가명화 이후의 pseudo_id 기준)
    if _is_resume and prior_completed:
        employee_items = [
            e for e in employee_items if str(e) not in prior_completed
        ]

    # 작업서 진행 추적: 저장 완료 직원 수(_persisted_count)와 아직 items 테이블에
    # 기록하지 않은 신규 직원 ID 델타(_pending_persisted)를 관리한다.
    _persisted_count = 0
    _pending_persisted = []

    # 핸드오프 코퍼스 인라인 적립 설정 (0622_01) — 배치 시작 시 사전 지정(dest_label).
    # 메타데이터 시점에 이미 계산된 sentence_emotion_cache를 재사용하므로 KoTE 재실행 0.
    _acq_handoff_enabled = bool(data.get('acq_handoff_enabled'))
    _acq_handoff_label = (data.get('acq_handoff_label') or 'default').strip() or 'default'
    _acq_handoff_count = 0
    if _acq_handoff_enabled:
        batch_processing_state['acq_handoff_count'] = 0

    # 판정 패킷 추출 설정 (0623_01) — 기본 활성. 배치 종료 후 1회, 어려운 문장만 자기설명 패킷으로 적립.
    _judgment_enabled = data.get('judgment_extract_enabled', True)
    _judgment_label = (data.get('judgment_label') or 'default').strip() or 'default'

    # 중복(미저장) 평가 집계: 총 건수(전수)와 상세 목록(상위 SKIP_DETAIL_CAP건)
    _skip_total = 0
    _skip_detail = []

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
                total_rows=_ingested_rows,
            )
        except Exception:
            pass

    if pre_init_success:
        total_employee_count = len(employee_items)
        _total_all = len(prior_completed) + len(employee_items) if _is_resume else total_employee_count
        _prior_count = len(prior_completed) if _is_resume else 0
        batch_processing_state['status_message'] = f'분석 처리 중 ({_prior_count:,} / {_total_all:,}명)'

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_employee = {
                executor.submit(process_single_employee, emp_id): emp_id
                for emp_id in employee_items
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
                            _inserted, _skip = upsert(_eid, _meta, _meta.get('evaluations', []), batch_id)
                            _persisted = True
                            if _skip:
                                _skip_total += len(_skip)
                                for s in _skip:
                                    if len(_skip_detail) < SKIP_DETAIL_CAP:
                                        _skip_detail.append(s)
                    except Exception as _ue:
                        import logging
                        logging.getLogger(__name__).warning(
                            f'직원 DB 저장 실패({result["employee_id"]}): {_ue}'
                        )
                    if _persisted:
                        _persisted_count += 1
                        _pending_persisted.append(_eid)
                        # 핸드오프 코퍼스 인라인 적립 (0622_01) — 단일(메인) 스레드 구간이라
                        # 파일 append 동시쓰기 안전. 파일은 x/y/s/e만 담아 db_id 불요.
                        if _acq_handoff_enabled:
                            try:
                                from src.services.acquired_handoff import (
                                    build_records_from_metadata, append_handoff_records)
                                _recs = build_records_from_metadata(_meta)
                                _acq_handoff_count += append_handoff_records(
                                    _acq_handoff_label, batch_id, _recs)
                                batch_processing_state['acq_handoff_count'] = _acq_handoff_count
                            except Exception as _he:
                                import logging
                                logging.getLogger(__name__).warning(
                                    f'핸드오프 적립 실패({_eid}): {_he}')
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
                _display_completed = _prior_count + completed
                # 45% ~ 90%: 분석 처리 단계 (Phase 2)
                batch_processing_state['progress'] = int(45 + (completed / max(total_employee_count, 1)) * 45)
                if completed % 10 == 0 or completed == total_employee_count:
                    batch_processing_state['status_message'] = f'분석 처리 중 ({_display_completed:,} / {_total_all:,}명)'
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
        batch_processing_state['progress'] = 90
    
    # 실패한 직원 추적
    failed_employees = [r for r in employee_results if not r['success']]
    batch_processing_state['failed_employees'] = [
        {
            'employee_id': r['employee_id'],
            'error': r.get('error', '알 수 없는 오류'),
            'error_summary': (r.get('error', '')[:500] + '...') if len(r.get('error', '')) > 500 else r.get('error', ''),
        }
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

            # 실패 원인 저장 (상세 에러 메시지 + traceback)
            error_detail = r.get('error', '알 수 없는 오류')
            with open(os.path.join(emp_dir, 'reason.txt'), 'w', encoding='utf-8') as f:
                f.write(error_detail)

            # 원본 데이터 저장 (staging.db에서 재조회 — grouped_data는 더 이상 없음)
            _emp_evals = []
            try:
                _conn = batch_staging.get_reader(batch_dir)
                _emp_evals = batch_staging.load_employee_evaluations(_conn, emp_id)
            except Exception:
                pass

            if _emp_evals:
                # CSV 형태로 저장
                try:
                    emp_df = pd.DataFrame(_emp_evals)
                    emp_df.to_csv(os.path.join(emp_dir, 'data.csv'), index=False, encoding='utf-8-sig')
                except Exception:
                    pass
                # JSON 형태로도 저장 (evaluations 원문 보존)
                try:
                    with open(os.path.join(emp_dir, 'evaluations.json'), 'w', encoding='utf-8') as f:
                        json.dump(_emp_evals, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
    
    # ============================================================
    # Stage 4: DB 저장 (employees + evaluations)
    # ============================================================
    successful_results = [r for r in employee_results if r['success']]
    total_successful = len(successful_results)

    batch_processing_state['status_message'] = f'Stage 4: DB 저장 완료 ({total_successful}명)'
    batch_processing_state['current_step'] = 3
    batch_processing_state['progress'] = 92

    # 직원별 DB 저장(upsert)은 Stage 3 루프에서 완료 즉시 수행됨 (crash-safe).
    # 여기서는 상태/카운트만 정리한다.
    batch_id = os.path.basename(batch_dir)

    batch_processing_state['total_employees'] = len(emp_id_set)
    batch_processing_state['processed_employees'] = len(employee_results)
    batch_processing_state['success_count'] = total_successful
    batch_processing_state['error_count'] = sum(1 for r in employee_results if not r['success'])
    batch_processing_state['total_rows'] = _ingested_rows
    batch_processing_state['skipped_count'] = _skip_total  # 중복 미저장 평가 총 건수(SSE 자동 전달)
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

    # batch_summary.json 생성 (display_name 저장)
    display_name = (data.get('batch_display_name') or '').strip()
    _ensure_batch_summary(batch_dir, batch_processing_state, display_name,
                          skipped_count=_skip_total, skipped_detail=_skip_detail)

    # 작업서 완료 처리 (남은 델타 flush 후 status=completed)
    try:
        _flush_work_order()
        complete_work_order(batch_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f'Work order 완료 처리 실패: {e}')

    # Stage 6: 판정 패킷 추출 (0623_01) — 배치 종료 후 1회. 영속된 평가를 batch_id로 재로드(db_id 확보,
    # KoTE 재실행 0). 어려운 문장만 자기설명 패킷으로 eval/judgment/<label>/<batch_id>.json에 저장.
    # 마진 3단(0.05/0.10/0.15) 동시 태깅. 실패해도 배치 본류 불방해(핸드오프와 동일 보호).
    if _judgment_enabled:
        try:
            from src.services.judgment_packet_service import (
                build_judgment_packet, save_packet_file)
            _packet, _quar = build_judgment_packet(batch_id=batch_id)
            _packet_path = save_packet_file(_packet, _judgment_label, batch_id)
            batch_processing_state['judgment_count'] = len(_packet['items'])
            batch_processing_state['judgment_bands'] = _packet['_margin']['bands']
            batch_processing_state['judgment_path'] = _packet_path
            batch_processing_state['status_message'] = (
                f"판정 패킷 추출 완료: {len(_packet['items'])}건 → {_packet_path}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f'판정 패킷 추출 실패: {e}')

    # staging 정리: 메인 스레드 잔여 reader 닫고 staging.db(+wal/shm) 삭제
    batch_staging.close_reader()
    batch_staging.close_and_remove(staging_conn, batch_dir)
    batch_processing_state.pop('_active_staging_dir', None)

    # GPU VRAM 모니터링 종료 및 로그 저장
    vram_monitor.stop()

    return {
        'success': True,
        'batch_dir': batch_dir,
        'batch_id': batch_id,
        'vram_log_path': vram_monitor.log_path,
    }, 200