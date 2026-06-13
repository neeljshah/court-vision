"""tests.platform.test_gate_test_asof_mlb — offline tests for the MLB SP as-of gate test.

Synthetic ONLY: no real parquet, no real gate run (too heavy).  Verifies the
load-bearing plumbing of scripts.platformkit.proof_mlb.gate_test_asof:

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
import scripts.platformkit.proof_mlb.gate_test_asof as mod


# --------------------------------------------------------------------------- #
# 1. _align_asof
# --------------------------------------------------------------------------- #

def _asof_fixture() -> pd.DataFrame:
    """Tiny synthetic asof_features frame with the three MLB SP candidates."""
    return pd.DataFrame({
        "event_id": ["e1", "e2", "e3"],
        "sp_ra_diff_asof": [0.50, -0.30, 1.20],
        "home_sp_ra_asof": [3.80, 4.10, 3.50],
        "away_sp_ra_asof": [4.30, 3.80, 4.70],
    })


def test_align_asof_maps_and_nans_missing():
    """Values map correctly; absent event_ids come back as NaN."""
    df = _asof_fixture()
    out = mod._align_asof(df, ["e3", "e1", "e_missing", "e2"], "sp_ra_diff_asof")
    assert out[0] == pytest.approx(1.20)
    assert out[1] == pytest.approx(0.50)
    assert np.isnan(out[2])
    assert out[3] == pytest.approx(-0.30)
    assert out.shape == (4,)


def test_align_asof_home_ra():
    """home_sp_ra_asof maps correctly by event_id."""
    df = _asof_fixture()
    out = mod._align_asof(df, ["e1", "e2", "e3"], "home_sp_ra_asof")
    assert out[0] == pytest.approx(3.80)
    assert out[1] == pytest.approx(4.10)
    assert out[2] == pytest.approx(3.50)


def test_align_asof_away_ra():
    """away_sp_ra_asof maps correctly by event_id."""
    df = _asof_fixture()
    out = mod._align_asof(df, ["e1", "e2", "e3"], "away_sp_ra_asof")
    assert out[0] == pytest.approx(4.30)
    assert out[1] == pytest.approx(3.80)
    assert out[2] == pytest.approx(4.70)


# --------------------------------------------------------------------------- #
# 2. _candidate_columns
# --------------------------------------------------------------------------- #

def test_candidate_columns_from_schema():
    """All three preferred candidates present -> returned in priority order."""
    df = _asof_fixture()
    cands = mod._candidate_columns(df)
    assert cands == ["sp_ra_diff_asof", "home_sp_ra_asof", "away_sp_ra_asof"]


def test_candidate_columns_drops_unsupported():
    """Only present cols included; absent preferred cols are silently dropped."""
    df = pd.DataFrame({"event_id": ["e1"], "sp_ra_diff_asof": [0.5]})
    assert mod._candidate_columns(df) == ["sp_ra_diff_asof"]


def test_candidate_columns_empty_schema():
    """When no preferred candidates present, empty list returned."""
    df = pd.DataFrame({"event_id": ["e1"], "other_col": [1.0]})
    assert mod._candidate_columns(df) == []


# --------------------------------------------------------------------------- #
# 3. _build_base_bundle_with_ids (synthetic wf via monkeypatched helpers)
# --------------------------------------------------------------------------- #

def _synthetic_wf() -> pd.DataFrame:
    """4-row synthetic walk-forward frame; row 4 has target_home_win=NaN (dropped)."""
    return pd.DataFrame({
        "event_id": ["e1", "e2", "e3", "e4"],
        "date": ["2015-04-01", "2015-04-02", "2015-04-03", "2015-04-04"],
        "home_team": ["NYY", "BOS", "LAD", "CHC"],
        "away_team": ["BOS", "LAD", "CHC", "NYY"],
        "target_home_win": [1.0, 0.0, 1.0, np.nan],  # row 4 dropped
        "elo_home":   [1510.0, 1490.0, 1502.0, 1495.0],
        "elo_away":   [1490.0, 1510.0, 1498.0, 1505.0],
        "elo_diff_hfa": [20.0, -20.0, 4.0, -10.0],
        "p_home_elo": [0.60, 0.40, 0.55, 0.45],
        "rest_days_home": [3.0, 2.0, 4.0, 1.0],
        "rest_days_away": [2.0, 3.0, 1.0, 4.0],
        "h2h_rate": [0.5, 0.6, 0.45, 0.55],
        "home_runs": [5, 3, 7, 4],
        "away_runs": [3, 6, 2, 4],
        "season": [2015, 2015, 2015, 2015],
    })


class _FakeMLBAdapter:
    """Stands in for MLBAdapter: serves synthetic games + empty odds."""

    def _get_games(self) -> pd.DataFrame:
        return pd.DataFrame({
            "event_id": ["e1", "e2", "e3", "e4"],
            "season": [2015, 2015, 2015, 2015],
            "target_home_win": [1.0, 0.0, 1.0, np.nan],
            "home_runs": [5, 3, 7, 4],
            "away_runs": [3, 6, 2, 4],
            "date": ["2015-04-01", "2015-04-02", "2015-04-03", "2015-04-04"],
            "home_team": ["NYY", "BOS", "LAD", "CHC"],
            "away_team": ["BOS", "LAD", "CHC", "NYY"],
        })

    def _get_odds(self) -> pd.DataFrame:
        return pd.DataFrame()  # no odds -> all-NaN closing -> None


def test_build_base_bundle_with_ids_alignment(monkeypatch):
    """Bundle rows == non-NaN-target rows; event_ids aligned 1:1; base shape correct."""
    wf = _synthetic_wf()
    # Patch the elo + context helpers so we feed a deterministic synthetic wf.
    monkeypatch.setattr(mod, "walk_forward_elo", lambda g: wf.copy())
    monkeypatch.setattr(mod, "_add_context", lambda g: g)

    bundle, event_ids = mod._build_base_bundle_with_ids(
        seasons=[2015], adapter=_FakeMLBAdapter())

    assert isinstance(bundle, FeatureBundle)
    # Row 4 (target_home_win NaN) dropped -> 3 kept rows.
    assert bundle.base.shape[0] == 3
    assert len(event_ids) == bundle.base.shape[0]
    # event_ids aligned 1:1 in keep-order.
    assert event_ids == ["e1", "e2", "e3"]
    # 6 base cols (elo_home, elo_away, elo_diff_hfa, rest_days_home, rest_days_away, h2h_rate).
    assert bundle.base.shape[1] == 6
    # col 0 = elo_home for kept rows.
    assert bundle.base[0, 0] == pytest.approx(1510.0)
    assert bundle.base[1, 0] == pytest.approx(1490.0)
    assert bundle.base[2, 0] == pytest.approx(1502.0)
    # targets match.
    assert list(bundle.target) == pytest.approx([1.0, 0.0, 1.0])
    # No odds -> closing is None.
    assert bundle.closing is None


def test_build_base_bundle_raises_on_empty_seasons(monkeypatch):
    """ValueError raised when no rows pass the target-NaN filter."""
    empty_wf = pd.DataFrame({
        "event_id": [], "date": [], "home_team": [], "away_team": [],
        "target_home_win": [],
        "elo_home": [], "elo_away": [], "elo_diff_hfa": [],
        "p_home_elo": [], "rest_days_home": [], "rest_days_away": [],
        "h2h_rate": [], "home_runs": [], "away_runs": [], "season": [],
    })
    monkeypatch.setattr(mod, "walk_forward_elo", lambda g: empty_wf)
    monkeypatch.setattr(mod, "_add_context", lambda g: g)

    with pytest.raises(ValueError, match="no rows"):
        mod._build_base_bundle_with_ids(seasons=[2015], adapter=_FakeMLBAdapter())


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
    """A SHIP verdict logs PROBABLE ARTIFACT + NO edge, never claims an edge."""
    df = pd.DataFrame({
        "event_id": ["e1", "e2"],
        "sp_ra_diff_asof": [0.5, -0.3],
    })
    bb = FeatureBundle(
        base=np.zeros((2, 6)), signal_col=np.zeros(2),
        target=np.array([1.0, 0.0]), dates=["2015-04-01", "2015-04-02"])
    monkeypatch.setattr(mod, "_build_base_bundle_with_ids",
                        lambda seasons=None, adapter=None: (bb, ["e1", "e2"]))
    monkeypatch.setattr(mod.pd, "read_parquet", lambda p: df)
    monkeypatch.setattr(mod.Path, "exists", lambda self: True)
    monkeypatch.setattr(mod, "evaluate", _fake_ship_result)

    with caplog.at_level(logging.WARNING):
        rows = mod.run_gate_test(seasons=[2015])

    assert len(rows) == 1
    assert rows[0]["verdict"] == "SHIP"
    # The warning fired and explicitly disclaims an edge.
    assert any(
        "PROBABLE ARTIFACT" in rec.message and "NO edge" in rec.message
        for rec in caplog.records
    )
    # The honest summary line flags it as an artifact, never an edge.
    summary = mod._summary_line(rows)
    assert "PROBABLE ARTIFACT" in summary and "NO edge claimed" in summary


def test_summary_line_reject_is_no_edge():
    """REJECT/DEFER verdicts produce a 'NO edge' summary; never 'PROBABLE ARTIFACT'."""
    rows = [{"name": "mlb_sp_ra_diff_asof", "verdict": "REJECT"},
            {"name": "mlb_home_sp_ra_asof", "verdict": "DEFER"}]
    s = mod._summary_line(rows)
    assert "NO edge" in s
    assert "PROBABLE ARTIFACT" not in s


def test_summary_line_empty():
    """No candidates -> degenerate DEFER summary."""
    s = mod._summary_line([])
    assert "DEFER" in s and "no edge" in s.lower()
