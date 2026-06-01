"""Admin audit log service - JSONL file-based logging."""

import os
import json
from datetime import datetime, timezone

AUDIT_LOG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs', 'audit.jsonl')
)


def _ensure_log_dir():
    d = os.path.dirname(AUDIT_LOG_PATH)
    if not os.path.exists(d):
        os.makedirs(d)


def log_action(action_type, details, request=None):
    _ensure_log_dir()
    entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'action_type': action_type,
        'ip': request.remote_addr if request else None,
        'details': details,
    }
    with open(AUDIT_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def get_audit_logs(limit=100, offset=0, action_type=None):
    if not os.path.exists(AUDIT_LOG_PATH):
        return []
    with open(AUDIT_LOG_PATH, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if action_type:
        entries = [e for e in entries if e.get('action_type') == action_type]
    entries.reverse()
    return entries[offset:offset + limit]
