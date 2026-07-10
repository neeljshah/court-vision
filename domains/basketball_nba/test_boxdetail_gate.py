"""Per-file test for domains.basketball_nba.boxdetail_gate.

Thin coverage:
1. _verdict_of: honest combine logic (planted-null must REJECT to trust any
   SHIP; real+truncation must both SHIP to ship).
2. _assert_no_banned_tokens: raises on a banned $-language token, passes clean.
3. run_sweep: real-slice integration run (points at the real on-disk
   boxdetail_asof.parquet, writes to a tmp out_dir) -- asserts the verdict
   shape and the current honest state. Since the 2024-25 backfill parquet
   (domains/basketball_nba/boxdetail_asof.py's _load_default_espn_box) now
   gives box-detail coverage that spans this gate's 70% train cutoff, every
   feature is a REAL evaluated test (no longer NOT_TESTABLE/premise-blocked).
   All 4 REJECT on the current corpus -- an honest REJECT is a success per
   repo policy, not a failure; no edge claimed.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/basketball_nba/test_boxdetail_gate.py -q
"""
from __future__ import annotations

import pytest

from domains.basketball_nba import boxdetail_gate as BG


def _res(real_v, null_v, trunc_v):
    return {"real": {"verdict": real_v}, "planted_null": {"verdict": null_v},
            "truncation": {"verdict": trunc_v}}


def test_verdict_of_requires_null_reject():
    # planted-null control failing to collapse means we can't trust any SHIP.
    assert BG._verdict_of(_res("SHIP", "SHIP", "SHIP")) == "REJECT"


def test_verdict_of_ships_only_when_real_and_trunc_ship():
    assert BG._verdict_of(_res("SHIP", "REJECT", "SHIP")) == "SHIP"
    assert BG._verdict_of(_res("SHIP", "REJECT", "REJECT")) == "REJECT"
    assert BG._verdict_of(_res("REJECT", "REJECT", "SHIP")) == "REJECT"


def test_assert_no_banned_tokens_raises_on_hit():
    with pytest.raises(ValueError):
        BG._assert_no_banned_tokens({"note": "projected ROI upside"})


def test_assert_no_banned_tokens_passes_clean():
    BG._assert_no_banned_tokens({"note": "calibration-only, no edge claimed"})


def test_run_sweep_real_slice_verdict_shape(tmp_path):
    rows = BG.run_sweep(seed=0, out_dir=tmp_path)

    assert len(rows) == len(BG.GATED_FEATURES)
    for r in rows:
        assert r["feature"] in BG.GATED_FEATURES
        assert r["verdict"] in ("SHIP", "REJECT", "NOT_TESTABLE")
        assert r["n_rows"] > 0
        assert "real" in r and "planted_null" in r and "truncation" in r
        # backfill-extended corpus: box-detail now spans the train cutoff ->
        # a REAL evaluated test, no longer premise-blocked. REJECT is honest.
        assert r["verdict"] == "REJECT"
        assert "calibration-only" in r["note"]

    assert (tmp_path / "boxdetail_gate_summary.json").exists()
    for feat in BG.GATED_FEATURES:
        assert (tmp_path / f"boxdetail_gate_{feat}.json").exists()
