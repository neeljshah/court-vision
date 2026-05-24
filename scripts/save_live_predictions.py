"""save_live_predictions.py — write in-game predictions to the daily ledger.

The cycle-47/49/80 ledger captures PRE-GAME predictions. The cycle-88a-h
live system produces in-game updates but doesn't persist them. Without
persistence, we can never empirically measure 30 days from now whether
"the cycle-88b in-game projection improves MAE vs pre-game" — every
in-game projection vanishes after the dashboard prints it.

This script bridges that:
  - Reads latest snapshot per active game
  - Projects current stats to final using pace + foul + blowout factors
  - Appends rows to `data/predictions/<date>_inplay.csv` with a `pred_kind`
    column = "Q{period}_inplay_{HHMM}"

Schema (mirrors cycle-80 with extra `pred_kind` + `snapshot_period`):
    date, game_id, player_id, player, team, opp, venue, stat, pred,
    lineup_status, lineup_class, play_pct, injury_status,
    pred_kind, snapshot_period, snapshot_clock, current_stat

Run:
    python scripts/save_live_predictions.py                     # all active games
    python scripts/save_live_predictions.py --game-id 0022400123
    python scripts/save_live_predictions.py --pred-kind manual_check
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import date as _date, datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data.live import (  # noqa: E402
    load_live_state, latest_snapshot_path, list_today_snapshots,
    clock_share_played, parse_clock, _name_key,
)
# Reuse cycle-88m factor tables — they mirror cycle 88e/88f
from scripts.live_player import (  # noqa: E402
    project_final, foul_factor_for, blowout_factor_for,
)

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")


def _period_kind(period: int, clock_str: str) -> str:
    """Convert (period, clock) -> a stable 'pred_kind' tag for the ledger."""
    hhmm = datetime.now().strftime("%H%M")
    return f"Q{period}_inplay_{hhmm}"


def derive_inplay_predictions(snapshot: dict, date_str: str,
                                 override_kind: Optional[str] = None
                                 ) -> List[Dict]:
    """Project final stats for every player in the snapshot.

    Returns one row per (player, stat) ready for ledger write. Includes the
    current actual value alongside the projection so future analysis can
    measure projection accuracy at the snapshot moment.
    """
    period = int(snapshot.get("period", 0) or 0)
    clock = snapshot.get("clock", "")
    clock_min = parse_clock(clock)
    share = clock_share_played(period, clock)
    margin = abs(int(snapshot.get("home_score", 0))
                  - int(snapshot.get("away_score", 0)))
    home_lead = int(snapshot.get("home_score", 0)) > int(snapshot.get("away_score", 0))
    home_team = snapshot.get("home_team", "").upper()
    away_team = snapshot.get("away_team", "").upper()
    game_id = snapshot.get("game_id", "")

    kind = override_kind or _period_kind(period, clock)
    rows: List[Dict] = []
    for p in snapshot.get("players", []) or []:
        name = p.get("name", "")
        if not name:
            continue
        team = (p.get("team", "") or "").upper()
        opp = away_team if team == home_team else home_team
        venue = "home" if team == home_team else "away"
        is_starter = bool(p.get("is_starter", False))
        on_leading = (team == home_team) == home_lead
        ff = foul_factor_for(int(p.get("pf", 0) or 0), period, clock_min)
        bf = blowout_factor_for(margin, period, clock_min, is_starter, on_leading)

        for stat in STATS:
            try:
                current = float(p.get(stat, 0) or 0)
            except (TypeError, ValueError):
                current = 0.0
            proj = project_final(current, share, ff, bf)
            rows.append({
                "date": date_str,
                "game_id": game_id,
                "player_id": p.get("player_id", ""),
                "player": name,
                "team": team,
                "opp": opp,
                "venue": venue,
                "stat": stat,
                "pred": f"{proj:.4f}",
                "lineup_status": "",      # not known from snapshot alone
                "lineup_class": "starter" if is_starter else "bench",
                "play_pct": "",
                "injury_status": "",
                "pred_kind": kind,
                "snapshot_period": str(period),
                "snapshot_clock": clock,
                "current_stat": f"{current:.4f}",
            })
    return rows


def append_to_ledger(rows: List[Dict], out_path: str) -> int:
    """Append rows to out_path (create with header if missing). Returns count written."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    file_exists = os.path.exists(out_path) and os.path.getsize(out_path) > 0
    fieldnames = [
        "date", "game_id", "player_id", "player", "team", "opp", "venue",
        "stat", "pred", "lineup_status", "lineup_class", "play_pct",
        "injury_status", "pred_kind", "snapshot_period", "snapshot_clock",
        "current_stat",
    ]
    with open(out_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        if not file_exists:
            w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-id", default=None,
                    help="Process only this game (latest snapshot).")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--out", default=None,
                    help="Ledger path (default: data/predictions/<date>_inplay.csv)")
    ap.add_argument("--pred-kind", default=None,
                    help="Override the auto-derived pred_kind tag.")
    args = ap.parse_args()

    date_str = args.date or _date.today().isoformat()
    out = args.out or os.path.join(PROJECT_DIR, "data", "predictions",
                                     f"{date_str}_inplay.csv")

    if args.game_id:
        path = latest_snapshot_path(args.game_id)
        if not path:
            print(f"[fail] no snapshots for game {args.game_id} in data/live/")
            return 1
        paths = [path]
    else:
        paths = list_today_snapshots(date_str)
        if not paths:
            print(f"[empty] no live snapshots for {date_str}")
            return 1

    total = 0
    for path in paths:
        snap = load_live_state(path)
        if not snap:
            continue
        rows = derive_inplay_predictions(snap, date_str,
                                             override_kind=args.pred_kind)
        n = append_to_ledger(rows, out)
        total += n
        print(f"  {os.path.basename(path)} -> {n} rows")
    print(f"\n[save_live_predictions] wrote {total} in-play rows -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
