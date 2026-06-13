"""domains.tennis.atlas_h2h — Head-to-head rivalry notes for the Obsidian tennis graph.

Reads the real ATP corpus (data/domains/tennis/matches.parquet) and emits
linked Obsidian matchup notes into *out_dir* (default: vault/Sports/Tennis/Matchups/).

build_h2h(out_dir, corpus_dir, top_n) -> list[pathlib.Path]

F5-clean: stdlib + pandas only.  No src.* / kernel.* / other-domain imports.
No edge / betting language anywhere.
Sackmann data is CC BY-NC-SA — private research use only.
"""
from __future__ import annotations

import pathlib
from collections import defaultdict
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

DEFAULT_CORPUS: pathlib.Path = _REPO_ROOT / "data" / "domains" / "tennis"
DEFAULT_OUT: pathlib.Path = _REPO_ROOT / "vault" / "Sports" / "Tennis" / "Matchups"

PRIMARY_SURFACES: tuple[str, ...] = ("Hard", "Clay", "Grass")
# tourney_level codes → friendly label
_LEVEL_MAP: dict[str, str] = {
    "G": "Grand Slam",
    "M": "Masters",
    "F": "Finals",
    "A": "ATP 250/500",
    "D": "Davis Cup",
    "O": "Olympics",
}
_GRAND_SLAM_CODE = "G"
MIN_MEETINGS = 3   # skip trivial rivalries in the index


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_matches(corpus_dir: pathlib.Path) -> pd.DataFrame:
    df = pd.read_parquet(corpus_dir / "matches.parquet")
    df = df.copy()
    df["date"] = df["date"].astype(str)
    return df


# ---------------------------------------------------------------------------
# Rivalry computation
# ---------------------------------------------------------------------------

def _pair_key(name_a: str, name_b: str) -> tuple[str, str]:
    """Return canonical (alphabetically first, second) pair."""
    return (name_a, name_b) if name_a <= name_b else (name_b, name_a)


def _compute_rivalries(df: pd.DataFrame) -> dict[tuple[str, str], dict]:
    """Return a dict keyed by canonical pair → rivalry stats dict."""
    # Build pair tallies
    meetings: dict[tuple[str, str], list[dict]] = defaultdict(list)

    for _, r in df.iterrows():
        n1, n2 = str(r["p1_name"]), str(r["p2_name"])
        winner = int(r["winner"])  # 1 = p1 won, 2 = p2 won
        key = _pair_key(n1, n2)
        # Canonical: key[0] is alphabetically first
        first_is_p1 = (key[0] == n1)
        first_won = (winner == 1 and first_is_p1) or (winner == 2 and not first_is_p1)
        meetings[key].append({
            "date": str(r["date"]),
            "surface": str(r.get("surface", "Unknown")),
            "tourney_level": str(r.get("tourney_level", "")),
            "tourney_name": str(r.get("tourney_name", "")),
            "round": str(r.get("round", "")),
            "score": str(r.get("score", "")),
            "first_won": bool(first_won),
        })

    rivalries: dict[tuple[str, str], dict] = {}
    for key, matches in meetings.items():
        a, b = key
        total = len(matches)
        a_wins = sum(1 for m in matches if m["first_won"])
        b_wins = total - a_wins

        # Surface splits
        surf_splits: dict[str, dict[str, int]] = {}
        for surf in PRIMARY_SURFACES:
            surf_ms = [m for m in matches if m["surface"] == surf]
            if surf_ms:
                a_s = sum(1 for m in surf_ms if m["first_won"])
                surf_splits[surf] = {"total": len(surf_ms), "a_wins": a_s, "b_wins": len(surf_ms) - a_s}

        # Grand Slam vs other
        gs_ms = [m for m in matches if m["tourney_level"] == _GRAND_SLAM_CODE]
        other_ms = [m for m in matches if m["tourney_level"] != _GRAND_SLAM_CODE]
        gs_split: Optional[dict[str, int]] = None
        if gs_ms:
            a_gs = sum(1 for m in gs_ms if m["first_won"])
            gs_split = {"total": len(gs_ms), "a_wins": a_gs, "b_wins": len(gs_ms) - a_gs}
        other_split: Optional[dict[str, int]] = None
        if other_ms:
            a_ot = sum(1 for m in other_ms if m["first_won"])
            other_split = {"total": len(other_ms), "a_wins": a_ot, "b_wins": len(other_ms) - a_ot}

        # Most-recent meetings (up to 8)
        recent = sorted(matches, key=lambda m: m["date"], reverse=True)[:8]

        rivalries[key] = {
            "a": a,
            "b": b,
            "total": total,
            "a_wins": a_wins,
            "b_wins": b_wins,
            "surf_splits": surf_splits,
            "gs_split": gs_split,
            "other_split": other_split,
            "recent": recent,
        }

    return rivalries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_h2h(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = DEFAULT_CORPUS,
    top_n: int = 120,
    *,
    _matches_df: pd.DataFrame | None = None,
) -> list[pathlib.Path]:
    """Generate Obsidian head-to-head rivalry notes and return written paths.

    Parameters
    ----------
    out_dir:
        Directory where notes are emitted.  Created if it does not exist.
        Default is vault/Sports/Tennis/Matchups/ relative to repo root.
    corpus_dir:
        Directory containing matches.parquet.
        Defaults to data/domains/tennis/ relative to repo root.
    top_n:
        Number of top rivalries (by meeting count) to emit.  Default 120.
    _matches_df:
        Optional override for the matches DataFrame (used in tests).

    Returns
    -------
    list[pathlib.Path]
        All note files written (index + per-rivalry notes).
    """
    from domains.tennis.atlas_h2h_render import _render_index, _render_matchup_note

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if _matches_df is not None:
        df = _matches_df.copy()
    else:
        df = _load_matches(corpus_dir)

    df["date"] = df["date"].astype(str)

    rivalries = _compute_rivalries(df)

    # Select top_n by meeting count; only include pairs with MIN_MEETINGS
    sorted_keys = sorted(
        (k for k, v in rivalries.items() if v["total"] >= MIN_MEETINGS),
        key=lambda k: rivalries[k]["total"],
        reverse=True,
    )[:top_n]

    written: list[pathlib.Path] = []
    written.append(_render_index({k: rivalries[k] for k in sorted_keys}, out_dir, top_n))

    for key in sorted_keys:
        written.append(_render_matchup_note(rivalries[key], out_dir))

    return written
