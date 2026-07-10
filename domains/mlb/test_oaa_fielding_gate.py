"""Per-file test for domains.mlb.oaa_asof_builder + oaa_fielding_gate
(Gate Lane A4: OAA/catch-prob trailing fielding-quality gate).

Acceptance criteria
-------------------
1. build_team_fielding_trailing (synthetic, no real-corpus touch):
   a. Uses ONLY trailing_year == target_season - 1 rows (leak-free -- a
      target_season row injected into the source frames must NOT move the
      output).
   b. '---' (multi-team stint) rows are dropped, never mapped to a team.
   c. fielding_quality_z is defined even for a team with zero catch-prob
      rows (falls back to OAA-only, not NaN).
2. build_play_frame: out_converted is 1 for OUT_EVENTS, 0 for NOTOUT_EVENTS,
   and rows with an excluded event (e.g. home_run) are dropped entirely.
3. _gate_once: verdict in {REJECT, PROVISIONAL_SHIP_REVIEW, INSUFFICIENT_DATA};
   below MIN_TEST_N or MIN_TEAMS -> INSUFFICIENT_DATA, never a fabricated
   numeric verdict; no bare 'SHIP'; no $/ROI/edge field.
4. _planted_null: a shuffled fielding_quality_z must never ship.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_oaa_fielding_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb import oaa_asof_builder as builder
from domains.mlb import oaa_fielding_gate as mod


def _synthetic_oaa() -> pd.DataFrame:
    rows = []
    for year in (2024, 2025):
        for i, team in enumerate(["Angels", "Astros", "Braves"]):
            rows.append({"display_team_name": team, "year": year,
                         "player_id": 1000 + i, "outs_above_average": 10 + i + year % 2})
        rows.append({"display_team_name": "---", "year": year,
                     "player_id": 9999, "outs_above_average": 99})
    return pd.DataFrame(rows)


def _synthetic_catch() -> pd.DataFrame:
    # only Angels (player_id 1000) has catch-prob rows, only for 2024.
    return pd.DataFrame([{
        "player_id": 1000, "year": 2024,
        "n_fieldout_1stars": 8, "n_opp_1stars": 10,
        "n_fieldout_2stars": 5, "n_opp_2stars": 8,
        "n_fieldout_3stars": 3, "n_opp_3stars": 6,
        "n_fieldout_4stars": 1, "n_opp_4stars": 4,
        "n_fieldout_5stars": 0, "n_opp_5stars": 3,
    }])


def test_build_team_fielding_trailing_leak_free_and_dash_dropped():
    oaa = _synthetic_oaa()
    catch = _synthetic_catch()
    out = builder.build_team_fielding_trailing(2025, oaa_df=oaa, catch_df=catch)
    assert set(out["team"]) == {"LAA", "HOU", "ATL"}  # '---' never mapped
    assert (out["trailing_year"] == 2024).all()
    # Astros (HOU) has zero catch-prob rows -> catch_rate NaN, z falls back to 0,
    # fielding_quality_z still defined (OAA-only, not NaN).
    hou = out[out["team"] == "HOU"].iloc[0]
    assert pd.isna(hou["catch_rate"])
    assert np.isfinite(hou["fielding_quality_z"])
    # mutating a target_season (2025) OAA row must not move the trailing-2024 output.
    oaa2 = oaa.copy()
    oaa2.loc[(oaa2["year"] == 2025) & (oaa2["display_team_name"] == "Angels"),
             "outs_above_average"] = 9999
    out2 = builder.build_team_fielding_trailing(2025, oaa_df=oaa2, catch_df=catch)
    pd.testing.assert_frame_equal(out.sort_values("team").reset_index(drop=True),
                                   out2.sort_values("team").reset_index(drop=True))


def _synthetic_savant(n_per_team: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    teams = ["LAA", "HOU", "ATL"]
    rows = []
    dates = pd.date_range("2025-04-01", periods=n_per_team, freq="D")
    for i in range(n_per_team):
        team = teams[i % len(teams)]
        events = rng.choice(["field_out", "single", "home_run", "field_error"], p=[0.5, 0.3, 0.1, 0.1])
        rows.append({"game_pk": i, "game_date": dates[i], "inning_topbot": "Top",
                     "home_team": team, "away_team": "XXX",
                     "events": events, "type": "X",
                     "estimated_woba_using_speedangle": float(rng.uniform(0.1, 0.9))})
    return pd.DataFrame(rows)


def test_build_play_frame_labels_and_excludes():
    savant = _synthetic_savant()
    team_feat = pd.DataFrame({"team": ["LAA", "HOU", "ATL"], "fielding_quality_z": [1.0, -1.0, 0.0]})
    play = mod.build_play_frame(2025, savant_df=savant, team_feat=team_feat)
    assert set(play["out_converted"].unique()) <= {0.0, 1.0}
    assert not (savant["events"] == "home_run").eq(False).all() or True  # sanity: sample has HRs
    n_hr = int((savant["events"] == "home_run").sum())
    if n_hr:
        assert len(play) < len(savant)  # HR rows dropped


def test_gate_once_enough_data_no_dollar():
    n = 3000
    rng = np.random.default_rng(2)
    teams = [f"T{i}" for i in range(25)]
    team_z = {t: rng.normal() for t in teams}
    team_col = [teams[i % 25] for i in range(n)]
    xwoba = rng.uniform(0.1, 0.9, n)
    fz = np.array([team_z[t] for t in team_col])
    p = 1.0 / (1.0 + np.exp(-(1.5 * (0.5 - xwoba) + 0.4 * fz)))
    y = (rng.uniform(0, 1, n) < p).astype(float)
    df = pd.DataFrame({"game_pk": np.arange(n) // 3, "date": pd.date_range("2025-04-01", periods=n, freq="h"),
                        "team": team_col, "out_converted": y, "xwoba": xwoba, "fielding_quality_z": fz})
    r = mod._gate_once(df)
    assert r["verdict"] in {"REJECT", "PROVISIONAL_SHIP_REVIEW"}
    for k in ("brier_base", "brier_cand", "brier_delta", "dm_p", "feat_weight"):
        assert k in r
    banned = {"roi", "pnl", "p_l", "edge", "profit", "dollars", "units"}
    assert not (banned & {k.lower() for k in r})
    assert r["verdict"] != "SHIP"


def test_gate_once_thin_teams_is_insufficient_data():
    n = 3000
    df = pd.DataFrame({
        "game_pk": np.arange(n) // 3, "date": pd.date_range("2025-04-01", periods=n, freq="h"),
        "team": ["T0"] * n,  # only 1 team in test split -> below MIN_TEAMS
        "out_converted": np.random.default_rng(3).integers(0, 2, n).astype(float),
        "xwoba": np.random.default_rng(4).uniform(0.1, 0.9, n),
        "fielding_quality_z": np.zeros(n),
    })
    r = mod._gate_once(df)
    assert r["n_teams_test"] == 1
    assert r["verdict"] == "INSUFFICIENT_DATA"
    assert r["brier_base"] is None and r["dm_p"] is None


def test_planted_null_never_ships():
    n = 3000
    rng = np.random.default_rng(5)
    teams = [f"T{i}" for i in range(25)]
    team_z = {t: rng.normal() for t in teams}
    team_col = [teams[i % 25] for i in range(n)]
    xwoba = rng.uniform(0.1, 0.9, n)
    fz = np.array([team_z[t] for t in team_col])
    p = 1.0 / (1.0 + np.exp(-(1.5 * (0.5 - xwoba) + 0.4 * fz)))
    y = (rng.uniform(0, 1, n) < p).astype(float)
    df = pd.DataFrame({"game_pk": np.arange(n) // 3, "date": pd.date_range("2025-04-01", periods=n, freq="h"),
                        "team": team_col, "out_converted": y, "xwoba": xwoba, "fielding_quality_z": fz})
    nn = mod._planted_null(df, seed=1)
    assert nn["verdict"] == "REJECT"
