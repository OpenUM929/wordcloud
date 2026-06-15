"""Batch manager module - handles batch listing and management (DB-backed)."""

import os
import json


def _get_conn():
    from src.services.user_data_manager import _get_eval_conn
    return _get_eval_conn()


def _get_pseudo_mgr():
    from src.modules.pseudonym_manager import PseudonymManager
    from src.config.settings import PSEUDONYM_MAPPINGS_PATH, ADMIN_PASSWORD
    return PseudonymManager(PSEUDONYM_MAPPINGS_PATH, ADMIN_PASSWORD)


def get_batch_list(processed_data_dir=None):
    """Get list of available batches from DB."""
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT batch_id,
                   COUNT(DISTINCT employee_id) AS employee_count,
                   MIN(created_at)             AS created_at
            FROM evaluations
            GROUP BY batch_id
            ORDER BY MIN(created_at) DESC
        """).fetchall()
    finally:
        conn.close()

    batches = []
    for row in rows:
        batch_id = row['batch_id']
        created_at = (row['created_at'] or '')[:10]

        display_name = batch_id
        if batch_id and batch_id.startswith('batch_') and len(batch_id) > 14:
            date_part = batch_id[6:]
            if len(date_part) >= 8:
                year, month, day = date_part[:4], date_part[4:6], date_part[6:8]
                if year and month and day:
                    display_name = f"{year}-{month}-{day} {batch_id}"

        batches.append({
            'name': display_name,
            'original_name': batch_id,
            'path': batch_id,
            'employee_count': row['employee_count'],
            'created_at': created_at,
        })
    return batches


def delete_batch_directory(batch_path):
    """Delete batch data from DB (and physical dir if it exists)."""
    import shutil
    batch_id = os.path.basename(batch_path) if batch_path else batch_path

    from src.services.user_data_manager import remove_batch_from_all
    remove_batch_from_all(batch_id, [])

    if batch_path and os.path.isdir(batch_path):
        try:
            shutil.rmtree(batch_path)
        except Exception:
            pass

    return {'success': True, 'message': '배치가 삭제되었습니다.'}, 200


def load_batch_metadata(processed_data_dir, batch_dir):
    """Load metadata for all employees in a batch from DB (가명 복원 포함)."""
    batch_id = os.path.basename(batch_dir) if batch_dir else None
    if not batch_id:
        return []

    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT e.employee_id, e.name, e.department, e.position, ev.data
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            WHERE ev.batch_id = ?
            ORDER BY e.employee_id, ev.id
        """, (batch_id,)).fetchall()
    finally:
        conn.close()

    pseudo_mgr = _get_pseudo_mgr()
    emp_evals = {}
    emp_info = {}
    for row in rows:
        eid = row['employee_id']
        if eid not in emp_info:
            real_id = pseudo_mgr.get_real_id(eid) if eid else eid
            real_name = pseudo_mgr.get_real_id(row['name']) if row['name'] else row['name']
            real_dept = pseudo_mgr.get_real_id(row['department']) if row['department'] else row['department']
            real_pos = pseudo_mgr.get_real_id(row['position']) if row['position'] else row['position']
            emp_info[eid] = {
                'name': real_name or real_id or '',
                'department': real_dept or '',
                'position': real_pos or '',
            }
            emp_evals[eid] = []
        if row['data']:
            emp_evals[eid].append(json.loads(row['data']))

    result = []
    for eid, info in emp_info.items():
        display_name = info['name'] or eid
        result.append({
            'employee_id': display_name,
            'metadata': {
                'target_employee_id': display_name,
                'target_employee_name': info['name'],
                'target_employee_department': info['department'],
                'target_employee_position': info['position'],
                'evaluations': emp_evals[eid],
            }
        })
    result.sort(key=lambda x: x['employee_id'])
    return result


def get_batch_summary(processed_data_dir, batch_path):
    """Get batch summary from DB."""
    batch_id = os.path.basename(batch_path) if batch_path else None
    if not batch_id:
        return None

    conn = _get_conn()
    try:
        row = conn.execute("""
            SELECT COUNT(DISTINCT employee_id) AS employee_count,
                   COUNT(*) AS total_evaluations,
                   MIN(created_at) AS created_at
            FROM evaluations
            WHERE batch_id = ?
        """, (batch_id,)).fetchone()
    finally:
        conn.close()

    if not row or row['employee_count'] == 0:
        return None

    return {
        'batch_info': {
            'batch_id': batch_id,
            'created_at': row['created_at'] or '',
            'unique_employees': row['employee_count'],
            'total_evaluations': row['total_evaluations'],
        }
    }


def get_sample_metadata_from_results(session_results, batch_dir, processed_data_dir):
    """Get sample metadata from DB for a given batch (가명 복원 포함)."""
    batch_id = os.path.basename(batch_dir) if batch_dir else None
    if not batch_id:
        return {'error': 'batch_id가 없습니다.'}, 400

    conn = _get_conn()
    try:
        row = conn.execute("""
            SELECT e.employee_id, e.name, e.department, e.position, ev.data
            FROM employees e
            INNER JOIN evaluations ev ON e.employee_id = ev.employee_id
            WHERE ev.batch_id = ?
            LIMIT 1
        """, (batch_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        return {'error': '처리된 직원이 없습니다.'}, 400

    pseudo_mgr = _get_pseudo_mgr()
    eid = row['employee_id']
    real_id = pseudo_mgr.get_real_id(eid) if eid else eid
    real_name = pseudo_mgr.get_real_id(row['name']) if row['name'] else row['name']
    real_dept = pseudo_mgr.get_real_id(row['department']) if row['department'] else row['department']
    real_pos = pseudo_mgr.get_real_id(row['position']) if row['position'] else row['position']

    ev_data = json.loads(row['data']) if row['data'] else {}
    display_name = real_name or real_id or eid
    return {
        'employee_id': display_name,
        'metadata': {
            'target_employee_id': display_name,
            'target_employee_name': real_name or '',
            'target_employee_department': real_dept or '',
            'target_employee_position': real_pos or '',
            'evaluations': [ev_data],
        }
    }, 200
