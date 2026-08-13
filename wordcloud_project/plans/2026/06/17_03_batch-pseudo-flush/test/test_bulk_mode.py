"""bulk_mode 일괄 저장 검증 (0617_03_batch-pseudo-flush).

- 기본 동작(즉시 저장)이 불변인지
- bulk_mode 블록 동안 디스크 미기록 → 종료 시 1회 flush, 전건 보존
- 블록 내 예외 발생 시에도 flush 보장
"""
import os
import sys
import tempfile

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
)
from src.modules.pseudonym_manager import PseudonymManager  # noqa: E402


def test_default_mode_saves_immediately():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "m.enc")
    m = PseudonymManager(p, "pw")
    m.get_pseudonym("A")
    assert os.path.exists(p)


def test_bulk_mode_defers_then_flushes_all():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "m.enc")
    m = PseudonymManager(p, "pw")
    with m.bulk_mode():
        for i in range(500):
            m.get_pseudonym("U%04d" % i)
        assert not os.path.exists(p)  # 블록 동안 디스크 미기록
    assert os.path.exists(p)  # 종료 시 flush

    reloaded = PseudonymManager(p, "pw")
    assert len(reloaded.get_all_mappings()) == 500


def test_bulk_mode_flushes_on_exception():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "m.enc")
    m = PseudonymManager(p, "pw")
    try:
        with m.bulk_mode():
            m.get_pseudonym("X")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    reloaded = PseudonymManager(p, "pw")
    assert len(reloaded.get_all_mappings()) == 1
