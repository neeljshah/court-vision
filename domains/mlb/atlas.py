"""domains.mlb.atlas — Obsidian intelligence-atlas generator for MLB.

Reads the real corpus (games.parquet, optional odds.parquet) and emits
a linked graph of Obsidian Markdown notes into a target directory.

Public API::

    from pathlib import Path
    from domains.mlb.atlas import build_atlas
    paths = build_atlas(Path("vault/Sports/MLB"))

All numbers are derived from the real data — no fabricated stats.
No betting/edge language: descriptive scouting intelligence only.

Import contract (F5-clean): stdlib + pathlib + pandas + numpy +
domains.mlb.config + domains.mlb.ratings +
scripts.platformkit.atlas.obsidian_emit only.
"""
from __future__ import annotations

import datetime as dt
import pathlib
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from domains.mlb.config import resolve_league, LEAGUE_MAP, ELO_MEAN
from domains.mlb.ratings import replay, EloState
from domains.mlb.atlas_render import (
    render_index,
    render_league,
    render_team,
)
from scripts.platformkit.atlas.obsidian_emit import write_note

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_DEFAULT_CORPUS = _REPO_ROOT / "data" / "domains" / "mlb"
_DEFAULT_OUT = _REPO_ROOT / "vault" / "Sports" / "MLB"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_games(corpus_dir: pathlib.Path) -> pd.DataFrame:
    """Load games.parquet from corpus_dir; raise FileNotFoundError if absent."""
    p = corpus_dir / "games.parquet"
    if not p.exists():
        raise FileNotFoundError(f"games.parquet not found in {corpus_dir}")
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


# ---------------------------------------------------------------------------
# Stats computation
# ---------------------------------------------------------------------------


def _team_records(games: pd.DataFrame) -> pd.DataFrame:
    """Build per-team aggregate stats from the full corpus.

    Returns a DataFrame indexed by team code with columns:
      games, wins, losses, win_pct, runs_per_game, runs_allowed_per_game,
      run_diff, home_games, home_wins, away_games, away_wins,
      home_win_pct, away_win_pct, league, seasons_active
    """
    rows: List[Dict[str, Any]] = []
    for _, g in games.iterrows():
        ht = str(g["home_team"])
        at = str(g["away_team"])
        hr = float(g["home_runs"])
        ar = float(g["away_runs"])
        hw = int(g["target_home_win"])
        season = int(g["season"])
        hl = str(g["home_league"])
        try:
            al = resolve_league(at, season)
        except KeyError:
            al = "UNK"
        rows.append(dict(team=ht, season=season, runs_for=hr, runs_against=ar,
                         win=hw, home=1, league=hl))
        rows.append(dict(team=at, season=season, runs_for=ar, runs_against=hr,
                         win=1 - hw, home=0, league=al))

    df = pd.DataFrame(rows)
    agg = df.groupby("team").agg(
        games=("win", "count"),
        wins=("win", "sum"),
        runs_per_game=("runs_for", "mean"),
        runs_allowed_per_game=("runs_against", "mean"),
        home_games=("home", "sum"),
        league=("league", "first"),
    ).reset_index()
    agg["losses"] = agg["games"] - agg["wins"]
    agg["win_pct"] = agg["wins"] / agg["games"]
    agg["run_diff"] = agg["runs_per_game"] - agg["runs_allowed_per_game"]

    # home/away splits
    home_df = df[df["home"] == 1].groupby("team").agg(
        home_games=("win", "count"), home_wins=("win", "sum")).reset_index()
    away_df = df[df["home"] == 0].groupby("team").agg(
        away_games=("win", "count"), away_wins=("win", "sum")).reset_index()
    agg = agg.merge(home_df[["team", "home_wins"]], on="team", how="left")
    agg = agg.merge(away_df[["team", "away_games", "away_wins"]], on="team", how="left")
    agg["home_win_pct"] = agg["home_wins"] / agg["home_games"]
    agg["away_win_pct"] = agg["away_wins"] / agg["away_games"]

    # seasons active
    seasons_map = df.groupby("team")["season"].apply(lambda s: sorted(s.unique())).to_dict()
    agg["seasons_active"] = agg["team"].map(seasons_map)

    # by-season win%
    season_wl = df.groupby(["team", "season"]).agg(
        sg=("win", "count"), sw=("win", "sum")).reset_index()
    season_wl["swp"] = season_wl["sw"] / season_wl["sg"]
    season_map = season_wl.groupby("team").apply(
        lambda x: {int(r["season"]): float(r["swp"]) for _, r in x.iterrows()},
        include_groups=False,
    ).to_dict()
    agg["season_win_pct"] = agg["team"].map(season_map)

    return agg.set_index("team")


def _final_elo(games: pd.DataFrame) -> Dict[str, float]:
    """Return final Elo ratings (end-of-corpus) for all teams."""
    state: EloState = replay(games)
    return dict(state.elo)


def _league_stats(games: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """Per-league aggregate stats."""
    result: Dict[str, Dict[str, Any]] = {}
    for league in ("AL", "NL"):
        lg = games[games["home_league"] == league]
        if lg.empty:
            continue
        n_games = len(lg)
        home_wins = int(lg["target_home_win"].sum())
        hw_rate = home_wins / n_games if n_games > 0 else float("nan")
        avg_runs = float((lg["home_runs"] + lg["away_runs"]).mean())
        result[league] = {
            "n_games": n_games,
            "home_win_rate": hw_rate,
            "avg_runs_per_game": avg_runs,
        }
    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_atlas(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = _DEFAULT_CORPUS,
) -> List[pathlib.Path]:
    """Generate Obsidian Markdown notes from the real MLB corpus.

    Parameters
    ----------
    out_dir:
        Directory to write notes into.  Created if absent.
        Subdirectories ``Teams/`` and ``Leagues/`` are created as needed.
    corpus_dir:
        Directory containing ``games.parquet`` (default: data/domains/mlb).

    Returns
    -------
    list[pathlib.Path]
        Absolute paths of every file written (idempotent: re-running rewrites
        with fresh data; same outputs for same corpus).
    """
    out_dir = pathlib.Path(out_dir)
    games = _load_games(corpus_dir)

    team_stats = _team_records(games)
    elo_ratings = _final_elo(games)
    league_stats = _league_stats(games)

    seasons = sorted(games["season"].unique().tolist())
    all_teams = sorted(team_stats.index.tolist())
    n_games = len(games)
    date_min = str(games["date"].min())
    date_max = str(games["date"].max())

    written: List[pathlib.Path] = []

    # --- League notes ---
    leagues_dir = out_dir / "Leagues"
    leagues_dir.mkdir(parents=True, exist_ok=True)
    league_teams: Dict[str, List[str]] = {"AL": [], "NL": []}
    for tm in all_teams:
        lg = str(team_stats.loc[tm, "league"]) if tm in team_stats.index else "UNK"
        if lg in league_teams:
            league_teams[lg].append(tm)

    for league, stats in league_stats.items():
        teams_in_lg = sorted(league_teams.get(league, []))
        top_teams = (
            team_stats[team_stats["league"] == league]
            .sort_values("win_pct", ascending=False)
            .head(5)
            .index.tolist()
        )
        path = leagues_dir / f"{league}.md"
        content = render_league(
            league=league,
            n_games=stats["n_games"],
            home_win_rate=stats["home_win_rate"],
            avg_runs=stats["avg_runs_per_game"],
            teams=teams_in_lg,
            top_teams=top_teams,
            seasons=seasons,
        )
        write_note(path, content)
        written.append(path)

    # --- Team notes ---
    teams_dir = out_dir / "Teams"
    teams_dir.mkdir(parents=True, exist_ok=True)
    for tm in all_teams:
        if tm not in team_stats.index:
            continue
        row = team_stats.loc[tm]
        elo = elo_ratings.get(tm, ELO_MEAN)
        league = str(row["league"])
        rivals = [t for t in league_teams.get(league, []) if t != tm]
        path = teams_dir / f"{tm}.md"
        content = render_team(
            team=tm,
            league=league,
            stats=row,
            elo=elo,
            rivals=rivals,
        )
        write_note(path, content)
        written.append(path)

    # --- Index note ---
    top_by_win_pct = (
        team_stats.sort_values("win_pct", ascending=False).head(10).index.tolist()
    )
    index_path = out_dir / "_Index.md"
    content = render_index(
        n_games=n_games,
        seasons=seasons,
        date_min=date_min,
        date_max=date_max,
        all_teams=all_teams,
        team_stats=team_stats,
        top_teams=top_by_win_pct,
        league_stats=league_stats,
    )
    write_note(index_path, content)
    written.append(index_path)

    return written
