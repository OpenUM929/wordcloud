"""Profanity DB service — save / query profanity data from deploy_sessions.db."""
import os
import json
import sqlite3

from src.config.settings import PROCESSED_DATA_DIR_PATH, PSEUDONYM_MAPPINGS_PATH, ADMIN_PASSWORD
from src.modules.pseudonym_manager import PseudonymManager

_DB_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '.sessions')
_DB_PATH = os.path.join(_DB_DIR, 'deploy_sessions.db')


def _get_pseudo_mgr():
    return PseudonymManager(PSEUDONYM_MAPPINGS_PATH, ADMIN_PASSWORD)


def _get_conn():
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def save_batch_profanity(batch_id, profanity_employees_list):
    """배치 완료 시 profanity_employees / profanity_sentences 저장."""
    conn = _get_conn()
    try:
        # 기존 동일 배치 데이터 삭제 (재처리 시 중복 방지)
        conn.execute("DELETE FROM profanity_employees WHERE batch_id = ?", (batch_id,))

        for emp in profanity_employees_list:
            eid = emp.get('employee_id', '')
            count = emp.get('profanity_count', 0)
            words = json.dumps(emp.get('profanity_words', []), ensure_ascii=False)

            cursor = conn.execute(
                "INSERT INTO profanity_employees (batch_id, employee_id, profanity_count, profanity_words) VALUES (?, ?, ?, ?)",
                (batch_id, eid, count, words)
            )
            pe_id = cursor.lastrowid

            for sent in emp.get('profanity_sentences', []):
                conn.execute(
                    "INSERT INTO profanity_sentences (profanity_employee_id, original_text, filtered_text, detected_words, evaluator_id) VALUES (?, ?, ?, ?, ?)",
                    (pe_id, sent.get('original_text', ''), sent.get('filtered_text', ''),
                     json.dumps(sent.get('detected_words', []), ensure_ascii=False),
                     sent.get('evaluator_id', ''))
                )
        conn.commit()
    finally:
        conn.close()


def delete_profanity_by_batch(batch_id):
    """배치 삭제 시 profanity_employees CASCADE (FK profanity_sentences 도 함께 삭제)."""
    conn = _get_conn()
    try:
        cursor = conn.execute("DELETE FROM profanity_employees WHERE batch_id = ?", (batch_id,))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def get_all_profanity_employees(search=None, department=None, min_count=1,
                                  sort='count', order='desc', page=1, limit=50):
    """전사 욕설 리스트 조회 (employees 테이블 JOIN)."""
    conn = _get_conn()
    try:
        conditions = []
        params = []

        if min_count:
            conditions.append("p.profanity_count >= ?")
            params.append(min_count)

        if search:
            conditions.append("(e.name LIKE ? OR e.employee_id LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])

        if department:
            conditions.append("e.department = ?")
            params.append(department)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        order_map = {
            'count': 'p.profanity_count',
            'ratio': 'CAST(p.profanity_count AS REAL) / e.total_eval',
            'name': 'e.name',
        }
        order_col = order_map.get(sort, 'p.profanity_count')
        order_dir = 'ASC' if order == 'asc' else 'DESC'

        # 전체 카운트
        count_sql = f"""
            SELECT COUNT(DISTINCT p.employee_id)
            FROM profanity_employees p
            JOIN employees e ON p.employee_id = e.employee_id
            {where}
        """
        total = conn.execute(count_sql, params).fetchone()[0]

        # 데이터 조회
        # 서브쿼리로 total_evaluations 계산 (employees 테이블에 직접 컬럼 없으므로)
        sql = f"""
            SELECT
                p.employee_id,
                e.name,
                e.department,
                (SELECT COUNT(*) FROM evaluations ev WHERE ev.employee_id = p.employee_id) as total_evaluations,
                SUM(p.profanity_count) as profanity_count,
                GROUP_CONCAT(p.profanity_words) as words_json
            FROM profanity_employees p
            JOIN employees e ON p.employee_id = e.employee_id
            {where}
            GROUP BY p.employee_id
            ORDER BY {order_col} {order_dir}
            LIMIT ? OFFSET ?
        """
        params.append(limit)
        params.append((page - 1) * limit)

        rows = conn.execute(sql, params).fetchall()

        pseudo_mgr = _get_pseudo_mgr()
        items = []
        for row in rows:
            total_eval = row['total_evaluations'] or 0
            prof_count = row['profanity_count'] or 0

            # GROUP_CONCAT 결과 파싱: ["a","b"]["c"] 형태 → 개별 JSON 배열 추출
            words = []
            raw_words_json = row['words_json'] or ''
            if raw_words_json:
                # 각 JSON 배열 문자열 추출 후 병합
                import re
                # ["..."] 형태 패턴 매칭
                for match in re.findall(r'\[.*?\]', raw_words_json):
                    try:
                        arr = json.loads(match)
                        if isinstance(arr, list):
                            words.extend(arr)
                    except Exception:
                        pass
            # 중복 제거
            words = list(set(words))

            # 원본 복원 (가명 → 실명)
            raw_eid = row['employee_id'] or ''
            real_eid = pseudo_mgr.get_real_id(raw_eid) if raw_eid else ''
            display_eid = real_eid if real_eid and real_eid != raw_eid else raw_eid

            raw_name = row['name'] or ''
            real_name = pseudo_mgr.get_real_id(raw_name) if raw_name else ''
            display_name = real_name if real_name and real_name != raw_name else raw_name
            raw_dept = row['department'] or ''
            real_dept = pseudo_mgr.get_real_id(raw_dept) if raw_dept else ''
            display_dept = real_dept if real_dept and real_dept != raw_dept else raw_dept

            items.append({
                'employee_id': display_eid,
                'name': display_name,
                'department': display_dept,
                'total_evaluations': total_eval,
                'profanity_count': prof_count,
                'profanity_ratio': round(prof_count / max(total_eval, 1), 4),
                'profanity_words': words,
            })

        return {
            'total': total,
            'page': page,
            'limit': limit,
            'items': items,
        }
    finally:
        conn.close()


def get_profanity_sentences(employee_id):
    """특정 직원의 모든 욕설 문장 조회 (모든 배치 통합)."""
    conn = _get_conn()
    try:
        # DB에는 가명으로 저장될 수 있으므로 원본+가명 모두 조회
        pseudo_mgr = _get_pseudo_mgr()
        pseudo_id = pseudo_mgr.get_pseudonym(employee_id) if employee_id else ''
        ids = [employee_id]
        if pseudo_id and pseudo_id != employee_id:
            ids.append(pseudo_id)
        placeholders = ','.join('?' for _ in ids)

        rows = conn.execute(f"""
            SELECT
                p.employee_id,
                s.original_text,
                s.filtered_text,
                s.detected_words,
                s.evaluator_id,
                p.batch_id
            FROM profanity_sentences s
            JOIN profanity_employees p ON s.profanity_employee_id = p.id
            WHERE p.employee_id IN ({placeholders})
            ORDER BY p.batch_id
        """, ids).fetchall()

        sentences = []
        for row in rows:
            try:
                words = json.loads(row['detected_words']) if row['detected_words'] else []
            except Exception:
                words = []
            sentences.append({
                'original_text': row['original_text'] or '',
                'filtered_text': row['filtered_text'] or '',
                'detected_words': words,
                'evaluator_id': row['evaluator_id'] or '',
                'batch_id': row['batch_id'] or '',
            })
        return sentences
    finally:
        conn.close()


def get_distinct_departments():
    """profanity_employees에 있는 부서 목록."""
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT DISTINCT e.department
            FROM profanity_employees p
            JOIN employees e ON p.employee_id = e.employee_id
            WHERE e.department IS NOT NULL AND e.department != ''
            ORDER BY e.department
        """).fetchall()
        return [r[0] for r in rows if r[0]]
    finally:
        conn.close()
