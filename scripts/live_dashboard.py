"""live_dashboard.py — pretty-print live game state + projections in the terminal.

Pulls together the cycle-88 in-game system:
  - live_game_poll snapshots (cycle 88a)
  - in-game projector (cycle 88b)
  - foul-trouble adjuster (cycle 88e)
  - blowout adjuster (cycle 88f)
  - the predictions ledger (cycle 47/49/80) for original pre-game comparison

Single screen per game: starters with current stat / projected final / pre-game
prediction, side-by-side. Quick read for "is the game tracking with my bets?"

Run:
    python scripts/live_dashboard.py                          # all live games today
    python scripts/live_dashboard.py --game-id 0022400123
    python scripts/live_dashboard.py --date 2026-05-24

Output (per game):
    === SAS @ OKC | Q2 5:30 | SAS 56 - OKC 48 (LIVE) ===
      Player                    MIN  PTS_now/proj/pre   REB_now/proj/pre  ...
      Shai Gilgeous-Alexander   18.0  12 / 32 / 28.5     4 / 11 / 8.5   ...
      Victor Wembanyama         22.0  10 / 22 / 24.0     8 / 18 / 13.0  ...
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date as _date
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data.live import (  # noqa: E402
    load_live_state, latest_snapshot_path, list_today_snapshots,
    parse_clock, remaining_game_minutes, clock_share_played,
    is_live, is_final, score_margin,
)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _name_key(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def load_pre_game_predictions(date_str: str,
                                project_dir: Optional[str] = None
                                ) -> Dict[str, Dict[str, float]]:
    """{(player_key, stat): pred} from data/predictions/<date>.csv if present."""
    project_dir = project_dir or PROJECT_DIR
    path = os.path.join(project_dir, "data", "predictions", f"{date_str}.csv")
    out: Dict[str, Dict[str, float]] = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                key = _name_key(r.get("player", ""))
                stat = (r.get("stat", "") or "").lower()
                try:
                    pred = float(r.get("pred", "nan"))
                except (TypeError, ValueError):
                    continue
                if key and stat:
                    out.setdefault(key, {})[stat] = pred
    except (OSError, csv.Error):
        pass
    return out


def project_remaining(current: float, share_played: float) -> float:
    """Pace-based projection: scale current value by 1/share_played.

    share_played=0.5 -> double current. share_played=1.0 -> current (game over).
    share_played=0.0 -> can't project (avoid division by zero), return current.
    """
    if share_played <= 0.0:
        return float(current)
    return float(current) / max(0.05, share_played)


def format_game_line(snapshot: dict) -> str:
    home = snapshot.get("home_team", "HOME")
    away = snapshot.get("away_team", "AWAY")
    h = snapshot.get("home_score", 0)
    a = snapshot.get("away_score", 0)
    period = snapshot.get("period", "?")
    clock = snapshot.get("clock", "?")
    status = snapshot.get("game_status", "?")
    return f"=== {away} @ {home} | Q{period} {clock} | {away} {a} - {home} {h} ({status}) ==="


def format_player_line(player: dict, share_played: float,
                        pre_game: Dict[str, Dict[str, float]]) -> str:
    name = player.get("name", "?")
    minutes = player.get("min", 0)
    starter_marker = "*" if player.get("is_starter") else " "
    pieces = [f"  {starter_marker}{name:<25} MIN {float(minutes):>5.1f}"]
    pre = pre_game.get(_name_key(name), {})
    for stat in STATS:
        now = player.get(stat, 0)
        try:
            now_f = float(now or 0)
        except (TypeError, ValueError):
            now_f = 0.0
        proj = project_remaining(now_f, share_played)
        pre_val = pre.get(stat, None)
        pre_s = f"{pre_val:.1f}" if pre_val is not None else "  - "
        pieces.append(f" {stat.upper():>4s} {now_f:>4.0f}/{proj:>4.1f}/{pre_s}")
    return "".join(pieces)


def render_game(snapshot: dict, pre_game: Dict[str, Dict[str, float]],
                 only_starters: bool = False) -> str:
    """Render one game's section."""
    if not snapshot:
        return "(empty snapshot)"
    lines = [format_game_line(snapshot)]
    share = clock_share_played(int(snapshot.get("period", 0) or 0),
                                snapshot.get("clock", ""))
    players = snapshot.get("players", []) or []
    if only_starters:
        players = [p for p in players if p.get("is_starter")]
    # Sort by current PTS desc — most relevant players first
    players = sorted(players, key=lambda p: -float(p.get("pts", 0) or 0))
    for p in players:
        lines.append(format_player_line(p, share, pre_game))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-id", default=None,
                    help="Show only this game. Default: all today's live snapshots.")
    ap.add_argument("--date", default=None,
                    help="Date for the pre-game ledger lookup (default: today).")
    ap.add_argument("--snapshot", default=None,
                    help="Render an explicit snapshot file path (overrides --game-id).")
    ap.add_argument("--starters-only", action="store_true",
                    help="Hide bench players.")
    args = ap.parse_args()

    date_str = args.date or _date.today().isoformat()
    pre_game = load_pre_game_predictions(date_str)

    if args.snapshot:
        snap = load_live_state(args.snapshot)
        if not snap:
            print(f"[fail] could not load snapshot: {args.snapshot}")
            return 1
        print(render_game(snap, pre_game, only_starters=args.starters_only))
        return 0

    if args.game_id:
        path = latest_snapshot_path(args.game_id)
        if not path:
            print(f"[fail] no snapshots for game {args.game_id} in data/live/")
            return 1
        snap = load_live_state(path)
        print(render_game(snap, pre_game, only_starters=args.starters_only))
        return 0

    # Default: all today's games
    paths = list_today_snapshots(date_str)
    if not paths:
        print(f"[empty] no live snapshots in data/live/ for {date_str}")
        print("  Run scripts/live_game_poll.py to start capturing.")
        return 1
    for path in paths:
        snap = load_live_state(path)
        if not snap:
            continue
        print(render_game(snap, pre_game, only_starters=args.starters_only))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
