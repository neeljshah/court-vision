"""Tests for the track-record ledger + drift monitor. numpy + stdlib; standalone or pytest."""
from __future__ import annotations
import os, tempfile
from datetime import datetime, timedelta
try:
    from scripts.platformkit.eval_gate.ledger import (LedgerRow, append_row, load,
                                                        settled, brier_of, drift_report)
except ModuleNotFoundError:  # standalone run from this directory
    from ledger import LedgerRow, append_row, load, settled, brier_of, drift_report


def _tmp():
    fd, path = tempfile.mkstemp(suffix=".jsonl"); os.close(fd); return path


def test_append_only_roundtrip():
    path = _tmp()
    try:
        append_row(path, LedgerRow("2024-01-01T12:00:00", "nba", "ml_home", "h1", 0.6, 1))
        append_row(path, LedgerRow("2024-01-02T12:00:00", "nba", "ml_home", "h2", 0.4, 0))
        rows = load(path)
        assert len(rows) == 2 and rows[0].prob == 0.6 and rows[1].outcome == 0
    finally:
        os.remove(path)


def test_settled_and_brier():
    rows = [LedgerRow("2024-01-01T12:00:00", "nba", "m", "h", 1.0, 1),
            LedgerRow("2024-01-01T12:00:00", "nba", "m", "h", 0.0, 0),
            LedgerRow("2024-01-01T12:00:00", "nba", "m", "h", 0.5, None)]  # pending
    assert len(settled(rows)) == 2
    assert brier_of(settled(rows)) == 0.0   # both perfect


def test_drift_alerts_on_degraded_recent_window():
    now = datetime(2024, 2, 1, 12, 0, 0)
    rows = []
    # baseline (8-30 days ago): well-calibrated, low Brier
    for i in range(40):
        t = (now - timedelta(days=12) + timedelta(hours=i)).isoformat()
        y = i % 2
        rows.append(LedgerRow(t, "nba", "m", "h", 0.95 if y else 0.05, y))  # sharp+correct
    # recent (last 3 days): degraded -- confidently wrong
    for i in range(20):
        t = (now - timedelta(days=2) + timedelta(hours=i)).isoformat()
        y = i % 2
        rows.append(LedgerRow(t, "nba", "m", "h", 0.05 if y else 0.95, y))  # sharp+wrong
    rep = drift_report(rows, now.isoformat(), recent_days=4, baseline_days=31)
    assert rep.recent_brier > rep.baseline_brier
    assert rep.alert is True
    assert rep.n_recent > 0 and rep.n_baseline > 0


def test_drift_quiet_when_stable():
    now = datetime(2024, 2, 1, 12, 0, 0)
    rows = []
    for i in range(50):
        t = (now - timedelta(days=10) + timedelta(hours=i * 4)).isoformat()
        y = i % 2
        rows.append(LedgerRow(t, "nba", "m", "h", 0.9 if y else 0.1, y))
    rep = drift_report(rows, now.isoformat(), recent_days=4, baseline_days=31)
    assert rep.alert is False     # stable calibration -> no false alarm


def test_drift_fail_quiet_without_data():
    rep = drift_report([], datetime(2024, 2, 1).isoformat())
    assert rep.alert is False and rep.recent_brier is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} ledger tests passed.")
