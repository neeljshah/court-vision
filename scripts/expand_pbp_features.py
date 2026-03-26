"""
expand_pbp_features.py — Parse raw PBP files to extract per-player expanded features.

Processes data/nba/pbp_0022*.json (3,630 files) and outputs:
    data/nba/pbp_features_expanded_{season}.json

EVENTMSGTYPE reference:
    1=made FG, 2=missed FG, 3=free throw, 4=rebound, 5=turnover,
    6=foul, 7=violation, 8=substitution, 10=jump ball, 12=period start/end

Usage:
    python scripts/expand_pbp_features.py --season 2024-25
    python scripts/expand_pbp_features.py --season 2024-25 --workers 4
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict
from typing import Any

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

# EVENTMSGTYPE constants
_MADE_FG    = 1
_MISSED_FG  = 2
_FREE_THROW = 3
_REBOUND    = 4
_TURNOVER   = 5
_FOUL       = 6
_SUBST      = 8


def _is_paint(desc: str) -> bool:
    """True if description indicates a paint/close-range shot."""
    d = (desc or "").upper()
    return any(kw in d for kw in ("LAYUP", "DUNK", "DRIVING", "REVERSE", "2PT", "HOOK", "FINGER ROLL"))


def _is_fastbreak(desc: str) -> bool:
    d = (desc or "").upper()
    return "FAST BREAK" in d or "FASTBREAK" in d


def _parse_score_margin(margin_str: Any) -> Optional[int]:
    """Parse SCOREMARGIN to int. 'TIE' → 0, other non-numeric → None."""
    try:
        if margin_str is None or margin_str == "":
            return None
        if str(margin_str).upper() == "TIE":
            return 0
        return int(margin_str)
    except (ValueError, TypeError):
        return None


# typing fix
from typing import Optional


def process_pbp_file(fpath: str) -> dict:
    """
    Parse one PBP JSON file.
    Returns {player_id: {stats}} accumulator entries for this game.
    Each player entry accumulates raw counts (not rates) for later division by games_played.
    """
    try:
        with open(fpath) as f:
            events = json.load(f)
    except Exception:
        return {}

    if not isinstance(events, list):
        return {}

    # Per-player accumulators for this game
    # We track player involvement per game to count games_played correctly
    players_seen: set[int] = set()
    accum: dict[int, dict] = defaultdict(lambda: {
        "assist_count":       0,   # EVENTMSGTYPE==1 and PLAYER2_ID==this player
        "made_fg_total":      0,   # total made FGs player1 involved in
        "paint_fg_count":     0,   # made FGs that are paint/2pt
        "fastbreak_count":    0,   # made FGs with fast break desc
        "clutch_pm":          0.0, # +2/3 or -2/3 when |margin|<=5 and period>=4
        "foul_drawn_count":   0,   # EVENTMSGTYPE==6 and PLAYER2_ID==this player
    })

    for ev in events:
        try:
            etype  = int(ev.get("EVENTMSGTYPE", 0))
            period = int(ev.get("PERIOD", 0))
            p1_id  = ev.get("PLAYER1_ID")
            p2_id  = ev.get("PLAYER2_ID")
            hdesc  = str(ev.get("HOMEDESCRIPTION") or "")
            vdesc  = str(ev.get("VISITORDESCRIPTION") or "")
            desc   = hdesc or vdesc
            margin = _parse_score_margin(ev.get("SCOREMARGIN"))

            if p1_id:
                try:
                    p1 = int(p1_id)
                    if p1 > 0:
                        players_seen.add(p1)
                except (ValueError, TypeError):
                    p1 = None
            else:
                p1 = None

            if p2_id:
                try:
                    p2 = int(p2_id)
                    if p2 > 0:
                        players_seen.add(p2)
                except (ValueError, TypeError):
                    p2 = None
            else:
                p2 = None

            if etype == _MADE_FG and p1:
                accum[p1]["made_fg_total"] += 1
                if _is_paint(desc):
                    accum[p1]["paint_fg_count"] += 1
                if _is_fastbreak(desc):
                    accum[p1]["fastbreak_count"] += 1

                # Assist (PLAYER2 is the assister on a made FG)
                if p2:
                    accum[p2]["assist_count"] += 1

                # Clutch +/- for scorer
                if margin is not None and abs(margin) <= 5 and period >= 4:
                    # Check if 3pt from description
                    pts = 3 if "3PT" in desc.upper() or "THREE" in desc.upper() else 2
                    accum[p1]["clutch_pm"] += pts

            elif etype == _MISSED_FG and p1:
                # Clutch -: opposing team shot (hard to attribute without team data)
                # We skip missed FG clutch PM — only track made FGs for simplicity
                pass

            elif etype == _FOUL and p2:
                # PLAYER2 is the player who drew the foul
                accum[p2]["foul_drawn_count"] += 1

        except Exception:
            continue

    return {pid: dict(d) for pid, d in accum.items() if pid in players_seen}


def aggregate_season(season: str, workers: int = 1) -> dict:
    """
    Process all PBP files for a season. Returns per-player feature dict.
    """
    pattern = os.path.join(_NBA_CACHE, "pbp_0022*.json")
    pbp_files = sorted(glob.glob(pattern))

    if not pbp_files:
        # Try alternate pattern without leading "pbp_"
        pattern2 = os.path.join(_NBA_CACHE, "0022*.json")
        pbp_files = sorted(glob.glob(pattern2))

    if not pbp_files:
        print(f"[expand_pbp] No PBP files found matching {pattern}")
        return {}

    print(f"[expand_pbp] Processing {len(pbp_files)} PBP files (season={season})")

    # Aggregate across all games
    season_accum: dict[int, dict] = defaultdict(lambda: {
        "assist_count": 0, "made_fg_total": 0, "paint_fg_count": 0,
        "fastbreak_count": 0, "clutch_pm": 0.0, "foul_drawn_count": 0,
        "games_played": 0,
    })

    for i, fpath in enumerate(pbp_files, 1):
        if i % 500 == 0:
            print(f"  [{i}/{len(pbp_files)}] processed...")
        game_data = process_pbp_file(fpath)
        for pid, d in game_data.items():
            acc = season_accum[pid]
            acc["assist_count"]    += d.get("assist_count", 0)
            acc["made_fg_total"]   += d.get("made_fg_total", 0)
            acc["paint_fg_count"]  += d.get("paint_fg_count", 0)
            acc["fastbreak_count"] += d.get("fastbreak_count", 0)
            acc["clutch_pm"]       += d.get("clutch_pm", 0.0)
            acc["foul_drawn_count"]+= d.get("foul_drawn_count", 0)
            acc["games_played"]    += 1

    print(f"[expand_pbp] Aggregated {len(season_accum)} players")

    # Compute rates
    features: dict[str, dict] = {}
    for pid, acc in season_accum.items():
        gp   = max(acc["games_played"], 1)
        mfg  = max(acc["made_fg_total"], 1)

        assist_rate    = round(acc["assist_count"]    / mfg,  4)
        paint_fg_rate  = round(acc["paint_fg_count"]  / mfg,  4)
        fastbreak_rate = round(acc["fastbreak_count"] / mfg,  4)
        clutch_pm      = round(acc["clutch_pm"]       / gp,   3)
        foul_drawn2    = round(acc["foul_drawn_count"] / gp,  3)

        features[str(pid)] = {
            "assist_rate_pbp":      assist_rate,
            "paint_fg_rate_pbp":    paint_fg_rate,
            "fastbreak_pts_rate":   fastbreak_rate,
            "clutch_pm_pbp":        clutch_pm,
            "foul_drawn_rate_pbp2": foul_drawn2,
            "_games_played":        gp,     # internal — not used as ML feature
        }

    return features


def main(season: str, workers: int = 1) -> None:
    features = aggregate_season(season, workers=workers)
    if not features:
        print("[expand_pbp] No features to write — check PBP file paths.")
        return

    out_path = os.path.join(_NBA_CACHE, f"pbp_features_expanded_{season}.json")
    with open(out_path, "w") as f:
        json.dump(features, f)

    print(f"[expand_pbp] Wrote {len(features)} player records → {out_path}")

    # Quick sanity check
    sample = list(features.items())[:3]
    for pid, feats in sample:
        print(f"  player_id={pid}: {feats}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Expand PBP features for NBA prop models")
    parser.add_argument("--season",  default="2024-25", help="NBA season string")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers (future)")
    args = parser.parse_args()
    main(season=args.season, workers=args.workers)
