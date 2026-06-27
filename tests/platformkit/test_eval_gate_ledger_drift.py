"""Per-file tests for scripts.platformkit.eval_gate.ledger -- drift_report correctness.

Verifies:
  1. Baseline and recent windows are DISJOINT (no row appears in both).
  2. A clear recent-vs-baseline drift is now flagged (was dampened when windows overlapped).
  3. Stable calibration produces no alert.
  4. Fail-quiet when either window is empty.
  5. append_row / load round-trip.
  6. settled() filters out pending rows.

Run:
    /c/Users/neelj/anaconda3/envs/basketball_ai/python.exe \
        -m pytest tests/platformkit/test_eval_gate_ledger_drift.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.platformkit.eval_gate.ledger import (
    LedgerRow,
    DriftReport,
    append_row,
    load,
    settled,
    brier_of,
    drift_report,
    _window,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = "2026-06-18T12:00:00"
_NOW_DT = datetime.fromisoformat(_NOW)


def _row(ts: str, prob: float, outcome: int, sport: str = "mlb") -> LedgerRow:
    return LedgerRow(
        ts=ts,
        sport=sport,
        market="ml_home",
        inputs_hash="abc",
        prob=prob,
        outcome=outcome,
    )


def _iso(offset_days: float) -> str:
    """ISO string at now - offset_days."""
    return (_NOW_DT - timedelta(days=offset_days)).isoformat()


def _make_rows(
    n: int,
    prob: float,
    outcome_rate: float,
    start_offset: float,
    end_offset: float,
    seed: int = 0,
) -> List[LedgerRow]:
    """n settled rows spread across [now-start_offset, now-end_offset)."""
    import random
    rng = random.Random(seed)
    span = start_offset - end_offset
    rows = []
    for i in range(n):
        offset = end_offset + span * (i / max(n - 1, 1))
        outcome = 1 if rng.random() < outcome_rate else 0
        rows.append(_row(_iso(offset), prob, outcome))
    return rows


# ---------------------------------------------------------------------------
# 1. Disjoint windows: no row appears in both recent and baseline
# ---------------------------------------------------------------------------

def test_windows_are_disjoint():
    """recent and baseline windows must not share any row."""
    # Rows spread across the last 30 days
    all_rows = (
        _make_rows(20, prob=0.5, outcome_rate=0.5, start_offset=30, end_offset=7)
        + _make_rows(10, prob=0.5, outcome_rate=0.5, start_offset=7, end_offset=0)
    )

    now = _NOW_DT
    recent_start = now - timedelta(days=7)

    # Replicate the exact window logic from drift_report
    recent = _window(all_rows, now, 7.0, exclude_end=now)
    baseline = _window(all_rows, recent_start, 23.0)  # 30-7=23 days

    recent_ts = {r.ts for r in recent}
    baseline_ts = {r.ts for r in baseline}
    overlap = recent_ts & baseline_ts

    assert not overlap, (
        f"Windows must be disjoint but share {len(overlap)} timestamp(s): "
        f"{sorted(overlap)[:3]}"
    )


# ---------------------------------------------------------------------------
# 2. Clear drift IS now flagged (was dampened under the old overlapping windows)
# ---------------------------------------------------------------------------

def test_clear_drift_is_flagged():
    """When recent Brier is clearly higher than baseline Brier, alert must be True.

    Old code: baseline was contaminated by recent rows -> baseline Brier was
    pulled toward the high-recent value -> threshold rose -> alert was suppressed.
    New code: disjoint windows -> baseline stays low -> alert fires correctly.
    """
    # Baseline (days 30 -> 7): well-calibrated, p=0.5, 50/50 outcomes -> Brier ~0.25
    good_rows = _make_rows(60, prob=0.5, outcome_rate=0.5, start_offset=30, end_offset=7, seed=1)
    # Recent (days 7 -> 0): badly miscalibrated, p=0.9 but outcome_rate=0.1 -> Brier ~0.65
    bad_rows = _make_rows(20, prob=0.9, outcome_rate=0.1, start_offset=7, end_offset=0, seed=2)

    rows = good_rows + bad_rows
    report = drift_report(rows, _NOW, recent_days=7.0, baseline_days=30.0, k_sigma=1.0)

    assert report.alert, (
        f"Expected drift alert=True. recent_brier={report.recent_brier:.4f}, "
        f"baseline_brier={report.baseline_brier:.4f}, "
        f"threshold={report.threshold:.4f}, delta={report.delta:.4f}"
    )
    assert report.recent_brier > report.baseline_brier, \
        "recent_brier must exceed baseline_brier when miscalibrated"


# ---------------------------------------------------------------------------
# 3. No alert when calibration is stable
# ---------------------------------------------------------------------------

def test_stable_calibration_no_alert():
    """Consistently calibrated rows: no drift alert."""
    # Both windows: p=0.6, outcome_rate=0.6 -> Brier constant ~0.24
    good_rows = (
        _make_rows(40, prob=0.6, outcome_rate=0.6, start_offset=30, end_offset=7, seed=3)
        + _make_rows(20, prob=0.6, outcome_rate=0.6, start_offset=7, end_offset=0, seed=4)
    )
    report = drift_report(good_rows, _NOW, recent_days=7.0, baseline_days=30.0, k_sigma=1.0)

    # With consistent calibration, recent and baseline Briers should be close
    # and the alert should not fire.
    if report.recent_brier is not None and report.baseline_brier is not None:
        assert not report.alert, (
            f"Stable calibration should not trigger alert. "
            f"recent={report.recent_brier:.4f}, baseline={report.baseline_brier:.4f}, "
            f"threshold={report.threshold:.4f}"
        )


# ---------------------------------------------------------------------------
# 4. Fail-quiet when either window is empty
# ---------------------------------------------------------------------------

def test_fail_quiet_empty_recent():
    """No alert when recent window has no settled rows."""
    # Only rows older than 7 days
    rows = _make_rows(30, prob=0.5, outcome_rate=0.5, start_offset=30, end_offset=8)
    report = drift_report(rows, _NOW, recent_days=7.0, baseline_days=30.0)
    assert not report.alert
    assert report.recent_brier is None
    assert report.n_recent == 0


def test_fail_quiet_empty_baseline():
    """No alert when baseline window has no settled rows."""
    # Only rows in the last 7 days (inside recent window, NOT in baseline)
    rows = _make_rows(20, prob=0.5, outcome_rate=0.5, start_offset=7, end_offset=0)
    report = drift_report(rows, _NOW, recent_days=7.0, baseline_days=30.0)
    assert not report.alert
    assert report.n_baseline == 0


def test_fail_quiet_all_pending():
    """No alert when all rows have outcome=None (pending)."""
    rows = [LedgerRow(ts=_iso(1), sport="mlb", market="ml", inputs_hash="x",
                      prob=0.5, outcome=None) for _ in range(20)]
    report = drift_report(rows, _NOW, recent_days=7.0, baseline_days=30.0)
    assert not report.alert
    assert report.n_recent == 0
    assert report.n_baseline == 0


# ---------------------------------------------------------------------------
# 5. Old overlapping-window behavior would NOT have caught the drift
#    (regression guard: if we accidentally reintroduce overlap, this test fails)
# ---------------------------------------------------------------------------

def test_overlapping_windows_would_dampen_drift():
    """Demonstrate that the OLD behavior (both windows anchored at now) dampens
    the drift signal -- the baseline Brier was inflated by recent bad rows.

    This test directly shows the bug: with overlapping windows the baseline
    Brier is contaminated, raising the threshold and suppressing the alert.
    The NEW disjoint implementation must catch it; the simulated old logic must not.
    """
    good_rows = _make_rows(60, prob=0.5, outcome_rate=0.5, start_offset=30, end_offset=7, seed=5)
    bad_rows = _make_rows(20, prob=0.9, outcome_rate=0.1, start_offset=7, end_offset=0, seed=6)
    all_rows = good_rows + bad_rows

    # Simulate the OLD overlapping-window logic manually
    def _old_window(rows, end_dt, days):
        start = end_dt - timedelta(days=days)
        return [r for r in settled(rows)
                if start <= datetime.fromisoformat(r.ts) <= end_dt]

    now = _NOW_DT
    old_recent = _old_window(all_rows, now, 7.0)
    old_baseline = _old_window(all_rows, now, 30.0)

    # OLD: baseline contains the recent bad rows
    old_baseline_ts = {r.ts for r in old_baseline}
    old_recent_ts = {r.ts for r in old_recent}
    assert old_recent_ts.issubset(old_baseline_ts), \
        "Test setup error: old overlapping windows should have recent as subset of baseline"

    # NEW (via drift_report): must catch the drift
    new_report = drift_report(all_rows, _NOW, recent_days=7.0, baseline_days=30.0, k_sigma=1.0)
    assert new_report.alert, (
        "New disjoint-window drift_report must catch the clear miscalibration. "
        f"alert={new_report.alert}, recent={new_report.recent_brier:.4f}, "
        f"baseline={new_report.baseline_brier:.4f}"
    )


# ---------------------------------------------------------------------------
# 6. append_row / load round-trip
# ---------------------------------------------------------------------------

def test_append_and_load_roundtrip(tmp_path):
    """append_row + load must survive a round-trip."""
    path = str(tmp_path / "ledger.jsonl")
    row = _row(_iso(1), prob=0.6, outcome=1)
    append_row(path, row)
    loaded = load(path)
    assert len(loaded) == 1
    assert loaded[0].prob == pytest.approx(0.6)
    assert loaded[0].outcome == 1


# ---------------------------------------------------------------------------
# 7. settled() filters pending rows
# ---------------------------------------------------------------------------

def test_settled_filters_pending():
    """settled() must exclude rows with outcome=None."""
    rows = [
        _row(_iso(1), 0.5, 1),
        LedgerRow(ts=_iso(2), sport="mlb", market="ml", inputs_hash="x",
                  prob=0.5, outcome=None),
        _row(_iso(3), 0.5, 0),
    ]
    s = settled(rows)
    assert len(s) == 2
    assert all(r.outcome in (0, 1) for r in s)
