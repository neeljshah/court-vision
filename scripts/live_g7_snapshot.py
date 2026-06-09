"""live_g7_snapshot.py -- G7 in-play projection driver (WCF Game 7, SAS @ OKC).

Single-purpose, self-contained wrapper around ``src.prediction.live_engine``
for WCF Game 7 (game_id 0042500317, OKC home, 2026-05-30). Takes a canonical
live game-state dict (the same schema the live poller writes) and emits:

  * per-(player, stat) final projections (pts/reb/ast/fg3m/stl/blk/tov)
  * in-play home-team win probability + the snapshot tag it was scored at
  * q10/q50/q90 quantile bands per projection (advisory)

It does NOT re-implement any math -- it calls ``project_from_snapshot`` so the
validated cycle-88 + learned-Q4-minutes + residual-head + inplay-winprob stack
drives every number. Validated end-to-end on WCF G5/G6 endQ3 (engine stat-MAE
0.60 vs pregame season-avg 1.65 = 63.6% better; endQ3 home-win Brier 0.0165).

USAGE
-----
    # from a snapshot JSON written by the live poller (data/live/<gid>_*.json):
    python scripts/live_g7_snapshot.py --snapshot data/live/0042500317_<ts>.json

    # at a quarter break, force the engine to treat it as an end-of-period read
    python scripts/live_g7_snapshot.py --snapshot <path> --period 4

    # built-in mock endQ3 demo (no live data needed):
    python scripts/live_g7_snapshot.py --demo

REQUIRED LIVE INPUTS (per snapshot)
-----------------------------------
Top-level:  game_id, period, clock ("MM:SS" remaining in the period),
            home_team, away_team, home_score, away_score
Per player (snap["players"][i]):
            player_id, name, team, min, pts, reb, ast, fg3m, stl, blk, tov, pf,
            min_q1, min_q2, min_q3 (per-quarter minutes -> drives the learned-Q4
            minute model + bench detection), is_starter
For the win-prob head at a quarter break ALSO supply per-quarter team points:
            home_q1..home_q3, away_q1..away_q3  (and home_team_id / season /
            pregame_win_prob improve it but are optional).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from src.prediction.live_engine import project_from_snapshot  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
G7_GAME_ID = "0042500317"


def project(snap: dict, period: int | None = None) -> list[dict]:
    """Run the validated live engine on one snapshot. period overrides the
    snapshot's reported period when you want to force an end-of-quarter read."""
    return project_from_snapshot(snap, period=period)


def summarize(rows: list[dict]) -> dict:
    """Collapse engine rows into {win_prob, snapshot, players:{name:{stat:proj}}}."""
    wp = None
    wp_snap = None
    players: dict = {}
    for r in rows:
        if r.get("home_win_prob_inplay") is not None:
            wp = r["home_win_prob_inplay"]
            wp_snap = r.get("inplay_winprob_snapshot")
        nm = r.get("name") or str(r.get("player_id"))
        players.setdefault(nm, {})[r["stat"]] = {
            "current": r.get("current"),
            "proj": round(float(r.get("projected_final", 0.0)), 2),
            "q10": r.get("q10"), "q90": r.get("q90"),
            "source": r.get("projection_source"),
        }
    return {"home_win_prob": wp, "winprob_snapshot": wp_snap, "players": players}


def print_report(snap: dict, rows: list[dict]) -> None:
    s = summarize(rows)
    print("\n=== %s @ %s  game_id=%s  P%s clock=%s  score %s-%s ==="
          % (snap.get("away_team"), snap.get("home_team"), snap.get("game_id"),
             snap.get("period"), snap.get("clock"),
             snap.get("home_score"), snap.get("away_score")))
    wp = s["home_win_prob"]
    print("home (%s) win prob: %s  [%s]"
          % (snap.get("home_team"),
             ("%.3f" % wp) if wp is not None else "n/a (mid-quarter or no artifact)",
             s["winprob_snapshot"]))
    print("\n%-26s %5s %6s %7s %12s" % ("player", "stat", "cur", "proj", "[q10,q90]"))
    print("-" * 64)
    # show the headline stat (pts) for every player, then full lines for stars
    for nm, stats in s["players"].items():
        p = stats.get("pts", {})
        band = "[%.1f,%.1f]" % (p.get("q10") or 0, p.get("q90") or 0)
        print("%-26s %5s %6s %7.1f %12s"
              % (nm[:26], "PTS", p.get("current"), p.get("proj"), band))


def mock_g7_endq3_state() -> dict:
    """A plausible WCF G7 end-of-Q3 state (OKC home). Numbers are illustrative;
    swap in the real poller snapshot during the live game."""
    def pl(pid, name, team, mn, pts, reb, ast, fg3m, stl, blk, tov, pf,
           q1, q2, q3, starter=True):
        return {"player_id": pid, "name": name, "team": team, "min": mn,
                "pts": pts, "reb": reb, "ast": ast, "fg3m": fg3m, "stl": stl,
                "blk": blk, "tov": tov, "pf": pf, "min_q1": q1, "min_q2": q2,
                "min_q3": q3, "min_q4": 0.0, "is_starter": starter,
                "pts_q1": round(pts / 3), "pts_q2": round(pts / 3),
                "pts_q3": pts - 2 * round(pts / 3)}
    players = [
        pl(1628983, "Shai Gilgeous-Alexander", "OKC", 30, 28, 4, 6, 2, 1, 0, 2, 2, 10, 10, 10),
        pl(1627936, "Alex Caruso", "OKC", 26, 12, 3, 2, 2, 2, 0, 1, 3, 9, 8, 9),
        pl(1631096, "Chet Holmgren", "OKC", 28, 14, 9, 1, 1, 0, 3, 1, 3, 10, 9, 9),
        pl(1630168, "Luguentz Dort", "OKC", 27, 9, 4, 1, 3, 1, 0, 0, 2, 9, 9, 9),
        pl(1628368, "De'Aaron Fox", "SAS", 31, 22, 3, 7, 1, 2, 0, 3, 2, 11, 10, 10),
        pl(1641705, "Victor Wembanyama", "SAS", 30, 21, 11, 2, 1, 1, 4, 3, 4, 10, 10, 10),
        pl(1631110, "Stephon Castle", "SAS", 28, 16, 4, 5, 1, 1, 0, 2, 3, 9, 9, 10),
        pl(1630577, "Julian Champagnie", "SAS", 24, 11, 5, 1, 3, 0, 0, 1, 2, 8, 8, 8),
    ]
    return {
        "game_id": G7_GAME_ID, "period": 4, "clock": "12:00",
        "home_team": "OKC", "away_team": "SAS",
        "home_score": 81, "away_score": 78,
        "home_q1": 27, "home_q2": 28, "home_q3": 26,
        "away_q1": 26, "away_q2": 27, "away_q3": 25,
        "home_team_id": 1610612760, "away_team_id": 1610612759,
        "season": "2025-26", "pregame_win_prob": 0.60,
        "game_status": "LIVE", "players": players,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="WCF G7 in-play projector")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--snapshot", help="path to a live snapshot JSON")
    g.add_argument("--demo", action="store_true",
                   help="run the built-in mock endQ3 G7 state")
    ap.add_argument("--period", type=int, default=None,
                    help="force the engine to read this as an end-of-period state")
    ap.add_argument("--json", action="store_true",
                    help="emit the summarized projection dict as JSON")
    args = ap.parse_args()

    if args.demo:
        snap = mock_g7_endq3_state()
    else:
        with open(args.snapshot, encoding="utf-8") as fh:
            snap = json.load(fh)

    rows = project(snap, period=args.period)
    if args.json:
        print(json.dumps(summarize(rows), indent=2, default=str))
    else:
        print_report(snap, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
