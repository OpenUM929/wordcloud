"""One-time migration: users/*.json → SQLite employees + evaluations tables.

Usage:
    python scripts/migrate_evaluations.py   (wordcloud_project/ 루트에서 실행)
"""
import os
import json
import glob
import sqlite3
import hashlib

# scripts/ 기준: wordcloud_project/.sessions/deploy_sessions.db
DB_PATH = os.path.join(os.path.dirname(__file__), '..', '.sessions', 'deploy_sessions.db')
USERS_DIR = os.path.join(os.path.dirname(__file__), '..', 'processed_data', 'users')


def _fingerprint(ev):
    key = (
        ev.get('evaluator_id', ''),
        ev.get('evaluation_date', ''),
        str(ev.get('evaluation_document', ev.get('content', '')))[:100],
    )
    return hashlib.md5(json.dumps(key, ensure_ascii=False).encode()).hexdigest()


def migrate():
    db_path = os.path.abspath(DB_PATH)
    users_dir = os.path.abspath(USERS_DIR)

    if not os.path.exists(users_dir):
        print(f"[migrate_evaluations] users 디렉토리 없음: {users_dir}")
        return

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    files = glob.glob(os.path.join(users_dir, '*.json'))
    total_inserted = 0
    total_skipped = 0

    for path in sorted(files):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                user = json.load(f)
        except Exception as e:
            print(f"  [skip] {path}: {e}")
            continue

        emp_id = user.get('employee_id', '')
        if not emp_id:
            continue

        conn.execute("""
            INSERT INTO employees (employee_id, name, department, position)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(employee_id) DO UPDATE SET
                name       = COALESCE(NULLIF(excluded.name, ''), name),
                department = COALESCE(NULLIF(excluded.department, ''), department),
                position   = COALESCE(NULLIF(excluded.position, ''), position)
        """, (
            emp_id,
            user.get('name', ''),
            user.get('department', ''),
            user.get('position', ''),
        ))

        for ev in user.get('evaluations', []):
            fp = _fingerprint(ev)
            try:
                conn.execute("""
                    INSERT INTO evaluations
                        (employee_id, evaluator_id, evaluation_date, batch_id, data, fingerprint)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    emp_id,
                    ev.get('evaluator_id', ''),
                    ev.get('evaluation_date', ''),
                    ev.get('batch_id', ''),
                    json.dumps(ev, ensure_ascii=False),
                    fp,
                ))
                total_inserted += 1
            except sqlite3.IntegrityError:
                total_skipped += 1

    conn.commit()
    conn.close()
    print(f"[migrate_evaluations] 완료: {total_inserted}건 삽입, {total_skipped}건 중복 건너뜀")


if __name__ == '__main__':
    migrate()
