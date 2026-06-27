"""Per-file tests for proof_soccer.gate_test_xg_proxy honesty behavior.

Base-bundle machinery is covered by the existing soccer gate tests (reused verbatim).
These lock the NEW module: candidate selection, summary vocabulary, and that a SHIP
fires a PROBABLE-ARTIFACT warning and is never claimed as an edge.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_gate_test_xg_proxy.py -q
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from src.loop.gate import FeatureBundle
from src.loop.signal import GateResult, Verdict
import scripts.platformkit.proof_soccer.gate_test_xg_proxy as mod


def test_candidate_columns_present_and_absent():
    df = pd.DataFrame({"event_id": ["e"], "diff_xg_for_asof": [0.1],
                       "diff_xg_against_asof": [0.0], "diff_xg_supremacy_asof": [0.0]})
    assert mod._candidate_columns(df) == list(mod._PREFERRED_CANDIDATES)
    assert mod._candidate_columns(pd.DataFrame({"event_id": ["e"]})) == []


def test_summary_line_reject_ship_empty():
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
    df = pd.DataFrame({"event_id": ["e1", "e2"], "diff_xg_supremacy_asof": [0.05, -0.03]})
    bb = FeatureBundle(base=np.zeros((2, 5)), signal_col=np.zeros(2),
                       target=np.array([1.0, 0.0]), dates=["2024-08-10", "2024-08-11"])
    monkeypatch.setattr(mod, "_build_base_bundle_with_ids", lambda seasons=None: (bb, ["e1", "e2"]))
    monkeypatch.setattr(mod.pd, "read_parquet", lambda p: df)
    monkeypatch.setattr(mod.Path, "exists", lambda self: True)
    monkeypatch.setattr(mod, "derive_bundle", lambda b, sc: object())
    monkeypatch.setattr(mod, "evaluate", _fake_ship)
    with caplog.at_level(logging.WARNING):
        rows = mod.run_gate_test()
    assert any(r["verdict"] == "SHIP" for r in rows)
    assert any("PROBABLE ARTIFACT" in rec.message for rec in caplog.records)
