"""domains.tennis.atlas — Obsidian intelligence-atlas generator for tennis.

Reads the real ATP corpus (data/domains/tennis/matches.parquet + players.parquet),
computes corpus-wide statistics and per-player stats using real Elo ratings, and
emits a linked Obsidian markdown graph into *out_dir*.

Public API
----------
build_atlas(out_dir, corpus_dir) -> list[pathlib.Path]
    Emit all notes and return the written paths.  Idempotent (reruns overwrite).

Emitted note layout::

    out_dir/
        _Index.md                  ← corpus hub, top-20 Elo table
        Players/<Name>.md          ← top ~150 players by match count
        Surfaces/Hard.md
        Surfaces/Clay.md
        Surfaces/Grass.md

F5-clean: imports only stdlib, numpy, pandas, and domains.tennis.*.
No src.* / kernel.* / other-domain imports.
No edge / betting language anywhere.

Sackmann data is CC BY-NC-SA — private research use only.
"""
from __future__ import annotations

import pathlib
from typing import Optional

import numpy as np
import pandas as pd

from domains.tennis.elo_core import BASE_RATING, replay
from scripts.platformkit.atlas.obsidian_emit import slug as _slug  # noqa: F401

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CORPUS: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "data" / "domains" / "tennis"
)
DEFAULT_OUT: pathlib.Path = (
    pathlib.Path(__file__).resolve().parents[2] / "vault" / "Sports" / "Tennis"
)

TOP_N_PLAYERS: int = 150          # max player notes emitted
TOP_N_INDEX: int = 20             # rows in the index Elo table
MIN_MATCHES_PLAYER: int = 10      # skip players with fewer matches (sparse stats)
PRIMARY_SURFACES: tuple[str, ...] = ("Hard", "Clay", "Grass")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_corpus(corpus_dir: pathlib.Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load matches and players DataFrames.  Returns (matches, players)."""
    matches = pd.read_parquet(corpus_dir / "matches.parquet")
    # Normalise date to string for display; keep original for Elo
    matches = matches.copy()
    matches["date"] = matches["date"].astype(str)

    players_path = corpus_dir / "players.parquet"
    players: pd.DataFrame
    if players_path.exists():
        players = pd.read_parquet(players_path)
    else:
        players = pd.DataFrame(columns=["player_id", "full_name", "ioc", "height", "hand"])
    return matches, players


# ---------------------------------------------------------------------------
# Derived statistics
# ---------------------------------------------------------------------------

def _compute_player_stats(matches: pd.DataFrame) -> pd.DataFrame:
    """Return one row per player with corpus-wide match statistics."""
    rows: list[dict] = []

    # Map player_id -> name from match rows
    id_to_name: dict[int, str] = {}
    for _, r in matches.iterrows():
        p1, p2 = int(r["p1_id"]), int(r["p2_id"])
        id_to_name.setdefault(p1, str(r.get("p1_name", p1)))
        id_to_name.setdefault(p2, str(r.get("p2_name", p2)))

    # Tallies per player
    from collections import defaultdict

    total: dict[int, int] = defaultdict(int)
    wins: dict[int, int] = defaultdict(int)
    surf_total: dict[tuple[int, str], int] = defaultdict(int)
    surf_wins: dict[tuple[int, str], int] = defaultdict(int)
    bo5_total: dict[int, int] = defaultdict(int)
    bo5_wins: dict[int, int] = defaultdict(int)
    peak_rank: dict[int, Optional[float]] = {}
    recent_results: dict[int, list[int]] = defaultdict(list)  # 1=win,0=loss (last 20)

    # Sort by date for recency ordering
    df_sorted = matches.sort_values("date", ascending=False).reset_index(drop=True)

    for _, r in df_sorted.iterrows():
        p1, p2 = int(r["p1_id"]), int(r["p2_id"])
        winner = int(r["winner"])
        surface = str(r.get("surface", "Unknown"))
        best_of = int(r.get("best_of", 3))
        p1_rank = r.get("p1_rank")
        p2_rank = r.get("p2_rank")

        for pid, is_p1 in [(p1, True), (p2, False)]:
            won = (winner == 1 and is_p1) or (winner == 2 and not is_p1)
            total[pid] += 1
            wins[pid] += int(won)
            surf_total[(pid, surface)] += 1
            surf_wins[(pid, surface)] += int(won)
            if best_of == 5:
                bo5_total[pid] += 1
                bo5_wins[pid] += int(won)
            # Peak rank (lowest numeric rank = best)
            rank = float(p1_rank) if is_p1 else float(p2_rank)
            if pd.notna(rank):
                if pid not in peak_rank or rank < peak_rank[pid]:  # type: ignore[operator]
                    peak_rank[pid] = rank
            # Recent form (track last 20 chronologically reversed)
            if len(recent_results[pid]) < 20:
                recent_results[pid].append(int(won))

    # Opponent rank for vs-top-10 record
    opp_rank_wins: dict[int, int] = defaultdict(int)
    opp_rank_total: dict[int, int] = defaultdict(int)
    for _, r in matches.iterrows():
        p1, p2 = int(r["p1_id"]), int(r["p2_id"])
        winner = int(r["winner"])
        p1_rank, p2_rank = r.get("p1_rank"), r.get("p2_rank")
        if pd.notna(p2_rank) and float(p2_rank) <= 10:
            opp_rank_total[p1] += 1
            opp_rank_wins[p1] += int(winner == 1)
        if pd.notna(p1_rank) and float(p1_rank) <= 10:
            opp_rank_total[p2] += 1
            opp_rank_wins[p2] += int(winner == 2)

    # Compile rows for players with enough matches
    for pid, name in id_to_name.items():
        n = total.get(pid, 0)
        if n < MIN_MATCHES_PLAYER:
            continue
        w = wins.get(pid, 0)
        row: dict = {
            "player_id": pid,
            "name": name,
            "total_matches": n,
            "wins": w,
            "losses": n - w,
            "win_pct": round(w / n * 100, 1) if n > 0 else 0.0,
            "peak_rank": int(peak_rank[pid]) if pid in peak_rank and peak_rank[pid] is not None else None,
        }
        # Surface splits
        for surf in PRIMARY_SURFACES:
            st = surf_total.get((pid, surf), 0)
            sw = surf_wins.get((pid, surf), 0)
            row[f"{surf.lower()}_matches"] = st
            row[f"{surf.lower()}_win_pct"] = round(sw / st * 100, 1) if st > 0 else None
        # Best-of-5
        b5t = bo5_total.get(pid, 0)
        b5w = bo5_wins.get(pid, 0)
        row["bo5_matches"] = b5t
        row["bo5_win_pct"] = round(b5w / b5t * 100, 1) if b5t > 0 else None
        # vs top-10
        vs10 = opp_rank_total.get(pid, 0)
        vs10w = opp_rank_wins.get(pid, 0)
        row["vs_top10_total"] = vs10
        row["vs_top10_wins"] = vs10w
        row["vs_top10_win_pct"] = round(vs10w / vs10 * 100, 1) if vs10 > 0 else None
        # Recent form string (last 20 most recent, 'W'/'L')
        recent = recent_results.get(pid, [])
        row["recent_form"] = "".join("W" if x else "L" for x in recent)
        rows.append(row)

    stats = pd.DataFrame(rows)
    if stats.empty:
        return stats
    return stats.sort_values("total_matches", ascending=False).reset_index(drop=True)


def _attach_elo(stats: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Attach final-corpus Elo ratings to the stats table."""
    if stats.empty:
        return stats

    state = replay(matches)
    overall_elos: list[Optional[float]] = []
    surface_elos: dict[str, list[Optional[float]]] = {s: [] for s in PRIMARY_SURFACES}

    for _, row in stats.iterrows():
        pid = int(row["player_id"])
        overall_elos.append(round(state.ratings.get(pid, BASE_RATING), 1))
        for surf in PRIMARY_SURFACES:
            val = state.surface.get((pid, surf))
            surface_elos[surf].append(round(val, 1) if val is not None else None)

    stats = stats.copy()
    stats["elo"] = overall_elos
    for surf in PRIMARY_SURFACES:
        stats[f"{surf.lower()}_elo"] = surface_elos[surf]
    return stats


# ---------------------------------------------------------------------------
# Rendering (delegates to atlas_render.py)
# ---------------------------------------------------------------------------

def build_atlas(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = DEFAULT_CORPUS,
    *,
    _matches_df: Optional[pd.DataFrame] = None,
) -> list[pathlib.Path]:
    """Generate the Obsidian tennis intelligence atlas and return written paths.

    Parameters
    ----------
    out_dir:
        Directory where notes are emitted.  Created if it does not exist.
    corpus_dir:
        Directory containing matches.parquet (and optionally players.parquet).
        Defaults to data/domains/tennis/ relative to repo root.
    _matches_df:
        Optional override for the matches DataFrame (used in tests to inject
        a synthetic fixture without touching the filesystem).

    Returns
    -------
    list[pathlib.Path]
        All note files written.
    """
    from domains.tennis.atlas_render import render_all

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if _matches_df is not None:
        matches = _matches_df.copy()
        players = pd.DataFrame(columns=["player_id", "full_name", "ioc", "height", "hand"])
    else:
        matches, players = _load_corpus(corpus_dir)

    stats = _compute_player_stats(matches)
    stats = _attach_elo(stats, matches)

    return render_all(out_dir=out_dir, stats=stats, matches=matches, players=players)
