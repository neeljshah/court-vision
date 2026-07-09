"""batter_pa_agg tests -- PA-weighted mean correctness, coverage floor, the
catcher-vs-batter same-role denominator, team-code crosswalk, and the full
batter -> team -> gate pipeline (planted signal -> MATTERS, noise -> NULL).
Mirrors test_player_team_agg.py's MLB pitcher section but with
atBats/baseOnBalls/hitByPitch PA weights and position-based role filters."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.intel_weighting.batter_pa_agg import aggregate_to_team_batter_pa
from scripts.platformkit.intel_weighting.relevance_gate import run_gate
from scripts.platformkit.intel_weighting.sport_config import WIN_COL


def _gamelogs(tmp_path, rows: dict):
    path = tmp_path / "gamelogs.parquet"
    pd.DataFrame(rows).to_parquet(path)
    return path


def test_pa_weighted_mean_is_correct(tmp_path):
    path = _gamelogs(tmp_path, {
        "date": [pd.Timestamp("2024-06-01")] * 2, "team": ["SD", "SD"],
        "player_id": [1, 2], "atBats": [4.0, 3.0], "baseOnBalls": [0.0, 0.0],
        "hitByPitch": [0.0, 0.0], "is_pitcher": [False, False],
        "position": ["1B", "2B"],
    })
    team_vals, dropped = aggregate_to_team_batter_pa({"1": 10.0, "2": 2.0}, "2024", gamelogs=path)
    assert dropped == []
    assert abs(team_vals["SDG"] - 46 / 7) < 1e-9   # (10*4 + 2*3) / 7, ESPN-code remap SD->SDG


def test_pitcher_rows_excluded_from_pa_weight(tmp_path):
    """A pitcher row (is_pitcher=True) with a huge atBats value must not leak
    into the batter PA weight -- this is exactly the bug being fixed."""
    path = _gamelogs(tmp_path, {
        "date": [pd.Timestamp("2024-06-01")] * 2, "team": ["SD", "SD"],
        "player_id": [1, 9], "atBats": [4.0, 999.0], "baseOnBalls": [0.0, 0.0],
        "hitByPitch": [0.0, 0.0], "is_pitcher": [False, True],
        "position": ["1B", "P"],
    })
    team_vals, dropped = aggregate_to_team_batter_pa({"1": 10.0}, "2024", gamelogs=path)
    assert dropped == []
    assert abs(team_vals["SDG"] - 10.0) < 1e-9   # pitcher row contributes zero PA weight


def test_catcher_role_uses_catcher_only_denominator(tmp_path):
    """A catcher attribute must denominate against CATCHER PA only, not the
    whole roster's -- else a catcher (a small share of team PA) would always
    fall below the coverage floor, reproducing the original bug for framing."""
    path = _gamelogs(tmp_path, {
        "date": [pd.Timestamp("2024-06-01")] * 3, "team": ["SD", "SD", "SD"],
        "player_id": [1, 2, 3],
        "atBats": [4.0, 4.0, 400.0],  # non-catcher batter PA is huge but irrelevant to role="catcher"
        "baseOnBalls": [0.0, 0.0, 0.0], "hitByPitch": [0.0, 0.0, 0.0],
        "is_pitcher": [False, False, False], "position": ["C", "C", "1B"],
    })
    team_vals, dropped = aggregate_to_team_batter_pa(
        {"1": 10.0}, "2024", role="catcher", min_coverage=0.5, gamelogs=path)
    assert dropped == []
    assert abs(team_vals["SDG"] - 10.0) < 1e-9   # 10*4 / 4 covered-PA, catcher-only denominator (8 total)


def test_coverage_floor_drops_undercovered_team(tmp_path):
    path = _gamelogs(tmp_path, {
        "date": [pd.Timestamp("2024-06-01")] * 4, "team": ["A", "A", "B", "B"],
        "player_id": [1, 2, 3, 4], "atBats": [3.0, 2.0, 1.0, 4.0],
        "baseOnBalls": [0.0, 0.0, 0.0, 0.0], "hitByPitch": [0.0, 0.0, 0.0, 0.0],
        "is_pitcher": [False, False, False, False],
        "position": ["1B", "2B", "3B", "SS"],
        # A: 3/5 = 60% covered (kept); B: 1/5 = 20% covered (dropped)
    })
    team_vals, dropped = aggregate_to_team_batter_pa(
        {"1": 5.0, "3": 5.0}, "2024", min_coverage=0.6, gamelogs=path)
    assert "A" in team_vals and "B" not in team_vals
    assert dropped == ["B"]


_OTHER_TEAMS = ["ATL", "BOS", "CIN", "CLE", "COL", "DET", "HOU", "LAA", "LAD", "MIA",
                "MIL", "MIN", "NYM", "NYY", "OAK", "PHI", "PIT"]
_MLB_STD_TEAMS = ["SD", "CHC", "KC"] + _OTHER_TEAMS
_MLB_ESPN_TEAMS = ["SDG", "CUB", "KAN"] + _OTHER_TEAMS


def _mlb_batter_gamelogs(tmp_path, teams, values_by_team):
    """One batter per team, fully covering that team's recorded PA (100%
    coverage)."""
    rows = {"date": [], "team": [], "player_id": [], "atBats": [],
            "baseOnBalls": [], "hitByPitch": [], "is_pitcher": [], "position": []}
    player_values = {}
    for i, t in enumerate(teams):
        rows["date"].append(pd.Timestamp("2025-06-01"))
        rows["team"].append(t)
        rows["player_id"].append(i)
        rows["atBats"].append(4.0)
        rows["baseOnBalls"].append(0.0)
        rows["hitByPitch"].append(0.0)
        rows["is_pitcher"].append(False)
        rows["position"].append("1B")
        player_values[str(i)] = values_by_team[t]
    path = tmp_path / "gamelogs.parquet"
    pd.DataFrame(rows).to_parquet(path)
    return path, player_values


def _synth_mlb_games(n=600, seed=0):
    rng = np.random.default_rng(seed)
    strength = {t: rng.normal() for t in _MLB_ESPN_TEAMS}
    home = rng.choice(_MLB_ESPN_TEAMS, n)
    away = rng.choice(_MLB_ESPN_TEAMS, n)
    ok = home != away
    home, away = home[ok], away[ok]
    z = 1.8 * np.array([strength[h] - strength[a] for h, a in zip(home, away)])
    y = (rng.random(len(z)) < 1 / (1 + np.exp(-z))).astype(float)
    games = pd.DataFrame({
        "home_team": home, "away_team": away, "season": "2026",
        WIN_COL: y, "game_id": [f"g{i}" for i in range(len(y))],
    })
    base_logit = np.zeros(len(games))
    mask = np.ones(len(games), dtype=bool)
    strength_std = {std: strength[espn] for std, espn in zip(_MLB_STD_TEAMS, _MLB_ESPN_TEAMS)}
    return games, base_logit, mask, strength_std


def test_planted_batter_pa_signal_flows_to_matters(tmp_path):
    games, bl, mask, strength_std = _synth_mlb_games()
    path, player_values = _mlb_batter_gamelogs(tmp_path, _MLB_STD_TEAMS, strength_std)

    team_vals, dropped = aggregate_to_team_batter_pa(player_values, "2025", gamelogs=path)
    assert dropped == []
    assert "SDG" in team_vals and "CUB" in team_vals and "KAN" in team_vals, team_vals
    res = run_gate("mlb", "fam", "planted_batter", team_vals, games, bl, mask,
                   "batter_pa_prior_season")
    assert res.verdict == "MATTERS_PROVISIONAL", (res.verdict, res.delta, res.dm_p)


def test_noise_batter_pa_signal_stays_null(tmp_path):
    games, bl, mask, _ = _synth_mlb_games()
    rng = np.random.default_rng(3)
    noise_std = {t: rng.normal() for t in _MLB_STD_TEAMS}
    path, player_values = _mlb_batter_gamelogs(tmp_path, _MLB_STD_TEAMS, noise_std)

    team_vals, dropped = aggregate_to_team_batter_pa(player_values, "2025", gamelogs=path)
    assert dropped == []
    res = run_gate("mlb", "fam", "noise_batter", team_vals, games, bl, mask,
                   "batter_pa_prior_season")
    assert res.verdict == "NULL", (res.verdict, res.delta, res.dm_p)


if __name__ == "__main__":
    print("run via pytest -- see module docstring")
