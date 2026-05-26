"""recover_line_killed.py — R21_N2 line_killed bet recovery tool.

Recovery flow for bets that got killed when the line moved or vanished
(typically by `scripts/nba_lineup_daemon.py`'s `mark_killed_in_ledger`).
These bets sit in limbo: never settled, never refunded, never re-attempted.

Modes (CLI):
    --list                          List all line_killed bets with details.
    --refund <bet_id>               Mark a single bet refunded (idempotent).
    --refund-all                    Refund every line_killed bet older than
                                    --min-age-hours (default 24).
                                    Dry-run by default; pass --commit to write.
    --reprice <bet_id>              Look up the current line for the (player,
                                    stat) combo across data/lines/<today>_*.csv
                                    snapshots; suggest a place_bet command if
                                    a fresh line at the same threshold exists.

Optional:
    --ledger <path>                 Override path to pnl_ledger.csv.
    --bankroll <path>               Override path to pnl_bankroll.csv.
    --lines-dir <path>              Override path to data/lines snapshot dir.
    --min-age-hours <int>           --refund-all age floor (default 24).
    --commit                        --refund-all: actually write (else dry-run).
    --today <YYYY-MM-DD>            --reprice: override "today" date.

Outputs are plain-text + JSON-ish blocks suitable for piping. Every write
goes through an atomic tmpfile+os.replace (same convention as pnl_ledger).
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

DEFAULT_LEDGER = os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv")
DEFAULT_BANKROLL = os.path.join(PROJECT_DIR, "data", "pnl_bankroll.csv")
DEFAULT_LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")

BANKROLL_COLS = ["timestamp", "amount", "running_balance", "note"]


# --------------------------------------------------------------------------- #
# IO helpers — file-local copies so the script never imports pnl_ledger and   #
# can therefore be unit-tested against arbitrary fixture paths cleanly.       #
# --------------------------------------------------------------------------- #
def _load_ledger(path: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """Return (rows, fieldnames). Empty list + [] if file missing."""
    if not os.path.exists(path):
        return [], []
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    return rows, fields


def _atomic_write_rows(path: str, fieldnames: List[str], rows: List[Dict]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}.{int(time.time() * 1e6)}"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)


def _read_bankroll_balance(bankroll_path: str) -> float:
    if not os.path.exists(bankroll_path):
        return 0.0
    try:
        with open(bankroll_path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            return 0.0
        return float(rows[-1].get("running_balance", "0") or 0.0)
    except (OSError, ValueError, KeyError):
        return 0.0


def _append_bankroll(bankroll_path: str, amount: float, note: str,
                     running: float) -> None:
    parent = os.path.dirname(bankroll_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    new_file = (not os.path.exists(bankroll_path)
                or os.path.getsize(bankroll_path) == 0)
    with open(bankroll_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(BANKROLL_COLS)
        w.writerow([
            datetime.now().isoformat(timespec="seconds"),
            f"{float(amount):.2f}",
            f"{float(running):.2f}",
            note,
        ])


# --------------------------------------------------------------------------- #
# Public helpers — re-exported for tests.                                     #
# --------------------------------------------------------------------------- #
def find_line_killed(ledger_path: str) -> List[Dict[str, str]]:
    """Return rows whose status (case-insensitive) == 'line_killed'."""
    rows, _ = _load_ledger(ledger_path)
    out = []
    for r in rows:
        if (r.get("status") or "").strip().lower() == "line_killed":
            out.append(r)
    return out


def _parse_placed_at(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        # tolerate Z suffix
        s = value.replace("Z", "+00:00") if value.endswith("Z") else value
        dt = datetime.fromisoformat(s)
        # strip tz for naive comparison
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _age_hours(row: Dict[str, str], now: Optional[datetime] = None) -> Optional[float]:
    placed = _parse_placed_at(row.get("placed_at", ""))
    if placed is None:
        return None
    base = now or datetime.now()
    return (base - placed).total_seconds() / 3600.0


def is_real_bet(row: Dict[str, str]) -> bool:
    """A 'real' bet has a non-synthetic player name (not 'Player_<digits>')."""
    p = (row.get("player") or "").strip()
    if not p:
        return False
    if p.startswith("Player_") and p[7:].isdigit():
        return False
    return True


def refund_bet(bet_id: str, ledger_path: str,
               bankroll_path: str) -> Dict[str, object]:
    """Flip a single line_killed bet to status=refunded.

    Idempotent: if the bet is already refunded, returns no-op.
    Returns {"changed": bool, "bet_id": str, "status": str, "credit": float,
             "bankroll_after": float, "reason": str}.
    """
    rows, fields = _load_ledger(ledger_path)
    if not fields:
        return {"changed": False, "bet_id": bet_id, "status": "missing",
                "credit": 0.0, "bankroll_after": 0.0,
                "reason": "ledger_missing_or_empty"}
    target = next((r for r in rows if r.get("bet_id") == bet_id), None)
    if target is None:
        return {"changed": False, "bet_id": bet_id, "status": "missing",
                "credit": 0.0, "bankroll_after": 0.0,
                "reason": "bet_id_not_found"}
    status = (target.get("status") or "").strip().lower()
    if status == "refunded":
        return {"changed": False, "bet_id": bet_id, "status": "refunded",
                "credit": 0.0,
                "bankroll_after": _read_bankroll_balance(bankroll_path),
                "reason": "already_refunded"}
    if status != "line_killed":
        return {"changed": False, "bet_id": bet_id, "status": status,
                "credit": 0.0,
                "bankroll_after": _read_bankroll_balance(bankroll_path),
                "reason": f"not_line_killed_status_is_{status}"}

    try:
        stake = float(target.get("stake") or 0.0)
    except ValueError:
        stake = 0.0
    new_bal = _read_bankroll_balance(bankroll_path) + stake

    target["status"] = "refunded"
    target["settled_at"] = datetime.now().isoformat(timespec="seconds")
    target["profit_loss"] = "0.00"
    target["bankroll_after"] = f"{new_bal:.2f}"
    _atomic_write_rows(ledger_path, fields, rows)
    _append_bankroll(bankroll_path, stake,
                     f"refund:{bet_id[:8]}", new_bal)

    return {"changed": True, "bet_id": bet_id, "status": "refunded",
            "credit": stake, "bankroll_after": new_bal,
            "reason": "refunded"}


def refund_all(ledger_path: str, bankroll_path: str,
               min_age_hours: float = 24.0, commit: bool = False,
               now: Optional[datetime] = None) -> Dict[str, object]:
    """Refund every line_killed bet older than min_age_hours.

    Dry-run by default. With commit=True, applies refund_bet() to each in turn.
    """
    killed = find_line_killed(ledger_path)
    eligible = []
    for r in killed:
        age = _age_hours(r, now=now)
        if age is None or age >= min_age_hours:
            eligible.append({
                "bet_id": r.get("bet_id", ""),
                "player": r.get("player", ""),
                "stat": r.get("stat", ""),
                "line": r.get("line", ""),
                "side": r.get("side", ""),
                "stake": r.get("stake", ""),
                "age_hours": None if age is None else round(age, 2),
            })

    if not commit:
        return {"dry_run": True, "n_killed": len(killed),
                "n_eligible": len(eligible), "eligible": eligible,
                "refunded": []}

    refunded = []
    for item in eligible:
        res = refund_bet(item["bet_id"], ledger_path, bankroll_path)
        refunded.append(res)
    return {"dry_run": False, "n_killed": len(killed),
            "n_eligible": len(eligible), "eligible": eligible,
            "refunded": refunded}


def _today_str(today: Optional[str]) -> str:
    if today:
        return today
    return datetime.now().strftime("%Y-%m-%d")


def lookup_current_line(player: str, stat: str, line: float,
                        lines_dir: str, today: Optional[str] = None
                        ) -> List[Dict[str, object]]:
    """Scan data/lines/<today>_*.csv for a matching (player, stat) row.

    Returns list of {book, line, over_price, under_price, captured_at, match}
    where match is "exact_threshold" (same line) or "different_threshold".
    """
    today = _today_str(today)
    pattern = os.path.join(lines_dir, f"{today}_*.csv")
    out: List[Dict[str, object]] = []
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    if (r.get("player_name") or "").strip().lower() != \
                            player.strip().lower():
                        continue
                    if (r.get("stat") or "").strip().lower() != \
                            stat.strip().lower():
                        continue
                    try:
                        snap_line = float(r.get("line") or 0.0)
                    except ValueError:
                        continue
                    match = ("exact_threshold"
                             if abs(snap_line - float(line)) < 1e-6
                             else "different_threshold")
                    out.append({
                        "book": r.get("book", ""),
                        "line": snap_line,
                        "over_price": r.get("over_price", ""),
                        "under_price": r.get("under_price", ""),
                        "captured_at": r.get("captured_at", ""),
                        "source_file": os.path.basename(path),
                        "match": match,
                    })
        except OSError:
            continue
    return out


def reprice_bet(bet_id: str, ledger_path: str, lines_dir: str,
                today: Optional[str] = None) -> Dict[str, object]:
    """Find a fresh line for the killed bet and suggest a re-place command."""
    rows, _ = _load_ledger(ledger_path)
    target = next((r for r in rows if r.get("bet_id") == bet_id), None)
    if target is None:
        return {"found_target": False, "reason": "bet_id_not_found",
                "bet_id": bet_id}
    status = (target.get("status") or "").strip().lower()
    if status != "line_killed":
        return {"found_target": True, "bet_id": bet_id,
                "status": status,
                "reason": f"not_line_killed_status_is_{status}",
                "matches": [], "exact_matches": [],
                "place_bet_commands": []}

    player = target.get("player", "")
    stat = target.get("stat", "")
    side = (target.get("side") or "").upper()
    try:
        line = float(target.get("line") or 0.0)
    except ValueError:
        line = 0.0
    try:
        stake = float(target.get("stake") or 0.0)
    except ValueError:
        stake = 0.0

    matches = lookup_current_line(player, stat, line, lines_dir, today=today)
    exact = [m for m in matches if m["match"] == "exact_threshold"]

    commands: List[str] = []
    for m in exact:
        odds_field = ("over_price" if side == "OVER" else "under_price")
        odds = str(m.get(odds_field) or "").strip()
        if not odds:
            continue
        # Format: python scripts/place_bet.py --player ... --stat ...
        cmd = (
            f'python scripts/place_bet.py --player "{player}" '
            f'--stat {stat} --side {side} --line {line} '
            f'--book {m["book"]} --odds {odds} --stake {stake:.2f}'
        )
        commands.append(cmd)

    return {
        "found_target": True,
        "bet_id": bet_id,
        "status": "line_killed",
        "player": player, "stat": stat, "line": line, "side": side,
        "stake": stake,
        "n_matches": len(matches),
        "n_exact_matches": len(exact),
        "matches": matches,
        "exact_matches": exact,
        "place_bet_commands": commands,
    }


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #
def _format_listing(killed: List[Dict[str, str]],
                    now: Optional[datetime] = None) -> str:
    if not killed:
        return "No line_killed bets found."
    lines = []
    lines.append(f"Found {len(killed)} line_killed bet(s):")
    lines.append("")
    n_real = sum(1 for r in killed if is_real_bet(r))
    n_synth = len(killed) - n_real
    lines.append(f"  real (non-synthetic): {n_real}")
    lines.append(f"  synthetic:            {n_synth}")
    lines.append("")
    header = ("bet_id (short) | placed_at | player | stat | line | side | "
              "book | stake | age_hours | synthetic?")
    lines.append(header)
    lines.append("-" * len(header))
    for r in killed:
        age = _age_hours(r, now=now)
        age_s = "?" if age is None else f"{age:.1f}"
        synth = "synth" if not is_real_bet(r) else "real"
        bet_id = (r.get("bet_id") or "")[:8]
        lines.append(f"{bet_id:>8} | {r.get('placed_at','')} | "
                     f"{r.get('player',''):<24} | {r.get('stat',''):<5} | "
                     f"{r.get('line',''):>5} | {r.get('side',''):<5} | "
                     f"{r.get('book',''):<6} | {r.get('stake',''):>6} | "
                     f"{age_s:>5} | {synth}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Recovery tool for line_killed bets in pnl_ledger.csv.",
    )
    p.add_argument("--ledger", default=DEFAULT_LEDGER,
                   help="path to pnl_ledger.csv")
    p.add_argument("--bankroll", default=DEFAULT_BANKROLL,
                   help="path to pnl_bankroll.csv")
    p.add_argument("--lines-dir", default=DEFAULT_LINES_DIR,
                   help="path to data/lines directory")
    p.add_argument("--today", default=None,
                   help="override 'today' date (YYYY-MM-DD) for --reprice")
    p.add_argument("--min-age-hours", type=float, default=24.0,
                   help="--refund-all age floor in hours (default 24)")
    p.add_argument("--commit", action="store_true",
                   help="--refund-all: actually write (default dry-run)")
    p.add_argument("--json", dest="emit_json", action="store_true",
                   help="emit JSON instead of human-readable text")

    mx = p.add_mutually_exclusive_group(required=True)
    mx.add_argument("--list", dest="do_list", action="store_true",
                    help="list all line_killed bets")
    mx.add_argument("--refund", dest="refund_id", metavar="BET_ID",
                    help="refund a single line_killed bet by id")
    mx.add_argument("--refund-all", dest="do_refund_all", action="store_true",
                    help="refund every eligible line_killed bet")
    mx.add_argument("--reprice", dest="reprice_id", metavar="BET_ID",
                    help="look up a fresh line for a killed bet")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.do_list:
        killed = find_line_killed(args.ledger)
        if args.emit_json:
            payload = {
                "n_killed": len(killed),
                "n_real": sum(1 for r in killed if is_real_bet(r)),
                "n_synth": sum(1 for r in killed if not is_real_bet(r)),
                "rows": killed,
            }
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(_format_listing(killed))
        return 0

    if args.refund_id:
        res = refund_bet(args.refund_id, args.ledger, args.bankroll)
        if args.emit_json:
            print(json.dumps(res, indent=2, default=str))
        else:
            verb = "REFUNDED" if res["changed"] else "NO-OP"
            print(f"{verb}: bet_id={res['bet_id']} "
                  f"status={res['status']} credit={res['credit']:.2f} "
                  f"bankroll_after={res['bankroll_after']:.2f} "
                  f"({res['reason']})")
        return 0 if res.get("status") in {"refunded"} else \
            (0 if res.get("reason") == "already_refunded" else 1)

    if args.do_refund_all:
        res = refund_all(args.ledger, args.bankroll,
                         min_age_hours=args.min_age_hours,
                         commit=args.commit)
        if args.emit_json:
            print(json.dumps(res, indent=2, default=str))
        else:
            mode = "COMMIT" if not res["dry_run"] else "DRY-RUN"
            print(f"[{mode}] n_killed={res['n_killed']} "
                  f"n_eligible={res['n_eligible']} "
                  f"(age>={args.min_age_hours}h)")
            for item in res["eligible"]:
                print(f"  - {item['bet_id'][:8]} {item['player']:<24} "
                      f"{item['stat']:<5} {item['side']:<5} "
                      f"line={item['line']} stake={item['stake']} "
                      f"age={item['age_hours']}h")
            if res["refunded"]:
                n_changed = sum(1 for r in res["refunded"] if r["changed"])
                print(f"  applied: {n_changed}/{len(res['refunded'])} refunds")
        return 0

    if args.reprice_id:
        res = reprice_bet(args.reprice_id, args.ledger, args.lines_dir,
                          today=args.today)
        if args.emit_json:
            print(json.dumps(res, indent=2, default=str))
        else:
            if not res.get("found_target"):
                print(f"NOT FOUND: bet_id={args.reprice_id} "
                      f"({res.get('reason','?')})")
                return 1
            if res.get("status") != "line_killed":
                print(f"SKIP: bet_id={args.reprice_id} "
                      f"status={res['status']} ({res.get('reason','?')})")
                return 0
            print(f"REPRICE: {res['player']} {res['stat']} {res['side']} "
                  f"{res['line']} stake={res['stake']}")
            print(f"  matches: {res['n_matches']} "
                  f"(exact_threshold: {res['n_exact_matches']})")
            for m in res["matches"]:
                print(f"  - {m['source_file']} book={m['book']} "
                      f"line={m['line']} over={m['over_price']} "
                      f"under={m['under_price']} ({m['match']})")
            if res["place_bet_commands"]:
                print("  suggested re-place commands:")
                for c in res["place_bet_commands"]:
                    print(f"    {c}")
            else:
                print("  no actionable exact-threshold match for this side.")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
