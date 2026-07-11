import os

import pytest

from main import _stale_run_logs


def _mk(tmp_path, name: str, mtime_offset: int):
    p = tmp_path / name
    p.write_text("x", encoding="utf-8")
    os.utime(p, (mtime_offset, mtime_offset))
    return p


# ---------- _stale_run_logs ----------

def test_empty_directory_returns_empty_list(tmp_path):
    assert _stale_run_logs(tmp_path, keep=30) == []


def test_fewer_than_keep_returns_empty_list(tmp_path):
    for i in range(5):
        _mk(tmp_path, f"run_{i}.txt", mtime_offset=1000 + i)
    assert _stale_run_logs(tmp_path, keep=30) == []


def test_exactly_keep_returns_empty_list(tmp_path):
    for i in range(30):
        _mk(tmp_path, f"run_{i}.txt", mtime_offset=1000 + i)
    assert _stale_run_logs(tmp_path, keep=30) == []


def test_overflow_returns_two_oldest(tmp_path):
    paths = [_mk(tmp_path, f"run_{i}.txt", mtime_offset=i) for i in range(1, 33)]
    stale = _stale_run_logs(tmp_path, keep=30)
    assert len(stale) == 2
    stale_names = {p.name for p in stale}
    assert stale_names == {"run_1.txt", "run_2.txt"}


def test_ignores_non_matching_files(tmp_path):
    for i in range(40):
        _mk(tmp_path, f"run_{i}.txt", mtime_offset=1000 + i)
    _mk(tmp_path, "scheduler_log.txt", mtime_offset=1)
    (tmp_path / "backups").mkdir()

    stale = _stale_run_logs(tmp_path, keep=30)

    assert len(stale) == 10
    stale_names = {p.name for p in stale}
    assert "scheduler_log.txt" not in stale_names
    assert "backups" not in stale_names
