"""
shot_zone_tendency.py — Per-player shot zone tendency profiles.

Aggregates all scraped shot charts into per-player zone distributions.
Outputs shot volume, shot% by zone, and a tendency vector used as features
in player prop models.

Output
------
    data/nba/shot_zone_tendency.json   — {player_id: {zone: {count, pct, fg_pct}}}
    data/nba/shot_tendency_features.json — flat feature dict per player

Public API
----------
    build(season_filter)    -> dict    # build + save tendency profiles
    load()                  -> dict    # load from cache
    get_player_profile(pid) -> dict    # tendency profile for one player
    as_feature_vector(pid)  -> list    # 42-dim feature vector for ML

Usage
-----
    python src/prediction/shot_zone_tendency.py --build
    python src/prediction/shot_zone_tendency.py --player 203999
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE   = os.path.join(PROJECT_DIR, "data", "nba")
_TENDENCY_PATH  = os.path.join(_NBA_CACHE, "shot_zone_tendency.json")
_FEATURES_PATH  = os.path.join(_NBA_CACHE, "shot_tendency_features.json")

_ZONES = [
    "Restricted Area",
    "In The Paint (Non-RA)",
    "Mid-Range",
    "Left Corner 3",
    "Right Corner 3",
    "Above the Break 3",
    "Backcourt",
]

_AREAS = [
    "Center(C)", "Left Side(L)", "Right Side(R)",
    "Left Side Center(LC)", "Right Side Center(RC)", "Back Court(BC)",
]

_RANGES = [
    "Less Than 8 ft.", "8-16 ft.", "16-24 ft.", "24+ ft.", "Back Court Shot",
]


# ── data loading ─────────────────────────────────────────────────────────────

def _load_all_shots() -> List[dict]:
    """Load all shot chart records from disk."""
    shots: List[dict] = []
    for fname in os.listdir(_NBA_CACHE):
        if not fname.startswith("shotchart_"):
            continue
        try:
            data = json.load(open(os.path.join(_NBA_CACHE, fname)))
            shots.extend(data)
        except Exception:
            continue
    return shots


# ── tendency builder ─────────────────────────────────────────────────────────

def build(season_filter: Optional[str] = None) -> dict:
    """
    Build shot zone tendency profiles for all players.

    Args:
        season_filter: If set (e.g. "2024-25"), only include shots from that
                       season (matches game_date prefix). None = all seasons.

    Returns:
        {player_id: {
            "name": str,
            "total_fga": int,
            "zones": {zone: {"fga": int, "fgm": int, "pct_of_total": float, "fg_pct": float}},
            "areas": {area: {...}},
            "ranges": {range: {...}},
            "corner_3_rate": float,
            "paint_rate": float,
            "mid_rate": float,
            "above_break_3_rate": float,
            "fg_pct_overall": float,
        }}
    """
    shots = _load_all_shots()
    if not shots:
        raise ValueError(f"No shot chart files found in {_NBA_CACHE}")

    if season_filter:
        # game_date format: "20241115" — filter by year prefix
        year = season_filter[:4]
        shots = [s for s in shots if str(s.get("game_date", "")).startswith(year)]

    print(f"[tendency] Processing {len(shots):,} shots...")

    # Aggregate per player
    player_data: Dict[str, dict] = defaultdict(lambda: {
        "name": "",
        "total_fga": 0,
        "total_fgm": 0,
        "zones":  defaultdict(lambda: {"fga": 0, "fgm": 0}),
        "areas":  defaultdict(lambda: {"fga": 0, "fgm": 0}),
        "ranges": defaultdict(lambda: {"fga": 0, "fgm": 0}),
    })

    for shot in shots:
        pid   = str(shot.get("player_id", ""))
        made  = int(shot.get("shot_made_flag", 0))
        zone  = str(shot.get("shot_zone_basic", "Unknown"))
        area  = str(shot.get("shot_zone_area", "Unknown"))
        rng   = str(shot.get("shot_zone_range", "Unknown"))
        name  = str(shot.get("player_name", ""))

        if not pid:
            continue

        p = player_data[pid]
        p["name"]       = name or p["name"]
        p["total_fga"] += 1
        p["total_fgm"] += made
        p["zones"][zone]["fga"]  += 1
        p["zones"][zone]["fgm"]  += made
        p["areas"][area]["fga"]  += 1
        p["areas"][area]["fgm"]  += made
        p["ranges"][rng]["fga"]  += 1
        p["ranges"][rng]["fgm"]  += made

    # Build final profiles
    profiles: Dict[str, dict] = {}
    for pid, p in player_data.items():
        total = max(p["total_fga"], 1)
        fgm   = p["total_fgm"]

        def _zone_stats(bucket: dict) -> dict:
            out = {}
            for cat, s in bucket.items():
                fga_ = s["fga"]
                out[cat] = {
                    "fga":          fga_,
                    "fgm":          s["fgm"],
                    "pct_of_total": round(fga_ / total, 4),
                    "fg_pct":       round(s["fgm"] / max(fga_, 1), 4),
                }
            return out

        zones_stats  = _zone_stats(p["zones"])
        areas_stats  = _zone_stats(p["areas"])
        ranges_stats = _zone_stats(p["ranges"])

        def _zone_rate(zone_key: str) -> float:
            return zones_stats.get(zone_key, {}).get("pct_of_total", 0.0)

        profiles[pid] = {
            "name":               p["name"],
            "total_fga":          p["total_fga"],
            "fg_pct_overall":     round(fgm / total, 4),
            "zones":              zones_stats,
            "areas":              areas_stats,
            "ranges":             ranges_stats,
            "paint_rate":         round(_zone_rate("Restricted Area") + _zone_rate("In The Paint (Non-RA)"), 4),
            "mid_rate":           round(_zone_rate("Mid-Range"), 4),
            "corner_3_rate":      round(_zone_rate("Left Corner 3") + _zone_rate("Right Corner 3"), 4),
            "above_break_3_rate": round(_zone_rate("Above the Break 3"), 4),
        }

    os.makedirs(_NBA_CACHE, exist_ok=True)
    with open(_TENDENCY_PATH, "w") as f:
        json.dump(profiles, f)

    _build_feature_cache(profiles)
    print(f"[tendency] {len(profiles)} player profiles → {_TENDENCY_PATH}")
    return profiles


def _build_feature_cache(profiles: dict) -> None:
    """Build flat 42-dim feature vectors per player for use in prop models."""
    features: Dict[str, dict] = {}
    for pid, p in profiles.items():
        vec: Dict[str, float] = {
            "total_fga":          float(p["total_fga"]),
            "fg_pct_overall":     p["fg_pct_overall"],
            "paint_rate":         p["paint_rate"],
            "mid_rate":           p["mid_rate"],
            "corner_3_rate":      p["corner_3_rate"],
            "above_break_3_rate": p["above_break_3_rate"],
        }
        # Zone-level fg_pct (7 zones)
        for zone in _ZONES:
            safe_key = zone.lower().replace(" ", "_").replace("(", "").replace(")", "")
            z = p["zones"].get(zone, {})
            vec[f"fg_pct_{safe_key}"] = z.get("fg_pct", 0.0)
            vec[f"rate_{safe_key}"]   = z.get("pct_of_total", 0.0)
        # Range-level fg_pct (5 ranges)
        for rng in _RANGES:
            safe_key = rng.lower().replace(" ", "_").replace(".", "").replace("-", "_")
            r = p["ranges"].get(rng, {})
            vec[f"fg_pct_range_{safe_key}"] = r.get("fg_pct", 0.0)
        features[pid] = vec

    with open(_FEATURES_PATH, "w") as f:
        json.dump(features, f)
    print(f"[tendency] Feature cache → {_FEATURES_PATH}")


# ── public API ────────────────────────────────────────────────────────────────

def load() -> dict:
    """Load tendency profiles from cache (builds if missing)."""
    if not os.path.exists(_TENDENCY_PATH):
        return build()
    with open(_TENDENCY_PATH) as f:
        return json.load(f)


def get_player_profile(player_id: str | int) -> Optional[dict]:
    """Return tendency profile for a single player, or None if not found."""
    profiles = load()
    return profiles.get(str(player_id))


def as_feature_vector(player_id: str | int) -> List[float]:
    """
    Return 42-dim flat feature vector for use in ML models.
    Returns zeros if player not found.
    """
    if not os.path.exists(_FEATURES_PATH):
        build()
    with open(_FEATURES_PATH) as f:
        features = json.load(f)
    vec = features.get(str(player_id), {})
    if not vec:
        return [0.0] * 42
    return list(vec.values())


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Shot zone tendency builder")
    ap.add_argument("--build",   action="store_true")
    ap.add_argument("--season",  default=None, help="e.g. 2024-25")
    ap.add_argument("--player",  type=str, help="Player ID to show profile")
    ap.add_argument("--summary", action="store_true", help="Print league-wide zone summary")
    args = ap.parse_args()

    if args.build:
        profiles = build(season_filter=args.season)

    if args.player:
        p = get_player_profile(args.player)
        if p is None:
            print(f"Player {args.player} not found.")
        else:
            print(f"\n{p['name']} — {p['total_fga']} FGA, {p['fg_pct_overall']:.1%} FG%")
            print(f"  Paint:        {p['paint_rate']:.1%}")
            print(f"  Mid-range:    {p['mid_rate']:.1%}")
            print(f"  Corner 3:     {p['corner_3_rate']:.1%}")
            print(f"  Above break 3:{p['above_break_3_rate']:.1%}")
            print(f"\nZone breakdown:")
            for zone, s in sorted(p["zones"].items(), key=lambda x: -x[1]["fga"]):
                print(f"  {zone:<30} {s['fga']:>5} FGA  {s['fg_pct']:.1%} FG%  {s['pct_of_total']:.1%} of attempts")

    if args.summary:
        profiles = load()
        print(f"\nTotal players: {len(profiles)}")
        total_fga = sum(p["total_fga"] for p in profiles.values())
        print(f"Total FGA: {total_fga:,}")
        # League-wide zone rates
        zone_totals: Dict[str, int] = defaultdict(int)
        for p in profiles.values():
            for zone, s in p["zones"].items():
                zone_totals[zone] += s["fga"]
        print("\nLeague-wide zone distribution:")
        for zone, fga in sorted(zone_totals.items(), key=lambda x: -x[1]):
            print(f"  {zone:<30} {fga/total_fga:.1%}")
