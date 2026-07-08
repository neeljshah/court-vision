"""player_team_agg tests -- weighted-mean correctness, the coverage floor, and
the full player -> team -> gate pipeline (planted signal -> MATTERS, noise -> NULL).
Covers both wired sports: nba (minutes) and mlb (outs recorded, pitcher-only,
plus the ESPN<->standard team-code crosswalk games_current.parquet needs)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.intel_weighting.player_team_agg import aggregate_to_team
from scripts.platformkit.intel_weighting.relevance_gate import run_gate
from scripts.platformkit.intel_weighting.sport_config import WIN_COL


def _boxscores(tmp_path, rows: dict):
    path = tmp_path / "boxscores.parquet"
    pd.DataFrame(rows).to_parquet(path)
    return path


def test_weighted_mean_is_correct(tmp_path):
    path = _boxscores(tmp_path, {
        "season": ["2024-25"] * 2, "team": ["A", "A"],
        "player_id": [1, 2], "min": [30.0, 10.0],
    })
    team_vals, dropped = aggregate_to_team({"1": 10.0, "2": 2.0}, "2024-25", boxscores=path)
    assert dropped == []
    assert abs(team_vals["A"] - 8.0) < 1e-9   # (10*30 + 2*10) / 40


def test_coverage_floor_drops_undercovered_team(tmp_path):
    path = _boxscores(tmp_path, {
        "season": ["2024-25"] * 4, "team": ["A", "A", "B", "B"],
        "player_id": [1, 2, 3, 4], "min": [30.0, 20.0, 10.0, 40.0],
        # A: 30/50 = 60% covered (kept); B: 10/50 = 20% covered (dropped)
    })
    team_vals, dropped = aggregate_to_team({"1": 5.0, "3": 5.0}, "2024-25",
                                           min_coverage=0.6, boxscores=path)
    assert "A" in team_vals and "B" not in team_vals
    assert dropped == ["B"]


def _synth_games(n_teams=20, n=600, seed=0):
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(n_teams)]
    strength = {t: rng.normal() for t in teams}
    home = rng.choice(teams, n)
    away = rng.choice(teams, n)
    ok = home != away
    home, away = home[ok], away[ok]
    z = 1.8 * np.array([strength[h] - strength[a] for h, a in zip(home, away)])
    y = (rng.random(len(z)) < 1 / (1 + np.exp(-z))).astype(float)
    games = pd.DataFrame({
        "home_team": home, "away_team": away, "season": "2025-26",
        "home_win": y, "game_id": [f"g{i}" for i in range(len(y))],
    })
    base_logit = np.zeros(len(games))
    mask = np.ones(len(games), dtype=bool)
    return games, base_logit, mask, teams, strength


def _one_star_per_team(tmp_path, teams, values_by_team):
    """Each team's whole roster is one 36-min player carrying `values_by_team[t]`
    -- aggregation must recover the per-team value losslessly (100% coverage)."""
    rows = {"season": [], "team": [], "player_id": [], "min": []}
    player_values = {}
    for i, t in enumerate(teams):
        rows["season"].append("2024-25")
        rows["team"].append(t)
        rows["player_id"].append(i)
        rows["min"].append(36.0)
        player_values[str(i)] = values_by_team[t]
    path = _boxscores(tmp_path, rows)
    return path, player_values


def test_planted_player_signal_flows_to_matters(tmp_path):
    games, bl, mask, teams, strength = _synth_games()
    path, player_values = _one_star_per_team(tmp_path, teams, strength)

    team_vals, dropped = aggregate_to_team(player_values, "2024-25", boxscores=path)
    assert dropped == []
    res = run_gate("nba", "fam", "planted_player", team_vals, games, bl, mask,
                   "player_minwt_prior_season")
    assert res.verdict == "MATTERS_PROVISIONAL", (res.verdict, res.delta, res.dm_p)
    assert res.delta > 0 and res.delta_trunc80 > 0


def test_noise_player_signal_stays_null(tmp_path):
    games, bl, mask, teams, _ = _synth_games()
    rng = np.random.default_rng(2)
    noise = {t: rng.normal() for t in teams}
    path, player_values = _one_star_per_team(tmp_path, teams, noise)

    team_vals, dropped = aggregate_to_team(player_values, "2024-25", boxscores=path)
    assert dropped == []
    res = run_gate("nba", "fam", "noise_player", team_vals, games, bl, mask,
                   "player_minwt_prior_season")
    assert res.verdict == "NULL", (res.verdict, res.delta, res.dm_p)


# ---------------------------------------------------------------------------
# MLB: outs-weighted pitcher -> team, plus the ESPN<->standard team-code
# crosswalk games_current.parquet's naming needs (SD -> SDG etc.).
# ---------------------------------------------------------------------------

_OTHER_TEAMS = ["ATL", "BOS", "CIN", "CLE", "COL", "DET", "HOU", "LAA", "LAD", "MIA",
                "MIL", "MIN", "NYM", "NYY", "OAK", "PHI", "PIT"]
_MLB_STD_TEAMS = ["SD", "CHC", "KC"] + _OTHER_TEAMS          # gamelogs codes (20 total)
_MLB_ESPN_TEAMS = ["SDG", "CUB", "KAN"] + _OTHER_TEAMS       # games_current codes (3 differ)


def _mlb_gamelogs(tmp_path, teams, values_by_team):
    """One pitcher per team, fully covering that team's recorded outs for the
    season (100% coverage) -- mirrors _one_star_per_team but for the MLB
    gamelogs schema (date-derived season, is_pitcher filter, outs weight)."""
    rows = {"date": [], "team": [], "player_id": [], "outs": [], "is_pitcher": []}
    player_values = {}
    for i, t in enumerate(teams):
        rows["date"].append(pd.Timestamp("2025-06-01"))
        rows["team"].append(t)
        rows["player_id"].append(i)
        rows["outs"].append(27.0)
        rows["is_pitcher"].append(True)
        player_values[str(i)] = values_by_team[t]
    path = tmp_path / "gamelogs.parquet"
    pd.DataFrame(rows).to_parquet(path)
    return path, player_values


def _synth_mlb_games(n=600, seed=0):
    """Games played between the ESPN-code spellings (games_current.parquet's
    convention) -- aggregate_to_team must remap gamelogs' standard-code keys
    (SD, CHC, KC) onto these before the gate can match them up."""
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
    # values_by_team keyed by the STANDARD (gamelogs) code, same signal.
    strength_std = {std: strength[espn] for std, espn in zip(_MLB_STD_TEAMS, _MLB_ESPN_TEAMS)}
    return games, base_logit, mask, strength_std


def test_mlb_pitcher_outs_weighted_signal_flows_to_matters(tmp_path):
    games, bl, mask, strength_std = _synth_mlb_games()
    path, player_values = _mlb_gamelogs(tmp_path, _MLB_STD_TEAMS, strength_std)

    team_vals, dropped = aggregate_to_team(player_values, "2025", sport="mlb", boxscores=path)
    assert dropped == []
    assert "SDG" in team_vals and "CUB" in team_vals and "KAN" in team_vals, team_vals
    res = run_gate("mlb", "fam", "planted_pitcher", team_vals, games, bl, mask,
                   "player_minwt_prior_season")
    assert res.verdict == "MATTERS_PROVISIONAL", (res.verdict, res.delta, res.dm_p)


def test_mlb_pitcher_outs_weighted_noise_stays_null(tmp_path):
    games, bl, mask, _ = _synth_mlb_games()
    rng = np.random.default_rng(3)
    noise_std = {t: rng.normal() for t in _MLB_STD_TEAMS}
    path, player_values = _mlb_gamelogs(tmp_path, _MLB_STD_TEAMS, noise_std)

    team_vals, dropped = aggregate_to_team(player_values, "2025", sport="mlb", boxscores=path)
    assert dropped == []
    res = run_gate("mlb", "fam", "noise_pitcher", team_vals, games, bl, mask,
                   "player_minwt_prior_season")
    assert res.verdict == "NULL", (res.verdict, res.delta, res.dm_p)
