"""Per-file test for the Statcast SP-fatigue K-prop gate wrapper. Checks the gate
machinery runs, the planted-null REJECTS (trustworthiness), the degenerate-base guard
exists, and no $/ROI field is emitted. Run ONLY this file:
  python -m pytest tests/test_gate_run_statcast_sp_fatigue_kprop.py -q
"""
from __future__ import annotations

import pytest

from domains.mlb import statcast_sp_fatigue_adapter as A
from scripts.platformkit import gate_run_statcast_sp_fatigue_kprop as W


def test_clustered_dm_needs_three_clusters():
    base = {"scored": True, "y": __import__("numpy").array([1.0, 2.0, 3.0]),
            "pred": __import__("numpy").array([1.0, 2.0, 3.0]),
            "mask_index": __import__("numpy").array([0, 1, 2])}
    full = dict(base)
    import pandas as pd
    df = pd.DataFrame({"date": [1, 2, 3], "game_id": [1, 2, 3],
                       "pitcher": [9, 9, 9]})  # 1 cluster -> p NaN
    _md, p = W.clustered_dm_by_pitcher(base, full, df)
    assert p != p  # NaN (g<3)


def test_run_on_real_corpora_is_honest():
    """Run the FULL gate on the real on-disk Statcast starter_table (if present)."""
    a, b, _ = A.load_both()
    if a.empty or b.empty:
        pytest.skip("real starter_table parquet not on disk")
    res = W.run()
    # No $/ROI/edge field anywhere; vs-close stays UNPROVEN/CALIBRATION.
    assert "vs_close" in res and "UNPROVEN" in res["vs_close"]
    assert not any(k in res for k in ("roi", "dollar", "edge", "hit_rate"))
    assert res["proposal_only"] is True
    # The planted-null MUST reject for the run to be trustworthy.
    assert res["null_rejects"] is True
    # Verdict is one of the honest set; a SHIP would require both-dir significant lift.
    assert res["verdict"] in ("SHIP", "PARTIAL", "REJECT", "INVALID_BASE",
                              "INSUFFICIENT_DATA", "NOT_TESTABLE")
    # Base skillfulness is reported (degenerate-base guard wired).
    assert "base_skillful" in res
