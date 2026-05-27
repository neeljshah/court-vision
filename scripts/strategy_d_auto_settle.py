"""strategy_d_auto_settle.py — auto-grade Strategy D dry-run ledgers.

Companion to scripts/strategy_d_daily_runner.py (iter-12). That runner writes
per-game ledgers at data/bets/strategy_d_<date>.csv with status="dry-run-pending".
This script closes the loop: for each pending row, look up the player's actual
stat in the final NBA box score and update the row with WIN/LOSS/PUSH + profit.

Box-source priority (mirrors src/prediction/settlement.fetch_final_boxscore +
scripts/settle_bets.sum_quarter_box):
    1. data/cache/quarter_box/<gid>_q1..q4.json  (free, offline, R16_E7 cache)
    2. cdn.nba.com finals box  (free, public, ~1 req/game, no auth)
    3. data/nba/player_gamelog_<pid>.json        (per-player fallback)

Usage:
    python scripts/strategy_d_auto_settle.py --date 2026-05-27
    python scripts/strategy_d_auto_settle.py --summary-all

Does NOT call NBA stats `boxscoretraditionalv2` (rate-limited / flaky); the CDN
finals box covers the same data with no auth, and the local quarter_box cache
covers historical games for free. Does NOT modify production scripts.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
import unicodedata
from datetime import datetime, date as _date
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# UTF-8 stdout (Wemby, Dončić, etc.)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

# Reuse the existing settlement helpers — DO NOT reimplement.
from src.prediction.settlement import fetch_final_boxscore  # noqa: E402
from src.betting.pnl_ledger import american_to_payout, _resolve_status  # noqa: E402
from scripts.settle_bets import sum_quarter_box, is_game_final  # noqa: E402

BETS_DIR = os.path.join(PROJECT_DIR, "data", "bets")
QB_DIR = os.path.join(PROJECT_DIR, "data", "cache", "quarter_box")
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")

# Settled ledger keeps the original columns and appends grading info.
EXTRA_COLS = ["actual_value", "profit", "running_pnl",
              "updated_at", "last_settle_attempt"]


# --------------------------------------------------------------------------- #
# String normalization (mirrors scripts/settle_bets._player_key)              #
# --------------------------------------------------------------------------- #
def _player_key(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower().strip()


# --------------------------------------------------------------------------- #
# Box-score lookup (3 fallback sources)                                        #
# --------------------------------------------------------------------------- #
def lookup_actual(game_id: str, player_name: str, stat: str,
                  use_cdn: bool = True) -> Tuple[Optional[float], str]:
    """Return (actual_value, source) or (None, source_tried_last).

    Source order: quarter_box -> cdn.nba.com -> player_gamelog json.
    """
    stat = stat.lower().strip()
    pkey = _player_key(player_name)

    # 1. quarter_box (offline, instant)
    if game_id and is_game_final(game_id, QB_DIR):
        totals = sum_quarter_box(game_id, QB_DIR)
        for nm, row in totals.items():
            if _player_key(nm) == pkey:
                v = row.get(stat)
                if v is not None:
                    return float(v), "quarter_box"

    # 2. cdn.nba.com finals box (network; respects "1/sec" by single call)
    if use_cdn and game_id:
        finals = fetch_final_boxscore(game_id)
        if finals:
            # finals is keyed by (player_id, stat) — we don't have player_id,
            # so re-fetch raw to extract the name -> stat map. Simpler: parse
            # the same endpoint via fetch_final_boxscore by also keeping name.
            actual = _cdn_by_name(game_id, pkey, stat)
            if actual is not None:
                return actual, "cdn_finals"

    # 3. per-player gamelog
    pid_guess = _find_player_gamelog(pkey)
    if pid_guess:
        v = _gamelog_stat(pid_guess, game_id, stat)
        if v is not None:
            return v, f"gamelog:{pid_guess}"

    return None, "none"


def _cdn_by_name(game_id: str, pkey: str, stat: str) -> Optional[float]:
    """Re-fetch CDN finals JSON to match player by NAME (not id). Returns float or None."""
    from src.prediction.settlement import _fetch_json, _CDN_URL, _STAT_MAP
    data = _fetch_json(_CDN_URL.format(game_id=game_id))
    if data is None:
        return None
    game = data.get("game", {})
    if int(game.get("gameStatus", 0)) != 3:
        return None
    cdn_key = _STAT_MAP.get(stat)
    if not cdn_key:
        return None
    for side_key in ("homeTeam", "awayTeam"):
        for p in game.get(side_key, {}).get("players", []):
            name = f"{p.get('firstName', '')} {p.get('familyName', '')}".strip()
            if _player_key(name) == pkey:
                v = p.get("statistics", {}).get(cdn_key)
                if v is not None:
                    return float(v)
    return None


def _find_player_gamelog(pkey: str) -> Optional[str]:
    """Scan data/nba/player_gamelog_*.json filenames for one whose contents match."""
    if not os.path.isdir(GAMELOG_DIR):
        return None
    for p in glob.glob(os.path.join(GAMELOG_DIR, "player_gamelog_*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = d.get("player_name") or d.get("name") or ""
        if name and _player_key(name) == pkey:
            stem = os.path.basename(p)
            pid = stem.replace("player_gamelog_", "").replace(".json", "")
            return pid
    return None


def _gamelog_stat(player_id: str, game_id: str,
                  stat: str) -> Optional[float]:
    """Pull actual stat for player_id in game_id from cached gamelog JSON."""
    path = os.path.join(GAMELOG_DIR, f"player_gamelog_{player_id}.json")
    if not os.path.exists(path):
        return None
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    games = d.get("games", []) or d.get("resultSets", [{}])[0].get("rowSet", [])
    field_map = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M",
                 "stl": "STL", "blk": "BLK", "tov": "TOV"}
    for g in games:
        if isinstance(g, dict):
            if str(g.get("game_id") or g.get("GAME_ID") or "") == str(game_id):
                v = g.get(stat) or g.get(field_map.get(stat, stat).upper())
                if v is not None:
                    return float(v)
    return None


# --------------------------------------------------------------------------- #
# Ledger I/O                                                                  #
# --------------------------------------------------------------------------- #
def _load_ledger(path: str) -> Tuple[List[str], List[Dict]]:
    with open(path, encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        cols = list(rdr.fieldnames or [])
        rows = list(rdr)
    return cols, rows


def _write_ledger(path: str, cols: List[str], rows: List[Dict]) -> None:
    for c in EXTRA_COLS:
        if c not in cols:
            cols.append(c)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            for c in cols:
                r.setdefault(c, "")
            w.writerow(r)


# --------------------------------------------------------------------------- #
# Settlement (single ledger)                                                  #
# --------------------------------------------------------------------------- #
def settle_ledger(path: str, use_cdn: bool = True) -> Dict:
    """Grade every dry-run-pending row in `path`. Returns counters dict."""
    if not os.path.exists(path):
        return {"date": "", "settled": 0, "win": 0, "loss": 0, "push": 0,
                "pending": 0, "total": 0, "pnl": 0.0, "lines_won": [],
                "lines_pending": []}

    cols, rows = _load_ledger(path)
    now_iso = datetime.now().isoformat(timespec="seconds")
    counters = {"win": 0, "loss": 0, "push": 0, "pending": 0,
                "settled_this_run": 0, "pnl": 0.0,
                "lines_won": [], "lines_lost": [], "lines_pending": []}

    # Running PnL = sum of profit on all WIN/LOSS/PUSH rows after this update.
    running = 0.0

    for r in rows:
        status = (r.get("status") or "").lower()
        if status in ("win", "loss", "push", "won", "lost", "pushed"):
            # Already settled — recompute running balance contribution.
            try:
                running += float(r.get("profit") or 0.0)
            except ValueError:
                pass
            if status in ("win", "won"):
                counters["win"] += 1
            elif status in ("loss", "lost"):
                counters["loss"] += 1
            else:
                counters["push"] += 1
            r["running_pnl"] = f"{running:.4f}"
            continue

        if status != "dry-run-pending":
            continue

        game_id = (r.get("game_id") or "").strip()
        player = (r.get("player") or "").strip()
        stat = (r.get("stat") or "").strip().lower()
        try:
            line = float(r.get("line") or 0.0)
            odds = int(float(r.get("odds") or -110))
            stake = float(r.get("stake") or 0.0)
        except (ValueError, TypeError):
            counters["pending"] += 1
            r["last_settle_attempt"] = now_iso
            continue
        side = (r.get("side") or "").strip().upper()

        actual, source = lookup_actual(game_id, player, stat, use_cdn=use_cdn)
        if actual is None:
            counters["pending"] += 1
            r["last_settle_attempt"] = now_iso
            descr = (f"{player} {stat.upper()} {side[0]} {line:g} "
                     f"({odds:+d}) — no box yet")
            counters["lines_pending"].append(descr)
            continue

        result = _resolve_status(line, side, actual)  # won / lost / push
        if result == "won":
            profit = round(stake * american_to_payout(odds), 4)
            counters["win"] += 1
            counters["lines_won"].append(
                f"{player} {stat.upper()} {side[0]} {line:g}")
        elif result == "lost":
            profit = round(-stake, 4)
            counters["loss"] += 1
            counters["lines_lost"].append(
                f"{player} {stat.upper()} {side[0]} {line:g}")
        else:
            profit = 0.0
            counters["push"] += 1

        running += profit
        counters["settled_this_run"] += 1
        counters["pnl"] += profit

        r["status"] = {"won": "WIN", "lost": "LOSS",
                       "push": "PUSH"}[result]
        r["actual_value"] = f"{actual:g}"
        r["profit"] = f"{profit:+.4f}"
        r["running_pnl"] = f"{running:.4f}"
        r["updated_at"] = now_iso
        r["last_settle_attempt"] = now_iso

    _write_ledger(path, cols, rows)
    counters["total"] = len(rows)
    return counters


# --------------------------------------------------------------------------- #
# Per-day printer                                                             #
# --------------------------------------------------------------------------- #
def print_settle_report(date_str: str, c: Dict) -> None:
    header = f"Strategy D Settlement - {date_str}"
    print("\n" + header)
    print("=" * len(header))
    n_settle = c["settled_this_run"]
    n_total = c["total"]
    settled_all = c["win"] + c["loss"] + c["push"]
    print(f"Settled: {settled_all} of {n_total} bets "
          f"({n_settle} graded this run)")
    if c["lines_won"]:
        wons = ", ".join(c["lines_won"][:6])
        print(f"WIN:  {c['win']} ({wons})")
    else:
        print(f"WIN:  {c['win']}")
    if c["lines_lost"]:
        losts = ", ".join(c["lines_lost"][:6])
        print(f"LOSS: {c['loss']} ({losts})")
    else:
        print(f"LOSS: {c['loss']}")
    print(f"PUSH: {c['push']}")
    if c["lines_pending"]:
        pend = c["lines_pending"][0]
        rest = (f" +{len(c['lines_pending']) - 1} more"
                if len(c["lines_pending"]) > 1 else "")
        print(f"PENDING: {c['pending']} ({pend}{rest})")
    else:
        print(f"PENDING: {c['pending']}")
    print("------")
    print(f"Daily PnL: ${c['pnl']:+,.2f}")


# --------------------------------------------------------------------------- #
# Cumulative summary across every strategy_d_*.csv                            #
# --------------------------------------------------------------------------- #
def summary_all() -> None:
    paths = sorted(glob.glob(os.path.join(BETS_DIR, "strategy_d_*.csv")))
    if not paths:
        print("  [summary-all] no strategy_d_*.csv ledgers in data/bets/")
        return
    tot = {"win": 0, "loss": 0, "push": 0, "pending": 0,
           "bets": 0, "pnl": 0.0, "staked": 0.0}
    per_stat = {s: {"win": 0, "loss": 0, "push": 0, "pending": 0,
                    "pnl": 0.0, "staked": 0.0}
                for s in ("blk", "fg3m", "stl")}
    for p in paths:
        _, rows = _load_ledger(p)
        for r in rows:
            tot["bets"] += 1
            try:
                stake = float(r.get("stake") or 0)
                profit = float(r.get("profit") or 0)
            except ValueError:
                stake = 0.0
                profit = 0.0
            stat = (r.get("stat") or "").lower()
            status = (r.get("status") or "").lower()
            bucket = per_stat.get(stat)
            if status in ("win", "won"):
                tot["win"] += 1
                tot["pnl"] += profit
                tot["staked"] += stake
                if bucket:
                    bucket["win"] += 1; bucket["pnl"] += profit
                    bucket["staked"] += stake
            elif status in ("loss", "lost"):
                tot["loss"] += 1
                tot["pnl"] += profit
                tot["staked"] += stake
                if bucket:
                    bucket["loss"] += 1; bucket["pnl"] += profit
                    bucket["staked"] += stake
            elif status in ("push", "pushed"):
                tot["push"] += 1
                tot["staked"] += stake
                if bucket:
                    bucket["push"] += 1; bucket["staked"] += stake
            else:
                tot["pending"] += 1
                if bucket:
                    bucket["pending"] += 1
    settled = tot["win"] + tot["loss"] + tot["push"]
    roi = (tot["pnl"] / tot["staked"] * 100.0) if tot["staked"] else 0.0
    hit = (tot["win"] / settled * 100.0) if settled else 0.0
    print("\n  Strategy D - cumulative summary across all ledgers")
    print("  " + "=" * 50)
    print(f"  Ledgers scanned : {len(paths)}")
    print(f"  Total bets      : {tot['bets']}")
    print(f"  Settled         : {settled}  (WIN {tot['win']} / "
          f"LOSS {tot['loss']} / PUSH {tot['push']})")
    print(f"  Pending         : {tot['pending']}")
    print(f"  Hit rate        : {hit:.1f}% (settled only)")
    print(f"  Staked          : ${tot['staked']:,.2f}")
    print(f"  Cumulative PnL  : ${tot['pnl']:+,.2f}")
    print(f"  ROI             : {roi:+.2f}%")
    print("  ---- by stat ----")
    for s, b in per_stat.items():
        sset = b["win"] + b["loss"] + b["push"]
        sroi = (b["pnl"] / b["staked"] * 100.0) if b["staked"] else 0.0
        print(f"  {s.upper():<5} W{b['win']:>2} L{b['loss']:>2} P{b['push']:>1} "
              f"pend{b['pending']:>2}  pnl ${b['pnl']:>+9,.2f}  ROI {sroi:>+7.2f}%")


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Auto-settle Strategy D daily ledger against final box scores.",
    )
    ap.add_argument("--date", default=None,
                    help="Date YYYY-MM-DD (default: today)")
    ap.add_argument("--no-cdn", action="store_true",
                    help="Skip cdn.nba.com fetch; use only local caches")
    ap.add_argument("--summary-all", action="store_true",
                    help="Print cumulative summary across all strategy_d_*.csv and exit")
    args = ap.parse_args(argv)

    if args.summary_all:
        summary_all()
        return 0

    date_str = args.date or _date.today().isoformat()
    path = os.path.join(BETS_DIR, f"strategy_d_{date_str}.csv")
    if not os.path.exists(path):
        print(f"[fail] no ledger at {path}")
        return 1

    counters = settle_ledger(path, use_cdn=not args.no_cdn)
    print_settle_report(date_str, counters)
    return 0


if __name__ == "__main__":
    sys.exit(main())
