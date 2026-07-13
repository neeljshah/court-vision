"""scripts.platformkit.omni.k_coverage -- K1 player-complete coverage matrix (S15).

One row per (player_id, player_name, dimension): status + staleness + claim
count. init_matrix() seeds it from the richest on-disk active-roster source;
k_sweep_nba.py (and future per-sport sweeps) call update_cell() as the
write-back API. k5_metrics() derives the S15.K5 standing metrics from the
matrix + the claims journal.

Active-player source (premise-checked 2026-07-13): data/cache/
player_profile_features.parquet has one row per player with from_year/
to_year (NBA season the player's career started/ended) -- to_year == the
current season's start-year means still active. 850 rows total, 559 with
to_year == 2025 (2025-26 season). No richer per-player "active" flag exists
on disk (profiles/nba_player_profiles.parquet is a long attribute-claims
table, not a roster).

INVARIANTS: pandas + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/. No $/edge claims.
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timezone

import pandas as pd

from scripts.platformkit.io_atomic import write_json_atomic

_ACTIVE_SOURCE = pathlib.Path("data/cache/player_profile_features.parquet")
_MATRIX_DIR = pathlib.Path("data/omni/k")
_MATRIX_NAME = "coverage_nba.parquet"
_METRICS_NAME = "k5_metrics.json"
_CURRENT_SEASON_START_YEAR = 2025  # 2025-26 season; bump each new season.

DIMENSIONS = ("health", "physical", "play_profile", "reactions", "synergy", "opponent")
STATUSES = ("UNMINED", "MINED", "INSUFFICIENT_DATA", "ESCALATED")


def _matrix_path(base_dir=None) -> pathlib.Path:
    d = pathlib.Path(base_dir) if base_dir is not None else _MATRIX_DIR
    return d / _MATRIX_NAME


def _metrics_path(base_dir=None) -> pathlib.Path:
    d = pathlib.Path(base_dir) if base_dir is not None else _MATRIX_DIR
    return d / _METRICS_NAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_active_players(source: pathlib.Path | None = None) -> pd.DataFrame:
    """ACTIVE players (to_year == current season start-year) with id + name."""
    src = source if source is not None else _ACTIVE_SOURCE
    df = pd.read_parquet(src, columns=["player_id", "player_name", "to_year"])
    active = df[df["to_year"] == _CURRENT_SEASON_START_YEAR]
    return active[["player_id", "player_name"]].drop_duplicates().reset_index(drop=True)


def init_matrix(sport: str = "nba", base_dir=None, players: pd.DataFrame | None = None) -> pd.DataFrame:
    """Enumerate ACTIVE players x DIMENSIONS -> coverage_nba.parquet, all UNMINED.

    *players* lets callers/tests inject a synthetic roster instead of reading
    the real parquet.
    """
    active = players if players is not None else load_active_players()
    rows = []
    for _, p in active.iterrows():
        for dim in DIMENSIONS:
            rows.append({
                "player_id": p["player_id"], "player_name": p["player_name"],
                "dimension": dim, "status": "UNMINED",
                "last_refreshed": None, "n_claims": 0,
            })
    matrix = pd.DataFrame(rows, columns=[
        "player_id", "player_name", "dimension", "status", "last_refreshed", "n_claims",
    ])
    path = _matrix_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    matrix.to_parquet(path, index=False)
    return matrix


def load_matrix(base_dir=None) -> pd.DataFrame:
    path = _matrix_path(base_dir)
    if not path.is_file():
        raise FileNotFoundError(f"no coverage matrix at {path} -- call init_matrix() first")
    return pd.read_parquet(path)


def update_cell(player_id, dimension: str, status: str, n_claims: int, base_dir=None) -> pd.DataFrame:
    """Write-back API for sweep workers. Upserts the (player_id, dimension) cell."""
    if dimension not in DIMENSIONS:
        raise ValueError(f"unknown dimension {dimension!r}; expected one of {DIMENSIONS}")
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}; expected one of {STATUSES}")
    matrix = load_matrix(base_dir)
    mask = (matrix["player_id"] == player_id) & (matrix["dimension"] == dimension)
    if not mask.any():
        raise KeyError(f"no coverage cell for player_id={player_id} dimension={dimension!r}")
    matrix.loc[mask, "status"] = status
    matrix.loc[mask, "last_refreshed"] = _utc_now_iso()
    matrix.loc[mask, "n_claims"] = n_claims
    matrix.to_parquet(_matrix_path(base_dir), index=False)
    return matrix


def k5_metrics(base_dir=None, claims_added_this_batch: int = 0) -> dict:
    """K5 standing metrics (S15.K5): coverage %, staleness, INSUFFICIENT_DATA
    share, escalation yield per 1k mined cells. Writes k5_metrics.json."""
    matrix = load_matrix(base_dir)
    total = len(matrix)
    by_dim = {}
    for dim in DIMENSIONS:
        sub = matrix[matrix["dimension"] == dim]
        n = len(sub)
        mined = int((sub["status"] != "UNMINED").sum())
        by_dim[dim] = {
            "n_cells": n,
            "coverage_pct": round(100.0 * mined / n, 4) if n else 0.0,
        }
    mined_mask = matrix["status"] != "UNMINED"
    mined_total = int(mined_mask.sum())
    insufficient = int((matrix["status"] == "INSUFFICIENT_DATA").sum())
    escalated = int((matrix["status"] == "ESCALATED").sum())
    stamps = pd.to_datetime(matrix.loc[mined_mask, "last_refreshed"], errors="coerce", utc=True)
    stamps = stamps.dropna()
    if len(stamps):
        now = pd.Timestamp.now(tz="UTC")
        staleness_days = (now - stamps).dt.total_seconds() / 86400.0
        median_staleness_days = round(float(staleness_days.median()), 4)
    else:
        median_staleness_days = None
    metrics = {
        "as_of": _utc_now_iso(),
        "total_cells": total,
        "mined_cells": mined_total,
        "coverage_pct_overall": round(100.0 * mined_total / total, 4) if total else 0.0,
        "insufficient_data_share": round(insufficient / mined_total, 4) if mined_total else 0.0,
        "escalated_cells": escalated,
        "escalation_yield_per_1k_mined": (
            round(1000.0 * escalated / mined_total, 4) if mined_total else 0.0
        ),
        "median_staleness_days": median_staleness_days,
        "by_dimension": by_dim,
    }
    write_json_atomic(_metrics_path(base_dir), metrics, indent=2)
    return metrics


__all__ = [
    "DIMENSIONS", "STATUSES", "load_active_players", "init_matrix",
    "load_matrix", "update_cell", "k5_metrics",
]
