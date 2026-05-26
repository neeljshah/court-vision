"""settle_bets.py - settle open bets in data/pnl_ledger.csv (probe R16_E7).

Two modes:

  (1) Quarter-box mode (R16_E7 design):
      python scripts/settle_bets.py --from-quarter-box

      Scans data/pnl_ledger.csv for open bets, then for each unique game_id
      looks for data/cache/quarter_box/<gid>_q4.json. If present, sums q1-q4
      stats per player and resolves each open bet for that game by calling
      src.betting.pnl_ledger.settle_bet(bet_id, actual_stat).

      Open bets with empty game_id can be settled by --player + date too,
      via fallback to gamelog auto-settle.

  (2) Legacy bet-log mode (cycle 68):
      python scripts/settle_bets.py data/bets/2026-05-24.csv \\
          data/actuals/2026-05-24.csv --out data/bets/2026-05-24_settled.csv

      Input bet log (timestamp,date,player,stat,line,side,model,edge,prob,
      odds,ev_per_dollar,kelly_pct,kelly_stake,bankroll) gets matched to an
      actuals CSV (date,player,stat,actual_value) and an enriched CSV is
      written. Used by the legacy compare_to_lines --bet-log flow.

Public API:
    settle(bet, actual)            -> (result, pnl)               # legacy
    settle_log(bets, actuals)      -> (enriched, summary)         # legacy
    load_actuals(path)             -> dict[(date,player,stat) -> val]
    sum_quarter_box(game_id, qb_dir=None) -> dict[player_name -> dict[stat -> val]]
    settle_from_quarter_box(qb_dir=None, dry_run=False) -> list[dict]
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
import unicodedata
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

DEFAULT_QB_DIR = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")


# --------------------------------------------------------------------------- #
# String normalization                                                        #
# --------------------------------------------------------------------------- #
def _stat_key(s: str) -> str:
    return s.strip().lower()


def _player_key(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower().strip()


# Map ledger stat names to NBA box-score field names (per-quarter JSON uses
# lowercase keys: pts, reb, ast, fg3m, stl, blk, tov -> "to").
_STAT_TO_BOX_FIELD = {
    "pts":  "pts",
    "reb":  "reb",
    "ast":  "ast",
    "fg3m": "fg3m",
    "stl":  "stl",
    "blk":  "blk",
    "tov":  "to",
}


# --------------------------------------------------------------------------- #
# Legacy bet-log API (cycle 68 surface, preserved verbatim)                   #
# --------------------------------------------------------------------------- #
def load_actuals(path: str) -> Dict[Tuple[str, str, str], float]:
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
    line = float(bet.get("line", 0.0) or 0.0)
    side = (bet.get("side", "") or "").upper()
    odds = int(bet.get("odds", -110) or -110)
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


def settle_log(
    bets: List[dict], actuals: Dict[Tuple[str, str, str], float],
) -> Tuple[List[dict], dict]:
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


# --------------------------------------------------------------------------- #
# Quarter-box settlement (R16_E7)                                             #
# --------------------------------------------------------------------------- #
def sum_quarter_box(
    game_id: str, qb_dir: Optional[str] = None,
) -> Dict[str, Dict[str, float]]:
    """Sum q1-q4 player stats for a game.

    Returns {player_name: {pts, reb, ast, fg3m, stl, blk, tov, player_id}}.
    Returns {} if any of q1-q4 is missing (game not final).
    """
    qb_dir = qb_dir or DEFAULT_QB_DIR
    totals: Dict[str, Dict[str, float]] = {}
    for q in (1, 2, 3, 4):
        p = os.path.join(qb_dir, f"{game_id}_q{q}.json")
        if not os.path.exists(p):
            return {}
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        for pl in d.get("players", []) or []:
            name = pl.get("player_name", "")
            if not name:
                continue
            row = totals.setdefault(name, {
                "pts": 0.0, "reb": 0.0, "ast": 0.0, "fg3m": 0.0,
                "stl": 0.0, "blk": 0.0, "tov": 0.0,
                "player_id": pl.get("player_id"),
                "team": pl.get("team_abbreviation"),
            })
            for ledger_stat, box_field in _STAT_TO_BOX_FIELD.items():
                v = pl.get(box_field, 0) or 0
                try:
                    row[ledger_stat] += float(v)
                except (TypeError, ValueError):
                    continue
    return totals


def is_game_final(game_id: str, qb_dir: Optional[str] = None) -> bool:
    """All four quarter_box JSON files exist on disk."""
    qb_dir = qb_dir or DEFAULT_QB_DIR
    return all(
        os.path.exists(os.path.join(qb_dir, f"{game_id}_q{q}.json"))
        for q in (1, 2, 3, 4)
    )


def settle_from_quarter_box(
    qb_dir: Optional[str] = None, dry_run: bool = False,
) -> List[Dict]:
    """Iterate open bets in data/pnl_ledger.csv, settle ones whose game is final.

    Returns list of result dicts:
        {bet_id, status, profit_loss, actual_stat, bankroll_after}  on success
        {bet_id, skipped: "<reason>"}                               on skip
    """
    from src.betting.pnl_ledger import open_bets, settle_bet
    qb_dir = qb_dir or DEFAULT_QB_DIR
    results: List[Dict] = []
    # Group open bets by game_id to amortise the quarter-box sum per game.
    open_now = open_bets()
    games: Dict[str, Dict[str, Dict[str, float]]] = {}
    for bet in open_now:
        gid = (bet.get("game_id") or "").strip()
        if not gid:
            results.append({"bet_id": bet["bet_id"],
                             "skipped": "no_game_id_in_ledger"})
            continue
        if not is_game_final(gid, qb_dir):
            results.append({"bet_id": bet["bet_id"],
                             "skipped": f"game_{gid}_not_final"})
            continue
        if gid not in games:
            games[gid] = sum_quarter_box(gid, qb_dir)
        totals = games[gid]
        # Match player by name_key, fall back to player_id when present.
        pname = bet.get("player", "")
        pkey = _player_key(pname)
        match = None
        for nm, row in totals.items():
            if _player_key(nm) == pkey:
                match = row; break
        if match is None and bet.get("player_id"):
            pid = str(bet["player_id"])
            for row in totals.values():
                if str(row.get("player_id") or "") == pid:
                    match = row; break
        if match is None:
            results.append({"bet_id": bet["bet_id"],
                             "skipped": f"player_{pname}_not_in_box"})
            continue
        stat = str(bet.get("stat", "")).lower()
        actual = match.get(stat)
        if actual is None:
            results.append({"bet_id": bet["bet_id"],
                             "skipped": f"stat_{stat}_missing"})
            continue
        if dry_run:
            results.append({"bet_id": bet["bet_id"],
                             "would_settle": True, "actual_stat": float(actual)})
            continue
        try:
            r = settle_bet(bet["bet_id"], float(actual))
            r["bet_id"] = bet["bet_id"]
            r["actual_stat"] = float(actual)
            results.append(r)
        except (KeyError, ValueError) as exc:
            results.append({"bet_id": bet["bet_id"], "error": str(exc)})
    return results


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bet_log", nargs="?", default=None,
                    help="(legacy mode) bet log CSV from compare_to_lines --bet-log")
    ap.add_argument("actuals", nargs="?", default=None,
                    help="(legacy mode) actuals CSV: date,player,stat,actual_value")
    ap.add_argument("--out", default=None,
                    help="(legacy mode) output path (default: <bet_log>_settled.csv)")
    ap.add_argument("--from-quarter-box", action="store_true",
                    help="R16_E7 mode: settle pnl_ledger.csv open bets from quarter_box JSON")
    ap.add_argument("--qb-dir", default=DEFAULT_QB_DIR,
                    help="quarter_box dir (default: data/cache/quarter_box)")
    ap.add_argument("--dry-run", action="store_true",
                    help="quarter-box mode: report what would happen, don't write ledger")
    args = ap.parse_args(argv)

    if args.from_quarter_box:
        results = settle_from_quarter_box(args.qb_dir, dry_run=args.dry_run)
        settled = [r for r in results if r.get("status")
                                            in ("won", "lost", "push")]
        would = [r for r in results if r.get("would_settle")]
        skipped = [r for r in results if "skipped" in r]
        errored = [r for r in results if "error" in r]
        print(f"== Quarter-box settlement {'(dry-run)' if args.dry_run else ''} ==")
        print(f"  settled:  {len(settled)}")
        if args.dry_run:
            print(f"  would-settle: {len(would)}")
        print(f"  skipped:  {len(skipped)}")
        print(f"  errored:  {len(errored)}")
        for r in settled[:10]:
            print(f"   - {r['bet_id'][:8]}  {r['status']:5s}  "
                  f"actual={r['actual_stat']:.2f}  pnl={r['profit_loss']:+.2f}")
        for r in would[:10]:
            print(f"   - {r['bet_id'][:8]}  would-settle actual={r['actual_stat']:.2f}")
        for r in skipped[:10]:
            print(f"   - {r['bet_id'][:8]}  SKIP {r['skipped']}")
        return 0

    # Legacy mode
    if not args.bet_log or not args.actuals:
        ap.error("legacy mode requires positional bet_log + actuals; "
                  "use --from-quarter-box for ledger mode")
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
    settled_rows, summary = settle_log(bets, actuals)
    out = args.out or args.bet_log.replace(".csv", "_settled.csv")
    n = write_settled(out, settled_rows)
    print(f"  Wrote {n} settled rows -> {out}")
    print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
