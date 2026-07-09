"""domains.tennis.knowledge._data -- shared loaders for the mechanism
validation scripts in this package. One place to point at the local tennis
parquets so every validate_*.py script reads the same corpora the same way.

Two independent local corpora, used for different grains:
  - slam_points.parquet: 2011-2015 Grand Slam POINT-by-point (Sackmann charting),
    543,772 rows, singles majors only. Point-level dynamics (serve speed, rally
    length, double faults, hold rate) live here.
  - matches.parquet / wta_matches.parquet: 2015-2025 ATP/WTA MATCH-level results
    (rank, hand, retirement, minutes) joined to players.parquet (hand, dob) and
    schedule_density.parquet (rest_days, recent match load). Match-level
    population mechanisms (ranking-gap shape, lefty matchups, age, fatigue,
    first-set-winner) live here. Disjoint years/corpus from slam_points on
    purpose -- no attempt to cross-join these two into one corpus.

ponytail: no cross-corpus player-identity join between slam_points (name
strings only, see point_engine/corpus.py landmine note) and matches.parquet
(numeric ids) -- would need fuzzy name matching for zero payoff here, since
every mechanism below only needs ONE of the two corpora.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[3]
SLAM_POINTS = REPO / "data" / "cache" / "sackmann_pbp" / "slam_points.parquet"
TENNIS_DIR = REPO / "data" / "domains" / "tennis"
LEDGER_PATH = Path(__file__).resolve().parent / "validation_ledger.jsonl"

SURFACE_OF_TOURNEY = {
    "ausopen": "Hard", "usopen": "Hard", "frenchopen": "Clay", "wimbledon": "Grass",
}


def load_slam_points() -> pd.DataFrame:
    """543,772 Grand Slam point-level rows, 2011-2015, all 4 majors, singles."""
    df = pd.read_parquet(SLAM_POINTS)
    df["surface"] = df["tourney"].map(SURFACE_OF_TOURNEY)
    return df


def load_matches() -> pd.DataFrame:
    """ATP + WTA match-level results, 2015-2025, one row per match. `tour` column
    already distinguishes atp/wta in both source files (verified: no relabeling
    needed)."""
    atp = pd.read_parquet(TENNIS_DIR / "matches.parquet")
    wta = pd.read_parquet(TENNIS_DIR / "wta_matches.parquet")
    return pd.concat([atp, wta], ignore_index=True)


def load_players() -> pd.DataFrame:
    """player_id -> hand (R/L/U/A), dob, height. Same numeric id scheme as
    matches.parquet p1_id/p2_id (verified: 100% p1 merge-hit rate)."""
    return pd.read_parquet(TENNIS_DIR / "players.parquet")


def load_schedule_density() -> pd.DataFrame:
    """event_id, player_id -> rest_days, matches_last_7d/14d. Same event_id
    scheme as matches.parquet (verified: 100% event_id overlap)."""
    return pd.read_parquet(TENNIS_DIR / "schedule_density.parquet")


__all__ = ["REPO", "SLAM_POINTS", "TENNIS_DIR", "LEDGER_PATH", "SURFACE_OF_TOURNEY",
           "load_slam_points", "load_matches", "load_players", "load_schedule_density"]
