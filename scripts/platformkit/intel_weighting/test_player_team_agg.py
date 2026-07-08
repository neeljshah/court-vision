"""player_team_agg tests -- weighted-mean correctness, the coverage floor, and
the full player -> team -> gate pipeline (planted signal -> MATTERS, noise -> NULL)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.intel_weighting.player_team_agg import aggregate_to_team
from scripts.platformkit.intel_weighting.relevance_gate import run_gate


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
    assert res.verdict == "MATTERS", (res.verdict, res.delta, res.dm_p)
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
