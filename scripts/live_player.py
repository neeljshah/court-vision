"""live_player.py — single-player live focus: current stats vs bets vs projection.

When you have a few bets on one player, you don't want to scroll a slate
dashboard — you want THAT PLAYER's screen. This script gives that.

Pulls:
  - latest snapshot from cycle-88a live_game_poll
  - pre-game prediction from cycle-47/49/80 ledger
  - open bets on this player from cycle-68 bet log
  - pace-projected final from cycle-88b project_final logic

Run:
    python scripts/live_player.py "Nikola Jokic"
    python scripts/live_player.py "Jokic" --date 2026-05-24
    python scripts/live_player.py --pid 203999
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
    find_player, find_player_by_id, clock_share_played, parse_clock,
    absolute_margin, is_blowout, is_live, is_final, _name_key,
)
# Cycle 89b (loop 5): unified foul-trouble table lives in src.prediction.live_factors.
from src.prediction.live_factors import foul_trouble_factor  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def project_final(current: float, share_played: float,
                    foul_factor: float = 1.0, blowout_factor: float = 1.0) -> float:
    """Combine pace + foul + blowout into single projection."""
    if share_played <= 0.0:
        return float(current)
    share = max(0.05, share_played)
    remaining_share = 1.0 - share
    projected_remaining = (float(current) / share) * remaining_share \
                          * foul_factor * blowout_factor
    return float(current) + projected_remaining


def foul_factor_for(pf: int, period: int, clock_min_remaining: float) -> float:
    """Backwards-compat wrapper. Cycle 89b unified the canonical table into
    ``src.prediction.live_factors.foul_trouble_factor``; this name is kept so
    ``save_live_predictions`` (and any other importers) don't break.
    """
    return foul_trouble_factor(pf, period, clock_min_remaining)


def blowout_factor_for(margin: int, period: int, clock_min_remaining: float,
                        is_starter: bool, on_leading_side: bool) -> float:
    """Mirror cycle-88f factor table. Only applies to starters on leading team."""
    if period < 4 or margin < 15:
        return 1.0
    # Bench players actually benefit from blowout (garbage time)
    if not is_starter:
        if margin >= 30: return 1.50
        if margin >= 20: return 1.30
        if margin >= 15: return 1.05
        return 1.0
    # Starters on the LEADING team see reduced minutes (coaches rest them)
    if not on_leading_side:
        return 1.0     # losing team starters keep playing (chasing)
    if period == 4 and clock_min_remaining < 3.0 and margin > 25:
        return 0.10
    if margin >= 30:
        return 0.25
    if margin >= 20:
        return 0.55
    if margin >= 15:
        return 0.85
    return 1.0


def load_pre_game_for_player(player_name: str, date_str: str,
                                project_dir: Optional[str] = None) -> Dict[str, float]:
    """Return {stat: pred} for one player from the cycle-80 ledger."""
    project_dir = project_dir or PROJECT_DIR
    path = os.path.join(project_dir, "data", "predictions", f"{date_str}.csv")
    out: Dict[str, float] = {}
    if not os.path.exists(path):
        return out
    key = _name_key(player_name)
    try:
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if _name_key(r.get("player", "")) != key:
                    continue
                stat = (r.get("stat") or "").lower()
                try:
                    out[stat] = float(r["pred"])
                except (KeyError, TypeError, ValueError):
                    continue
    except (OSError, csv.Error):
        pass
    return out


def load_bets_for_player(player_name: str, date_str: str,
                          project_dir: Optional[str] = None) -> List[Dict]:
    """Return rows from cycle-68 bet log filtered to one player."""
    project_dir = project_dir or PROJECT_DIR
    path = os.path.join(project_dir, "data", "bets", f"{date_str}.csv")
    out: List[Dict] = []
    if not os.path.exists(path):
        return out
    key = _name_key(player_name)
    try:
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if _name_key(r.get("player", "")) == key:
                    out.append(r)
    except (OSError, csv.Error):
        pass
    return out


def find_player_snapshot(player_name: Optional[str], player_id: Optional[int],
                          date_str: str) -> Optional[Dict]:
    """Search today's snapshots; return (player_dict, snapshot, game_id) if found."""
    for path in list_today_snapshots(date_str):
        snap = load_live_state(path)
        if not snap:
            continue
        p = (find_player_by_id(snap, player_id) if player_id
             else find_player(snap, player_name))
        if p is not None:
            return {"player": p, "snapshot": snap, "path": path}
    return None


def render(player_name: str, player_id: Optional[int], date_str: str) -> str:
    found = find_player_snapshot(player_name, player_id, date_str)
    if not found:
        return f"[no live snapshot] {player_name or player_id} not in any active game today."
    p = found["player"]
    snap = found["snapshot"]
    period = int(snap.get("period", 0) or 0)
    clock = snap.get("clock", "?")
    clock_min = parse_clock(clock)
    margin = abs(int(snap.get("home_score", 0)) - int(snap.get("away_score", 0)))
    home_lead = int(snap.get("home_score", 0)) > int(snap.get("away_score", 0))
    p_team = p.get("team", "").upper()
    home_team = snap.get("home_team", "").upper()
    on_leading_side = (p_team == home_team) == home_lead
    share = clock_share_played(period, clock)

    ff = foul_factor_for(int(p.get("pf", 0) or 0), period, clock_min)
    bf = blowout_factor_for(margin, period, clock_min,
                              bool(p.get("is_starter", False)), on_leading_side)

    pre = load_pre_game_for_player(p.get("name", player_name or ""), date_str)
    bets = load_bets_for_player(p.get("name", player_name or ""), date_str)
    bets_by_stat = {(b.get("stat", "") or "").lower(): b for b in bets}

    lines = [
        f"=== {p.get('name', '?')} ({p_team}) — Q{period} {clock}  "
        f"margin {margin}  status {snap.get('game_status', '?')} ===",
        f"  MIN {float(p.get('min', 0) or 0):>5.1f}   PF {p.get('pf', 0)}   "
        f"starter={p.get('is_starter')}   foul_factor={ff:.2f}   blowout_factor={bf:.2f}",
        "",
        f"  {'stat':4s} | {'pre':>6s} | {'now':>5s} | {'proj':>6s} | "
        f"{'line':>5s} {'side':>5s} {'edge':>7s}",
        "  " + "-" * 60,
    ]
    for stat in STATS:
        current = float(p.get(stat, 0) or 0)
        proj = project_final(current, share, ff, bf)
        pre_v = pre.get(stat, None)
        pre_s = f"{pre_v:>6.1f}" if pre_v is not None else "    - "
        bet = bets_by_stat.get(stat)
        if bet:
            try:
                line = float(bet.get("line", "nan"))
                side = bet.get("side", "?")
                edge_value = proj - line if side == "OVER" else line - proj
                edge_s = f"{edge_value:>+7.2f}"
                line_s = f"{line:>5.1f}"
                side_s = f"{side:>5s}"
            except (TypeError, ValueError):
                line_s, side_s, edge_s = "  -  ", "  -  ", "  -    "
        else:
            line_s, side_s, edge_s = "  -  ", "  -  ", "  -    "
        lines.append(
            f"  {stat.upper():4s} | {pre_s} | {current:>5.0f} | {proj:>6.1f} | "
            f"{line_s} {side_s} {edge_s}"
        )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("name", nargs="?", help="Player name (diacritic-insensitive)")
    grp.add_argument("--pid", type=int, help="Player ID for exact lookup")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    args = ap.parse_args()
    date_str = args.date or _date.today().isoformat()
    print(render(args.name, args.pid, date_str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
