"""tests.platform.test_gate_test_asof_tennis — offline tests for the tennis as-of gate test.

Synthetic ONLY: no real parquet, no real gate run (too heavy).  Verifies the
load-bearing plumbing of scripts.platformkit.proof_tennis.gate_test_asof:

  1. _align_asof maps event_ids correctly + NaN on missing.
  2. _candidate_columns reads the candidate list from the asof schema.
  3. _build_base_bundle_with_ids returns a FeatureBundle with
     len(event_ids)==base.shape[0] and event_ids aligned 1:1 (synthetic wf via
     monkeypatched adapter helpers).
  4. A SHIP verdict triggers the PROBABLE-ARTIFACT warning and is NOT claimed as
     an edge (monkeypatched evaluate returns a fake SHIP GateResult).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from src.loop.gate import FeatureBundle
from src.loop.signal import GateResult, Verdict
import scripts.platformkit.proof_tennis.gate_test_asof as mod


# --------------------------------------------------------------------------- #
# Helpers: synthetic fixtures
# --------------------------------------------------------------------------- #
def _asof_fixture() -> pd.DataFrame:
    """Minimal asof_features DataFrame with the five diff_* candidates."""
    return pd.DataFrame({
        "event_id": ["ev1", "ev2", "ev3"],
        "diff_1st_win_asof": [0.05, -0.03, 0.08],
        "diff_ace_rate_asof": [0.02, -0.01, 0.04],
        "diff_1st_in_asof": [0.03, 0.00, -0.02],
        "diff_2nd_win_asof": [-0.01, 0.04, 0.01],
        "diff_bp_saved_asof": [0.10, -0.05, 0.07],
    })


# --------------------------------------------------------------------------- #
# 1. _align_asof
# --------------------------------------------------------------------------- #
def test_align_asof_maps_and_nans_missing():
    """_align_asof returns correct values and NaN for absent event_id."""
    df = _asof_fixture()
    # ev4 is absent -> NaN; order follows requested event_ids, not df order.
    out = mod._align_asof(df, ["ev3", "ev1", "ev4", "ev2"], "diff_1st_win_asof")
    assert out[0] == pytest.approx(0.08)
    assert out[1] == pytest.approx(0.05)
    assert np.isnan(out[2])
    assert out[3] == pytest.approx(-0.03)
    assert out.shape == (4,)


def test_align_asof_all_present():
    """_align_asof with all event_ids present returns aligned float array."""
    df = _asof_fixture()
    out = mod._align_asof(df, ["ev1", "ev2", "ev3"], "diff_ace_rate_asof")
    np.testing.assert_allclose(out, [0.02, -0.01, 0.04])
    assert out.dtype == np.float64


def test_align_asof_all_absent_returns_nans():
    """_align_asof with no matching ids returns all NaN."""
    df = _asof_fixture()
    out = mod._align_asof(df, ["x", "y"], "diff_1st_in_asof")
    assert np.all(np.isnan(out))
    assert out.shape == (2,)


# --------------------------------------------------------------------------- #
# 2. _candidate_columns
# --------------------------------------------------------------------------- #
def test_candidate_columns_returns_all_when_present():
    """All five preferred candidates returned when schema has them all."""
    df = _asof_fixture()
    cands = mod._candidate_columns(df)
    assert cands == list(mod._PREFERRED_CANDIDATES)


def test_candidate_columns_drops_absent():
    """Only columns actually in the schema are returned."""
    df = pd.DataFrame({
        "event_id": ["ev1"],
        "diff_1st_win_asof": [0.05],
        "diff_ace_rate_asof": [0.02],
        # diff_1st_in_asof, diff_2nd_win_asof, diff_bp_saved_asof absent
    })
    cands = mod._candidate_columns(df)
    assert cands == ["diff_1st_win_asof", "diff_ace_rate_asof"]


def test_candidate_columns_empty_df_returns_empty():
    """Empty DataFrame (no matching cols) returns empty list."""
    df = pd.DataFrame({"event_id": ["ev1"], "irrelevant_col": [1.0]})
    assert mod._candidate_columns(df) == []


# --------------------------------------------------------------------------- #
# 3. _build_base_bundle_with_ids (synthetic via monkeypatched adapter helpers)
# --------------------------------------------------------------------------- #
def _synthetic_wf() -> pd.DataFrame:
    """Minimal walk-forward frame mirroring real TennisAdapter wf columns.

    No ps_p1/ps_p2 columns so that closing resolves to all-NaN -> None, making
    the bundle.closing assertion deterministic (no odds merge path).
    """
    return pd.DataFrame({
        "event_id": ["ev1", "ev2", "ev3"],
        "date": ["2024-01-10", "2024-01-11", "2024-01-12"],
        "winner": [1.0, 0.0, np.nan],   # row 3 dropped (winner NaN = walkover)
        "p1_elo": [1550.0, 1480.0, 1510.0],
        "p2_elo": [1490.0, 1520.0, 1500.0],
        "p1_surface_elo": [1540.0, 1470.0, 1505.0],
        "p2_surface_elo": [1485.0, 1515.0, 1498.0],
        "best_of": [3.0, 3.0, 5.0],
        "rest_days_a": [2.0, 7.0, 4.0],
        "rest_days_b": [5.0, 3.0, 1.0],
        "win_prob_p1": [0.62, 0.38, 0.51],
        # No ps_p1/ps_p2/b365_p1/b365_p2 -> all closing = NaN -> bundle.closing = None
    })


class _FakeTennisAdapter:
    """Stands in for TennisAdapter: serves synthetic matches + empty odds."""
    def _get_matches(self) -> pd.DataFrame:
        return pd.DataFrame({
            "event_id": ["ev1", "ev2", "ev3"],
            "date": ["2024-01-10", "2024-01-11", "2024-01-12"],
            "winner": [1.0, 0.0, np.nan],
        })

    def _get_odds(self) -> pd.DataFrame:
        return pd.DataFrame()  # no odds -> closing None path


def test_build_base_bundle_with_ids_alignment(monkeypatch):
    """_build_base_bundle_with_ids returns FeatureBundle with ids 1:1 to kept rows."""
    wf = _synthetic_wf()
    monkeypatch.setattr(mod, "walk_forward_elo", lambda m: wf.copy())
    monkeypatch.setattr(mod, "_add_rest_days", lambda w: w)  # already has cols

    bundle, event_ids = mod._build_base_bundle_with_ids(
        seasons=[2024], adapter=_FakeTennisAdapter())

    assert isinstance(bundle, FeatureBundle)
    # row 3 (winner NaN) dropped -> 2 kept rows; ids 1:1 with bundle.
    assert bundle.base.shape[0] == 2
    assert len(event_ids) == bundle.base.shape[0]
    assert event_ids == ["ev1", "ev2"]
    # base col 0 = elo_diff = p1_elo - p2_elo
    assert bundle.base[0, 0] == pytest.approx(1550.0 - 1490.0)
    assert bundle.base[1, 0] == pytest.approx(1480.0 - 1520.0)
    # target = 1.0 for winner==1, 0.0 for winner==0
    assert list(bundle.target) == [1.0, 0.0]
    # No odds provided -> closing is None
    assert bundle.closing is None


def test_build_base_bundle_raises_on_no_rows(monkeypatch):
    """ValueError raised when no rows survive the winner-NaN filter."""
    empty_wf = pd.DataFrame({
        "event_id": ["ev1"], "date": ["2024-01-10"],
        "winner": [np.nan],  # all NaN -> dropped
        "p1_elo": [1500.0], "p2_elo": [1500.0],
        "p1_surface_elo": [1500.0], "p2_surface_elo": [1500.0],
        "best_of": [3.0], "rest_days_a": [7.0], "rest_days_b": [7.0],
        "win_prob_p1": [0.5],
    })
    monkeypatch.setattr(mod, "walk_forward_elo", lambda m: empty_wf.copy())
    monkeypatch.setattr(mod, "_add_rest_days", lambda w: w)
    with pytest.raises(ValueError, match="no rows"):
        mod._build_base_bundle_with_ids(seasons=[2024], adapter=_FakeTennisAdapter())


# --------------------------------------------------------------------------- #
# 4. SHIP verdict -> probable-artifact warning, never claimed as edge
# --------------------------------------------------------------------------- #
def _fake_ship_result(signal, **kw) -> GateResult:
    return GateResult(
        signal_name=signal.name, verdict=Verdict.SHIP, reason="fake ship",
        wf_folds=[-0.01, -0.02, -0.03], wf_all_improve=True,
        ablation_delta=-0.02, ablation_pass=True, null_pass=True,
        calibration_ok=True, clv=None, clv_pass=True,
        p_value=1e-6, fdr_pass=True)


def test_ship_verdict_logs_artifact_warning(monkeypatch, caplog):
    """SHIP verdict fires PROBABLE ARTIFACT warning; no edge is claimed."""
    df = pd.DataFrame({
        "event_id": ["ev1", "ev2"],
        "diff_1st_win_asof": [0.05, -0.03],
    })
    bb = FeatureBundle(
        base=np.zeros((2, 5)), signal_col=np.zeros(2),
        target=np.array([1.0, 0.0]), dates=["2024-01-10", "2024-01-11"])
    monkeypatch.setattr(mod, "_build_base_bundle_with_ids",
                        lambda seasons=None, adapter=None: (bb, ["ev1", "ev2"]))
    monkeypatch.setattr(mod.pd, "read_parquet", lambda p: df)
    monkeypatch.setattr(mod.Path, "exists", lambda self: True)
    monkeypatch.setattr(mod, "evaluate", _fake_ship_result)

    with caplog.at_level(logging.WARNING):
        rows = mod.run_gate_test(seasons=[2024])

    assert len(rows) == 1
    assert rows[0]["verdict"] == "SHIP"
    # Warning fired and explicitly disclaims edge.
    assert any(
        "PROBABLE ARTIFACT" in rec.message and "NO edge" in rec.message
        for rec in caplog.records
    )
    # Honest summary flags artifact, never claims edge.
    summary = mod._summary_line(rows)
    assert "PROBABLE ARTIFACT" in summary and "NO edge claimed" in summary


def test_summary_line_reject_is_no_edge():
    """REJECT/DEFER verdicts produce 'NO edge' summary without artifact flag."""
    rows = [{"name": "tennis_diff_1st_win_asof", "verdict": "REJECT"},
            {"name": "tennis_diff_ace_rate_asof", "verdict": "DEFER"}]
    s = mod._summary_line(rows)
    assert "NO edge" in s
    assert "PROBABLE ARTIFACT" not in s


def test_summary_line_empty_rows():
    """Empty rows list produces a DEFER / no edge summary."""
    s = mod._summary_line([])
    assert "DEFER" in s or "no edge" in s.lower()
