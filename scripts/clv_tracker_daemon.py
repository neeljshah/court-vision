"""clv_tracker_daemon.py — R16_E8 Real-Time CLV Tracker.

Per-minute CLV tracker that watches every pending bet in data/pnl_ledger.csv,
finds the LATEST snapshot for that (player, stat, book) in data/lines/, and
computes realized CLV vs the line at placement. As snapshots accumulate after
placement, the time-series of CLV is the canonical edge signal — independent
of any single game's outcome.

Why
---
Closing Line Value is the only honest measurement of model edge that is robust
to outcome variance. If, across N bets, the market consistently moves toward
our number AFTER we place, the model is real. This daemon turns a one-shot
post-hoc enrichment (src/betting/clv.py) into a live monitor.

Output files
------------
    data/pnl_ledger_clv.csv          - append-only (bet_id, snapshot_time) tuples
    data/cache/clv_running_total.json - aggregate every 5 min
    vault/Predictions/clv_live.md    - color-coded dashboard refreshed every tick

CLV direction convention (matches scripts/clv_tracker.py._compute_clv)
----------------------------------------------------------------------
    OVER : line moves UP   -> positive CLV  (we got the lower number)
    UNDER: line moves DOWN -> positive CLV  (we got the higher number)
    clv_pct = (current_line - placed_line) / placed_line  signed by direction

Closing-line capture
--------------------
When game tip-off is within 30 minutes (start_time - now <= 30 min), the next
tick stamps closing_line_<book> into a side-car file, then continues writing
post-close ticks for forensic analysis. start_time is read from the snapshot
file's start_time column.

CLI
---
    python scripts/clv_tracker_daemon.py --once
    python scripts/clv_tracker_daemon.py --interval-sec 60
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import glob
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# R19_L3 heartbeat import (sys.path bootstrap so daemons launched via
# 'python -u scripts/<name>.py' can still find src.monitor at the project root).
try:
    import os as _r19_os, sys as _r19_sys
    _r19_root = _r19_os.path.dirname(_r19_os.path.dirname(_r19_os.path.abspath(__file__)))
    if _r19_root not in _r19_sys.path:
        _r19_sys.path.insert(0, _r19_root)
    from src.monitor.daemon_heartbeat import write_heartbeat as _r19_hb
except Exception:
    def _r19_hb(_name):
        return False


PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# Paths.
DEFAULT_PNL_PATH   = PROJECT_DIR / "data" / "pnl_ledger.csv"
DEFAULT_LINES_DIR  = PROJECT_DIR / "data" / "lines"
DEFAULT_CLV_OUT    = PROJECT_DIR / "data" / "pnl_ledger_clv.csv"
DEFAULT_AGG_OUT    = PROJECT_DIR / "data" / "cache" / "clv_running_total.json"
DEFAULT_VAULT_OUT  = PROJECT_DIR / "vault" / "Predictions" / "clv_live.md"
DEFAULT_CLOSING_OUT = PROJECT_DIR / "data" / "closing_lines.csv"
DEFAULT_LOG_PATH   = PROJECT_DIR / "vault" / "Improvements" / "clv_tracker_daemon.log"

# Tuning.
CLOSING_WINDOW_MIN  = 30      # mark closing line when tip is within this many min
AGG_INTERVAL_SEC    = 300     # refresh aggregate JSON every 5 min
DEFAULT_INTERVAL_SEC = 60

# Book aliases — keep in sync with src/betting/clv.py._BOOK_ALIASES.
_BOOK_ALIASES = {
    "dk": "draftkings",  "draftkings": "draftkings",
    "fd": "fanduel",     "fanduel":    "fanduel",
    "mgm": "betmgm",     "betmgm":     "betmgm",
    "pp": "prizepicks",  "prizepicks": "prizepicks",
    "bov": "bovada",     "bovada":     "bovada",
    "pin": "pinnacle",   "pinnacle":   "pinnacle",
}

_CLV_LEDGER_FIELDS = [
    "bet_id", "snapshot_time", "placed_at", "player", "stat", "side", "book",
    "placed_line", "current_line", "placed_odds", "current_over_odds",
    "current_under_odds", "clv_pct", "clv_line", "beat_close", "is_closing",
    "minutes_to_tip", "start_time",
]


# --------------------------------------------------------------------------- #
# Helpers.                                                                    #
# --------------------------------------------------------------------------- #
def _book_canon(b: str) -> str:
    return _BOOK_ALIASES.get((b or "").lower().strip(), (b or "").lower().strip())


def _name_key(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _parse_iso(ts: str) -> Optional[_dt.datetime]:
    if not ts:
        return None
    raw = ts.strip()
    # Trim trailing Z (UTC).
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return _dt.datetime.fromisoformat(raw)
    except ValueError:
        # Snapshot timestamps may lack seconds (e.g. "2026-05-26T12:27").
        try:
            return _dt.datetime.strptime(raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            return None


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _to_aware(dt: _dt.datetime) -> _dt.datetime:
    """Coerce a naive datetime to UTC-aware (assume already UTC if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_dt.timezone.utc)
    return dt


# --------------------------------------------------------------------------- #
# Ledger + line snapshot loaders.                                             #
# --------------------------------------------------------------------------- #
def load_pending_bets(pnl_path: Path) -> List[Dict]:
    """Read ledger and return rows with status=='pending' and placed_at < now."""
    if not pnl_path.exists():
        return []
    now = _now_utc()
    pending: List[Dict] = []
    with open(pnl_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("status", "") or "").lower().strip() != "pending":
                continue
            placed = _parse_iso(row.get("placed_at", ""))
            if placed is None:
                continue
            if _to_aware(placed) > now:
                continue
            pending.append(row)
    return pending


def load_recent_snapshots(lines_dir: Path) -> List[Dict]:
    """Union of every data/lines/*.csv (NOT the snapshots/ subfolder).

    Each row is a dict — caller filters by (book, player, stat) and picks max
    captured_at.
    """
    if not lines_dir.is_dir():
        return []
    rows: List[Dict] = []
    for path in sorted(glob.glob(str(lines_dir / "*.csv"))):
        try:
            with open(path, encoding="utf-8") as fh:
                rows.extend(list(csv.DictReader(fh)))
        except (OSError, csv.Error):
            continue
    return rows


def find_latest_snapshot(
    bet: Dict,
    snapshots: List[Dict],
) -> Optional[Dict]:
    """Return the most recent snapshot row matching (book, player, stat)."""
    book_c = _book_canon(bet.get("book", ""))
    stat_l = (bet.get("stat", "") or "").lower().strip()
    pname_k = _name_key(bet.get("player", ""))
    pid_s = str(bet.get("player_id", "") or "").strip()
    placed_line = _safe_float(bet.get("line", ""))

    best: Optional[Tuple[_dt.datetime, Dict]] = None
    for r in snapshots:
        if _book_canon(r.get("book", "")) != book_c:
            continue
        if (r.get("stat", "") or "").lower().strip() != stat_l:
            continue
        # Prefer id-based match, fall back to name.
        rpid = str(r.get("player_id", "") or "").strip()
        if pid_s and rpid:
            if rpid != pid_s:
                continue
        else:
            if _name_key(r.get("player_name", "")) != pname_k:
                continue
        # Prefer the alt-line that EXACTLY matches the bet's placed line, so we
        # track the same ladder rung (different alt-lines are different markets).
        rline = _safe_float(r.get("line", ""))
        if placed_line is not None and rline is not None and abs(rline - placed_line) > 1e-6:
            # Allow ladder mismatch only if no exact match found by end of loop.
            # Track best-exact and best-any separately.
            pass
        ts = _parse_iso(r.get("captured_at", ""))
        if ts is None:
            continue
        ts_aware = _to_aware(ts)
        cand = (ts_aware, r)
        # We rank: exact-line match first, then most recent.
        if best is None:
            best = cand
            continue
        b_line = _safe_float(best[1].get("line", ""))
        cur_line = _safe_float(r.get("line", ""))
        if placed_line is not None and b_line is not None and cur_line is not None:
            b_match = abs(b_line - placed_line) < 1e-6
            c_match = abs(cur_line - placed_line) < 1e-6
            if c_match and not b_match:
                best = cand
                continue
            if b_match and not c_match:
                continue
        if cand[0] > best[0]:
            best = cand
    return best[1] if best else None


def _safe_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# CLV math.                                                                   #
# --------------------------------------------------------------------------- #
def compute_realized_clv(
    placed_line: float,
    current_line: float,
    side: str,
) -> Tuple[float, float]:
    """Return (clv_line, clv_pct) with the sign matching `side`.

    OVER  : positive when current > placed (line moved UP — we locked LOWER)
    UNDER : positive when current < placed (line moved DOWN — we locked HIGHER)

    clv_line = signed line movement in stat units
    clv_pct  = clv_line / placed_line  (fraction, e.g. 0.0286 for +2.86%)
    """
    side_u = (side or "").upper()
    if side_u == "OVER":
        clv_line = current_line - placed_line
    elif side_u == "UNDER":
        clv_line = placed_line - current_line
    else:
        raise ValueError(f"Unknown side: {side!r}")
    clv_pct = (clv_line / placed_line) if placed_line not in (0, None) else 0.0
    return round(clv_line, 4), round(clv_pct, 6)


# --------------------------------------------------------------------------- #
# One tick.                                                                   #
# --------------------------------------------------------------------------- #
def run_tick(
    pnl_path: Path,
    lines_dir: Path,
    clv_out_path: Path,
    vault_md_path: Path,
    closing_out_path: Path,
    now: Optional[_dt.datetime] = None,
) -> Dict:
    """One CLV-tracker iteration.

    Returns a small report dict:
        {bets_tracked, ticks_written, closing_lines_captured, rows_written}
    """
    now = _to_aware(now) if now else _now_utc()
    pending = load_pending_bets(pnl_path)
    snapshots = load_recent_snapshots(lines_dir)

    written_rows: List[Dict] = []
    dashboard_rows: List[Dict] = []
    closing_captured = 0

    for bet in pending:
        snap = find_latest_snapshot(bet, snapshots)
        if snap is None:
            continue
        placed_line = _safe_float(bet.get("line", ""))
        current_line = _safe_float(snap.get("line", ""))
        if placed_line is None or current_line is None:
            continue
        side = (bet.get("side", "") or "").upper()
        try:
            clv_line, clv_pct = compute_realized_clv(placed_line, current_line, side)
        except ValueError:
            continue

        start_dt = _parse_iso(snap.get("start_time", ""))
        snap_ts = _parse_iso(snap.get("captured_at", "")) or now
        snap_ts = _to_aware(snap_ts)
        if start_dt is not None:
            start_dt = _to_aware(start_dt)
            mins_to_tip = (start_dt - now).total_seconds() / 60.0
        else:
            mins_to_tip = None

        is_closing = (
            mins_to_tip is not None
            and 0 <= mins_to_tip <= CLOSING_WINDOW_MIN
        )
        if is_closing and not _closing_already_logged(closing_out_path, bet["bet_id"], bet.get("book", "")):
            _append_closing_line(
                closing_out_path,
                bet_id=bet["bet_id"],
                book=bet.get("book", ""),
                stat=bet.get("stat", ""),
                player=bet.get("player", ""),
                closing_line=current_line,
                closing_over_odds=_safe_int(snap.get("over_price")),
                closing_under_odds=_safe_int(snap.get("under_price")),
                captured_at=snap.get("captured_at", ""),
                start_time=snap.get("start_time", ""),
            )
            closing_captured += 1

        row = {
            "bet_id":            bet["bet_id"],
            "snapshot_time":     snap.get("captured_at", ""),
            "placed_at":         bet.get("placed_at", ""),
            "player":            bet.get("player", ""),
            "stat":              bet.get("stat", ""),
            "side":              side,
            "book":              bet.get("book", ""),
            "placed_line":       placed_line,
            "current_line":      current_line,
            "placed_odds":       _safe_int(bet.get("american_odds")),
            "current_over_odds":  _safe_int(snap.get("over_price")),
            "current_under_odds": _safe_int(snap.get("under_price")),
            "clv_pct":           clv_pct,
            "clv_line":          clv_line,
            "beat_close":        clv_pct > 0,
            "is_closing":        is_closing,
            "minutes_to_tip":    round(mins_to_tip, 2) if mins_to_tip is not None else "",
            "start_time":        snap.get("start_time", ""),
        }
        written_rows.append(row)
        dashboard_rows.append(row)

    _append_clv_rows(clv_out_path, written_rows)
    _write_dashboard(vault_md_path, dashboard_rows, now)

    return {
        "bets_tracked":          len(dashboard_rows),
        "rows_written":          len(written_rows),
        "closing_lines_captured": closing_captured,
        "snapshot_count":        len(snapshots),
    }


# --------------------------------------------------------------------------- #
# Writers.                                                                    #
# --------------------------------------------------------------------------- #
def _append_clv_rows(path: Path, rows: List[Dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_CLV_LEDGER_FIELDS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def _closing_already_logged(path: Path, bet_id: str, book: str) -> bool:
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("bet_id") == bet_id and row.get("book", "") == book:
                    return True
    except (OSError, csv.Error):
        return False
    return False


def _append_closing_line(
    path: Path,
    bet_id: str,
    book: str,
    stat: str,
    player: str,
    closing_line: float,
    closing_over_odds: Optional[int],
    closing_under_odds: Optional[int],
    captured_at: str,
    start_time: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    fields = [
        "bet_id", "book", "stat", "player", "closing_line",
        "closing_over_odds", "closing_under_odds",
        "captured_at", "start_time", "logged_at",
    ]
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if new_file:
            w.writeheader()
        w.writerow({
            "bet_id":             bet_id,
            "book":               book,
            "stat":                stat,
            "player":              player,
            "closing_line":        closing_line,
            "closing_over_odds":   "" if closing_over_odds is None else closing_over_odds,
            "closing_under_odds":  "" if closing_under_odds is None else closing_under_odds,
            "captured_at":         captured_at,
            "start_time":          start_time,
            "logged_at":           _now_utc().isoformat(timespec="seconds"),
        })


# --------------------------------------------------------------------------- #
# Vault dashboard.                                                            #
# --------------------------------------------------------------------------- #
def _color_dot(clv_pct: float) -> str:
    """Color marker per the spec.

    green if CLV > +1%, yellow if 0 <= CLV <= +1%, red if negative.
    Markdown-safe — uses emoji that render in Obsidian.
    """
    if clv_pct > 0.01:
        return "GREEN"
    if clv_pct >= 0:
        return "YELLOW"
    return "RED"


def _write_dashboard(path: Path, rows: List[Dict], now: _dt.datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Live CLV Dashboard",
        "",
        f"_Last refresh: {now.isoformat(timespec='seconds')}_",
        "",
        f"Tracking **{len(rows)}** pending bets.",
        "",
        "| Status | Bet ID | Player | Stat | Side | Book | Placed Line | Current Line | CLV% | Min to Tip |",
        "|--------|--------|--------|------|------|------|------------:|-------------:|-----:|-----------:|",
    ]
    # Sort by CLV descending so winners surface first.
    for r in sorted(rows, key=lambda r: r.get("clv_pct", 0), reverse=True):
        status = _color_dot(float(r["clv_pct"]))
        bet_id_short = (r["bet_id"] or "")[:8]
        mtt = r["minutes_to_tip"]
        mtt_s = f"{mtt:.1f}" if isinstance(mtt, (int, float)) else "-"
        lines.append(
            f"| {status} | `{bet_id_short}` | {r['player']} | {r['stat'].upper()} | "
            f"{r['side']} | {r['book']} | {r['placed_line']:.1f} | "
            f"{r['current_line']:.1f} | {r['clv_pct']*100:+.2f}% | {mtt_s} |"
        )
    if not rows:
        lines.append("| - | _no pending bets_ | | | | | | | | |")

    lines += [
        "",
        "## Legend",
        "- **GREEN**: CLV > +1.0% (model beating close)",
        "- **YELLOW**: 0 <= CLV <= +1.0%",
        "- **RED**: negative CLV (market moved against you)",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Aggregate.                                                                  #
# --------------------------------------------------------------------------- #
def compute_aggregate(clv_csv: Path) -> Dict:
    if not clv_csv.exists():
        return {"n_bets_tracked": 0, "mean_clv_pct": 0.0, "pct_positive_clv": 0.0, "by_book": {}}
    rows: List[Dict] = []
    with open(clv_csv, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    # Latest tick per bet_id only — so we measure CURRENT clv, not double-count history.
    latest: Dict[str, Dict] = {}
    for r in rows:
        bid = r.get("bet_id", "")
        if not bid:
            continue
        snap_ts = _parse_iso(r.get("snapshot_time", "")) or _dt.datetime.min
        prev_ts = _parse_iso(latest.get(bid, {}).get("snapshot_time", "")) or _dt.datetime.min
        if bid not in latest or snap_ts > prev_ts:
            latest[bid] = r

    bets = list(latest.values())
    n = len(bets)
    if n == 0:
        return {"n_bets_tracked": 0, "mean_clv_pct": 0.0, "pct_positive_clv": 0.0, "by_book": {}}

    pcts = [_safe_float(r.get("clv_pct")) for r in bets]
    pcts = [p for p in pcts if p is not None]
    mean_pct = sum(pcts) / len(pcts) if pcts else 0.0
    pos = sum(1 for p in pcts if p > 0)
    pct_pos = pos / len(pcts) if pcts else 0.0

    by_book: Dict[str, Dict] = {}
    for r in bets:
        book = (r.get("book", "") or "").lower() or "(none)"
        p = _safe_float(r.get("clv_pct"))
        if p is None:
            continue
        bb = by_book.setdefault(book, {"n": 0, "sum": 0.0, "pos": 0})
        bb["n"] += 1
        bb["sum"] += p
        if p > 0:
            bb["pos"] += 1
    for book, v in by_book.items():
        v["mean_clv_pct"] = round(v["sum"] / v["n"], 6) if v["n"] else 0.0
        v["pct_positive"] = round(v["pos"] / v["n"], 4) if v["n"] else 0.0
        del v["sum"]

    return {
        "n_bets_tracked":   n,
        "mean_clv_pct":     round(mean_pct, 6),
        "pct_positive_clv": round(pct_pos, 4),
        "by_book":          by_book,
        "updated_at":       _now_utc().isoformat(timespec="seconds"),
    }


def write_aggregate(clv_csv: Path, out_path: Path) -> Dict:
    agg = compute_aggregate(clv_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(agg, indent=2), encoding="utf-8")
    return agg


# --------------------------------------------------------------------------- #
# Main loop.                                                                  #
# --------------------------------------------------------------------------- #
def _log(line: str, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(f"[{_now_utc().isoformat(timespec='seconds')}] {line}\n")


_STOP = False


def _on_signal(signum, frame):
    global _STOP
    _STOP = True


def main_loop(
    pnl_path: Path = DEFAULT_PNL_PATH,
    lines_dir: Path = DEFAULT_LINES_DIR,
    clv_out_path: Path = DEFAULT_CLV_OUT,
    vault_md_path: Path = DEFAULT_VAULT_OUT,
    closing_out_path: Path = DEFAULT_CLOSING_OUT,
    agg_path: Path = DEFAULT_AGG_OUT,
    log_path: Path = DEFAULT_LOG_PATH,
    interval_sec: int = DEFAULT_INTERVAL_SEC,
    once: bool = False,
    max_ticks: Optional[int] = None,
) -> Dict:
    """Persistent CLV-tracking loop. Returns final cumulative stats."""
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT,  _on_signal)

    cycle = 0
    ticks_observed = 0
    last_agg_ts = 0.0
    bets_tracked_total = 0

    while not _STOP:
        # R19_L3 heartbeat
        _r19_hb('clv_tracker_daemon')
        cycle += 1
        try:
            rpt = run_tick(
                pnl_path=pnl_path,
                lines_dir=lines_dir,
                clv_out_path=clv_out_path,
                vault_md_path=vault_md_path,
                closing_out_path=closing_out_path,
            )
            ticks_observed += 1
            bets_tracked_total = max(bets_tracked_total, rpt["bets_tracked"])
            _log(
                f"cycle={cycle} bets={rpt['bets_tracked']} "
                f"rows_written={rpt['rows_written']} "
                f"closing_captured={rpt['closing_lines_captured']} "
                f"snapshots={rpt['snapshot_count']}",
                log_path=log_path,
            )
        except Exception as exc:  # pragma: no cover — log & keep looping
            _log(f"cycle={cycle} ERROR: {exc!r}", log_path=log_path)

        # Aggregate every 5 min wall-clock.
        now_ts = time.time()
        if now_ts - last_agg_ts >= AGG_INTERVAL_SEC:
            try:
                agg = write_aggregate(clv_out_path, agg_path)
                _log(
                    f"agg n={agg['n_bets_tracked']} mean_clv={agg['mean_clv_pct']:.6f} "
                    f"pos={agg['pct_positive_clv']:.2%}",
                    log_path=log_path,
                )
            except Exception as exc:  # pragma: no cover
                _log(f"agg ERROR: {exc!r}", log_path=log_path)
            last_agg_ts = now_ts

        if once:
            break
        if max_ticks is not None and cycle >= max_ticks:
            break
        # Sleep in small slices so SIGTERM is responsive.
        slept = 0
        while slept < interval_sec and not _STOP:
            time.sleep(min(1, interval_sec - slept))
            slept += 1

    # Final aggregate write on exit.
    final_agg = write_aggregate(clv_out_path, agg_path)
    final_agg["ticks_observed"] = ticks_observed
    final_agg["bets_tracked"] = bets_tracked_total
    return final_agg


# --------------------------------------------------------------------------- #
# CLI.                                                                        #
# --------------------------------------------------------------------------- #
def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Real-time CLV tracker daemon")
    p.add_argument("--interval-sec", type=int, default=DEFAULT_INTERVAL_SEC,
                   help="Seconds between ticks (default 60)")
    p.add_argument("--once", action="store_true",
                   help="Run one tick + aggregate, then exit")
    p.add_argument("--max-ticks", type=int, default=None,
                   help="Stop after N ticks (smoke-test mode)")
    p.add_argument("--pnl-path",   default=str(DEFAULT_PNL_PATH))
    p.add_argument("--lines-dir",  default=str(DEFAULT_LINES_DIR))
    p.add_argument("--clv-out",    default=str(DEFAULT_CLV_OUT))
    p.add_argument("--vault-md",   default=str(DEFAULT_VAULT_OUT))
    p.add_argument("--closing-out", default=str(DEFAULT_CLOSING_OUT))
    p.add_argument("--agg-out",    default=str(DEFAULT_AGG_OUT))
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    final = main_loop(
        pnl_path=Path(args.pnl_path),
        lines_dir=Path(args.lines_dir),
        clv_out_path=Path(args.clv_out),
        vault_md_path=Path(args.vault_md),
        closing_out_path=Path(args.closing_out),
        agg_path=Path(args.agg_out),
        interval_sec=args.interval_sec,
        once=args.once,
        max_ticks=args.max_ticks,
    )
    print(json.dumps(final, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
