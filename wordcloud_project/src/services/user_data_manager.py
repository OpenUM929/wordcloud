"""User data manager - manages per-user consolidated data files.

Each user has a single JSON file at processed_data/users/{employee_id}.json
containing all their evaluations across all batches, tagged by batch_id.
This replaces the old model where batch_summary.json held full evaluation data.
"""
import os
import json
import re
from src.config.settings import PROCESSED_DATA_DIR_PATH


USERS_DIR = os.path.join(PROCESSED_DATA_DIR_PATH, 'users')


def _user_path(employee_id):
    safe = re.sub(r'[\\/*?:"<>|]', '_', str(employee_id))
    return os.path.join(USERS_DIR, f"{safe}.json")


def _get_meta_val(metadata, key, user, fallback):
    val = metadata.get(key)
    if val:
        return val
    return user.get(key.replace('target_employee_', '').replace('employee_', ''), fallback)


def upsert(employee_id, metadata, evaluations, batch_id):
    """Upsert user data from a batch. Tags evaluations with batch_id and merges."""
    path = _user_path(employee_id)
    user = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            user = json.load(f)

    user['employee_id'] = employee_id

    name = metadata.get('target_employee_name') or user.get('name') or employee_id
    dept = metadata.get('target_employee_department') or user.get('department') or ''
    pos = metadata.get('target_employee_position') or user.get('position') or ''
    user['name'] = name
    user['department'] = dept
    user['position'] = pos

    existing_keys = set()
    for ev in user.get('evaluations', []):
        ev_id = ev.get('evaluator_id', '')
        ev_date = ev.get('evaluation_date', '')
        ev_content_preview = str(ev.get('content', ''))[:100]
        existing_keys.add((ev_id, ev_date, ev_content_preview))

    new_evals = []
    for ev in evaluations:
        ev['batch_id'] = batch_id
        key = (ev.get('evaluator_id', ''), ev.get('evaluation_date', ''), str(ev.get('content', ''))[:100])
        if key not in existing_keys:
            existing_keys.add(key)
            new_evals.append(ev)

    user.setdefault('evaluations', []).extend(new_evals)

    os.makedirs(USERS_DIR, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(user, f, ensure_ascii=False, indent=2)

    return len(new_evals)


def remove_batch(employee_id, batch_id):
    """Remove all evaluations with given batch_id from a user file.
    
    If no evaluations remain, the user file is deleted.
    """
    path = _user_path(employee_id)
    if not os.path.exists(path):
        return 0
    with open(path, 'r', encoding='utf-8') as f:
        user = json.load(f)
    before = len(user.get('evaluations', []))
    user['evaluations'] = [ev for ev in user.get('evaluations', []) if ev.get('batch_id') != batch_id]
    removed = before - len(user['evaluations'])

    if not user.get('evaluations'):
        os.remove(path)
    else:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(user, f, ensure_ascii=False, indent=2)
    return removed


def remove_batch_from_all(batch_id, employee_ids):
    """Remove batch data from all specified user files."""
    total = 0
    for emp_id in employee_ids:
        total += remove_batch(emp_id, batch_id)
    return total


def get_user(employee_id):
    """Return user dict or None."""
    path = _user_path(employee_id)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_all_employee_results():
    """Read all user files and return in employee_results format.
    
    Each entry:
    {
        'metadata': {
            'target_employee_id': str,
            'target_employee_name': str,
            'target_employee_department': str,
            'target_employee_position': str,
            'evaluations': [...]
        }
    }
    """
    if not os.path.exists(USERS_DIR):
        return []
    results = []
    for fname in sorted(os.listdir(USERS_DIR)):
        if not fname.endswith('.json'):
            continue
        path = os.path.join(USERS_DIR, fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                user = json.load(f)
        except Exception:
            continue
        emp_id = user.get('employee_id', '')
        if not emp_id:
            continue
        results.append({
            'metadata': {
                'target_employee_id': emp_id,
                'target_employee_name': user.get('name', ''),
                'target_employee_department': user.get('department', ''),
                'target_employee_position': user.get('position', ''),
                'evaluations': user.get('evaluations', []),
            }
        })
    return results


def count_users():
    """Quick count of user files without loading data."""
    if not os.path.exists(USERS_DIR):
        return 0
    return len([f for f in os.listdir(USERS_DIR) if f.endswith('.json')])


def migrate_from_old_format(processed_data_dir=None):
    """One-time migration: convert old batch_summary.json (full data) to users/*.json + lightweight summaries.
    
    Scans all batch directories. For each batch_summary.json that has 'employee_results'
    (old format), upserts each employee's evaluations to users/*.json and rewrites the
    batch_summary as lightweight. Skips if users/*.json already has data.
    """
    if processed_data_dir is None:
        processed_data_dir = PROCESSED_DATA_DIR_PATH

    if count_users() > 0:
        return {'migrated': False, 'reason': 'users data already exists, skipping'}

    batch_dir = os.path.join(processed_data_dir, 'batch')
    if not os.path.exists(batch_dir):
        return {'migrated': False, 'reason': 'no batch directory found'}

    total_employees = 0
    total_evaluations = 0
    migrated_batches = 0

    for item in sorted(os.listdir(batch_dir)):
        item_path = os.path.join(batch_dir, item)
        if not os.path.isdir(item_path) or not item.startswith('batch_'):
            continue

        from src.services.perspective_service import load_batch_summary
        summary = load_batch_summary(item_path)
        if not summary:
            continue

        old_results = summary.get('employee_results', [])
        if not old_results:
            continue  # already lightweight or empty

        batch_id = item

        for er in old_results:
            meta = er.get('metadata', {})
            emp_id = er.get('employee_id') or meta.get('target_employee_id')
            if not emp_id:
                continue
            evals = meta.get('evaluations', [])
            upsert(emp_id, meta, evals, batch_id)
            total_employees += 1
            total_evaluations += len(evals)

        # Rewrite batch_summary as lightweight
        summary['employee_ids'] = list(set(
            er.get('employee_id') or er.get('metadata', {}).get('target_employee_id', '')
            for er in old_results
        ))
        if 'employee_results' in summary:
            del summary['employee_results']

        summary_path = os.path.join(item_path, "tmeta", "batch_summary.json")
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        migrated_batches += 1

    return {
        'migrated': migrated_batches > 0,
        'batches_migrated': migrated_batches,
        'employees_migrated': total_employees,
        'evaluations_migrated': total_evaluations,
    }
