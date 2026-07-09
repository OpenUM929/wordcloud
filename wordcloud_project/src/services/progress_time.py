"""Progress time helpers — elapsed time and ETA estimation."""
from datetime import datetime


def format_elapsed(start_iso: str) -> str:
    """경과 시간 문자열. start_iso와 모두 timezone-naive UTC 가정."""
    delta = datetime.now() - datetime.fromisoformat(start_iso)
    total_sec = int(delta.total_seconds())
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}시간 {m}분 {s}초"
    return f"{m}분 {s}초"
