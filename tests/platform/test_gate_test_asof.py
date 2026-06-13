"""tests.platform.test_gate_test_asof — offline tests for the NBA as-of AST gate test.

Synthetic ONLY: no real parquet, no real gate run (too heavy).  Verifies the
load-bearing plumbing of scripts.platformkit.proof_basketball_nba.gate_test_asof:

  1. _align_asof maps game_ids correctly + NaN on missing + derived oreb_diff.
  2. _candidate_columns reads the candidate list from the asof schema.
  3. _build_base_bundle_with_ids returns a FeatureBundle with
     len(game_ids)==base.shape[0] and game_ids aligned 1:1 (synthetic wf via
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
import scripts.platformkit.proof_basketball_nba.gate_test_asof as mod


# --------------------------------------------------------------------------- #
# 1. _align_asof
# --------------------------------------------------------------------------- #
def _asof_fixture() -> pd.DataFrame:
    return pd.DataFrame({
        "game_id": ["g1", "g2", "g3"],
        "ast_rate_diff_asof": [0.10, -0.05, 0.20],
        "home_ast_rate_asof": [0.60, 0.55, 0.62],
        "home_pace_asof": [99.0, 100.5, 98.2],
        "home_oreb_pg_asof": [10.0, 12.0, 9.0],
        "away_oreb_pg_asof": [8.0, 11.0, 9.5],
    })


def test_align_asof_maps_and_nans_missing():
    df = _asof_fixture()
    # g4 is absent -> NaN; order follows the requested game_ids, not the df order.
    out = mod._align_asof(df, ["g3", "g1", "g4", "g2"], "ast_rate_diff_asof")
    assert out[0] == pytest.approx(0.20)
    assert out[1] == pytest.approx(0.10)
    assert np.isnan(out[2])
    assert out[3] == pytest.approx(-0.05)
    assert out.shape == (4,)


def test_align_asof_derived_oreb_diff():
    df = _asof_fixture()
    out = mod._align_asof(df, ["g1", "g2", "g3"], "oreb_diff_asof")
    # home_oreb_pg - away_oreb_pg
    assert out[0] == pytest.approx(2.0)
    assert out[1] == pytest.approx(1.0)
    assert out[2] == pytest.approx(-0.5)


# --------------------------------------------------------------------------- #
# 2. _candidate_columns
# --------------------------------------------------------------------------- #
def test_candidate_columns_from_schema():
    df = _asof_fixture()  # has all preferred + the oreb derived-source cols
    cands = mod._candidate_columns(df)
    assert cands == ["ast_rate_diff_asof", "home_ast_rate_asof",
                     "home_pace_asof", "oreb_diff_asof"]


def test_candidate_columns_drops_unsupported():
    # Only ast_rate_diff present; pace + derived oreb sources absent -> dropped.
    df = pd.DataFrame({"game_id": ["g1"], "ast_rate_diff_asof": [0.1]})
    assert mod._candidate_columns(df) == ["ast_rate_diff_asof"]


# --------------------------------------------------------------------------- #
# 3. _build_base_bundle_with_ids (synthetic wf via monkeypatched helpers)
# --------------------------------------------------------------------------- #
def _synthetic_wf() -> pd.DataFrame:
    """3-game synthetic walk-forward frame mirroring real wf columns."""
    return pd.DataFrame({
        "game_id": ["g1", "g2", "g3"],
        "date": ["2024-11-01", "2024-11-02", "2024-11-03"],
        "home_team": ["AAA", "BBB", "CCC"],
        "away_team": ["BBB", "CCC", "AAA"],
        "home_win": [1.0, 0.0, np.nan],  # row 3 dropped (home_win NaN)
        "elo_home": [1510.0, 1490.0, 1505.0],
        "elo_away": [1490.0, 1510.0, 1500.0],
        "elo_diff_hfa": [20.0, -20.0, 5.0],
        "p_home_elo": [0.60, 0.40, 0.55],
        "rest_days_home": [2.0, 3.0, 1.0],
        "rest_days_away": [1.0, 2.0, 3.0],
        "home_b2b": [False, True, False],
        "away_b2b": [True, False, False],
        "rolling_win10_home": [0.5, 0.6, 0.4],
        "season": [2024, 2024, 2024],
        # walk_forward_elo passes the input columns through, incl _season_orig.
        "_season_orig": ["2024-25", "2024-25", "2024-25"],
    })


class _FakeAdapter:
    """Stands in for NBAAdapter: serves synthetic games + empty odds."""
    def _get_games(self) -> pd.DataFrame:
        return pd.DataFrame({
            "game_id": ["g1", "g2", "g3"],
            "season": ["2024-25", "2024-25", "2024-25"],
            "home_win": [1.0, 0.0, np.nan],
        })

    def _get_odds(self) -> pd.DataFrame:
        return pd.DataFrame()  # no odds -> closing None path


def test_build_base_bundle_with_ids_alignment(monkeypatch):
    wf = _synthetic_wf()
    # Patch the elo + rolling helpers so we feed a deterministic synthetic wf.
    monkeypatch.setattr(mod, "walk_forward_elo", lambda g: wf.copy())
    monkeypatch.setattr(mod, "_add_rolling_win10", lambda g: g)
    monkeypatch.setattr(mod, "_season_to_int", lambda s: 2024)

    bundle, game_ids = mod._build_base_bundle_with_ids(
        seasons=["2024-25"], adapter=_FakeAdapter())

    assert isinstance(bundle, FeatureBundle)
    # row 3 (home_win NaN) dropped -> 2 kept rows, ids 1:1 with the bundle.
    assert bundle.base.shape[0] == 2
    assert len(game_ids) == bundle.base.shape[0]
    assert game_ids == ["g1", "g2"]
    # base col 0/1 == elo_home/elo_away for the kept rows.
    assert bundle.base[0, 0] == pytest.approx(1510.0)
    assert bundle.base[1, 1] == pytest.approx(1510.0)
    assert list(bundle.target) == [1.0, 0.0]
    assert bundle.closing is None  # empty odds -> all-NaN closing -> None


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
        "game_id": ["g1", "g2"],
        "ast_rate_diff_asof": [0.1, -0.1],
    })
    bb = FeatureBundle(
        base=np.zeros((2, 8)), signal_col=np.zeros(2),
        target=np.array([1.0, 0.0]), dates=["2024-11-01", "2024-11-02"])
    monkeypatch.setattr(mod, "_build_base_bundle_with_ids",
                        lambda seasons=None, adapter=None: (bb, ["g1", "g2"]))
    monkeypatch.setattr(mod.pd, "read_parquet", lambda p: df)
    monkeypatch.setattr(mod.Path, "exists", lambda self: True)
    monkeypatch.setattr(mod, "evaluate", _fake_ship_result)

    with caplog.at_level(logging.WARNING):
        rows = mod.run_gate_test(seasons=["2024-25"])

    assert len(rows) == 1
    assert rows[0]["verdict"] == "SHIP"
    # The warning fired and explicitly disclaims an edge.
    assert any("PROBABLE ARTIFACT" in rec.message and "NO edge" in rec.message
               for rec in caplog.records)
    # The honest summary line flags it as an artifact, never an edge.
    summary = mod._summary_line(rows)
    assert "PROBABLE ARTIFACT" in summary and "NO edge claimed" in summary


def test_summary_line_reject_is_no_edge():
    rows = [{"name": "nba_x", "verdict": "REJECT"},
            {"name": "nba_y", "verdict": "DEFER"}]
    s = mod._summary_line(rows)
    assert "NO edge" in s
    assert "PROBABLE ARTIFACT" not in s
