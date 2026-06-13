"""tests.platform.test_gate_test_asof_soccer — offline tests for the soccer as-of gate test.

Synthetic ONLY: no real parquet, no real gate run (too heavy for CI).  Verifies the
load-bearing plumbing of scripts.platformkit.proof_soccer.gate_test_asof:

  1. _align_asof maps event_ids correctly + NaN on missing ids.
  2. _candidate_columns reads the candidate list from the asof schema.
  3. _build_base_bundle_with_ids returns a FeatureBundle with
     len(event_ids)==base.shape[0], event_ids aligned 1:1 (synthetic wf via
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
import scripts.platformkit.proof_soccer.gate_test_asof as mod


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

def _asof_fixture() -> pd.DataFrame:
    """Tiny synthetic asof_features DataFrame with the expected columns."""
    return pd.DataFrame({
        "event_id": ["evt1", "evt2", "evt3"],
        "diff_sot_for_asof":        [1.5, -0.8, 2.1],
        "diff_sot_against_asof":    [-0.5, 0.3, -1.2],
        "diff_shots_for_asof":      [3.0, -1.0, 4.0],
        "home_sot_ratio_for_asof":  [0.45, 0.38, 0.50],
        "home_sot_for_asof":        [5.0, 4.2, 6.1],
        "away_sot_for_asof":        [3.5, 5.0, 4.0],
    })


def _minimal_wf() -> pd.DataFrame:
    """Synthetic walk-forward frame mirroring real wf columns from walk_forward_goals."""
    return pd.DataFrame({
        "event_id":       ["evt1", "evt2", "evt3"],
        "date":           ["2022-08-06", "2022-08-07", "2022-08-08"],
        "home_team":      ["AAA", "BBB", "CCC"],
        "away_team":      ["BBB", "CCC", "AAA"],
        "lam_home":       [1.4, 1.3, 1.5],
        "lam_away":       [1.2, 1.4, 1.3],
        "lam_total":      [2.6, 2.7, 2.8],
        "p_over25":       [0.52, 0.55, 0.60],
        "target_over25":  [1.0, 0.0, np.nan],  # NaN row dropped -> 2 kept rows
        "rest_days_home": [7.0, 5.0, 3.0],
        "rest_days_away": [6.0, 4.0, 8.0],
    })


# --------------------------------------------------------------------------- #
# 1. _align_asof
# --------------------------------------------------------------------------- #

def test_align_asof_maps_and_nans_missing():
    df = _asof_fixture()
    # evt4 absent -> NaN; order follows the requested event_ids, not the df order.
    out = mod._align_asof(df, ["evt3", "evt1", "evt4", "evt2"], "diff_sot_for_asof")
    assert out[0] == pytest.approx(2.1)
    assert out[1] == pytest.approx(1.5)
    assert np.isnan(out[2])
    assert out[3] == pytest.approx(-0.8)
    assert out.shape == (4,)


def test_align_asof_all_match():
    df = _asof_fixture()
    out = mod._align_asof(df, ["evt1", "evt2", "evt3"], "home_sot_ratio_for_asof")
    np.testing.assert_allclose(out, [0.45, 0.38, 0.50])


def test_align_asof_empty_ids():
    df = _asof_fixture()
    out = mod._align_asof(df, [], "diff_sot_for_asof")
    assert out.shape == (0,)


# --------------------------------------------------------------------------- #
# 2. _candidate_columns
# --------------------------------------------------------------------------- #

def test_candidate_columns_all_preferred():
    df = _asof_fixture()  # has all four preferred columns
    cands = mod._candidate_columns(df)
    assert cands == list(mod._PREFERRED_CANDIDATES)


def test_candidate_columns_drops_unsupported():
    # Only diff_sot_for_asof present; the rest are absent -> dropped.
    df = pd.DataFrame({"event_id": ["e1"], "diff_sot_for_asof": [1.0]})
    assert mod._candidate_columns(df) == ["diff_sot_for_asof"]


def test_candidate_columns_empty_schema():
    df = pd.DataFrame({"event_id": ["e1"], "unknown_col": [0.0]})
    assert mod._candidate_columns(df) == []


# --------------------------------------------------------------------------- #
# 3. _build_base_bundle_with_ids (synthetic wf via monkeypatched helpers)
# --------------------------------------------------------------------------- #

class _FakeAdapter:
    """Stands in for SoccerAdapter: serves synthetic matches + no odds."""

    def _get_matches(self) -> pd.DataFrame:
        return pd.DataFrame({
            "event_id":      ["evt1", "evt2", "evt3"],
            "season":        [2022, 2022, 2022],
            "target_over25": [1.0, 0.0, np.nan],
        })

    def _get_odds(self) -> pd.DataFrame:
        return pd.DataFrame()  # no odds -> closing=None path


def test_build_base_bundle_ids_alignment(monkeypatch):
    wf = _minimal_wf()
    monkeypatch.setattr(mod, "walk_forward_goals", lambda df: wf.copy())
    monkeypatch.setattr(mod, "_add_rest_days", lambda df: df)

    bundle, event_ids = mod._build_base_bundle_with_ids(
        seasons=[2022], adapter=_FakeAdapter())

    assert isinstance(bundle, FeatureBundle)
    # Row 3 (target_over25 NaN) dropped -> 2 kept rows, ids 1:1 with the bundle.
    assert bundle.base.shape[0] == 2
    assert len(event_ids) == bundle.base.shape[0]
    assert event_ids == ["evt1", "evt2"]
    # base col 0/1/2 == lam_home/lam_away/lam_total for kept rows.
    assert bundle.base[0, 0] == pytest.approx(1.4)
    assert bundle.base[1, 1] == pytest.approx(1.4)
    assert bundle.base[0, 2] == pytest.approx(2.6)
    assert list(bundle.target) == [1.0, 0.0]
    assert bundle.closing is None  # empty odds -> all-NaN -> None


def test_build_base_bundle_no_rows_raises(monkeypatch):
    wf = _minimal_wf()
    # Drop all rows by making target_over25 all-NaN.
    wf["target_over25"] = np.nan
    monkeypatch.setattr(mod, "walk_forward_goals", lambda df: wf.copy())
    monkeypatch.setattr(mod, "_add_rest_days", lambda df: df)
    with pytest.raises(ValueError, match="no rows"):
        mod._build_base_bundle_with_ids(seasons=[2022], adapter=_FakeAdapter())


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
    df = pd.DataFrame({
        "event_id": ["e1", "e2"],
        "diff_sot_for_asof": [1.5, -0.8],
    })
    bb = FeatureBundle(
        base=np.zeros((2, 5)), signal_col=np.zeros(2),
        target=np.array([1.0, 0.0]), dates=["2022-08-06", "2022-08-07"])
    monkeypatch.setattr(mod, "_build_base_bundle_with_ids",
                        lambda seasons=None, adapter=None: (bb, ["e1", "e2"]))
    monkeypatch.setattr(mod.pd, "read_parquet", lambda p: df)
    monkeypatch.setattr(mod.Path, "exists", lambda self: True)
    monkeypatch.setattr(mod, "evaluate", _fake_ship_result)

    with caplog.at_level(logging.WARNING):
        rows = mod.run_gate_test(seasons=None)

    assert len(rows) == 1
    assert rows[0]["verdict"] == "SHIP"
    # Warning fired and explicitly disclaims an edge.
    assert any(
        "PROBABLE ARTIFACT" in rec.message and "NO edge" in rec.message
        for rec in caplog.records
    )
    # The honest summary line flags it as an artifact, never an edge.
    summary = mod._summary_line(rows)
    assert "PROBABLE ARTIFACT" in summary and "NO edge claimed" in summary


def test_summary_line_reject_is_no_edge():
    rows = [{"name": "soccer_diff_sot_for_asof", "verdict": "REJECT"},
            {"name": "soccer_diff_sot_against_asof", "verdict": "DEFER"}]
    s = mod._summary_line(rows)
    assert "NO edge" in s
    assert "PROBABLE ARTIFACT" not in s


def test_summary_line_empty_rows():
    s = mod._summary_line([])
    assert "DEFER" in s
    assert "no edge" in s
