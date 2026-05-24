"""settle_bets.py — score the cycle-68 bet log against post-game actuals.

The cycle-68 --bet-log flag accumulates recommended bets to
data/bets/<date>.csv. Once games complete and you have actual stat lines
(NBA Stats API, sportsbook settlement, manual entry, etc.), this script
matches bets to actuals and computes real P&L.

Input bet log schema (cycle 68):
    timestamp, date, player, stat, line, side, model, edge, prob, odds,
    ev_per_dollar, kelly_pct, kelly_stake, bankroll

Input actuals CSV (user-supplied):
    date, player, stat, actual_value

Output bet log w/ settlement (extra columns):
    ..., actual_value, result ("W"|"L"|"P"|"NA"), payout, pnl

Summary printed to stdout:
    bets: N matched / M unmatched
    won: W / N = X%   |   ROI: Y%   |   Total P&L: $Z

Run:
    python scripts/settle_bets.py data/bets/2026-05-24.csv \\
        data/actuals/2026-05-24.csv \\
        --out data/bets/2026-05-24_settled.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Dict, List, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Stat names in bet log may be uppercase; in actuals lowercase. Normalize both.
def _stat_key(s: str) -> str:
    return s.strip().lower()


def _player_key(s: str) -> str:
    # Match the cycle-53 src/data/injuries name-key convention.
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower().strip()


def load_actuals(path: str) -> Dict[Tuple[str, str, str], float]:
    """Return {(date, player_key, stat_key): actual_value}."""
    out: Dict[Tuple[str, str, str], float] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            date = r.get("date", "").strip()
            player = _player_key(r.get("player", ""))
            stat = _stat_key(r.get("stat", ""))
            try:
                actual = float(r.get("actual_value", "nan"))
            except ValueError:
                continue
            if date and player and stat:
                out[(date, player, stat)] = actual
    return out


def _american_payout(odds: int, stake: float = 1.0) -> float:
    if odds >= 100:
        return stake * odds / 100.0
    return stake * 100.0 / abs(abs(odds) or 1)


def settle(bet: dict, actual: float) -> Tuple[str, float]:
    """Return (result, pnl) for one bet vs the actual stat value.

    result: 'W' win, 'L' loss, 'P' push (line == actual).
    pnl assumes stake of 1.0 unit (or kelly_stake if non-empty / >0).
    """
    line = float(bet.get("line", 0.0) or 0.0)
    side = (bet.get("side", "") or "").upper()
    odds = int(bet.get("odds", -110) or -110)
    # Prefer kelly_stake when present; otherwise flat $1.
    try:
        stake = float(bet.get("kelly_stake") or 0.0)
        if stake <= 0:
            stake = 1.0
    except ValueError:
        stake = 1.0

    if actual == line:
        return "P", 0.0
    won = (actual > line) if side == "OVER" else (actual < line)
    if won:
        return "W", round(_american_payout(odds, stake), 4)
    return "L", round(-stake, 4)


def settle_log(bets: List[dict], actuals: Dict[Tuple[str, str, str], float]
                 ) -> Tuple[List[dict], dict]:
    """Settle each bet; return (enriched_bets, summary_dict)."""
    out: List[dict] = []
    matched = 0; wins = 0; pushes = 0
    total_pnl = 0.0; total_stake = 0.0
    for b in bets:
        key = (b.get("date", "").strip(),
               _player_key(b.get("player", "")),
               _stat_key(b.get("stat", "")))
        actual = actuals.get(key)
        if actual is None:
            row = dict(b); row["actual_value"] = ""; row["result"] = "NA"
            row["payout"] = ""; row["pnl"] = ""
            out.append(row); continue
        result, pnl = settle(b, actual)
        try:
            stake = float(b.get("kelly_stake") or 0.0) or 1.0
        except ValueError:
            stake = 1.0
        matched += 1
        if result == "W": wins += 1
        elif result == "P": pushes += 1
        total_pnl += pnl
        total_stake += stake
        row = dict(b)
        row["actual_value"] = f"{actual:g}"
        row["result"] = result
        row["payout"] = (f"{_american_payout(int(b.get('odds', -110) or -110), stake):.4f}"
                          if result == "W" else "")
        row["pnl"] = f"{pnl:+.4f}"
        out.append(row)
    summary = {
        "total":     len(bets),
        "matched":   matched,
        "unmatched": len(bets) - matched,
        "wins":      wins,
        "pushes":    pushes,
        "losses":    matched - wins - pushes,
        "total_pnl": total_pnl,
        "total_stake": total_stake,
        "roi_pct":   (100.0 * total_pnl / total_stake) if total_stake else 0.0,
        "hit_pct":   (100.0 * wins / matched) if matched else 0.0,
    }
    return out, summary


def write_settled(out_path: str, rows: List[dict]) -> int:
    """Write settled bets to CSV. Header from first row's keys."""
    if not rows:
        return 0
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


def print_summary(s: dict) -> None:
    print("\n== Settlement summary ==")
    print(f"Bets: {s['matched']} matched / {s['unmatched']} unmatched "
          f"({s['total']} total)")
    if s["matched"]:
        print(f"Won: {s['wins']} / {s['matched']} = {s['hit_pct']:.1f}%  "
              f"(pushes: {s['pushes']})")
        print(f"ROI: {s['roi_pct']:+.2f}%   |   Total P&L: ${s['total_pnl']:+.2f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bet_log", help="bet log CSV from compare_to_lines --bet-log")
    ap.add_argument("actuals", help="actuals CSV: date,player,stat,actual_value")
    ap.add_argument("--out", default=None,
                    help="Output path (default: <bet_log>_settled.csv)")
    args = ap.parse_args()

    if not os.path.exists(args.bet_log):
        print(f"[fail] bet log not found: {args.bet_log}")
        return 1
    bets = []
    with open(args.bet_log, encoding="utf-8") as fh:
        bets = list(csv.DictReader(fh))
    if not bets:
        print("[done] bet log is empty"); return 0

    actuals = load_actuals(args.actuals)
    if not actuals:
        print(f"[warn] actuals file empty or missing: {args.actuals}")

    settled, summary = settle_log(bets, actuals)
    out = args.out or args.bet_log.replace(".csv", "_settled.csv")
    n = write_settled(out, settled)
    print(f"  Wrote {n} settled rows -> {out}")
    print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
