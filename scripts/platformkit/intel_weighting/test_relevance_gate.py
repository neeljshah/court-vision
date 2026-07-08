"""The gate is only trusted if it can BOTH detect signal and refuse noise.

Also covers the two NEW entity mappings added when the gate was extended past
nba/mlb: tennis's direct player->side mapping and soccer's referee->game
mapping (a referee has no home/away sign -- see sport_config.soccer_referee_view)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.intel_weighting.claim_features import window_to_season
from scripts.platformkit.intel_weighting.relevance_gate import run_gate
from scripts.platformkit.intel_weighting.sport_config import WIN_COL, soccer_referee_view


def _synth(n=600, seed=0):
    rng = np.random.default_rng(seed)
    teams = [f"T{i:02d}" for i in range(20)]
    strength = {t: rng.normal() for t in teams}
    home = rng.choice(teams, n)
    away = rng.choice(teams, n)
    ok = home != away
    home, away = home[ok], away[ok]
    # outcome driven by strength diff (base_logit is uninformative -> zeros)
    z = 1.8 * np.array([strength[h] - strength[a] for h, a in zip(home, away)])
    y = (rng.random(len(z)) < 1 / (1 + np.exp(-z))).astype(float)
    df = pd.DataFrame({
        "home_team": home, "away_team": away, "season": "2025-26",
        "home_win": y, "game_id": [f"g{i}" for i in range(len(y))],
    })
    base_logit = np.zeros(len(df))
    mask = np.ones(len(df), dtype=bool)
    return df, base_logit, mask, strength, {t: rng.normal() for t in teams}


def test_gate_detects_planted_signal():
    df, bl, mask, strength, noise = _synth()
    res = run_gate("nba", "fam", "planted", strength, df, bl, mask, "team")
    assert res.verdict == "MATTERS_PROVISIONAL", (res.verdict, res.delta, res.dm_p)
    assert res.delta > 0 and res.delta_trunc80 > 0


def test_gate_refuses_pure_noise():
    df, bl, mask, strength, noise = _synth()
    res = run_gate("nba", "fam", "noise", noise, df, bl, mask, "team")
    assert res.verdict == "NULL", (res.verdict, res.delta, res.dm_p)


def test_untestable_when_too_few_oos():
    df, bl, mask, strength, _ = _synth(n=120)  # 0.4*~114 test < 60 -> UNTESTABLE
    res = run_gate("nba", "fam", "planted", strength, df, bl, mask, "team")
    assert res.verdict == "UNTESTABLE"


def test_window_to_season_rejects_splits():
    assert window_to_season("season_2024_25") == "2024-25"
    assert window_to_season("season_2024_25_home") is None
    assert window_to_season("career_to_date") is None
    assert window_to_season("2024-25") == "2024-25"


def _synth_soccer(n=600, seed=0, fractional=True):
    """Same construction as _synth but entity ids double as tennis p1/p2 ids
    and the outcome column is WIN_COL (target_home_win) -- the normalized
    column name sport_config gives every non-nba sport."""
    rng = np.random.default_rng(seed)
    teams = [f"E{i:02d}" for i in range(20)]
    strength = {t: rng.normal() for t in teams}
    home = rng.choice(teams, n)
    away = rng.choice(teams, n)
    ok = home != away
    home, away = home[ok], away[ok]
    z = 1.8 * np.array([strength[h] - strength[a] for h, a in zip(home, away)])
    p = 1 / (1 + np.exp(-z))
    if fractional:
        # soccer H/D/A -> 1.0/0.5/0.0: turn ~15% of games into draws.
        draw = rng.random(len(p)) < 0.15
        y = (rng.random(len(p)) < p).astype(float)
        y = np.where(draw, 0.5, y)
    else:
        y = (rng.random(len(p)) < p).astype(float)
    df = pd.DataFrame({
        "home_team": home, "away_team": away, "season": "2025",
        WIN_COL: y, "game_id": [f"g{i}" for i in range(len(y))],
    })
    base_logit = np.zeros(len(df))
    mask = np.ones(len(df), dtype=bool)
    return df, base_logit, mask, strength, {t: rng.normal() for t in teams}


def test_gate_handles_fractional_draw_outcome():
    """A 0.5 draw label is a valid soft target for Brier/log-loss -- no
    special-casing needed to condition on it, matching generic_rating.py's
    soccer H/D/A convention (do not invent a binary win/loss for soccer)."""
    df, bl, mask, strength, noise = _synth_soccer(fractional=True)
    assert (df[WIN_COL] == 0.5).sum() > 0, "fixture should contain draws"
    res = run_gate("soccer", "fam", "planted", strength, df, bl, mask, "team")
    assert res.verdict == "MATTERS_PROVISIONAL", (res.verdict, res.delta, res.dm_p)
    res_noise = run_gate("soccer", "fam", "noise", noise, df, bl, mask, "team")
    assert res_noise.verdict == "NULL", (res_noise.verdict, res_noise.delta)


def test_tennis_player_direct_mapping_detects_signal_and_noise():
    """Tennis maps a player straight onto a game side (fdiff = z_p1 - z_p2,
    no aggregation) -- mechanically identical to the team path, but this is
    the first sport where the entity IS one of the two competitors by id."""
    df, bl, mask, strength, noise = _synth_soccer(fractional=False)
    res = run_gate("tennis", "fam", "planted", strength, df, bl, mask, "player_direct")
    assert res.verdict == "MATTERS_PROVISIONAL", (res.verdict, res.delta, res.dm_p)
    res_noise = run_gate("tennis", "fam", "noise", noise, df, bl, mask, "player_direct")
    assert res_noise.verdict == "NULL", (res_noise.verdict, res_noise.delta)


def _synth_referee_view(n=600, seed=0):
    """Build a games_df + the referee-view transform by hand (no parquet I/O):
    each game gets a randomly assigned referee whose prior-season z-score is
    the planted/noise feature; soccer_referee_view swaps home_team for the
    referee id and away_team for the sentinel, so fdiff = z(referee) - 0."""
    rng = np.random.default_rng(seed)
    referees = [f"R{i:02d}" for i in range(15)]
    strength = {r: rng.normal() for r in referees}
    home = rng.choice([f"T{i:02d}" for i in range(20)], n)
    away = rng.choice([f"T{i:02d}" for i in range(20)], n)
    ok = home != away
    home, away = home[ok], away[ok]
    ref = rng.choice(referees, len(home))
    z = 1.8 * np.array([strength[r] for r in ref])  # unsigned -- a referee has no "side"
    y = (rng.random(len(z)) < 1 / (1 + np.exp(-z))).astype(float)
    games = pd.DataFrame({
        "home_team": home, "away_team": away, "season": "2025",
        WIN_COL: y, "game_id": [f"g{i}" for i in range(len(y))], "date": pd.NaT,
    })
    match_stats = pd.DataFrame({"event_id": games["game_id"], "referee": ref})
    return games, match_stats, strength, {r: rng.normal() for r in referees}


def test_referee_raw_z_mapping_end_to_end(tmp_path):
    games, match_stats, strength, noise = _synth_referee_view()
    ms_path = tmp_path / "match_stats.parquet"
    match_stats.to_parquet(ms_path)
    view = soccer_referee_view(games, match_stats_path=ms_path)
    assert (view["away_team"] == "_NONE_").all()

    bl = np.zeros(len(view))
    mask = np.ones(len(view), dtype=bool)
    res = run_gate("soccer", "fam", "planted", strength, view, bl, mask, "referee_raw_z")
    assert res.verdict == "MATTERS_PROVISIONAL", (res.verdict, res.delta, res.dm_p)
    res_noise = run_gate("soccer", "fam", "noise", noise, view, bl, mask, "referee_raw_z")
    assert res_noise.verdict == "NULL", (res_noise.verdict, res_noise.delta)
