"""domains.tennis.atlas_h2h — Aggregate, name-free H2H dynamics notes.

Emits 5 aggregate notes (no individual rivalries, no player names):
  _Matchups_Index, _Surface_Dynamics, _Upset_Patterns, _Format_Patterns, _Rematch_Effects.

build_h2h(out_dir, corpus_dir=..., top_n=120) -> list[pathlib.Path]
F5-clean: stdlib + pandas/numpy.  No src.*/kernel.*/other-domain imports.
No edge/betting language.  Sackmann data CC BY-NC-SA — private research use only.
"""
from __future__ import annotations

import pathlib
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

DEFAULT_CORPUS: pathlib.Path = _REPO_ROOT / "data" / "domains" / "tennis"
DEFAULT_OUT: pathlib.Path = _REPO_ROOT / "vault" / "Sports" / "Tennis" / "Matchups"

PRIMARY_SURFACES: Tuple[str, ...] = ("Hard", "Clay", "Grass")

_LEVEL_MAP: Dict[str, str] = {
    "G": "Grand Slam",
    "M": "Masters",
    "F": "Finals",
    "A": "ATP 250/500",
    "D": "Davis Cup",
    "O": "Olympics",
}
_GRAND_SLAM_CODE = "G"

# Minimum meetings for a pair to be included in aggregate statistics
MIN_MEETINGS: int = 3

# Rank-gap bins for upset analysis (difference = lower_rank - higher_rank, positive)
RANK_GAP_BINS: List[int] = [0, 10, 25, 50, 100, 200]
RANK_GAP_LABELS: List[str] = ["1-10", "11-25", "26-50", "51-100", ">100"]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_matches(corpus_dir: pathlib.Path) -> pd.DataFrame:
    """Load the ATP matches parquet and normalise date to string."""
    df = pd.read_parquet(corpus_dir / "matches.parquet")
    df = df.copy()
    df["date"] = df["date"].astype(str)
    return df


# ---------------------------------------------------------------------------
# Pair utilities
# ---------------------------------------------------------------------------

def _pair_key(name_a: str, name_b: str) -> Tuple[str, str]:
    """Return canonical (alphabetically first, second) pair — used internally."""
    return (name_a, name_b) if name_a <= name_b else (name_b, name_a)


# ---------------------------------------------------------------------------
# Aggregate computation helpers
# ---------------------------------------------------------------------------

def _compute_pair_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per match with canonical pair key and higher-rank-wins flag."""
    records = []
    for _, r in df.iterrows():
        try:
            p1_rank = float(r.get("p1_rank", np.nan))
            p2_rank = float(r.get("p2_rank", np.nan))
        except (TypeError, ValueError):
            p1_rank = np.nan
            p2_rank = np.nan

        winner = int(r["winner"])  # 1 = p1 won, 2 = p2 won

        higher_rank_wins: Optional[bool] = None
        rank_gap: Optional[float] = None
        if not (np.isnan(p1_rank) or np.isnan(p2_rank)):
            rank_gap = abs(p1_rank - p2_rank)
            # lower rank number = better ranked
            if p1_rank < p2_rank:
                higher_rank_wins = (winner == 1)
            elif p2_rank < p1_rank:
                higher_rank_wins = (winner == 2)
            # equal ranks → leave None

        records.append({
            "p1_name": str(r["p1_name"]),
            "p2_name": str(r["p2_name"]),
            "pair": _pair_key(str(r["p1_name"]), str(r["p2_name"])),
            "date": str(r["date"]),
            "surface": str(r.get("surface", "Unknown")),
            "tourney_level": str(r.get("tourney_level", "")),
            "best_of": int(r.get("best_of", 3)) if pd.notna(r.get("best_of")) else 3,
            "winner": winner,
            "higher_rank_wins": higher_rank_wins,
            "rank_gap": rank_gap,
        })

    return pd.DataFrame(records) if records else pd.DataFrame(
        columns=["p1_name", "p2_name", "pair", "date", "surface",
                 "tourney_level", "best_of", "winner", "higher_rank_wins", "rank_gap"]
    )


def _meeting_count_distribution(pair_df: pd.DataFrame) -> Dict[str, int]:
    """Return a histogram of how often pairs meet: bucket → count of pairs."""
    counts = pair_df.groupby("pair").size()
    buckets: Dict[str, int] = {
        "1-2":   int((counts.between(1, 2)).sum()),
        "3-5":   int((counts.between(3, 5)).sum()),
        "6-10":  int((counts.between(6, 10)).sum()),
        "11-20": int((counts.between(11, 20)).sum()),
        "21+":   int((counts >= 21).sum()),
    }
    return buckets


def _surface_dynamics(pair_df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Higher-ranked-player win rate per surface (rank_gap >= 1 only)."""
    out: Dict[str, Dict[str, float]] = {}
    valid = pair_df[pair_df["higher_rank_wins"].notna() & (pair_df["rank_gap"].fillna(0) >= 1)]
    for surf in PRIMARY_SURFACES:
        sub = valid[valid["surface"] == surf]
        if len(sub) == 0:
            continue
        n_pairs = sub["pair"].nunique()
        win_rate = float(sub["higher_rank_wins"].mean())
        out[surf] = {
            "matches": len(sub),
            "win_rate": round(win_rate, 4),
            "n_pairs": n_pairs,
        }
    return out


def _upset_patterns(pair_df: pd.DataFrame) -> List[Dict]:
    """Upset rate (lower-ranked wins) per rank-gap bin."""
    valid = pair_df[pair_df["higher_rank_wins"].notna() & pair_df["rank_gap"].notna()]
    results: List[Dict] = []
    for i, label in enumerate(RANK_GAP_LABELS):
        lo = RANK_GAP_BINS[i]
        hi = RANK_GAP_BINS[i + 1]
        if i == len(RANK_GAP_LABELS) - 1:
            sub = valid[valid["rank_gap"] > lo]
        else:
            sub = valid[(valid["rank_gap"] > lo) & (valid["rank_gap"] <= hi)]
        if len(sub) == 0:
            continue
        upset_rate = float((~sub["higher_rank_wins"].astype(bool)).mean())
        results.append({
            "gap_label": label,
            "matches": len(sub),
            "upset_rate": round(upset_rate, 4),
        })
    return results


def _format_patterns(pair_df: pd.DataFrame) -> Dict[str, Dict]:
    """Higher-rank win rate by match format (best-of-3 vs best-of-5)."""
    valid = pair_df[pair_df["higher_rank_wins"].notna()]
    out: Dict[str, Dict] = {}
    for fmt, label in [(3, "Best-of-3"), (5, "Best-of-5")]:
        sub = valid[valid["best_of"] == fmt]
        if len(sub) == 0:
            continue
        out[label] = {
            "matches": len(sub),
            "win_rate": round(float(sub["higher_rank_wins"].mean()), 4),
            "n_pairs": sub["pair"].nunique(),
        }
    return out


def _rematch_effects(pair_df: pd.DataFrame) -> Dict[str, float]:
    """% of pairs where the first-meeting winner also wins the second meeting."""
    results: Dict[str, float] = {}
    # Sort by date within each pair
    valid = pair_df.dropna(subset=["date"]).copy()
    valid["p1_canonical"] = valid["pair"].apply(lambda p: p[0])
    valid["first_won_canonical"] = valid.apply(
        lambda r: (r["winner"] == 1 and r["p1_name"] == r["p1_canonical"])
                  or (r["winner"] == 2 and r["p2_name"] == r["p1_canonical"]),
        axis=1,
    )

    qualifying = 0
    repeat_count = 0
    total_analysed = 0

    for pair, grp in valid.groupby("pair"):
        grp_sorted = grp.sort_values("date").reset_index(drop=True)
        if len(grp_sorted) < 2:
            continue
        qualifying += 1
        first_winner_won_first = bool(grp_sorted.loc[0, "first_won_canonical"])
        second_winner_won_first = bool(grp_sorted.loc[1, "first_won_canonical"])
        if first_winner_won_first == second_winner_won_first:
            repeat_count += 1
        total_analysed += 1

    if qualifying > 0:
        results["qualifying_pairs"] = qualifying
        results["first_winner_repeats_pct"] = round(repeat_count / qualifying * 100, 1)
        results["sample_size"] = total_analysed
    else:
        results["qualifying_pairs"] = 0
        results["first_winner_repeats_pct"] = 0.0
        results["sample_size"] = 0

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_h2h(
    out_dir: pathlib.Path,
    corpus_dir: pathlib.Path = DEFAULT_CORPUS,
    top_n: int = 120,
    *,
    _matches_df: Optional[pd.DataFrame] = None,
) -> List[pathlib.Path]:
    """Generate name-free aggregate H2H-dynamics notes and return written paths.

    Parameters
    ----------
    out_dir:
        Directory where notes are emitted.  Created if it does not exist.
        Default is vault/Sports/Tennis/Matchups/ relative to repo root.
    corpus_dir:
        Directory containing matches.parquet.
        Defaults to data/domains/tennis/ relative to repo root.
    top_n:
        Retained for API compatibility (unused in the aggregate view).
    _matches_df:
        Optional override for the matches DataFrame (used in tests).

    Returns
    -------
    list[pathlib.Path]
        All note files written.  Guaranteed to be at least 4 paths.
    """
    from domains.tennis.atlas_h2h_render import (
        render_index,
        render_surface_dynamics,
        render_upset_patterns,
        render_format_patterns,
        render_rematch_effects,
    )

    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if _matches_df is not None:
        df = _matches_df.copy()
    else:
        df = _load_matches(corpus_dir)

    df["date"] = df["date"].astype(str)

    pair_df = _compute_pair_stats(df)

    meeting_dist = _meeting_count_distribution(pair_df)
    surface_dyn = _surface_dynamics(pair_df)
    upset_pats = _upset_patterns(pair_df)
    fmt_pats = _format_patterns(pair_df)
    rematch_eff = _rematch_effects(pair_df)

    total_matches = len(df)
    total_pairs = pair_df["pair"].nunique()
    qualified_pairs = int((pair_df.groupby("pair").size() >= MIN_MEETINGS).sum())

    corpus_meta = {
        "total_matches": total_matches,
        "total_pairs": total_pairs,
        "qualified_pairs": qualified_pairs,
        "min_meetings": MIN_MEETINGS,
    }

    written: List[pathlib.Path] = []
    written.append(render_index(corpus_meta, meeting_dist, out_dir))
    written.append(render_surface_dynamics(surface_dyn, out_dir))
    written.append(render_upset_patterns(upset_pats, out_dir))
    written.append(render_format_patterns(fmt_pats, out_dir))
    written.append(render_rematch_effects(rematch_eff, out_dir))

    return written
