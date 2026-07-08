"""Per-file test for prereg_shift_framing.py -- premise checks, borderline-shell
classification on toy pitches, the as-of pull-share leak guard, and the H2
LR-test/verdict machinery on synthetic data.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_prereg_shift_framing.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb import prereg_shift_framing as psf


def test_check_hit_coords_false_on_real_schema():
    # the real savant_full schema (42 cols, verified live) -- no hc_x/hc_y/hit_location
    df = pd.DataFrame({"plate_x": [0.0], "plate_z": [2.5], "batter": [1]})
    assert psf.check_hit_coords(df) is False
    df2 = pd.DataFrame({"hc_x": [120.0], "batter": [1]})
    assert psf.check_hit_coords(df2) is True


def test_check_catcher_col_blocked_path_when_absent():
    df_missing = pd.DataFrame({"description": ["ball"], "strikes": [0], "balls": [0]})
    assert psf.check_catcher_col(df_missing) is False
    df_present = pd.DataFrame({"fielder_2": [592663], "description": ["ball"]})
    assert psf.check_catcher_col(df_present) is True


def _blank_taken_row(catcher, description, plate_x, plate_z, sz_top=3.5, sz_bot=1.5,
                      strikes=0, balls=0):
    return {"fielder_2": catcher, "description": description, "plate_x": plate_x,
            "plate_z": plate_z, "sz_top": sz_top, "sz_bot": sz_bot,
            "strikes": strikes, "balls": balls}


def test_run_h2_test_blocked_when_catcher_col_absent():
    df = pd.DataFrame([_blank_taken_row(1, "called_strike", 0.0, 2.5)])
    df = df.drop(columns=["fielder_2"])
    row = psf.run_h2_test(df)
    assert row["verdict"] == "BLOCKED"
    assert "fielder_2" in row["note"]


def test_run_h1_blocked_no_hit_coords():
    df = pd.DataFrame({
        "type": ["X", "X"], "bb_type": ["ground_ball", "ground_ball"],
        "if_fielding_alignment": ["Standard", "Infield shade"],
    })
    row = psf.run_h1(df)
    assert row["verdict"] == "BLOCKED"
    assert "hc_x" in row["note"]


def test_classify_borderline_toy_pitches():
    # PLATE_HALF_WIDTH_FT=0.83, SHELL_FT=0.25, sz_top=3.5 sz_bot=1.5
    df = pd.DataFrame({
        "plate_x": [0.0, 0.83, 1.5, 0.05],   # dead-center / exactly on edge / way outside / near edge
        "plate_z": [2.5, 2.5, 2.5, 3.5],     # mid-zone / mid-zone / mid-zone / exactly on top edge
        "sz_top": [3.5, 3.5, 3.5, 3.5],
        "sz_bot": [1.5, 1.5, 1.5, 1.5],
    })
    out = psf.classify_borderline(df)
    assert out.tolist() == [False, True, False, True]


def test_build_pull_share_asof_leak_guard_and_no_silent_zero():
    """Day1 must be NaN (never a silent 0.0 -- the brief's nansum landmine), day2
    uses ONLY day1's data, day3 uses day1+day2 (never day3's own rows)."""
    df = pd.DataFrame({
        "batter": [1, 1, 1, 1, 1],
        "game_date": ["2023-04-01", "2023-04-01", "2023-04-02", "2023-04-02", "2023-04-03"],
        "is_pull": [1, 0, 1, 1, 0],  # day1: 1/2 pulled, day2: 2/2 pulled, day3: irrelevant to its own share
    })
    out = psf.build_pull_share_asof(df).set_index("game_date")["pull_share_asof"]
    assert np.isnan(out.loc["2023-04-01"])            # first date: 0/0, must be NaN not 0.0
    assert out.loc["2023-04-02"] == 0.5                # prior day1 only: 1 pulled / 2 total
    assert out.loc["2023-04-03"] == (1 + 2) / (2 + 2)  # prior day1+day2: 3 pulled / 4 total


def _synthetic_borderline_catcher_df(n_per_catcher=400, n_catchers=6, seed=3) -> pd.DataFrame:
    """Enough rows to clear a floor=50 test override, with a PLANTED catcher effect
    (catcher index shifts baseline call rate) and a planted interaction (the effect
    widens when pitcher_ahead) so the LR tests have real signal to detect."""
    rng = np.random.default_rng(seed)
    rows = []
    for c in range(n_catchers):
        base = 0.3 + 0.08 * c  # distinct per-catcher baseline -> real between-catcher variance
        for _ in range(n_per_catcher):
            ahead = rng.integers(0, 2)
            p = base + (0.35 * c / n_catchers if ahead else 0.0)  # planted interaction
            p = min(max(p, 0.05), 0.95)
            # description (NOT a separate is_strike column) drives build_taken_pitches's
            # own is_strike recompute -- setting is_strike directly here would be silently
            # discarded and overwritten from description, which is what actually happened
            # the first time this test was written (every row came out description=
            # 'called_strike' -> is_strike always 1 -> perfect separation).
            description = "called_strike" if rng.random() < p else "ball"
            rows.append({"fielder_2": 1000 + c, "plate_x": 0.83, "plate_z": 2.5,
                         "sz_top": 3.5, "sz_bot": 1.5,  # exactly on the edge shell
                         "description": description, "strikes": 1 if ahead else 0, "balls": 0})
    return pd.DataFrame(rows)


def test_fit_h2_detects_planted_catcher_variance_and_interaction(monkeypatch):
    monkeypatch.setattr(psf, "CATCHER_FLOOR", 50)
    df = _synthetic_borderline_catcher_df()
    fit = psf._fit_h2(df)
    assert fit is not None
    assert fit["n_catchers"] == 6
    assert fit["variance"]["p"] < 0.01     # strong planted between-catcher spread
    assert fit["interaction"]["p"] < 0.05  # planted widening under pitcher_ahead


def test_fit_h2_none_when_no_qualifying_catchers(monkeypatch):
    monkeypatch.setattr(psf, "CATCHER_FLOOR", 10_000)  # nothing clears this floor
    df = _synthetic_borderline_catcher_df(n_per_catcher=20, n_catchers=3)
    assert psf._fit_h2(df) is None


def test_run_h2_replicate_verdict_rules(monkeypatch):
    monkeypatch.setattr(psf, "CATCHER_FLOOR", 50)
    df23 = _synthetic_borderline_catcher_df(seed=1)
    df24 = _synthetic_borderline_catcher_df(seed=2)
    test_row = psf.run_h2_test(df23)
    assert test_row["verdict"] in ("SURVIVES_PREREG", "NULL")
    rep_row = psf.run_h2_replicate(df24, test_row)
    if test_row["verdict"] == "SURVIVES_PREREG":
        assert rep_row["verdict"] in ("REPLICATED", "FAILED_REPLICATION")
    else:
        assert rep_row["verdict"] == "FAILED_REPLICATION"
    assert rep_row["edge_claimed"] is False


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
