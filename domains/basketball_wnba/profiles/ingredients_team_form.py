"""domains.basketball_wnba.profiles.ingredients_team_form -- WNBA team
season-aggregate form off data/domains/wnba/espn_scoreboard.parquet
(season=='2026' only, all STATUS_FINAL). Multi-season 2024-2026 pooling was
available on disk but would MISLABEL build_profiles.py's single WINDOW=
"season_2026" tag applied to every attribute here -- so this family stays
single-season, matching every other WNBA attribute in this package.

entity="team", entity_id/entity_name = the espn_scoreboard team name string
(e.g. "Las Vegas Aces") -- a DIFFERENT id namespace than ingredients_
schedule_rest's boxscore team_id; don't cross-reference the two families'
entity_id columns without a name join.

floor=TEAM_FLOOR games (declared; the 15 real 2026 WNBA teams play 25-28
games in this corpus, well above it -- two rows, "NIGERIA"/"JAPAN"
national-team exhibition entries with 2-3 games each, are EXCLUDED by this
floor, which is the correct behavior, not a bug).

Metrics (all descriptive season aggregates, no independent claims-store
corroboration -- DESCRIPTIVE): win_pct, home_win_pct, away_win_pct,
home_ppg, away_ppg, home_away_ppg_diff, points_for_pg, points_against_pg,
net_ppg, last10_win_pct (rolling last-10-games-by-date win rate).

NOT built here: pairwise head_to_head_win_pct / "final score last time X
played Y" -- these are PAIRWISE fact lookups, not a per-entity scalar the
shared ATTRIBUTES/percentile schema can express (percentile-ranking a
same-two-teams pair doesn't fit "one row per entity"); the build spec's own
compare-path note already flags this as a separate, non-family fix, so it
is honestly left unbuilt here rather than force-fit into this schema.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/profiles/test_team_form.py -q
"""
from __future__ import annotations

from typing import Callable

import pandas as pd

SEASON = "2026"
TEAM_FLOOR = 10  # games, declared (spec gave no explicit team-form floor)
LAST_N_GAMES = 10


def _team_game_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Reshape one match-row-per-game into two team-perspective rows (home +
    away side), same melt idiom as tennis_surface_context_claims.py's
    match -> per-player-per-match reshape."""
    season = df[df["season"].astype(str) == SEASON].copy()
    home = season.rename(columns={
        "home_team": "team", "away_team": "opponent",
        "home_score": "pts_for", "away_score": "pts_against", "home_win": "win",
    })[["team", "opponent", "date", "pts_for", "pts_against", "win"]].copy()
    home["is_home"] = True
    away = season.rename(columns={
        "away_team": "team", "home_team": "opponent",
        "away_score": "pts_for", "home_score": "pts_against",
    })[["team", "opponent", "date", "pts_for", "pts_against", "home_win"]].copy()
    away["win"] = 1.0 - away["home_win"]
    away = away.drop(columns=["home_win"])
    away["is_home"] = False
    out = pd.concat([home, away], ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out


def _compute_win_pct(g: pd.DataFrame):
    return float(g["win"].mean()), len(g), {"wins": int(g["win"].sum()), "games": len(g)}


def _compute_home_win_pct(g: pd.DataFrame):
    h = g[g["is_home"]]
    return float(h["win"].mean()), len(h), {"wins_home": int(h["win"].sum()), "games_home": len(h)}


def _compute_away_win_pct(g: pd.DataFrame):
    a = g[~g["is_home"]]
    return float(a["win"].mean()), len(a), {"wins_away": int(a["win"].sum()), "games_away": len(a)}


def _compute_home_ppg(g: pd.DataFrame):
    h = g[g["is_home"]]
    return float(h["pts_for"].mean()), len(h), {"games_home": len(h)}


def _compute_away_ppg(g: pd.DataFrame):
    a = g[~g["is_home"]]
    return float(a["pts_for"].mean()), len(a), {"games_away": len(a)}


def _compute_home_away_ppg_diff(g: pd.DataFrame):
    h, a = g[g["is_home"]], g[~g["is_home"]]
    home_ppg, away_ppg = float(h["pts_for"].mean()), float(a["pts_for"].mean())
    return home_ppg - away_ppg, min(len(h), len(a)), {
        "home_ppg": round(home_ppg, 4), "away_ppg": round(away_ppg, 4),
        "games_home": len(h), "games_away": len(a),
    }


def _compute_points_for_pg(g: pd.DataFrame):
    return float(g["pts_for"].mean()), len(g), {"games": len(g)}


def _compute_points_against_pg(g: pd.DataFrame):
    return float(g["pts_against"].mean()), len(g), {"games": len(g)}


def _compute_net_ppg(g: pd.DataFrame):
    return float((g["pts_for"] - g["pts_against"]).mean()), len(g), {"games": len(g)}


def _compute_last10_win_pct(g: pd.DataFrame):
    last = g.sort_values("date").tail(LAST_N_GAMES)
    return float(last["win"].mean()), len(last), {"games_in_window": len(last)}


_COMPUTE_FNS = {
    "win_pct": _compute_win_pct,
    "home_win_pct": _compute_home_win_pct,
    "away_win_pct": _compute_away_win_pct,
    "home_ppg": _compute_home_ppg,
    "away_ppg": _compute_away_ppg,
    "home_away_ppg_diff": _compute_home_away_ppg_diff,
    "points_for_pg": _compute_points_for_pg,
    "points_against_pg": _compute_points_against_pg,
    "net_ppg": _compute_net_ppg,
    "last10_win_pct": _compute_last10_win_pct,
}


def _team_form_builder(metric: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    compute = _COMPUTE_FNS[metric]

    def _builder(df: pd.DataFrame) -> pd.DataFrame:
        tg = _team_game_frame(df)
        rows = []
        for team, g in tg.groupby("team"):
            value, n, ingredients = compute(g.sort_values("date"))
            rows.append({"entity_id": team, "entity_name": team, "raw_value": value,
                         "n": n, "ingredients": ingredients})
        return pd.DataFrame(rows, columns=["entity_id", "entity_name", "raw_value", "n", "ingredients"])
    return _builder


BUILDERS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    metric: _team_form_builder(metric) for metric in _COMPUTE_FNS
}
