"""recommend_endQ2_bets.py -- cycle 98d (loop 5). Halftime betting recommender.

Cycle 97d (backtest_inplay_edge_v2) showed endQ2 ROI is competitive
(>= 80% of endQ3) for 5/7 stats -- REB, AST, FG3M, STL, BLK. That unlocks
placing bets at HALFTIME instead of waiting for endQ3, doubling the
line-movement window. PTS+TOV fall below the bar (0.74, 0.79) so they sit
behind --include-pts-tov.

Workflow: scan data/live/ for halftime snapshots (period=2 clock=0:00 OR
period=3 clock~12:00) for --date; call live_engine.project_from_snapshot
(the cycle-95c entry into the cycle-94d-validated stack); build an L5
rolling-mean line proxy per (player, stat) from gamelogs (same proxy cycle
97d's ROI table is computed against); filter |edge| >= --threshold and
rank by Kelly-positive EV.

Strictly read-only -- does NOT modify live_engine or predict_in_game.

CLI:
    python scripts/recommend_endQ2_bets.py --date 2026-05-24
    python scripts/recommend_endQ2_bets.py --date 2026-05-24 --threshold 1.5
    python scripts/recommend_endQ2_bets.py --date 2026-05-24 --include-pts-tov
    python scripts/recommend_endQ2_bets.py --date 2026-05-24 --dry-run
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import date as _date, datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Encoding for Windows so accented player names don't crash stdout.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from src.data.live import list_today_snapshots, load_live_state  # noqa: E402
from src.prediction import live_engine                          # noqa: E402
# Reuse cycle 95d's pure betting math for Kelly + EV (same math the
# cycle 97d backtest used, so the recommender is internally consistent).
import backtest_inplay_edge as bie                              # noqa: E402
from src.betting.recommendation import (                         # noqa: E402
    format_recommendation_row, to_place_bet_command,
    ensure_strategy_registered,
)


# Cycle 97d viable stats (endQ2 ROI >= 80% of endQ3 ROI at threshold 1.0).
ENDQ2_VIABLE_STATS = ("reb", "ast", "fg3m", "stl", "blk")
# Stats that did NOT clear the 80% bar at endQ2.
ENDQ2_MARGINAL_STATS = ("pts", "tov")
ALL_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

DEFAULT_ODDS = -110


# ── halftime detection ────────────────────────────────────────────────────────

def is_halftime_snapshot(snap: dict) -> bool:
    """True if the snapshot is the end-of-Q2 / halftime moment.

    Two equivalent forms depending on how the live feed encodes the period
    rollover: (a) period=2 clock="0:00", (b) period=3 clock~"12:00".
    """
    if not snap:
        return False
    try:
        period = int(snap.get("period") or 0)
    except (TypeError, ValueError):
        return False
    clock_s = str(snap.get("clock") or "").strip()
    if period == 2 and clock_s in ("0:00", "00:00", "0:0", "0.00"):
        return True
    if period == 3:
        # Within ~10s of tip-of-Q3 also counts as halftime (operator hasn't
        # missed the window). Parse "MM:SS" -> minutes.
        try:
            if ":" in clock_s:
                mins, secs = clock_s.split(":", 1)
                m = float(mins); s = float(secs)
                return m >= 11 and s + (m - 11) * 60 >= 50
            return float(clock_s) >= 11.83  # 11:50 in decimal
        except (TypeError, ValueError):
            return False
    return False


def discover_halftime_snapshots(date_iso: str,
                                project_dir: Optional[str] = None
                                ) -> List[Tuple[str, dict]]:
    """Iterate data/live/<game>_*.json for the date, return halftime ones.

    Returns a list of ``(path, snapshot_dict)`` tuples.
    """
    paths = list_today_snapshots(date_iso, project_dir=project_dir)
    out: List[Tuple[str, dict]] = []
    for path in paths:
        snap = load_live_state(path)
        if not snap:
            continue
        if is_halftime_snapshot(snap):
            out.append((path, snap))
    return out


# ── L5 line proxy ─────────────────────────────────────────────────────────────

_BOX = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M",
        "stl": "STL", "blk": "BLK", "tov": "TOV"}


def _parse_gamelog_date(s) -> Optional[str]:
    """'Apr 13, 2025' -> '2025-04-13'."""
    if not s:
        return None
    try:
        return datetime.strptime(str(s), "%b %d, %Y").date().isoformat()
    except ValueError:
        return None


def l5_line_for_player(player_id: int, on_or_before: str,
                       project_dir: Optional[str] = None
                       ) -> Dict[str, float]:
    """{stat: L5_rolling_mean} for a player -- the same proxy cycle 97d uses.

    Reads data/nba/gamelog_<pid>_*.json; skips DNPs (MIN<1); {} if no priors.
    """
    project_dir = project_dir or PROJECT_DIR
    pattern = os.path.join(project_dir, "data", "nba", f"gamelog_{player_id}_*.json")
    log: List[Tuple[str, Dict[str, float]]] = []
    for fp in glob.glob(pattern):
        try:
            with open(fp, encoding="utf-8") as fh:
                games = json.load(fh) or []
        except (OSError, json.JSONDecodeError):
            continue
        for row in games:
            d = _parse_gamelog_date(row.get("GAME_DATE"))
            if d is None or d >= on_or_before:
                continue
            try:
                if float(row.get("MIN") or 0) < 1.0:
                    continue
            except (TypeError, ValueError):
                continue
            stats: Dict[str, float] = {}
            for s, col in _BOX.items():
                try:
                    stats[s] = float(row.get(col) or 0)
                except (TypeError, ValueError):
                    stats[s] = 0.0
            log.append((d, stats))
    if not log:
        return {}
    log.sort(key=lambda x: x[0])
    prior = log[-5:]
    out: Dict[str, float] = {}
    for s in ALL_STATS:
        vals = [p[1].get(s, 0.0) for p in prior]
        out[s] = sum(vals) / len(vals)
    return out


# ── recommendation builder ────────────────────────────────────────────────────

# Per-stat ROI baseline (cycle 97d endQ2 ROI_flat at threshold 1.0). Used to
# annotate each recommendation with the empirical edge expectation. PTS+TOV
# kept so --include-pts-tov can surface them.
ENDQ2_ROI_BASELINE = {
    "reb": 0.6376,
    "ast": 0.6806,
    "fg3m": 0.7088,
    "stl": 0.7797,
    "blk": 0.8286,
    "pts": 0.5189,    # marginal -- 0.74 of endQ3
    "tov": 0.6632,    # marginal -- 0.79 of endQ3
}


def build_recommendations(snapshots: List[Tuple[str, dict]],
                          threshold: float,
                          include_pts_tov: bool,
                          date_iso: str,
                          ) -> List[Dict]:
    """Project + L5-line + Kelly-filter every (player, stat) in halftime snaps."""
    target_stats = set(ENDQ2_VIABLE_STATS)
    if include_pts_tov:
        target_stats |= set(ENDQ2_MARGINAL_STATS)

    out: List[Dict] = []
    for _path, snap in snapshots:
        # Force period=3 / clock=12:00 so the projector sees the snapshot as
        # "Q3 not started" regardless of how the live feed encoded the rollover.
        # Matches cycle 97d's endQ2 reconstruction (snap_period=3, clock=12:00).
        proj_snap = dict(snap)
        proj_snap["period"] = 3
        proj_snap["clock"] = "12:00"
        rows = live_engine.project_from_snapshot(proj_snap)

        for r in rows:
            stat = (r.get("stat") or "").lower()
            if stat not in target_stats:
                continue
            pid = r.get("player_id")
            if pid is None:
                continue
            try:
                pid_i = int(pid)
            except (TypeError, ValueError):
                continue
            try:
                projection = float(r.get("projected_final") or 0)
            except (TypeError, ValueError):
                continue

            line_map = l5_line_for_player(pid_i, date_iso)
            line = line_map.get(stat)
            if line is None:
                continue

            edge = projection - line
            if abs(edge) < threshold:
                continue
            side = "OVER" if edge > 0 else "UNDER"
            sigma = bie._CAL_SPREAD.get(stat, 1.0) / (2.0 * 1.2816)
            prob = bie.model_hit_prob(projection, line, sigma, side)
            kf = bie.kelly_fraction(prob, DEFAULT_ODDS)
            if kf <= 0:
                continue
            net_payout = bie.american_payout(DEFAULT_ODDS, 1.0)
            ev = prob * net_payout - (1.0 - prob) * 1.0

            out.append({
                "player": r.get("name", ""),
                "team": r.get("team", ""),
                "stat": stat,
                "line": round(line, 2),
                "projection": round(projection, 2),
                "edge": round(edge, 2),
                "side": side,
                "prob": round(prob, 3),
                "ev_per_dollar": round(ev, 4),
                "kelly_pct": round(kf * 100, 2),
                "kelly_stake": round(kf * 1000.0, 2),  # $1000 default bankroll
                "endQ2_roi_baseline": ENDQ2_ROI_BASELINE.get(stat, 0.0),
                "snapshot_period": snap.get("period"),
                "snapshot_clock": snap.get("clock"),
                "game_id": snap.get("game_id"),
            })

    # Rank by Kelly-positive EV descending.
    out.sort(key=lambda x: x["ev_per_dollar"], reverse=True)
    return out


# ── report formatting ─────────────────────────────────────────────────────────

def _header(include_pts_tov: bool, n_snapshots: int, date_iso: str) -> str:
    stats_in = ", ".join(s.upper() for s in ENDQ2_VIABLE_STATS)
    extra = " + PTS, TOV (marginal)" if include_pts_tov else ""
    return (
        "=== endQ2 (HALFTIME) BET RECOMMENDER -- cycle 98d ===\n"
        f"  date            : {date_iso}\n"
        f"  halftime snaps  : {n_snapshots}\n"
        f"  viable stats    : {stats_in}{extra}\n"
        "  empirical basis : These 5 stats have >=80% of endQ3 ROI when placed\n"
        "                    at halftime, per cycle 97d backtest (see\n"
        "                    scripts/_results/inplay_edge_backtest_v2.md).\n"
    )


def format_table(recs: List[Dict], strategy: str = "endQ2_auto") -> str:
    if not recs:
        return "  (no recommendations passed the threshold + Kelly gate)\n"
    lines = [
        f"  {'player':<22s} {'team':4s} {'stat':4s} {'line':>5s} "
        f"{'proj':>6s} {'edge':>6s} {'side':5s} {'kelly$':>7s} "
        f"{'endQ2_ROI':>9s} {'strategy':<14s}",
        "  " + "-" * 96,
    ]
    for r in recs:
        tag = r.get("strategy", strategy)
        lines.append(
            f"  {r['player'][:22]:<22s} {r['team']:<4s} "
            f"{r['stat'].upper():<4s} {r['line']:>5.1f} "
            f"{r['projection']:>6.2f} {r['edge']:>+6.2f} {r['side']:<5s} "
            f"{r['kelly_stake']:>7.2f} "
            f"{r['endQ2_roi_baseline']:>+9.4f} {tag:<14s}"
        )
    lines.append("")
    lines.append("  --- copy-pasteable place_bet commands ---")
    for r in recs:
        lines.append("  " + to_place_bet_command(r, r.get("strategy", strategy)))
    return "\n".join(lines) + "\n"


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default=None,
                    help="YYYY-MM-DD (default: today)")
    ap.add_argument("--threshold", type=float, default=1.0,
                    help="Minimum |projection - L5_line|. Default 1.0.")
    ap.add_argument("--include-pts-tov", action="store_true",
                    help="Also surface PTS + TOV recommendations. Cycle 97d "
                         "showed <80%% of endQ3 ROI for these -- use only when "
                         "no Q3 data is forthcoming.")
    ap.add_argument("--strategy", default="endQ2_auto",
                    help="A/B strategy tag stamped on each recommendation "
                         "(cycle 104c). Default 'endQ2_auto'.")
    ap.add_argument("--register", action="store_true",
                    help="If set, auto-register --strategy in ab_strategies.csv "
                         "with bankroll $1000 / max_bet_pct 0.05 when missing.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the resolved date + halftime-snap count, then "
                         "exit 0 even when no snapshots exist. Useful for the "
                         "offseason smoke test.")
    args = ap.parse_args()

    date_iso = args.date or _date.today().isoformat()
    snaps = discover_halftime_snapshots(date_iso)

    if args.register:
        try:
            ensure_strategy_registered(args.strategy, bankroll=1000.0,
                                        max_bet_pct=0.05)
        except Exception as exc:
            print(f"[warn] could not auto-register {args.strategy!r}: {exc}")

    if args.dry_run:
        print(f"[dry-run] date={date_iso} halftime_snapshots={len(snaps)} "
              f"include_pts_tov={args.include_pts_tov} threshold={args.threshold} "
              f"strategy={args.strategy}")
        return 0

    print(_header(args.include_pts_tov, len(snaps), date_iso))
    if not snaps:
        print("  (no halftime snapshots in data/live/ -- nothing to do)\n")
        return 0
    recs = build_recommendations(
        snaps, args.threshold, args.include_pts_tov, date_iso,
    )
    for r in recs:
        r["strategy"] = args.strategy
    print(format_table(recs, strategy=args.strategy))
    return 0


if __name__ == "__main__":
    sys.exit(main())
