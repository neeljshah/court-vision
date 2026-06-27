"""Per-file tests for proof_tennis.gate_test_asof_return honesty behavior.

The base-bundle machinery is already covered by tests/platform/test_gate_test_asof_tennis.py
(reused verbatim here). These tests lock the NEW module's contract: candidate selection,
the honest summary vocabulary, and that a SHIP fires a PROBABLE-ARTIFACT warning and is
NEVER claimed as an edge.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_gate_test_asof_return.py -q
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from src.loop.gate import FeatureBundle
from src.loop.signal import GateResult, Verdict
import scripts.platformkit.proof_tennis.gate_test_asof_return as mod


def test_candidate_columns_present_and_absent():
    df = pd.DataFrame({"event_id": ["e1"], "diff_return_won_asof": [0.1],
                       "diff_break_pct_asof": [0.0]})
    assert mod._candidate_columns(df) == list(mod._PREFERRED_CANDIDATES)
    df2 = pd.DataFrame({"event_id": ["e1"], "diff_return_won_asof": [0.1]})
    assert mod._candidate_columns(df2) == ["diff_return_won_asof"]
    assert mod._candidate_columns(pd.DataFrame({"event_id": ["e1"]})) == []


def test_summary_line_reject_is_no_edge():
    rows = [{"name": "tennis_diff_return_won_asof", "verdict": "REJECT"},
            {"name": "tennis_diff_break_pct_asof", "verdict": "REJECT"}]
    s = mod._summary_line(rows)
    assert "NO edge" in s and "PROBABLE ARTIFACT" not in s


def test_summary_line_ship_flags_artifact_no_edge():
    rows = [{"name": "tennis_diff_return_won_asof", "verdict": "SHIP"}]
    s = mod._summary_line(rows)
    assert "PROBABLE ARTIFACT" in s and "NO edge claimed" in s


def test_summary_line_empty():
    s = mod._summary_line([])
    assert "DEFER" in s or "no edge" in s.lower()


def _fake_ship(signal, **kw) -> GateResult:
    return GateResult(
        signal_name=signal.name, verdict=Verdict.SHIP, reason="fake ship",
        wf_folds=[-0.01, -0.02, -0.03], wf_all_improve=True,
        ablation_delta=-0.02, ablation_pass=True, null_pass=True,
        calibration_ok=True, clv=None, clv_pass=True,
        p_value=1e-6, fdr_pass=True)


def test_ship_verdict_logs_artifact_warning(monkeypatch, caplog):
    df = pd.DataFrame({"event_id": ["ev1", "ev2"], "diff_return_won_asof": [0.05, -0.03]})
    bb = FeatureBundle(
        base=np.zeros((2, 5)), signal_col=np.zeros(2),
        target=np.array([1.0, 0.0]), dates=["2024-01-10", "2024-01-11"])
    monkeypatch.setattr(mod, "_build_base_bundle_with_ids",
                        lambda seasons=None: (bb, ["ev1", "ev2"]))
    monkeypatch.setattr(mod.pd, "read_parquet", lambda p: df)
    monkeypatch.setattr(mod.Path, "exists", lambda self: True)
    monkeypatch.setattr(mod, "derive_bundle", lambda b, sc: object())
    monkeypatch.setattr(mod, "evaluate", _fake_ship)

    with caplog.at_level(logging.WARNING):
        rows = mod.run_gate_test(seasons=[2024])

    assert len(rows) == 1 and rows[0]["verdict"] == "SHIP"
    assert any("PROBABLE ARTIFACT" in rec.message and "NO edge" in rec.message
               for rec in caplog.records)
    summary = mod._summary_line(rows)
    assert "PROBABLE ARTIFACT" in summary and "NO edge claimed" in summary
