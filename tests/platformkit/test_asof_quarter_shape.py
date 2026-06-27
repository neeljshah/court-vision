"""Per-file tests for domains.basketball_nba.asof_quarter_shape.

Drives the full builder on a hand-computed 3-game / 2-team synthetic corpus, checking
the realized metric derivation, shared home/away per-team state, the diff sign, the
volatility metric, and leak-freeness (debut -> NaN). Plus a guarded real-data check.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_asof_quarter_shape.py -q
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from domains.basketball_nba.asof_quarter_shape import (
    _METRICS,
    _derive_realized,
    build_asof_quarter_shape,
)


def _linescores() -> pd.DataFrame:
    # g1: AAA(home) vs BBB(away); g2 sides SWAP; g3 back.
    return pd.DataFrame({
        "event_id": ["g1", "g2", "g3"],
        "date": ["2025-01-01", "2025-01-03", "2025-01-05"],
        "home_abbr": ["AAA", "BBB", "AAA"],
        "away_abbr": ["BBB", "AAA", "BBB"],
        "home_q1": [30, 28, 26], "home_q2": [20, 28, 24],
        "home_q3": [25, 28, 25], "home_q4": [25, 28, 25],
        "away_q1": [20, 25, 22], "away_q2": [25, 25, 26],
        "away_q3": [20, 25, 24], "away_q4": [25, 25, 23],
    })


def test_derive_realized_margins_and_volatility():
    r = _derive_realized(_linescores()).set_index("event_id")
    # g1 AAA(home): q1_margin 30-20=10; first_half (50)-(45)=5; second_half (50)-(45)=5; q4 0
    assert r.loc["g1", "home_q1_margin"] == 10
    assert r.loc["g1", "home_first_half_margin"] == 5
    assert r.loc["g1", "home_second_half_margin"] == 5
    assert r.loc["g1", "home_q4_margin"] == 0
    # volatility = population std of [30,20,25,25] = 3.5355...
    assert r.loc["g1", "home_quarter_volatility"] == pytest.approx(np.std([30, 20, 25, 25]))
    # away is the mirror: q1_margin -10
    assert r.loc["g1", "away_q1_margin"] == -10


def test_build_shared_state_diff_sign_and_leak_free(tmp_path):
    dest = build_asof_quarter_shape(
        linescores=_linescores(), games=pd.DataFrame(), out_path=str(tmp_path / "qs.parquet"))
    df = pd.read_parquet(dest).set_index("event_id")

    # g1: both teams debut -> NaN, n_prior 0
    assert np.isnan(df.loc["g1", "diff_q1_margin_asof"])
    assert df.loc["g1", "home_n_prior"] == 0 and df.loc["g1", "away_n_prior"] == 0

    # g2: sides swapped. AAA is AWAY now; its prior (as home in g1) q1_margin=10 -> SHARED.
    # BBB is HOME now; its prior (as away in g1) q1_margin=-10.
    assert df.loc["g2", "away_q1_margin_asof"] == pytest.approx(10.0)
    assert df.loc["g2", "home_q1_margin_asof"] == pytest.approx(-10.0)
    # diff = home_asof - away_asof = -10 - 10 = -20
    assert df.loc["g2", "diff_q1_margin_asof"] == pytest.approx(-20.0)
    assert df.loc["g2", "home_n_prior"] == 1 and df.loc["g2", "away_n_prior"] == 1
    # volatility carries through (AAA g1 vol)
    assert df.loc["g2", "away_quarter_volatility_asof"] == pytest.approx(np.std([30, 20, 25, 25]))


def test_output_columns_present(tmp_path):
    dest = build_asof_quarter_shape(
        linescores=_linescores(), games=pd.DataFrame(), out_path=str(tmp_path / "qs.parquet"))
    cols = set(pd.read_parquet(dest).columns)
    for m in _METRICS:
        for pre in ("home", "away", "diff"):
            assert f"{pre}_{m}_asof" in cols
    assert {"event_id", "home_n_prior", "away_n_prior"} <= cols


def test_no_future_quarter_leaks_into_own_asof(tmp_path):
    # Leak-free assertion: a game's own realized quarters must NEVER appear in its own
    # as-of value. g1 is AAA's debut (-> NaN); g2's AAA as-of equals ONLY its g1 prior,
    # never any g2 quarter. We mutate g2's quarters wildly and confirm g2's as-of is
    # unchanged (proving the snapshot strictly precedes the update).
    base = _linescores()
    a = build_asof_quarter_shape(
        linescores=base, games=pd.DataFrame(), out_path=str(tmp_path / "a.parquet"))
    da = pd.read_parquet(a).set_index("event_id")
    mut = base.copy()
    mut.loc[mut["event_id"] == "g2", ["home_q1", "home_q2", "home_q3", "home_q4"]] = 99
    b = build_asof_quarter_shape(
        linescores=mut, games=pd.DataFrame(), out_path=str(tmp_path / "b.parquet"))
    db = pd.read_parquet(b).set_index("event_id")
    for m in _METRICS:
        assert da.loc["g2", f"home_{m}_asof"] == pytest.approx(db.loc["g2", f"home_{m}_asof"])
        assert da.loc["g2", f"away_{m}_asof"] == pytest.approx(db.loc["g2", f"away_{m}_asof"])


def test_game_id_join_maps_abbr_and_date(tmp_path):
    # Synthetic games corpus with NBA abbrs; linescores uses ESPN 'GS' -> canonical 'GSW'.
    ls = pd.DataFrame({
        "event_id": ["e1"], "date": ["2025-01-01"],
        "home_abbr": ["GS"], "away_abbr": ["BOS"],
        "home_q1": [30], "home_q2": [20], "home_q3": [25], "home_q4": [25],
        "away_q1": [20], "away_q2": [25], "away_q3": [20], "away_q4": [25],
    })
    games = pd.DataFrame({
        "game_id": ["0022500999"], "date": ["2025-01-01"],
        "home_team": ["GSW"], "away_team": ["BOS"],
    })
    dest = build_asof_quarter_shape(
        linescores=ls, games=games, out_path=str(tmp_path / "qs.parquet"))
    df = pd.read_parquet(dest)
    assert df.loc[0, "game_id"] == "0022500999"


def test_guarded_real_linescores_leak_free():
    path = "data/domains/basketball_nba/linescores.parquet"
    if not os.path.exists(path):
        pytest.skip("linescores.parquet absent")
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        dest = build_asof_quarter_shape(out_path=os.path.join(d, "qs.parquet"))
        df = pd.read_parquet(dest)
    assert len(df) > 500
    # no future leak: debut rows (home_n_prior==0) must have NaN as-of
    debut = df[df["home_n_prior"] == 0]
    assert debut["diff_q1_margin_asof"].notna().sum() == 0 or debut.empty
    for m in _METRICS:
        assert f"diff_{m}_asof" in df.columns
