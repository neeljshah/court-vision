"""predict_service.tests.test_calib_drift_monitor -- per-file test.

Acceptance criteria (from workstream BE-CALIB-DRIFT-MON):
  1. current ECE > baseline ECE + threshold -> status="drift", drift=True, reason set.
  2. current ECE within tolerance of baseline -> status="ok", drift=False.
  3. n_holdout < MIN_HOLDOUT on live row -> status="INSUFFICIENT_DATA", drift=None.
  4. missing baseline -> status="unavailable", drift=None (not green).
  5. baseline n_holdout < MIN_HOLDOUT -> status="INSUFFICIENT_DATA".
  6. No $ key in any DriftResult field name (units only; calibration not edge).
  7. check_drift never raises on malformed / empty inputs.
  8. save_baseline + load_baseline round-trips all field values.
  9. Brier degradation also triggers drift=True when ECE is within threshold.
 10. Both metrics within tolerance -> ok, drift=False.

Run (per-file only -- full suite FREEZES the box)::
    cd /c/Users/neelj/nba-ai-system && python -m pytest predict_service/tests/test_calib_drift_monitor.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path.
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from predict_service.calib_drift_monitor import (  # noqa: E402
    BRIER_DRIFT_THRESHOLD,
    ECE_DRIFT_THRESHOLD,
    BaselineEntry,
    DriftResult,
    check_drift,
    load_baseline,
    save_baseline,
)
from predict_service.calib_scoreboard import (  # noqa: E402
    MIN_HOLDOUT,
    ScoreboardRow,
    SportInput,
    build_scoreboard,
)


# ---------------------------------------------------------------------------
# Helpers -- build synthetic ScoreboardRow values
# ---------------------------------------------------------------------------

def _ok_row(
    sport: str = "nba",
    ece: float = 0.05,
    brier: float = 0.20,
    n: int = 200,
) -> ScoreboardRow:
    """Construct a synthetic ScoreboardRow with status='ok'."""
    return ScoreboardRow(
        sport=sport,
        n_holdout=n,
        status="ok",
        brier=brier,
        ece=ece,
        bss=0.05,
        metrics_source="test",
        note="synthetic",
    )


def _insuf_row(sport: str = "nba") -> ScoreboardRow:
    """Construct a synthetic ScoreboardRow with status='INSUFFICIENT_DATA'."""
    return ScoreboardRow(
        sport=sport,
        n_holdout=MIN_HOLDOUT - 1,
        status="INSUFFICIENT_DATA",
        brier=None,
        ece=None,
        bss=None,
        metrics_source="test",
        note="thin data",
    )


def _ok_baseline(
    sport: str = "nba",
    ece: float = 0.05,
    brier: float = 0.20,
    n: int = 200,
) -> BaselineEntry:
    return BaselineEntry(sport=sport, brier=brier, ece=ece, n_holdout=n, status="ok")


# ---------------------------------------------------------------------------
# 1. ECE degradation beyond threshold -> drift detected
# ---------------------------------------------------------------------------

def test_ece_drift_triggers():
    live_ece = 0.05 + ECE_DRIFT_THRESHOLD + 0.005  # above threshold
    live = _ok_row(ece=live_ece, brier=0.20)
    baseline = [_ok_baseline(ece=0.05, brier=0.20)]

    results = check_drift([live], baseline)
    assert len(results) == 1
    r = results[0]
    assert r.status == "drift", f"expected drift, got {r.status}: {r.reason}"
    assert r.drift is True
    assert r.ece_delta is not None and r.ece_delta > ECE_DRIFT_THRESHOLD
    assert "ECE" in r.reason
    assert r.sport == "nba"


# ---------------------------------------------------------------------------
# 2. Both metrics within tolerance -> ok, drift=False
# ---------------------------------------------------------------------------

def test_within_tolerance_ok():
    live = _ok_row(ece=0.05, brier=0.20)
    baseline = [_ok_baseline(ece=0.049, brier=0.199)]  # tiny delta

    results = check_drift([live], baseline)
    r = results[0]
    assert r.status == "ok", f"expected ok, got {r.status}: {r.reason}"
    assert r.drift is False
    assert r.ece_delta is not None
    assert r.brier_delta is not None


# ---------------------------------------------------------------------------
# 3. Live n_holdout < MIN_HOLDOUT -> INSUFFICIENT_DATA, drift=None
# ---------------------------------------------------------------------------

def test_thin_live_insufficient():
    live = _insuf_row("soccer")
    baseline = [_ok_baseline("soccer")]

    results = check_drift([live], baseline)
    r = results[0]
    assert r.status == "INSUFFICIENT_DATA"
    assert r.drift is None
    assert r.ece_delta is None


# ---------------------------------------------------------------------------
# 4. Missing baseline -> unavailable, drift=None (not green)
# ---------------------------------------------------------------------------

def test_missing_baseline_unavailable():
    live = _ok_row("mlb")
    results = check_drift([live], baseline=None)
    r = results[0]
    assert r.status == "unavailable"
    assert r.drift is None
    assert "baseline" in r.reason.lower()


def test_sport_absent_from_baseline_dict():
    """Sport present in live but absent from baseline list -> unavailable."""
    live = _ok_row("tennis")
    baseline = [_ok_baseline("nba")]  # tennis not in baseline

    results = check_drift([live], baseline)
    r = results[0]
    assert r.status == "unavailable"
    assert r.drift is None


# ---------------------------------------------------------------------------
# 5. Baseline n_holdout < MIN_HOLDOUT -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

def test_thin_baseline_insufficient():
    live = _ok_row("nba", n=200)
    bl = BaselineEntry(
        sport="nba", brier=0.20, ece=0.05, n_holdout=MIN_HOLDOUT - 1,
        status="INSUFFICIENT_DATA",
    )
    results = check_drift([live], [bl])
    r = results[0]
    assert r.status == "INSUFFICIENT_DATA"
    assert r.drift is None


# ---------------------------------------------------------------------------
# 6. No $ key in DriftResult fields
# ---------------------------------------------------------------------------

def test_no_dollar_key_in_fields():
    fields_lower = {f.lower() for f in DriftResult._fields}
    forbidden = {"pnl", "roi", "profit", "dollar", "ev", "edge", "winnings"}
    overlap = fields_lower & forbidden
    assert not overlap, f"DriftResult contains forbidden field(s): {overlap}"


# ---------------------------------------------------------------------------
# 7. check_drift never raises
# ---------------------------------------------------------------------------

def test_check_drift_never_raises_empty():
    # Empty live list
    results = check_drift([], None)
    assert results == []


def test_check_drift_never_raises_none_baseline():
    live = _ok_row()
    # Should return unavailable, not raise
    results = check_drift([live], None)
    assert results[0].drift is None


def test_check_drift_never_raises_corrupt_none_metrics():
    """A ScoreboardRow with status='ok' but None ece/brier -> INSUFFICIENT_DATA, not raise."""
    live = ScoreboardRow(
        sport="nba", n_holdout=200, status="ok",
        brier=None, ece=None, bss=None,
        metrics_source="test", note="corrupt",
    )
    baseline = [_ok_baseline("nba")]
    results = check_drift([live], baseline)
    r = results[0]
    # Should not raise; status is INSUFFICIENT_DATA or similar defensive state
    assert r.drift is None


# ---------------------------------------------------------------------------
# 8. save_baseline + load_baseline round-trip
# ---------------------------------------------------------------------------

def test_save_load_baseline_roundtrip():
    row = _ok_row("nba", ece=0.06, brier=0.21, n=300)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "baseline.json"
        save_baseline([row], path)
        assert path.exists()

        loaded = load_baseline(path)
        assert loaded is not None
        assert len(loaded) == 1
        b = loaded[0]
        assert b.sport == "nba"
        assert abs(b.ece - 0.06) < 1e-9
        assert abs(b.brier - 0.21) < 1e-9
        assert b.n_holdout == 300
        assert b.status == "ok"


def test_load_baseline_missing_file_returns_none():
    result = load_baseline("/nonexistent/path/baseline.json")
    assert result is None


def test_load_baseline_corrupt_json_returns_none():
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        f.write("{corrupt json{{")
        fname = f.name
    result = load_baseline(fname)
    assert result is None


# ---------------------------------------------------------------------------
# 9. Brier degradation alone triggers drift=True (ECE within threshold)
# ---------------------------------------------------------------------------

def test_brier_only_drift_triggers():
    live = _ok_row(ece=0.05, brier=0.20 + BRIER_DRIFT_THRESHOLD + 0.005)
    baseline = [_ok_baseline(ece=0.05, brier=0.20)]

    results = check_drift([live], baseline)
    r = results[0]
    assert r.status == "drift"
    assert r.drift is True
    assert "Brier" in r.reason


# ---------------------------------------------------------------------------
# 10. Multi-sport: mix of drift / ok / insufficient in one call
# ---------------------------------------------------------------------------

def test_multi_sport_mixed():
    drifted_ece = 0.05 + ECE_DRIFT_THRESHOLD + 0.01
    live_rows = [
        _ok_row("nba", ece=drifted_ece, brier=0.20),   # drift
        _ok_row("mlb", ece=0.04, brier=0.19),           # ok
        _insuf_row("soccer"),                             # insufficient
    ]
    baseline = [
        _ok_baseline("nba", ece=0.05, brier=0.20),
        _ok_baseline("mlb", ece=0.04, brier=0.19),
        _ok_baseline("soccer"),
        # tennis absent -> unavailable for a tennis live row
    ]
    results = check_drift(live_rows, baseline)
    assert len(results) == 3

    statuses = {r.sport: r.status for r in results}
    assert statuses["nba"] == "drift"
    assert statuses["mlb"] == "ok"
    assert statuses["soccer"] == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# 11. Exact-threshold boundary: ECE delta == threshold is NOT drift
# ---------------------------------------------------------------------------

def test_exact_threshold_boundary_not_drift():
    # delta == threshold exactly is NOT over the threshold (strictly greater)
    live = _ok_row(ece=0.05 + ECE_DRIFT_THRESHOLD, brier=0.20)
    baseline = [_ok_baseline(ece=0.05, brier=0.20)]

    results = check_drift([live], baseline)
    r = results[0]
    # delta == threshold -> NOT drift (strictly > required)
    assert r.drift is False
    assert r.status == "ok"


# ---------------------------------------------------------------------------
# 12. Improving calibration (live better than baseline) -> ok, drift=False
# ---------------------------------------------------------------------------

def test_improved_calibration_not_drift():
    live = _ok_row(ece=0.03, brier=0.18)  # better than baseline
    baseline = [_ok_baseline(ece=0.05, brier=0.20)]

    results = check_drift([live], baseline)
    r = results[0]
    assert r.drift is False
    assert r.status == "ok"
    assert r.ece_delta is not None and r.ece_delta < 0  # improvement


# ---------------------------------------------------------------------------
# 13. Integration: use build_scoreboard to produce real live rows
# ---------------------------------------------------------------------------

def test_integration_with_build_scoreboard():
    """Build a real ScoreboardRow from synthetic probs and check drift."""
    rng = np.random.default_rng(99)
    n = 150
    true_p = rng.uniform(0.3, 0.7, n)
    outcomes = rng.binomial(1, true_p).astype(float).tolist()
    probs = np.clip(true_p + rng.normal(0, 0.04, n), 0.01, 0.99).tolist()

    from predict_service.calib_scoreboard import build_scoreboard, SportInput

    live = build_scoreboard([SportInput("nba", probs=probs, outcomes=outcomes)])
    assert live[0].status == "ok"

    # Save then load baseline
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "snap.json"
        save_baseline(live, path)
        bl = load_baseline(path)
        assert bl is not None

        # Same live vs same baseline -> no drift
        results = check_drift(live, bl)
        assert results[0].status == "ok"
        assert results[0].drift is False
