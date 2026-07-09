"""Per-file test for exception_burst. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_exception_burst.py -q
"""
from __future__ import annotations

from pathlib import Path

from scripts.platformkit.ops_sentinel import exception_burst as eb

_TB = "Traceback (most recent call last):\n  ...\nRuntimeError: boom\n"


def test_first_tick_baselines_second_tick_rates(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    state = tmp_path / "state.json"
    err = logs / "m99_test_daemon.err"
    err.write_text(_TB)

    # first sight: baseline only, no verdict rows (rate unknown)
    rows = eb.check_all(now=1000.0, log_dir=logs, state_path=state)
    assert rows == []

    # 4 new tracebacks in 60s = 4/min > threshold 3/min -> YELLOW named row
    with err.open("a") as fh:
        fh.write(_TB * 4)
    rows = eb.check_all(now=1060.0, log_dir=logs, state_path=state)
    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "m99_test_daemon" and r["status"] == "YELLOW"
    assert r["new_tracebacks"] == 4 and r["rate_per_min"] == 4.0
    assert r["reason"] == "traceback_burst"

    # 1 new traceback in 60s = 1/min <= threshold -> informational GREEN
    with err.open("a") as fh:
        fh.write(_TB)
    rows = eb.check_all(now=1120.0, log_dir=logs, state_path=state)
    assert rows[0]["status"] == "GREEN" and rows[0]["new_tracebacks"] == 1

    # quiet interval -> no rows at all
    rows = eb.check_all(now=1180.0, log_dir=logs, state_path=state)
    assert rows == []


def test_rotated_log_rebaselines_without_verdict(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    state = tmp_path / "state.json"
    err = logs / "m99_test_daemon.err"
    err.write_text(_TB * 10)
    eb.check_all(now=1000.0, log_dir=logs, state_path=state)
    err.write_text(_TB)  # shrank: rotation/truncate
    rows = eb.check_all(now=1060.0, log_dir=logs, state_path=state)
    assert rows == []
    # after re-baseline, appends count again
    with err.open("a") as fh:
        fh.write(_TB * 5)
    rows = eb.check_all(now=1120.0, log_dir=logs, state_path=state)
    assert rows[0]["new_tracebacks"] == 5 and rows[0]["status"] == "YELLOW"


def test_non_daemon_logs_ignored(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    state = tmp_path / "state.json"
    (logs / "cv_local.err").write_text(_TB)      # not an m<N>_ daemon log
    (logs / "m10_x.out").write_text(_TB)         # .out is not tailed
    eb.check_all(now=1000.0, log_dir=logs, state_path=state)
    rows = eb.check_all(now=1060.0, log_dir=logs, state_path=state)
    assert rows == []


def test_missing_log_dir_never_raises(tmp_path):
    rows = eb.check_all(now=1.0, log_dir=tmp_path / "absent",
                        state_path=tmp_path / "state.json")
    assert rows == []
