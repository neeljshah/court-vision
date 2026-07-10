"""Per-file test for domains.mlb.asof_debut_freshness_gate (MiLB debut-freshness
first gate, Gate Lane F3).

Acceptance criteria
-------------------
1. build_candidate_frame (synthetic, no real-corpus touch):
   a. Season-filters to target_season only.
   b. is_debut_game is 1 exactly for games the injected debut_game_pks resolve
      to via the game_pk_bridge, 0 elsewhere (honest, not fabricated).
   c. Stays chronologically sorted by date; p_base in (0, 1).
2. _gate_once:
   a. Verdict in {'REJECT', 'PROVISIONAL_SHIP_REVIEW', 'INSUFFICIENT_DATA'}.
   b. Below MIN_TEST_N debut-flagged test rows -> INSUFFICIENT_DATA (thin-N
      honesty), never a fabricated numeric verdict.
   c. No $ / P&L / ROI / edge field anywhere in the result dict, and never a
      bare 'SHIP' (verdict is capped PROVISIONAL, single-corpus).
3. _planted_null: a shuffled debut flag must never ship (verdict != 'PROVISIONAL_SHIP_REVIEW').

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_asof_debut_freshness_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb import asof_debut_freshness_gate as mod


def _synthetic_games_current() -> pd.DataFrame:
    """2 seasons x 10 games each, disjoint game_pk-style team pool (no dialect
    crosswalk needed -- that mapping is game_pk_bridge's own concern)."""
    rows = []
    for season, dates in ((2025, pd.date_range("2025-04-01", periods=10, freq="D")),
                          (2026, pd.date_range("2026-04-01", periods=10, freq="D"))):
        for i, d in enumerate(dates):
            home, away = f"T{i % 4}", f"T{(i + 1) % 4}"
            rows.append({
                "event_id": f"{d.strftime('%Y%m%d')}-{home}-{away}-1",
                "date": d, "season": season, "home_team": home, "away_team": away,
                "home_runs": 4, "away_runs": 3, "target_home_win": 1.0,
            })
    return pd.DataFrame(rows)


def test_build_candidate_frame_season_filter_and_flag():
    gc = _synthetic_games_current()
    # 2026 game_pks 1..10 map 1:1 to the 10 season-2026 rows in date order.
    game_pks_2026 = list(range(1, 11))
    team_rows = pd.concat([
        pd.DataFrame({"game_pk": game_pks_2026,
                      "date": gc[gc.season == 2026]["date"].values,
                      "team": gc[gc.season == 2026]["home_team"].values}),
        pd.DataFrame({"game_pk": game_pks_2026,
                      "date": gc[gc.season == 2026]["date"].values,
                      "team": gc[gc.season == 2026]["away_team"].values}),
    ], ignore_index=True)
    debut_game_pks = {2, 5, 9}  # 3 of the 10 season-2026 games are "debuts"

    df = mod.build_candidate_frame(target_season=2026, games_current=gc,
                                    debut_game_pks=debut_game_pks, team_rows=team_rows)

    assert set(df["season"].unique()) == {2026}
    assert df["date"].is_monotonic_increasing
    assert df["is_debut_game"].sum() == 3
    pb = df["p_base"].dropna().values
    assert np.all((pb > 0.0) & (pb < 1.0))


def _flat_gate_df(n: int, flag_positions: set) -> pd.DataFrame:
    """A flat (event_id, date, target_home_win, p_base, is_debut_game) frame for
    _gate_once, bypassing build_candidate_frame's real-data plumbing entirely."""
    rng = np.random.default_rng(3)
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    p_base = rng.uniform(0.3, 0.7, n)
    y = (rng.uniform(0.0, 1.0, n) < p_base).astype(float)
    is_debut = np.zeros(n)
    for i in flag_positions:
        is_debut[i] = 1.0
    return pd.DataFrame({
        "event_id": [f"E{i}" for i in range(n)], "date": dates,
        "target_home_win": y, "p_base": p_base, "is_debut_game": is_debut,
    })


def test_gate_once_enough_data_shape_no_dollar():
    n = 300
    flag_positions = {i for i in range(n) if i % 4 == 0}  # ~22 land in the last-30% test split
    df = _flat_gate_df(n, flag_positions)
    r = mod._gate_once(df)
    assert r["n_cov_test"] >= mod.MIN_TEST_N
    assert r["verdict"] in {"REJECT", "PROVISIONAL_SHIP_REVIEW"}
    for k in ("brier_base", "brier_cand", "brier_delta", "dm_p", "feat_weight"):
        assert k in r
    banned = {"roi", "pnl", "p_l", "edge", "profit", "dollars", "units"}
    assert not (banned & {k.lower() for k in r})
    assert r["verdict"] != "SHIP"  # never a bare SHIP -- capped PROVISIONAL


def test_gate_once_thin_n_is_insufficient_data():
    n = 60
    flag_positions = {45, 50}  # only 2 flagged rows, both inside the test split -> below MIN_TEST_N
    df = _flat_gate_df(n, flag_positions)
    r = mod._gate_once(df)
    assert r["n_cov_test"] == 2
    assert r["verdict"] == "INSUFFICIENT_DATA"
    assert r["brier_base"] is None and r["dm_p"] is None


def test_planted_null_never_ships():
    n = 300
    flag_positions = {i for i in range(n) if i % 4 == 0}
    df = _flat_gate_df(n, flag_positions)
    nn = mod._planted_null(df, seed=1)
    assert nn["verdict"] == "REJECT"
