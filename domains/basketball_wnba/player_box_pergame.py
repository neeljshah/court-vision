"""domains.basketball_wnba.player_box_pergame -- per-GAME player boxscore rows
from the 169-game CDN backfill corpus (data/domains/wnba/cdn_backfill/<gid>/
boxscore.json).

Fixes a stale census claim ("player boxscores not derivable"): they are --
straight off the same JSON atlas_extract_player.py already walks, just never
persisted at per-game grain (that module collapses straight to season
aggregate). This module writes the per-game grain the census says is missing.

One row per (game_id, player_id): game_date (ET calendar date, from
game.gameEt), team_id, opponent_id, home/away, minutes, and the core box
stats. GAME-DATED, not season-aggregated.

INVARIANTS: standalone; <=250 LOC; ASCII only; no pip installs; never raises
(a malformed game dir is skipped and LISTED, not fabricated); no $ fields.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_player_box_pergame.py -q
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from domains.basketball_wnba.atlas_extract_common import BACKFILL_DIR, iso_minutes

logger = logging.getLogger(__name__)

OUT_PATH = BACKFILL_DIR.parent / "player_boxscores.parquet"

_SIDES = ("homeTeam", "awayTeam")
_CORE_FIELDS = ["minutes", "pts", "reb", "ast", "stl", "blk", "tov",
                "fga", "fgm", "fg3a", "fg3m", "fta", "ftm", "plus_minus"]


def _game_date(game: dict) -> Optional[str]:
    """ET calendar date the game was played, e.g. '2026-04-25'. Falls back to
    gameTimeUTC's date if gameEt is absent/malformed. None if neither parses."""
    for key in ("gameEt", "gameTimeUTC"):
        v = game.get(key)
        if isinstance(v, str) and "T" in v:
            return v.split("T", 1)[0]
    return None


def _load_boxscore(game_dir: Path) -> Optional[dict]:
    """boxscore.json's 'game' dict, or None if missing/malformed. Never
    raises."""
    p = game_dir / "boxscore.json"
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    game = payload.get("game")
    return game if isinstance(game, dict) else None


def _player_rows_for_game(game_id: str, game: dict) -> List[Dict[str, Any]]:
    """One row per player across both sides of *game*. Pure, never raises --
    a malformed player entry is skipped, an absent stat comes through as
    None (pandas -> NaN), never fabricated."""
    rows: List[Dict[str, Any]] = []
    game_date = _game_date(game)
    sides = {s: (game.get(s) or {}) for s in _SIDES}
    team_ids = {s: sides[s].get("teamId") for s in _SIDES}
    for side in _SIDES:
        team = sides[side]
        opp_side = "awayTeam" if side == "homeTeam" else "homeTeam"
        team_id = team_ids[side]
        opponent_id = team_ids[opp_side]
        for p in team.get("players") or []:
            if not isinstance(p, dict):
                continue
            pid = p.get("personId")
            if pid is None:
                continue
            stats = p.get("statistics") or {}
            rows.append({
                "game_id": str(game_id),
                "game_date": game_date,
                "player_id": str(pid),
                "player_name": p.get("name"),
                "team_id": str(team_id) if team_id is not None else None,
                "opponent_id": str(opponent_id) if opponent_id is not None else None,
                "is_home": side == "homeTeam",
                "started": str(p.get("starter")) == "1",
                "played": str(p.get("played")) == "1",
                "minutes": iso_minutes(stats.get("minutesCalculated")),
                "pts": stats.get("points"),
                "reb": stats.get("reboundsTotal"),
                "ast": stats.get("assists"),
                "stl": stats.get("steals"),
                "blk": stats.get("blocks"),
                "tov": stats.get("turnovers"),
                "fga": stats.get("fieldGoalsAttempted"),
                "fgm": stats.get("fieldGoalsMade"),
                "fg3a": stats.get("threePointersAttempted"),
                "fg3m": stats.get("threePointersMade"),
                "fta": stats.get("freeThrowsAttempted"),
                "ftm": stats.get("freeThrowsMade"),
                "plus_minus": stats.get("plusMinusPoints"),
            })
    return rows


def build_player_box_frame(root: Optional[Path] = None
                            ) -> Tuple[pd.DataFrame, List[str], int]:
    """Walk every game dir under *root* (default BACKFILL_DIR). Returns
    (per-game-player frame, failed_game_ids, n_games_parsed). Never raises --
    a malformed/empty game dir is skipped and listed in failed_game_ids."""
    root = root if root is not None else BACKFILL_DIR
    if not root.exists():
        return pd.DataFrame(), [], 0
    all_rows: List[Dict[str, Any]] = []
    failed: List[str] = []
    n_parsed = 0
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        game = _load_boxscore(d)
        if game is None:
            failed.append(d.name)
            continue
        rows = _player_rows_for_game(d.name, game)
        if not rows:
            failed.append(d.name)
            continue
        all_rows.extend(rows)
        n_parsed += 1
    df = pd.DataFrame(all_rows) if all_rows else pd.DataFrame()
    return df, failed, n_parsed


def _team_point_check(root: Optional[Path] = None, n_samples: int = 5,
                       seed: int = 42) -> List[Dict[str, Any]]:
    """Cross-check n_samples random games: sum of player pts per team vs the
    team's recorded box score. Returns a per-game mismatch report (empty list
    if no games loadable)."""
    root = root if root is not None else BACKFILL_DIR
    game_dirs = [d for d in sorted(root.iterdir()) if d.is_dir()] if root.exists() else []
    rng = random.Random(seed)
    sample = rng.sample(game_dirs, min(n_samples, len(game_dirs)))
    report = []
    for d in sample:
        game = _load_boxscore(d)
        if game is None:
            continue
        row: Dict[str, Any] = {"game_id": d.name}
        for side in _SIDES:
            team = game.get(side) or {}
            recorded = team.get("score")
            summed = sum(
                (p.get("statistics") or {}).get("points") or 0
                for p in team.get("players") or [] if isinstance(p, dict)
            )
            row[f"{side}_recorded"] = recorded
            row[f"{side}_summed"] = summed
            row[f"{side}_match"] = recorded == summed
        report.append(row)
    return report


def _null_rates(df: pd.DataFrame) -> Dict[str, float]:
    return {f: round(float(df[f].isna().mean()), 4) for f in _CORE_FIELDS if f in df.columns}


def run() -> Dict[str, Any]:
    """Build the per-game player boxscore frame, write it, and run the honest
    validation summary. Never raises -- an empty corpus writes no file and
    reports 0s."""
    df, failed, n_parsed = build_player_box_frame()
    summary: Dict[str, Any] = {
        "n_games_parsed": n_parsed,
        "n_games_failed": len(failed),
        "failed_game_ids": failed,
        "n_rows": len(df),
        "n_players": int(df["player_id"].nunique()) if not df.empty else 0,
    }
    if not df.empty:
        summary["date_range"] = [str(df["game_date"].min()), str(df["game_date"].max())]
        summary["null_rates"] = _null_rates(df)
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUT_PATH.with_suffix(".parquet.tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(OUT_PATH)
        summary["out_path"] = str(OUT_PATH)
    summary["team_point_check"] = _team_point_check()
    return summary


def _main() -> int:
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = [
    "build_player_box_frame", "run", "OUT_PATH",
]
