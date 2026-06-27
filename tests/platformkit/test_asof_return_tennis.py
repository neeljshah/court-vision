"""Per-file tests for domains.tennis.asof_return (the surface-split return builder).

Drives the FULL builder on a hand-computed 3-match synthetic corpus and checks the
return-from-opponent-serve derivation, the overall + per-surface (NaN-mask) as-of
values, the p1-p2 diffs, and leak-freeness (debut row -> NaN). Dogfoods asof_common.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_asof_return_tennis.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from domains.tennis.asof_return import _derive_realized_return, build_asof_return


def _matches() -> pd.DataFrame:
    # A (id 1) always p1, B (id 2) always p2. ev1 Hard, ev2 Clay, ev3 Hard.
    return pd.DataFrame({
        "event_id": ["ev1", "ev2", "ev3"],
        "date": ["2024-01-01", "2024-01-08", "2024-01-15"],
        "tour": ["atp", "atp", "atp"],
        "tourney_id": ["t1", "t2", "t3"],
        "round": ["R32", "R32", "R32"],
        "match_num": [1, 1, 1],
        "p1_id": [1, 1, 1],
        "p2_id": [2, 2, 2],
        "surface": ["Hard", "Clay", "Hard"],
    })


def _match_stats() -> pd.DataFrame:
    # serve lines; return/break are derived from the OPPONENT's serve line.
    return pd.DataFrame({
        "event_id": ["ev1", "ev2", "ev3"],
        # p1 (A) serve
        "p1_SvGms": [10, 10, 10], "p1_bpFaced": [4, 3, 5], "p1_bpSaved": [1, 1, 2],
        "p1_svpt": [100, 100, 100], "p1_1stWon": [40, 45, 30], "p1_2ndWon": [20, 15, 20],
        # p2 (B) serve
        "p2_SvGms": [10, 10, 10], "p2_bpFaced": [6, 5, 4], "p2_bpSaved": [2, 2, 1],
        "p2_svpt": [100, 100, 100], "p2_1stWon": [30, 20, 35], "p2_2ndWon": [20, 20, 15],
    })


def test_derive_realized_return_formula():
    r = _derive_realized_return(_match_stats()).set_index("event_id")
    # ev1: A return vs B serve = 1 - (30+20)/100 = 0.50; A break% = (6-2)/10 = 0.40
    assert r.loc["ev1", "p1_return_won_realized"] == pytest.approx(0.50)
    assert r.loc["ev1", "p1_break_pct_realized"] == pytest.approx(0.40)
    # B return vs A serve = 1 - (40+20)/100 = 0.40; B break% = (4-1)/10 = 0.30
    assert r.loc["ev1", "p2_return_won_realized"] == pytest.approx(0.40)
    assert r.loc["ev1", "p2_break_pct_realized"] == pytest.approx(0.30)
    # ev2: A return = 1 - (20+20)/100 = 0.60
    assert r.loc["ev2", "p1_return_won_realized"] == pytest.approx(0.60)


def test_build_asof_return_values_and_leak_free(tmp_path):
    dest = build_asof_return(
        match_stats=_match_stats(), matches=_matches(),
        out_path=str(tmp_path / "asof_return.parquet"))
    df = pd.read_parquet(dest).set_index("event_id")

    # ev1: both players debut -> every as-of NaN, n_prior 0.
    assert np.isnan(df.loc["ev1", "p1_return_won_asof"])
    assert np.isnan(df.loc["ev1", "p2_return_won_asof"])
    assert np.isnan(df.loc["ev1", "diff_return_won_asof"])
    assert df.loc["ev1", "p1_return_won_n_prior"] == 0

    # ev2: one prior each. A return-won prior = 0.50, B = 0.40 -> diff 0.10.
    assert df.loc["ev2", "p1_return_won_asof"] == pytest.approx(0.50)
    assert df.loc["ev2", "p2_return_won_asof"] == pytest.approx(0.40)
    assert df.loc["ev2", "diff_return_won_asof"] == pytest.approx(0.10)
    # break%: A prior 0.40, B prior 0.30 -> diff 0.10.
    assert df.loc["ev2", "p1_break_pct_asof"] == pytest.approx(0.40)
    assert df.loc["ev2", "diff_break_pct_asof"] == pytest.approx(0.10)

    # ev3: A has two priors. Overall return-won = mean(0.50, 0.60) = 0.55.
    assert df.loc["ev3", "p1_return_won_asof"] == pytest.approx(0.55)
    assert df.loc["ev3", "p1_return_won_n_prior"] == 2
    # Surface buckets: hard sees only ev1 (0.50); clay only ev2 (0.60); grass none.
    assert df.loc["ev3", "p1_return_won_hard_asof"] == pytest.approx(0.50)
    assert df.loc["ev3", "p1_return_won_clay_asof"] == pytest.approx(0.60)
    assert np.isnan(df.loc["ev3", "p1_return_won_grass_asof"])


def test_output_has_surface_and_diff_columns(tmp_path):
    dest = build_asof_return(
        match_stats=_match_stats(), matches=_matches(),
        out_path=str(tmp_path / "asof_return.parquet"))
    cols = set(pd.read_parquet(dest).columns)
    for m in ("return_won", "break_pct"):
        assert f"diff_{m}_asof" in cols
        for s in ("hard", "clay", "grass"):
            assert f"p1_{m}_{s}_asof" in cols and f"p2_{m}_{s}_asof" in cols
    assert "surface" in cols
