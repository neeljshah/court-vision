"""Per-file tests for proof_basketball_nba.gate_test_quarter_shape honesty + crosswalk.

Base-bundle machinery is covered by the existing NBA gate tests (reused verbatim).
These lock the NEW module: candidate selection, the ESPN->NBA game_id crosswalk, the
honest summary vocabulary, and that a SHIP fires a PROBABLE-ARTIFACT warning.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_gate_test_quarter_shape.py -q
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from src.loop.gate import FeatureBundle
from src.loop.signal import GateResult, Verdict
import scripts.platformkit.proof_basketball_nba.gate_test_quarter_shape as mod


def test_candidate_columns_present_and_absent():
    df = pd.DataFrame({"game_id": ["g"], "diff_q1_margin_asof": [0.1],
                       "diff_second_half_margin_asof": [0.0], "diff_q4_margin_asof": [0.0],
                       "diff_quarter_volatility_asof": [0.0]})
    assert mod._candidate_columns(df) == list(mod._PREFERRED_CANDIDATES)
    df2 = pd.DataFrame({"game_id": ["g"], "diff_q1_margin_asof": [0.1]})
    assert mod._candidate_columns(df2) == ["diff_q1_margin_asof"]


def test_resolve_game_ids_crosswalk(monkeypatch):
    games = pd.DataFrame({"game_id": ["0022500999"], "date": ["2025-01-01"],
                          "home_team": ["GSW"], "away_team": ["BOS"]})
    monkeypatch.setattr(mod.pd, "read_parquet", lambda p: games)
    asof = pd.DataFrame({"event_id": ["e1"], "date": ["2025-01-01"],
                         "home_abbr": ["GS"], "away_abbr": ["BOS"],  # ESPN 'GS' -> 'GSW'
                         "diff_q1_margin_asof": [0.5]})
    out = mod._resolve_game_ids(asof)
    assert out.loc[0, "game_id"] == "0022500999"


def test_resolve_game_ids_short_circuits_when_present():
    asof = pd.DataFrame({"game_id": ["x"], "diff_q1_margin_asof": [0.1]})
    out = mod._resolve_game_ids(asof)
    assert list(out["game_id"]) == ["x"]  # untouched


def test_summary_line_reject_and_ship_and_empty():
    assert "NO edge" in mod._summary_line([{"name": "a", "verdict": "REJECT"}])
    s = mod._summary_line([{"name": "a", "verdict": "SHIP"}])
    assert "PROBABLE ARTIFACT" in s and "NO edge claimed" in s
    assert "DEFER" in mod._summary_line([]) or "no edge" in mod._summary_line([]).lower()


def _fake_ship(signal, **kw) -> GateResult:
    return GateResult(
        signal_name=signal.name, verdict=Verdict.SHIP, reason="fake ship",
        wf_folds=[-0.01, -0.02, -0.03], wf_all_improve=True,
        ablation_delta=-0.02, ablation_pass=True, null_pass=True,
        calibration_ok=True, clv=None, clv_pass=True, p_value=1e-6, fdr_pass=True)


def test_ship_verdict_logs_artifact_warning(monkeypatch, caplog):
    df = pd.DataFrame({"game_id": ["g1", "g2"], "diff_q1_margin_asof": [0.05, -0.03]})
    bb = FeatureBundle(base=np.zeros((2, 8)), signal_col=np.zeros(2),
                       target=np.array([1.0, 0.0]), dates=["2025-01-10", "2025-01-11"])
    monkeypatch.setattr(mod, "_build_base_bundle_with_ids", lambda seasons=None: (bb, ["g1", "g2"]))
    monkeypatch.setattr(mod.pd, "read_parquet", lambda p: df)
    monkeypatch.setattr(mod.Path, "exists", lambda self: True)
    monkeypatch.setattr(mod, "derive_bundle", lambda b, sc: object())
    monkeypatch.setattr(mod, "evaluate", _fake_ship)

    with caplog.at_level(logging.WARNING):
        rows = mod.run_gate_test(seasons=["2025-26"])
    assert rows and rows[0]["verdict"] == "SHIP"
    assert any("PROBABLE ARTIFACT" in r.message for r in caplog.records)
