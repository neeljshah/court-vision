"""Snapshot-building I/O helpers for npb_kbo_claims.py (kept in its own file
to hold the parent module under the 300-LOC rail, same 3-way-split precedent
as basketball_claims.py/_dims.py/_io.py in this directory).

Builds the per-team strength snapshot (one row per team, plain numeric sums
already computed) from the GAME-level, WIDE results parquets -- see
npb_kbo_claims.py's module docstring for the full rationale (why a
pre-aggregated side parquet rather than criteria.aggregate).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

_OUT_DIR_COLS = [
    "team", "games", "wins", "decided_games", "runs_for", "runs_against",
    "home_games", "home_wins", "home_decided_games",
    "away_games", "away_wins", "away_decided_games",
]


def build_team_strength_table(games: pd.DataFrame) -> pd.DataFrame:
    """One row per team: wins, decided_games, games, runs_for, runs_against,
    home_wins, home_games, away_wins, away_games -- all plain sums a formula
    can read straight off the materialized columns. Tied games (home_win is
    NaN) count toward games/runs but never toward decided_games/wins."""
    decided = games[~games["tied"]]

    home_g = games.groupby("home_team").size().rename("home_games")
    away_g = games.groupby("away_team").size().rename("away_games")
    home_w = decided[decided["home_win"] == 1.0].groupby("home_team").size().rename("home_wins")
    away_w = decided[decided["home_win"] == 0.0].groupby("away_team").size().rename("away_wins")
    home_decided = decided.groupby("home_team").size().rename("home_decided")
    away_decided = decided.groupby("away_team").size().rename("away_decided")

    home_rf = games.groupby("home_team")["home_score"].sum().rename("home_runs_for")
    home_ra = games.groupby("home_team")["away_score"].sum().rename("home_runs_against")
    away_rf = games.groupby("away_team")["away_score"].sum().rename("away_runs_for")
    away_ra = games.groupby("away_team")["home_score"].sum().rename("away_runs_against")

    teams = sorted(set(games["home_team"]) | set(games["away_team"]))
    table = pd.DataFrame({"team": teams}).set_index("team")
    for series in (
        home_g, away_g, home_w, away_w, home_decided, away_decided,
        home_rf, home_ra, away_rf, away_ra,
    ):
        table = table.join(series, how="left")
    table = table.fillna(0)

    table["games"] = table["home_games"] + table["away_games"]
    table["wins"] = table["home_wins"] + table["away_wins"]
    table["decided_games"] = table["home_decided"] + table["away_decided"]
    table["runs_for"] = table["home_runs_for"] + table["away_runs_for"]
    table["runs_against"] = table["home_runs_against"] + table["away_runs_against"]
    table["home_decided_games"] = table["home_decided"]
    table["away_decided_games"] = table["away_decided"]

    for col in (
        "games", "wins", "decided_games", "runs_for", "runs_against",
        "home_games", "home_wins", "home_decided_games",
        "away_games", "away_wins", "away_decided_games",
    ):
        table[col] = table[col].astype("int64")

    return table.reset_index()[_OUT_DIR_COLS]


def build_league_snapshot(
    league: str, results_path: Path, snapshot_out: Path, out_dir: Path,
) -> tuple[Path, str, int]:
    """Build + persist the per-team strength snapshot for one league.
    Returns (parquet_path, as_of_date_iso, n_teams_considered)."""
    games = pd.read_parquet(results_path)
    last_date = pd.to_datetime(games["date"]).dt.date.max()
    table = build_team_strength_table(games)
    table["league"] = league

    out_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(table, preserve_index=False), snapshot_out)
    return snapshot_out, last_date.isoformat(), len(table)
