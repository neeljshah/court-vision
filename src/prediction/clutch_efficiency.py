"""
clutch_efficiency.py — Per-player clutch efficiency model.

Builds a composite clutch score from PBP-derived clutch stats
(Q4/OT, margin ≤5) and player base stats. Updates automatically
as more PBP games are scraped.

Clutch Score (0–1) weights:
    clutch_fg_pct        0.35   — shooting efficiency when it matters
    foul_drawn_rate      0.20   — drawing fouls in crunch time
    clutch_pts_pg        0.25   — clutch scoring volume
    clutch_ft_pct        0.20   — FT execution under pressure

Output
------
    data/nba/clutch_scores_{season}.json  — {player_id: {score, stats, rank}}

Public API
----------
    build(season)       -> dict    # derive PBP clutch stats + score + save
    load(season)        -> dict    # load from cache
    get_player(pid)     -> dict    # scores for one player
    top_clutch(n, season) -> list  # top-N clutch performers

Usage
-----
    python src/prediction/clutch_efficiency.py --build
    python src/prediction/clutch_efficiency.py --top 20
    python src/prediction/clutch_efficiency.py --player 203999
"""

from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

_W_FG_PCT        = 0.35
_W_FOUL_RATE     = 0.20
_W_PTS_PG        = 0.25
_W_FT_PCT        = 0.20

# Minimum clutch FGA to include in scoring (filter noise from 1-shot samples)
_MIN_CLUTCH_FGA  = 10


def _cache_path(season: str) -> str:
    return os.path.join(_NBA_CACHE, f"clutch_scores_{season}.json")


# ── build ─────────────────────────────────────────────────────────────────────

def build(season: str = "2024-25") -> dict:
    """
    Derive clutch stats from cached PBP files and compute clutch scores.

    Falls back gracefully if few PBP games are cached — scores are still
    valid, just based on a smaller sample. Call again after more PBP is scraped.

    Returns:
        {player_id: {
            "name": str,
            "clutch_score": float,      # composite 0–1
            "clutch_rank": int,         # rank among qualified players
            "clutch_fg_pct": float,
            "clutch_fga": int,
            "foul_drawn_rate": float,
            "clutch_pts_pg": float,
            "clutch_ft_pct": float,
            "games_with_clutch": int,
        }}
    """
    from src.data.pbp_scraper import derive_clutch_stats

    raw = derive_clutch_stats(season=season)
    if not raw:
        print(f"[clutch] No clutch stats derived for {season} — PBP cache empty?")
        return {}

    # Only score players with enough clutch FGA
    qualified = {
        pid: s for pid, s in raw.items()
        if s.get("clutch_fga", 0) >= _MIN_CLUTCH_FGA
    }
    print(f"[clutch] {len(raw)} players raw → {len(qualified)} qualified (≥{_MIN_CLUTCH_FGA} clutch FGA)")

    if not qualified:
        print(f"[clutch] Not enough data — try after scraping more PBP games")
        return {}

    # Extract arrays for normalisation
    fg_pcts   = np.array([s["clutch_fg_pct"]   for s in qualified.values()])
    foul_rates= np.array([s["foul_drawn_rate"]  for s in qualified.values()])
    pts_pgs   = np.array([s["clutch_pts_pg"]    for s in qualified.values()])
    ft_pcts   = np.array([
        s["clutch_ftm"] / max(s["clutch_fta"], 1)
        for s in qualified.values()
    ])

    def _norm(arr: np.ndarray) -> np.ndarray:
        lo, hi = arr.min(), arr.max()
        if hi == lo:
            return np.full_like(arr, 0.5, dtype=float)
        return (arr - lo) / (hi - lo)

    fg_norm   = _norm(fg_pcts)
    foul_norm = _norm(foul_rates)
    pts_norm  = _norm(pts_pgs)
    ft_norm   = _norm(ft_pcts)

    composite = (
        _W_FG_PCT   * fg_norm
        + _W_FOUL_RATE * foul_norm
        + _W_PTS_PG    * pts_norm
        + _W_FT_PCT    * ft_norm
    )

    # Try to load player names from player base cache
    player_names = _load_player_names()

    scores: Dict[str, dict] = {}
    for i, (pid, s) in enumerate(qualified.items()):
        scores[pid] = {
            "name":              player_names.get(pid, s.get("player_name", pid)),
            "clutch_score":      round(float(composite[i]), 4),
            "clutch_fg_pct":     s["clutch_fg_pct"],
            "clutch_fga":        s["clutch_fga"],
            "clutch_pts_pg":     s["clutch_pts_pg"],
            "foul_drawn_rate":   s["foul_drawn_rate"],
            "clutch_ft_pct":     round(s["clutch_ftm"] / max(s["clutch_fta"], 1), 4),
            "games_with_clutch": s["games_with_clutch"],
        }

    # Add rank (1 = best)
    ranked = sorted(scores.items(), key=lambda x: -x[1]["clutch_score"])
    for rank, (pid, _) in enumerate(ranked, start=1):
        scores[pid]["clutch_rank"] = rank

    out_path = _cache_path(season)
    os.makedirs(_NBA_CACHE, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(scores, f, indent=2)
    print(f"[clutch] Saved {len(scores)} clutch scores → {out_path}")
    return scores


def _load_player_names() -> Dict[str, str]:
    """Try to load player id → name mapping from scraper_coverage.json."""
    try:
        cov_path = os.path.join(_NBA_CACHE, "scraper_coverage.json")
        if os.path.exists(cov_path):
            cov = json.load(open(cov_path))
            return {pid: info.get("name", "") for pid, info in cov.items() if "name" in info}
    except Exception:
        pass
    return {}


# ── public API ────────────────────────────────────────────────────────────────

def load(season: str = "2024-25") -> dict:
    """Load clutch scores from cache, building if missing."""
    path = _cache_path(season)
    if not os.path.exists(path):
        return build(season=season)
    with open(path) as f:
        return json.load(f)


def get_player(player_id: str | int, season: str = "2024-25") -> Optional[dict]:
    """Return clutch profile for one player, or None."""
    scores = load(season)
    return scores.get(str(player_id))


def top_clutch(n: int = 20, season: str = "2024-25") -> List[dict]:
    """Return top-N clutch performers sorted by clutch_score desc."""
    scores = load(season)
    ranked = sorted(scores.values(), key=lambda x: -x["clutch_score"])
    return ranked[:n]


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Clutch efficiency model")
    ap.add_argument("--build",   action="store_true")
    ap.add_argument("--season",  default="2024-25")
    ap.add_argument("--top",     type=int, default=0, help="Show top N players")
    ap.add_argument("--player",  type=str, help="Player ID to show")
    args = ap.parse_args()

    if args.build:
        build(season=args.season)

    if args.top:
        players = top_clutch(n=args.top, season=args.season)
        print(f"\nTop {args.top} Clutch Performers ({args.season})")
        print(f"{'Rank':<5} {'Name':<25} {'Score':>7} {'FG%':>7} {'FTA/g':>7} {'Pts/g':>7} {'FT%':>7} {'Games':>6}")
        print("-" * 75)
        for p in players:
            print(
                f"{p['clutch_rank']:<5} {p['name']:<25} "
                f"{p['clutch_score']:>7.3f} {p['clutch_fg_pct']:>7.3f} "
                f"{p['foul_drawn_rate']:>7.2f} {p['clutch_pts_pg']:>7.2f} "
                f"{p['clutch_ft_pct']:>7.3f} {p['games_with_clutch']:>6}"
            )

    if args.player:
        p = get_player(args.player, season=args.season)
        if p is None:
            print(f"Player {args.player} not found (may need ≥{_MIN_CLUTCH_FGA} clutch FGA)")
        else:
            print(f"\n{p['name']} — Clutch Score: {p['clutch_score']:.3f} (Rank #{p['clutch_rank']})")
            print(f"  FG%:           {p['clutch_fg_pct']:.3f}")
            print(f"  Pts/g:         {p['clutch_pts_pg']:.2f}")
            print(f"  Fouls drawn/g: {p['foul_drawn_rate']:.2f}")
            print(f"  FT%:           {p['clutch_ft_pct']:.3f}")
            print(f"  Clutch games:  {p['games_with_clutch']}")
