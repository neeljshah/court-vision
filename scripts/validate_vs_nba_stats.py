"""
validate_vs_nba_stats.py — Cross-validate tracked stats against NBA Stats API.

Compares box-score-derivable stats from pipeline tracking output against
official NBA Stats API box scores for a game, reports per-stat error.

Public API
----------
    validate_game(game_id, tracking_csv, season) -> ValidationReport
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

_NBA_CACHE = PROJECT_DIR / "data" / "nba"
_DERIVABLE_STATS = ["fg3m", "ast", "reb", "pts", "stl", "blk", "tov"]


@dataclass
class StatError:
    stat: str
    tracked: float
    official: float
    abs_error: float
    pct_error: float


@dataclass
class ValidationReport:
    game_id: str
    season: str
    n_players: int = 0
    per_stat: Dict[str, StatError] = field(default_factory=dict)
    overall_mae: float = 0.0
    notes: List[str] = field(default_factory=list)
    success: bool = False

    def to_dict(self) -> Dict:
        return {
            "game_id": self.game_id,
            "season": self.season,
            "n_players": self.n_players,
            "overall_mae": round(self.overall_mae, 4),
            "success": self.success,
            "notes": self.notes,
            "per_stat": {
                s: {
                    "tracked": round(e.tracked, 3),
                    "official": round(e.official, 3),
                    "abs_error": round(e.abs_error, 3),
                    "pct_error": round(e.pct_error, 3),
                }
                for s, e in self.per_stat.items()
            },
        }


def _load_official_boxscore(game_id: str, season: str) -> Optional[List[Dict]]:
    """Load official NBA Stats box score from cache. Returns None on miss."""
    # Try game-specific cache first
    for fname in (
        f"boxscore_{game_id}.json",
        f"game_{game_id}.json",
    ):
        p = _NBA_CACHE / fname
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                # Normalize: extract player rows from various formats
                if isinstance(data, list):
                    return data
                if "resultSets" in data:
                    for rs in data["resultSets"]:
                        if rs.get("name") == "PlayerStats":
                            headers = rs["headers"]
                            rows = [dict(zip(headers, row)) for row in rs["rowSet"]]
                            return rows
                if "player_stats" in data:
                    return data["player_stats"]
            except Exception:
                pass

    # Try fetching via nba_api if online
    try:
        os.environ.setdefault("NBA_OFFLINE", "0")
        if os.environ.get("NBA_OFFLINE", "0") == "1":
            return None
        from nba_api.stats.endpoints import boxscoretraditionalv2  # type: ignore
        import time
        time.sleep(0.6)
        bs = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        ps = bs.player_stats.get_data_frame()
        return ps.to_dict("records")
    except Exception:
        return None


def _load_tracked_stats(tracking_csv: str) -> Optional[Dict[str, Dict[str, float]]]:
    """Load tracked per-player stats from tracking_data.csv. Returns {player: {stat: val}}."""
    import pandas as pd

    p = Path(tracking_csv)
    if not p.exists():
        return None
    try:
        df = pd.read_csv(p, low_memory=False)
    except Exception:
        return None

    if "player_name" not in df.columns:
        return None

    result: Dict[str, Dict[str, float]] = {}
    stat_map = {
        "fg3m": ["fg3m", "three_pt_made"],
        "ast":  ["ast", "assists"],
        "reb":  ["reb", "rebounds", "total_reb"],
        "pts":  ["pts", "points"],
        "stl":  ["stl", "steals"],
        "blk":  ["blk", "blocks"],
        "tov":  ["tov", "turnovers"],
    }

    for player, grp in df.groupby("player_name"):
        row: Dict[str, float] = {}
        for stat, col_candidates in stat_map.items():
            for col in col_candidates:
                if col in grp.columns:
                    # Sum if per-frame, or take max if already per-game
                    val = grp[col].sum() if grp[col].dtype.kind in "fi" else 0.0
                    row[stat] = float(val)
                    break
        if row:
            result[str(player)] = row

    return result if result else None


def validate_game(
    game_id: str,
    tracking_csv: str,
    season: str = "2024-25",
) -> ValidationReport:
    """
    Cross-validate tracked box-score stats against official NBA Stats.

    Returns a ValidationReport with per-stat MAE and pct_error.
    On data miss (no tracking or no official data), sets success=False with notes.
    """
    report = ValidationReport(game_id=game_id, season=season)

    tracked = _load_tracked_stats(tracking_csv)
    if tracked is None:
        report.notes.append(f"tracking_csv not found or has no player_name column: {tracking_csv}")
        return report

    official_rows = _load_official_boxscore(game_id, season)
    if official_rows is None:
        report.notes.append(f"NBA Stats API unavailable and no cache for game {game_id}")
        return report

    # Build official lookup: {player_name: {stat: val}}
    official: Dict[str, Dict[str, float]] = {}
    name_keys = ["PLAYER_NAME", "player_name", "name"]
    stat_map_official = {
        "fg3m": ["FG3M", "fg3m"],
        "ast":  ["AST", "ast"],
        "reb":  ["REB", "reb"],
        "pts":  ["PTS", "pts"],
        "stl":  ["STL", "stl"],
        "blk":  ["BLK", "blk"],
        "tov":  ["TO", "tov", "TOV"],
    }
    for row in official_rows:
        name = None
        for k in name_keys:
            if k in row:
                name = str(row[k])
                break
        if not name:
            continue
        pstats: Dict[str, float] = {}
        for stat, cols in stat_map_official.items():
            for col in cols:
                if col in row and row[col] is not None:
                    pstats[stat] = float(row[col])
                    break
        if pstats:
            official[name] = pstats

    if not official:
        report.notes.append("No player rows extracted from official box score")
        return report

    # Cross-validate: match by player name (exact or partial)
    errors_by_stat: Dict[str, List[float]] = {s: [] for s in _DERIVABLE_STATS}
    matched = 0

    for t_name, t_stats in tracked.items():
        # Find best official match
        o_stats = official.get(t_name)
        if o_stats is None:
            # Try partial match
            for o_name in official:
                if t_name.lower() in o_name.lower() or o_name.lower() in t_name.lower():
                    o_stats = official[o_name]
                    break
        if o_stats is None:
            continue
        matched += 1
        for stat in _DERIVABLE_STATS:
            if stat in t_stats and stat in o_stats:
                err = abs(t_stats[stat] - o_stats[stat])
                errors_by_stat[stat].append(err)

    if matched == 0:
        report.notes.append("No player name matches between tracked and official data")
        return report

    report.n_players = matched
    all_errors: List[float] = []
    for stat, errs in errors_by_stat.items():
        if not errs:
            continue
        mean_err = sum(errs) / len(errs)
        # Estimate pct_error from typical official value
        typical = {"pts": 15.0, "reb": 5.0, "ast": 3.5, "fg3m": 1.5,
                   "stl": 0.9, "blk": 0.6, "tov": 1.8}.get(stat, 5.0)
        pct_err = mean_err / max(typical, 0.01)
        tracked_mean = sum(tracked.get(p, {}).get(stat, 0) for p in tracked) / max(len(tracked), 1)
        official_mean = sum(official.get(p, {}).get(stat, 0) for p in official) / max(len(official), 1)
        report.per_stat[stat] = StatError(
            stat=stat,
            tracked=round(tracked_mean, 3),
            official=round(official_mean, 3),
            abs_error=round(mean_err, 3),
            pct_error=round(pct_err, 3),
        )
        all_errors.extend(errs)

    if all_errors:
        report.overall_mae = round(sum(all_errors) / len(all_errors), 4)
    report.success = True
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cross-validate tracking vs NBA Stats API")
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--tracking-csv", required=True)
    parser.add_argument("--season", default="2024-25")
    args = parser.parse_args()

    rpt = validate_game(args.game_id, args.tracking_csv, args.season)
    print(json.dumps(rpt.to_dict(), indent=2))
