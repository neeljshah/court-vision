"""live_edge_eval.py — cycle 88j (loop 5). Mid-game bet EV re-evaluator.

The cycle-68 bet log captures bets at PLACEMENT TIME with the pre-game model's
edge / EV / Kelly. Once the game tips, those numbers go stale fast: Jokic OVER
28.5 PTS at -110 might have been +6% EV pre-game, but if he's on pace for 22
mid-game the bet has gone negative. This script re-evaluates every open bet
against the latest live snapshot and prints an updated edge / EV / suggested
action so we know which bets to hedge vs let ride.

Pipeline:
    bet log row  ──>  find player in latest live snapshot
                      │
                      ├─ not playing tonight  -> action="not playing tonight"
                      ├─ game FINAL          -> final_proj = current stat
                      └─ otherwise           -> project_final() (cycle 88b)
                            │
                            └─ normal-approx hit-prob vs line
                                 │
                                 └─ EV = p*payout - (1-p)
                                       │
                                       └─ action by EV band

Action bands (per-dollar EV terms):
    ev >= +0.05   → LET IT RIDE   (still solidly +EV, no action needed)
    ev > -0.05    → MONITOR        (close to even, hedge cost likely > edge)
    ev <= -0.05   → HEDGE         (clearly -EV, consider live-betting other side)
The 0.05 threshold matches the Kelly-fraction cliff: at -110 odds, a 2.6pp
hit-prob swing across the line drops a +EV bet to near-zero EV, so anything
beyond a 5% EV gap is "the model has actually changed its mind" rather than
noise from per-quarter variance.

CLI:
    python scripts/live_edge_eval.py
    python scripts/live_edge_eval.py --date 2026-05-24
    python scripts/live_edge_eval.py --bet-log data/bets/x.csv --snapshots data/live/
    python scripts/live_edge_eval.py --action HEDGE
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import re
import sys
from datetime import date as _date, datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Reconfigure stdout to UTF-8 on Windows so accented player names don't crash.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# Cycle 88 single-source-of-truth for live snapshot parsing.
from src.data.live import (  # noqa: E402
    load_live_state,
    find_player,
    is_final,
    parse_clock as live_parse_clock,
    remaining_game_minutes,
    elapsed_game_minutes,
)
# Cycle 88b projector — imported as a module so tests can monkeypatch it.
import predict_in_game as pig  # noqa: E402


BET_DIR = os.path.join(PROJECT_DIR, "data", "bets")
LIVE_DIR = os.path.join(PROJECT_DIR, "data", "live")

# Stat → rough per-game sigma (used as the normal-approx baseline when we
# can't infer it from the bet log). Derived from cycle-40 quantile calibration:
# (q90 - q10) / 2.56 at typical projection magnitudes. These are intentionally
# WIDE — better to underestimate edge than overstate it mid-game.
_BASELINE_SIGMA: Dict[str, float] = {
    "pts":  6.5,
    "reb":  3.0,
    "ast":  2.4,
    "fg3m": 1.4,
    "stl":  1.0,
    "blk":  0.9,
    "tov":  1.5,
}

# Action thresholds in per-dollar EV.
HEDGE_THRESHOLD = -0.05      # ev <= -0.05 → HEDGE
LET_IT_RIDE_THRESHOLD = 0.05  # ev >= +0.05 → LET IT RIDE
ACTIONS = ("HEDGE", "MONITOR", "LET IT RIDE", "NOT PLAYING", "FINAL")


# ── small EV helpers (mirrored from compare_to_lines so we don't import the
#     full prop_pergame model graph just for arithmetic) ─────────────────────

def american_payout(odds: int, stake: float = 1.0) -> float:
    """Profit on $stake at American odds (NOT including stake return)."""
    odds = int(odds)
    if odds > 0:
        return stake * (odds / 100.0)
    return stake * (100.0 / -odds)


def normal_cdf(z: float) -> float:
    """Standard normal CDF via math.erf — no scipy dependency."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def hit_probability(proj_final: float, line: float, side: str,
                    sigma: float) -> float:
    """P(actual {>|<} line) under N(proj_final, sigma^2).

    side is "OVER" or "UNDER" (case-insensitive). sigma is clamped to a
    small positive number so degenerate inputs don't blow up.
    """
    s = max(float(sigma), 1e-6)
    z = (line - proj_final) / s
    cdf_at_line = normal_cdf(z)
    p_over = 1.0 - cdf_at_line
    return p_over if side.upper() == "OVER" else (1.0 - p_over)


def remaining_sigma(stat: str, period: int, clock_str) -> float:
    """Scale the baseline per-game sigma by sqrt(remaining_share).

    A bet placed pre-game has full per-game variance ahead of it; with only
    one quarter left, sigma should shrink by sqrt(0.25) = 0.5. This is the
    Brownian-motion / variance-additive intuition: variance scales with time,
    so stdev scales with sqrt(time). Floor at 10% of baseline sigma so even
    with seconds left the distribution isn't a delta function (the projector
    itself has noise, e.g. final FT attempts).
    """
    base = _BASELINE_SIGMA.get(stat.lower(), 5.0)
    rem_min = remaining_game_minutes(int(period or 0), clock_str)
    share_remaining = max(0.0, min(1.0, rem_min / 48.0))
    return max(base * math.sqrt(share_remaining), base * 0.10)


def classify_action(ev: float) -> str:
    """Map per-dollar EV to a suggested action.

    HEDGE: ev clearly -EV — model now disagrees with the bet enough that the
    expected loss outweighs typical hedge costs (~5% vig per leg).
    LET IT RIDE: ev clearly +EV — model still likes the bet, no need to act.
    MONITOR: edge has eroded but not flipped meaningfully; hedging would
    likely cost more than the residual edge is worth.
    """
    if ev <= HEDGE_THRESHOLD:
        return "HEDGE"
    if ev >= LET_IT_RIDE_THRESHOLD:
        return "LET IT RIDE"
    return "MONITOR"


# ── bet log + snapshot loading ───────────────────────────────────────────────

def load_bet_log(path: str) -> List[dict]:
    """Read a cycle-68 bet log. Returns list-of-dicts (column names lowercased).

    Missing file → []. Malformed rows → skipped (no exception).
    """
    if not path or not os.path.exists(path):
        return []
    rows: List[dict] = []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            if r is None:
                continue
            rows.append({(k or "").strip().lower(): (v or "").strip()
                         for k, v in r.items()})
    return rows


def default_bet_log_path(date_str: str) -> str:
    return os.path.join(BET_DIR, f"{date_str}.csv")


def list_latest_snapshots(snap_dir: str) -> List[str]:
    """Return the latest snapshot file per game_id under snap_dir."""
    if not os.path.isdir(snap_dir):
        return []
    by_game: Dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(snap_dir, "*.json"))):
        base = os.path.basename(path)
        m = re.match(r"^(\d+)_", base)
        if not m:
            continue
        by_game[m.group(1)] = path   # lex-sort -> latest timestamp wins
    return list(by_game.values())


def find_player_across_snapshots(name: str, snapshots: List[dict]):
    """Locate (player_dict, snapshot_dict) for the first snapshot containing
    the player. None if not present in any snapshot.
    """
    for snap in snapshots:
        p = find_player(snap, name)
        if p is not None:
            return p, snap
    return None, None


# ── single-bet evaluation ────────────────────────────────────────────────────

def evaluate_bet(bet: dict, snapshots: List[dict]) -> dict:
    """Re-evaluate one bet against the live snapshots. Returns a dict with
    the fields needed for the stdout table + downstream CSV.

    The bet dict is the cycle-68 schema (lowercased keys). The returned dict
    is suitable for printing AND for writing back as an "updated bet log".
    """
    name = bet.get("player", "")
    stat = bet.get("stat", "").lower()
    try:
        line = float(bet.get("line", "nan"))
    except (TypeError, ValueError):
        line = float("nan")
    side = (bet.get("side", "") or "").upper() or "OVER"
    try:
        odds = int(float(bet.get("odds", -110) or -110))
    except (TypeError, ValueError):
        odds = -110
    try:
        pregame_pred = float(bet.get("model", "nan"))
    except (TypeError, ValueError):
        pregame_pred = float("nan")

    result = {
        "player": name, "stat": stat.upper(), "line": line, "side": side,
        "odds": odds, "pregame_pred": pregame_pred,
        "current": None, "proj_final": None,
        "new_edge": None, "new_prob": None, "new_ev": None,
        "action": "",   # filled in below; only "NOT PLAYING" if no snapshot match
        "game_status": "", "period": "", "clock": "",
    }

    player, snap = find_player_across_snapshots(name, snapshots)
    if player is None:
        result["action"] = "NOT PLAYING"
        return result

    period = int(snap.get("period") or 0)
    clock_str = snap.get("clock") or "0:00"
    result["period"] = period
    result["clock"] = clock_str
    result["game_status"] = snap.get("game_status", "")

    try:
        current = float(player.get(stat, 0) or 0)
    except (TypeError, ValueError):
        current = 0.0
    result["current"] = current

    is_game_final = is_final(snap)
    if is_game_final:
        proj_final = current
    else:
        clock_min = live_parse_clock(clock_str)
        try:
            pf = float(player.get("pf", 0) or 0)
        except (TypeError, ValueError):
            pf = 0.0
        # Use the projector's foul-trouble adjustment; blowout/pace stay neutral
        # so this script doesn't bake in roster-specific assumptions.
        foul_factor = pig.foul_trouble_factor(pf, period)
        proj_final = pig.project_final(
            current_stat=current,
            period=period,
            clock_remaining_min=clock_min,
            foul_factor=foul_factor,
        )

    result["proj_final"] = proj_final

    # Hit-prob + EV
    sigma = remaining_sigma(stat, period, clock_str)
    # FINAL games collapse sigma to baseline*0.1 floor since the result is
    # fully realized — but for math consistency we still compute EV.
    prob = hit_probability(proj_final, line, side, sigma)
    payout = american_payout(odds, 1.0)
    ev = prob * payout - (1.0 - prob) * 1.0
    if side.upper() == "OVER":
        edge = proj_final - line
    else:
        edge = line - proj_final
    result["new_prob"] = prob
    result["new_ev"] = ev
    result["new_edge"] = edge

    if is_game_final:
        # At FINAL, we know the answer. Classify by realized side vs bet side.
        if proj_final > line + 1e-9:
            actual_side_won = "OVER"
        elif proj_final < line - 1e-9:
            actual_side_won = "UNDER"
        else:
            actual_side_won = "PUSH"
        if actual_side_won == "PUSH":
            result["action"] = "MONITOR"
        elif actual_side_won == side.upper():
            result["action"] = "LET IT RIDE"
        else:
            result["action"] = "HEDGE"
        result["game_status"] = f"FINAL ({actual_side_won})"
    else:
        result["action"] = classify_action(ev)

    return result


# ── orchestration ────────────────────────────────────────────────────────────

def evaluate_all(bets: List[dict], snapshots: List[dict]) -> List[dict]:
    """Run evaluate_bet on every row and preserve input order."""
    return [evaluate_bet(b, snapshots) for b in bets]


def write_updated_csv(out_path: str, results: List[dict]) -> int:
    """Write evaluations back to CSV — same row count as input bet log.

    Schema:
        player, stat, line, side, odds, pregame_pred, current,
        proj_final, new_edge, new_prob, new_ev, action,
        game_status, period, clock
    """
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    cols = ["player", "stat", "line", "side", "odds", "pregame_pred",
            "current", "proj_final", "new_edge", "new_prob", "new_ev",
            "action", "game_status", "period", "clock"]
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in results:
            w.writerow([r.get(c) if r.get(c) is not None else "" for c in cols])
    return len(results)


def format_stdout(results: List[dict], refresh_ts: str) -> str:
    """Render the evaluation table as a multi-line stdout report."""
    lines: List[str] = []
    lines.append(f"\n== Live edge update (last refresh: {refresh_ts}) ==")
    lines.append(
        f"  {'player':<22s} {'stat':4s} {'line':>5s} {'side':5s} "
        f"{'pre':>5s} {'cur':>4s} {'proj':>6s} "
        f"{'edge':>6s} {'prob':>5s} {'action':<12s}"
    )
    lines.append("  " + "-" * 86)
    for r in results:
        pre = f"{r['pregame_pred']:.1f}" if r.get("pregame_pred") is not None \
              and not (isinstance(r["pregame_pred"], float)
                       and math.isnan(r["pregame_pred"])) else " — "
        cur = f"{r['current']:.0f}" if r.get("current") is not None else " — "
        proj = (f"{r['proj_final']:.1f}"
                if r.get("proj_final") is not None else "  —  ")
        edge = (f"{r['new_edge']:+.1f}"
                if r.get("new_edge") is not None else "  —  ")
        prob = (f"{r['new_prob']:.2f}"
                if r.get("new_prob") is not None else " — ")
        lines.append(
            f"  {r['player'][:22]:<22s} {r['stat']:4s} {r['line']:>5.1f} "
            f"{r['side']:5s} {pre:>5s} {cur:>4s} {proj:>6s} "
            f"{edge:>6s} {prob:>5s} {r['action']:<12s}"
        )
    return "\n".join(lines) + "\n"


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None,
                    help="ISO date (default today). Resolves bet-log to "
                         "data/bets/<date>.csv when --bet-log is omitted.")
    ap.add_argument("--bet-log", default=None,
                    help="Explicit bet log path (default data/bets/<date>.csv)")
    ap.add_argument("--snapshots", default=None,
                    help="Live snapshot directory (default data/live/)")
    ap.add_argument("--action", default=None, choices=[a for a in ACTIONS],
                    help="Filter stdout to one action (e.g. HEDGE)")
    ap.add_argument("--save", nargs="?", const="__default__", default=None,
                    help="Write updated CSV. Bare flag → data/bets/<date>_live.csv.")
    args = ap.parse_args(argv)

    date_str = args.date or _date.today().isoformat()
    bet_path = args.bet_log or default_bet_log_path(date_str)
    snap_dir = args.snapshots or LIVE_DIR

    bets = load_bet_log(bet_path)
    if not bets:
        print(f"[fail] no bets loaded from {bet_path}")
        return 2

    snap_paths = list_latest_snapshots(snap_dir)
    snapshots = [load_live_state(p) for p in snap_paths]
    snapshots = [s for s in snapshots if s]

    results = evaluate_all(bets, snapshots)

    if args.action:
        flt = args.action.upper()
        # 'NOT PLAYING' filter matches both "not playing tonight" and "NOT PLAYING"
        results = [r for r in results
                   if (r.get("action") or "").upper() == flt]

    refresh = datetime.now().isoformat(timespec="seconds")
    print(format_stdout(results, refresh))

    if args.save is not None:
        out_path = (os.path.join(BET_DIR, f"{date_str}_live.csv")
                    if args.save == "__default__" else args.save)
        n = write_updated_csv(out_path, results)
        print(f"  Wrote {n} updated bet row(s) -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
