"""Batch events module - handles SSE events and batch result downloads."""

import json
import os
import zipfile
from flask import Response, send_file
from io import BytesIO


def _restore_profanity_employees(prof_emps):
    if not prof_emps:
        return prof_emps
    from src.services.profanity_db_service import _get_pseudo_mgr
    mgr = _get_pseudo_mgr()
    restored = []
    for emp in prof_emps:
        emp = dict(emp)
        eid = emp.get('employee_id', '') or ''
        real = mgr.get_real_id(eid) if eid else ''
        if real and real != eid:
            emp['employee_id'] = real
        sentences = emp.get('profanity_sentences', [])
        if sentences:
            restored_sents = []
            for s in sentences:
                s = dict(s)
                raw_eval = s.get('evaluator_id', '') or ''
                real_eval = mgr.get_real_id(raw_eval) if raw_eval else ''
                if real_eval and real_eval != raw_eval:
                    s['evaluator_id'] = real_eval
                restored_sents.append(s)
            emp['profanity_sentences'] = restored_sents
        restored.append(emp)
    return restored


def stream_batch_events(global_state):
    """
    Generate SSE stream for batch processing events.
    
    Args:
        global_state: Batch processing state dictionary
        
    Yields:
        str: SSE formatted data
    """
    import time
    
    while True:
        data = {
            'step': global_state.get('current_step', 0),
            'progress': global_state.get('progress', 0),
            'status': global_state.get('status_message', ''),
            'unique_employees': global_state.get('total_employees', 0),
            'processed_employees': global_state.get('processed_employees', 0),
            'success_count': global_state.get('success_count', 0),
            'error_count': global_state.get('error_count', 0),
            'total_processed': global_state.get('total_rows', 0),
            'processed_rows': global_state.get('processed_rows', 0),
            'profanity_employees': _restore_profanity_employees(global_state.get('profanity_employees', [])),
            'failed_employees': global_state.get('failed_employees', []),
            'completed': global_state.get('completed', False),
            'error': global_state.get('error', ''),
            'batch_dir': global_state.get('batch_dir', '')
        }
        
        yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        
        if global_state.get('completed'):
            break
        
        if global_state.get('error'):
            break
        
        time.sleep(0.5)


def create_batch_zip(batch_dir, session_results):
    """
    Create ZIP file containing batch results.
    
    Args:
        batch_dir: Batch directory path
        session_results: JSON string of batch results (unused, kept for compat)
        
    Returns:
        Flask send_file: ZIP file for download
    """
    try:
        if not batch_dir or not os.path.exists(batch_dir):
            return {'error': '배치 처리 결과를 찾을 수 없습니다.'}, 404
        
        summary_path = os.path.join(batch_dir, "tmeta", "batch_summary.json")
        if not os.path.exists(summary_path):
            return {'error': 'batch_summary.json을 찾을 수 없습니다.'}, 404
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        
        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('batch_summary.json', json.dumps(summary, ensure_ascii=False, indent=2))
            
            # Add tmeta files
            tmeta_dir = os.path.join(batch_dir, 'tmeta')
            if os.path.exists(tmeta_dir):
                for file_name in os.listdir(tmeta_dir):
                    file_path = os.path.join(tmeta_dir, file_name)
                    if os.path.isfile(file_path):
                        relative_path = os.path.relpath(file_path, batch_dir)
                        zf.write(file_path, relative_path)
            
            # Add word files
            word_dir = os.path.join(batch_dir, 'word')
            if os.path.exists(word_dir):
                for file_name in os.listdir(word_dir):
                    file_path = os.path.join(word_dir, file_name)
                    if os.path.isfile(file_path):
                        relative_path = os.path.relpath(file_path, batch_dir)
                        zf.write(file_path, relative_path)
        
        memory_file.seek(0)
        
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'batch_results_{os.path.basename(batch_dir)}.zip'
        ), 200
        
    except Exception as e:
        return {'error': f'결과 다운로드 실패: {str(e)}'}, 500


def create_sse_response(global_state):
    """
    Create SSE response for batch processing.
    
    Args:
        global_state: Batch processing state dictionary
        
    Returns:
        Flask Response: SSE response
    """
    return Response(
        stream_batch_events(global_state),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )