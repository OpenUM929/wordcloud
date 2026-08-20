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


# 배치 명칭(display_name)에 쓸 수 없는 문자 — 물리 폴더명 규약과 동일하게 막는다.
_DISPLAY_NAME_FORBIDDEN = set('\\/:*?"<>|')


def validate_display_name(name):
    """배치 명칭 입력 검증 (20_07). 반환: (ok: bool, error: str|None).

    빈 문자열은 '명칭 해제'(batch_id 표시로 되돌림)를 뜻하므로 허용한다.
    한글을 포함한 비ASCII 문자는 거부한다 — 사용자가 영문 사용을 요구했고,
    이 값은 배치관리·그룹분석·미리보기 세 화면이 공유하는 라벨이다.
    """
    if name is None:
        return True, None
    name = str(name)
    if not name:
        return True, None
    for ch in name:
        if ord(ch) > 0x7E or ord(ch) < 0x20:
            return False, '배치 명칭은 영문·숫자·기호만 사용할 수 있습니다(한글 등 비영문 불가).'
    bad = sorted({ch for ch in name if ch in _DISPLAY_NAME_FORBIDDEN})
    if bad:
        return False, '사용할 수 없는 문자가 있습니다: ' + ' '.join(bad)
    return True, None


def read_display_name(processed_data_dir, batch_id):
    """batch_summary.json에 저장된 배치 명칭을 읽는다(없으면 빈 문자열).

    정본 위치는 processed_data/batch/<batch_id>/tdata/batch_summary.json 의
    batch_info.display_name — PATCH /api/perspective/batch/<id>/display-name 가 쓰는 곳이다.
    """
    if not processed_data_dir or not batch_id:
        return ''
    summary_path = os.path.join(processed_data_dir, 'batch', batch_id, 'tdata', 'batch_summary.json')
    if not os.path.exists(summary_path):
        return ''
    try:
        with open(summary_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
        return summary.get('batch_info', {}).get('display_name', '') or ''
    except Exception:
        return ''


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

        # batch_summary.json에서 저장된 display_name 우선 로드
        display_name = ''
        summary_path = os.path.join(processed_data_dir, 'batch', batch_id, 'tdata', 'batch_summary.json') if processed_data_dir else None
        if summary_path and os.path.exists(summary_path):
            try:
                with open(summary_path, 'r', encoding='utf-8') as _sf:
                    _summary = json.load(_sf)
                display_name = _summary.get('batch_info', {}).get('display_name', '') or ''
            except Exception:
                pass

        if not display_name:
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


def get_sample_integrated_data_from_results(session_results, batch_dir, processed_data_dir):
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
