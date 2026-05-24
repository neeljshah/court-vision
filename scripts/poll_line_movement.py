"""poll_line_movement.py - intraday DK/FD line-movement daemon (cycle 88g, loop 5).

Why
---
Intraday line movement is the strongest single sharp-money signal. The public
moves money; sharps move lines. `fetch_dk_props.py` (cycle 59) snapshots once
per call - sharps reprice multiple times per hour. This daemon polls DK + FD
on a fixed interval, accumulates timestamped snapshots, diffs each one against
the previous, and emits a `movement_log_<date>.csv` of every change. When a
line moves >= 0.5 with no public action driving it (game-level public_bets_pct
< 60% from `src.data.action_network`) it is flagged REVERSE-LINE-MOVEMENT
(sharp steam) and printed prominently.

Pipeline per poll
-----------------
  1. `scripts.fetch_dk_props.collect_props(books)` -> live prop list.
  2. Write `data/lines/snapshots/<date>_<HHMM>.csv` (canonical schema).
  3. Load previous snapshot from same date (if any), diff by (player, stat).
  4. Append each meaningful diff to `data/lines/movement_log_<date>.csv`.
  5. Stdout: only meaningful moves (line delta >= 0.5 OR odds delta >= 10 c)
     - bold-prefix RLM moves when Action Network public_bets_pct < 60%.

CLI
---
    python scripts/poll_line_movement.py --once
    python scripts/poll_line_movement.py --daemon --interval-min 5
    python scripts/poll_line_movement.py --book draftkings --book fanduel

Sandbox note
------------
The sandbox cannot reach DK / FD live - `collect_props` returns [] when the
3-tier scraper is fully blocked. Tests inject synthetic snapshots directly
into `diff_snapshots()` and mock both `collect_props` and Action Network's
`refresh_action_network`.
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Thresholds for "meaningful" movement worth printing / RLM consideration.
_LINE_DELTA_MIN  = 0.5     # stat units
_ODDS_DELTA_MIN  = 10      # American-odds cents
_PUBLIC_RLM_MAX  = 60.0    # public_bets_pct under this -> sharp money implied

_SNAP_DIR = os.path.join(PROJECT_DIR, "data", "lines", "snapshots")
_LOG_DIR  = os.path.join(PROJECT_DIR, "data", "lines")

_FIELDS = ["timestamp", "player", "stat", "prev_line", "new_line",
           "line_delta", "prev_over_odds", "new_over_odds",
           "prev_under_odds", "new_under_odds", "move_type", "rlm"]


# ── snapshot I/O ──────────────────────────────────────────────────────────────

def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _stamp_hhmm() -> str:
    return datetime.now().strftime("%H%M")


def snapshot_path(date_str: str, hhmm: str,
                  snap_dir: str = _SNAP_DIR) -> str:
    """Path for the current poll's snapshot CSV."""
    return os.path.join(snap_dir, f"{date_str}_{hhmm}.csv")


def find_previous_snapshot(date_str: str, current_hhmm: str,
                            snap_dir: str = _SNAP_DIR) -> Optional[str]:
    """Return the most recent snapshot for date_str strictly before current_hhmm.

    Snapshots are named `<date>_<HHMM>.csv` so lexical sort == chronological
    sort within a date.
    """
    if not os.path.isdir(snap_dir):
        return None
    pat = os.path.join(snap_dir, f"{date_str}_*.csv")
    cands = sorted(glob.glob(pat))
    older = [p for p in cands
             if os.path.basename(p).split("_", 1)[1].split(".")[0] < current_hhmm]
    return older[-1] if older else None


def write_snapshot(props: List[Dict], out_path: str) -> int:
    """Write canonical-schema snapshot CSV (player,stat,line,over_odds,under_odds).

    No opp/venue join here - this is a transient snapshot, not the daily
    canonical file. `fetch_dk_props.py --out` is still the way to write the
    daily canonical line file. Returns rows written.
    """
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["player", "stat", "line", "over_odds", "under_odds"])
        for p in props:
            w.writerow([p["player"], p["stat"], f"{float(p['line']):g}",
                        int(p.get("over_odds", -110)),
                        int(p.get("under_odds", -110))])
    return len(props)


def load_snapshot(path: str) -> Dict[Tuple[str, str], dict]:
    """Return {(player_lower, stat_lower): {line, over_odds, under_odds}}."""
    out: Dict[Tuple[str, str], dict] = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                key = ((r.get("player", "") or "").lower().strip(),
                       (r.get("stat", "") or "").lower().strip())
                if not key[0] or not key[1]:
                    continue
                out[key] = {
                    "line":       float(r.get("line", "nan")),
                    "over_odds":  int(r.get("over_odds", -110)),
                    "under_odds": int(r.get("under_odds", -110)),
                }
            except (ValueError, TypeError):
                continue
    return out


# ── diffing ───────────────────────────────────────────────────────────────────

def _move_type(line_delta: float, over_delta: int, under_delta: int) -> str:
    """Classify the move:
        "line"      - line moved (with or without odds)
        "odds_only" - line same, odds shifted on either side
        "both"      - line moved AND odds shifted (combined steam signal)
    """
    line_moved = abs(line_delta) > 1e-9
    odds_moved = abs(over_delta) > 0 or abs(under_delta) > 0
    if line_moved and odds_moved:
        return "both"
    if line_moved:
        return "line"
    return "odds_only"


def diff_snapshots(prev: Dict[Tuple[str, str], dict],
                    curr: Dict[Tuple[str, str], dict],
                    timestamp: str,
                    public_pct_lookup: Optional[Dict[Tuple[str, str], float]] = None,
                    ) -> List[dict]:
    """Yield one row per (player, stat) where SOMETHING changed.

    `public_pct_lookup` is a {(player_lower, stat_lower): public_bets_pct}
    map (typically built from `src.data.action_network.refresh_action_network`).
    When a >= 0.5 line move corresponds to a public_bets_pct < 60% we mark
    rlm=True - the public isn't driving this line, sharps are.
    """
    public_pct_lookup = public_pct_lookup or {}
    out: List[dict] = []
    for key, c in curr.items():
        p = prev.get(key)
        if p is None:
            continue   # first appearance - not a "move"
        line_delta  = round(c["line"] - p["line"], 2)
        over_delta  = int(c["over_odds"])  - int(p["over_odds"])
        under_delta = int(c["under_odds"]) - int(p["under_odds"])
        if (abs(line_delta) < 1e-9 and over_delta == 0 and under_delta == 0):
            continue
        move_type = _move_type(line_delta, over_delta, under_delta)
        rlm = False
        if abs(line_delta) >= _LINE_DELTA_MIN:
            pub = public_pct_lookup.get(key)
            # No public data -> neutral 50 -> RLM by the < 60 rule. The
            # alternative (require explicit data) silently swallows every
            # interesting move in PRO-gated free-tier mode, so we lean in.
            if pub is None or pub < _PUBLIC_RLM_MAX:
                rlm = True
        out.append({
            "timestamp":       timestamp,
            "player":          key[0],
            "stat":            key[1],
            "prev_line":       f"{p['line']:g}",
            "new_line":        f"{c['line']:g}",
            "line_delta":      f"{line_delta:+g}",
            "prev_over_odds":  int(p["over_odds"]),
            "new_over_odds":   int(c["over_odds"]),
            "prev_under_odds": int(p["under_odds"]),
            "new_under_odds":  int(c["under_odds"]),
            "move_type":       move_type,
            "rlm":             "Y" if rlm else "N",
        })
    return out


def is_meaningful(row: dict) -> bool:
    """True iff move is worth printing to stdout (suppresses noise)."""
    try:
        line_delta = abs(float(row.get("line_delta", "0")))
    except (TypeError, ValueError):
        line_delta = 0.0
    over_delta = abs(int(row.get("new_over_odds", 0))
                     - int(row.get("prev_over_odds", 0)))
    under_delta = abs(int(row.get("new_under_odds", 0))
                      - int(row.get("prev_under_odds", 0)))
    return (line_delta >= _LINE_DELTA_MIN
            or over_delta >= _ODDS_DELTA_MIN
            or under_delta >= _ODDS_DELTA_MIN)


# ── movement-log writer ───────────────────────────────────────────────────────

def append_movement_log(rows: List[dict], date_str: str,
                        log_dir: str = _LOG_DIR) -> str:
    """Append rows to `data/lines/movement_log_<date>.csv`. Returns path."""
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"movement_log_{date_str}.csv")
    new_file = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in _FIELDS})
    return path


# ── Action Network lookup ─────────────────────────────────────────────────────

def build_public_lookup() -> Dict[Tuple[str, str], float]:
    """Return {(player_lower, stat_lower): public_bets_pct} from Action Network.

    Falls back to an empty dict on any failure (sandbox, network, schema). The
    diff_snapshots RLM rule then defaults missing -> treated as < 60% (sharp),
    which is the desired default for free-tier mode where prop-level public%
    is gated to PRO.
    """
    try:
        from src.data.action_network import refresh_action_network
        cache = refresh_action_network()
    except Exception as e:
        print(f"  [warn] Action Network lookup unavailable: {e}")
        return {}
    out: Dict[Tuple[str, str], float] = {}
    for key, rec in (cache or {}).items():
        try:
            player = (rec.get("player") or "").lower().strip()
            stat   = (rec.get("stat")   or "").lower().strip()
            pct    = float(rec.get("public_bets_pct", 50.0))
            if player and stat:
                out[(player, stat)] = pct
        except (TypeError, ValueError):
            continue
    return out


# ── poll orchestration ────────────────────────────────────────────────────────

def _print_diff(row: dict) -> None:
    rlm = row.get("rlm") == "Y"
    prefix = "[RLM-STEAM] " if rlm else "  "
    print(f"{prefix}{row['player']:24s} {row['stat']:4s} "
          f"{row['prev_line']:>5s} -> {row['new_line']:<5s} "
          f"({row['line_delta']})  "
          f"O {int(row['prev_over_odds']):+d}->{int(row['new_over_odds']):+d}  "
          f"U {int(row['prev_under_odds']):+d}->{int(row['new_under_odds']):+d}  "
          f"[{row['move_type']}]")


def poll_once(books: List[str], date_str: Optional[str] = None,
              snap_dir: str = _SNAP_DIR, log_dir: str = _LOG_DIR,
              fetch_fn=None, public_fn=None,
              hhmm: Optional[str] = None) -> Tuple[str, List[dict]]:
    """One poll cycle. Returns (snapshot_path, diff_rows).

    `fetch_fn(books) -> List[Dict]` and `public_fn() -> Dict` are injectable
    for tests. Default to the real DK/FD fetcher + Action Network. `hhmm`
    overrides the snapshot suffix (useful for tests asserting accumulation).
    """
    date_str = date_str or _today_iso()
    hhmm     = hhmm or _stamp_hhmm()
    ts_iso   = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    if fetch_fn is None:
        from scripts.fetch_dk_props import collect_props as fetch_fn  # noqa: PLC0415
    if public_fn is None:
        public_fn = build_public_lookup

    props = fetch_fn(books)
    snap = snapshot_path(date_str, hhmm, snap_dir)
    n = write_snapshot(props, snap)
    print(f"[{ts_iso}] poll: {n} props -> {snap}")

    prev_path = find_previous_snapshot(date_str, hhmm, snap_dir)
    if prev_path is None:
        print("  (first snapshot of the day - nothing to diff yet)")
        return snap, []

    prev = load_snapshot(prev_path)
    curr = load_snapshot(snap)
    public = public_fn() or {}
    rows = diff_snapshots(prev, curr, ts_iso, public)
    if not rows:
        print(f"  no changes since {os.path.basename(prev_path)}")
        return snap, []

    meaningful = [r for r in rows if is_meaningful(r)]
    log_path = append_movement_log(rows, date_str, log_dir)
    rlm_n = sum(1 for r in meaningful if r.get("rlm") == "Y")
    print(f"  {len(rows)} total moves, {len(meaningful)} meaningful "
          f"({rlm_n} RLM) -> {log_path}")
    for r in meaningful:
        _print_diff(r)
    return snap, rows


def run_daemon(books: List[str], interval_min: int,
               sleep_fn=time.sleep, max_iters: Optional[int] = None) -> int:
    """Loop forever (or max_iters times for tests). Returns iterations run."""
    i = 0
    interval_sec = max(1, int(interval_min * 60))
    while True:
        try:
            poll_once(books)
        except Exception as e:        # never let a single failure kill the loop
            print(f"  [error] poll failed: {e}")
        i += 1
        if max_iters is not None and i >= max_iters:
            return i
        sleep_fn(interval_sec)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="Run a single poll + diff and exit.")
    ap.add_argument("--daemon", action="store_true",
                    help="Loop forever, polling every --interval-min minutes.")
    ap.add_argument("--interval-min", type=int, default=5,
                    help="Daemon poll interval in minutes (default 5).")
    ap.add_argument("--book", action="append", default=None,
                    help="Repeatable. Default: draftkings.")
    args = ap.parse_args()

    books = args.book or ["draftkings"]
    if args.daemon:
        print(f"[poll_line_movement] daemon books={books} "
              f"interval={args.interval_min}min  Ctrl-C to stop.")
        run_daemon(books, args.interval_min)
        return 0
    # default: --once
    poll_once(books)
    return 0


if __name__ == "__main__":
    sys.exit(main())
