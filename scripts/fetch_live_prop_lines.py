"""fetch_live_prop_lines.py - LIVE DK/FD player-prop snapshotter (tier1-1, loop 5).

Why
---
Without REAL sportsbook prop lines, every ROI claim in cycles 95d/97d/99d is an
L5-baseline ESTIMATE. With real lines captured intraday we can:
  * validate model ROI vs the actual CLOSING line a bet would have taken
  * measure CLV (closing line value) per pick
  * compute honest EV from real American odds (not the -110 placeholder)
  * power the hedge calculator + P&L ledger downstream

This script is the foundation: it polls DraftKings + FanDuel for today's
NBA player props on all 7 supported stats (pts/reb/ast/fg3m/stl/blk/tov),
parses per-player per-stat (line, over_price, under_price), and appends to
`data/lines/<date>_<book>.csv`. With `--interval-min N`, it runs as a daemon
suitable for `nohup`.

Why not just reuse poll_line_movement.py?
-----------------------------------------
`poll_line_movement.py` (cycle 88g) writes a TRANSIENT diff log keyed to short
HHMM snapshots, then forgets the underlying line history. This script writes
the PERMANENT per-book ledger that `compute_clv.py`, `clv_tracker.py`, and a
future `backtest_vs_closing_lines.py` will consume to compare model picks to
real closing lines. They're complementary, not duplicative - both feed off
`scripts.fetch_dk_props.collect_props` (which itself layers Odds API -> direct
scrape -> seed file via `src.data.props_scraper.get_current_props`).

Schema (data/lines/<date>_<book>.csv)
-------------------------------------
    captured_at, book, game_id, player_id, player_name, team,
    stat, line, over_price, under_price, market_status

`game_id`, `player_id`, `team` are best-effort - the underlying public DK/FD
endpoints don't always carry NBA Stats IDs, so blanks are tolerated downstream
(they get re-resolved at backtest time via player_name + date).

Dedup
-----
If `(player_name, stat, captured_at-rounded-to-minute)` already exists in the
file, the new row is dropped. This makes daemon mode idempotent under crash +
restart at minute granularity.

CLI
---
    python scripts/fetch_live_prop_lines.py --once
    python scripts/fetch_live_prop_lines.py --book dk --once
    python scripts/fetch_live_prop_lines.py --interval-min 10           # daemon
    python scripts/fetch_live_prop_lines.py --stats pts,reb --book both

Launch as background daemon:
    nohup python scripts/fetch_live_prop_lines.py --interval-min 10 \
        > vault/Improvements/live_prop_scraper.log 2>&1 &
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from datetime import date as _date
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger("fetch_live_prop_lines")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(message)s",
                                       datefmt="%Y-%m-%dT%H:%M:%S"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

# Canonical schema - keep order stable; downstream parsers (compute_clv,
# clv_tracker, backtest_vs_closing_lines) read by name, not index, but
# changing this order breaks human-eye scans of the CSVs.
_FIELDS = ["captured_at", "book", "game_id", "player_id", "player_name",
           "team", "stat", "line", "over_price", "under_price",
           "market_status"]

_VALID_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_BOOK_MAP = {"dk": "draftkings", "fd": "fanduel", "pp": "prizepicks", "bov": "bovada"}
_LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")

# PrizePicks is fixed-payout. Encode both sides as -119 (fair 50/50 with juice)
# per the canonical-schema spec in `improve_R9_C2_multibook_scraper_spec.md`.
_PP_FAIR_PRICE = -119

# Underlying scraper retry/backoff knobs.
_RATE_429_BACKOFF_SEC = 30.0
_INTER_BOOK_PAUSE_SEC = 1.0       # never hammer either book faster than 1 rps


# ── time helpers ──────────────────────────────────────────────────────────────

def _today_iso() -> str:
    return _date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _minute_key(iso_ts: str) -> str:
    """Truncate an ISO timestamp to minute granularity (for dedup)."""
    # 2026-05-24T17:33:21 -> 2026-05-24T17:33
    return iso_ts[:16]


# ── dedup loader ──────────────────────────────────────────────────────────────

def load_existing_keys(path: str) -> Set[Tuple[str, str, str]]:
    """Return {(player_name_lower, stat, minute_key)} already present in path.

    The minute key is `captured_at[:16]`, so two writes inside the same minute
    are treated as duplicates. This is intentional for daemon idempotency
    under crash/restart; if you genuinely want intra-minute granularity, lower
    the minute key length.
    """
    keys: Set[Tuple[str, str, str]] = set()
    if not os.path.exists(path):
        return keys
    try:
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                pn = (r.get("player_name") or "").lower().strip()
                st = (r.get("stat") or "").lower().strip()
                ts = (r.get("captured_at") or "").strip()
                if pn and st and ts:
                    keys.add((pn, st, _minute_key(ts)))
    except Exception as e:    # noqa: BLE001
        log.warning("could not read existing %s for dedup: %s", path, e)
    return keys


# ── fetch + parse ─────────────────────────────────────────────────────────────

class BlockedByBook(Exception):
    """Raised when book returns 403 / IP-block. Caller logs + commits partial."""


class RateLimitExceeded(Exception):
    """Raised after backing off once on a 429 and still being rate-limited."""


def _fetch_book(book_short: str, fetch_fn=None) -> List[Dict]:
    """Fetch raw prop dicts for one book using src.data.props_scraper.

    `fetch_fn(book_full_name) -> List[Dict]` is injectable for tests; in
    production it defaults to `src.data.props_scraper.get_current_props`,
    which already runs the three-tier fallback (Odds API -> direct scrape ->
    seed file). We deliberately layer on top of that helper rather than
    re-implementing requests here - cycle 59 already debugged the auth
    headers and Odds API quota handling.

    Maps short codes (dk/fd) -> full book names (draftkings/fanduel).
    PrizePicks (pp) uses a separate native projections endpoint - see
    `_fetch_prizepicks_raw`.

    Returns [] silently on block/empty (caller handles), but raises
    `RateLimitExceeded` if the underlying scraper signals a 429-after-backoff.
    """
    # PrizePicks has its own public projections API (no key needed) - handled separately
    # so we don't drag the DK/FD odds-api / direct-scrape machinery into the PP path.
    if book_short == "pp":
        try:
            return _fetch_prizepicks_raw()
        except RateLimitExceeded:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("prizepicks fetch error: %s", e)
            return []

    # Bovada is the only US-facing book whose public coupon JSON we can pull
    # without WAF blocks (R14_H1). Its own scraper lives in
    # scripts/bov_scraper_daemon.py; here we just call its fetch_cycle for one
    # snapshot. Note: bov_scraper writes its CSV directly to
    # data/lines/<date>_bov.csv, so we return [] here on purpose - the rows
    # have already been persisted.
    if book_short == "bov":
        try:
            from scripts.bov_scraper_daemon import fetch_cycle as _bov_fetch_cycle  # noqa: PLC0415
            _bov_fetch_cycle(["nba", "wnba", "mlb"])
        except Exception as e:  # noqa: BLE001
            log.warning("bovada fetch error: %s", e)
        return []

    book_full = _BOOK_MAP.get(book_short, book_short)
    if fetch_fn is None:
        try:
            from src.data.props_scraper import get_current_props as fetch_fn  # noqa: PLC0415
        except Exception as e:
            log.error("could not import props_scraper: %s", e)
            return []
    try:
        raw = fetch_fn(book_full) or []
    except RateLimitExceeded:
        # Surface to caller so daemon mode can back off the whole cycle.
        raise
    except BlockedByBook as e:
        log.warning("blocked by %s: %s", book_full, e)
        return []
    except Exception as e:    # noqa: BLE001
        log.warning("%s fetch error: %s", book_full, e)
        return []
    return raw


# ── PrizePicks native fetcher ─────────────────────────────────────────────────

_PP_URL = "https://api.prizepicks.com/projections?league_id=7&per_page=500&single_stat=true"

_PP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://app.prizepicks.com/",
    "Origin":  "https://app.prizepicks.com",
    "Accept-Language": "en-US,en;q=0.9",
}

# PrizePicks stat_type name -> our canonical short codes. Mirrors
# scripts/validation/real_lines_check/fetch_prizepicks.py so the two ETLs
# stay consistent; composites (pra, pa, etc.) are deliberately dropped here
# because the CLV ledger schema only handles the 7 primitive stats.
_PP_STAT_MAP = {
    "Points":        "pts",
    "Rebounds":      "reb",
    "Assists":       "ast",
    "3-PT Made":     "fg3m",
    "Steals":        "stl",
    "Blocked Shots": "blk",
    "Turnovers":     "tov",
}


def _fetch_prizepicks_raw() -> List[Dict]:
    """Pull live PrizePicks NBA projections + return raw dicts shaped for
    parse_props_for_book (i.e. with `prop_type`, `player_name`, `line`,
    `over_odds`, `under_odds`). Both sides set to `_PP_FAIR_PRICE` since PP
    is fixed-payout.

    No auth required; PP gates by UA + Origin which `_PP_HEADERS` satisfies.
    Composite stats (PRA, PA, PR, RA, BS+STL) are silently dropped.
    """
    import urllib.request  # noqa: PLC0415 - keep stdlib-only at module level
    import json as _json   # noqa: PLC0415
    req = urllib.request.Request(_PP_URL, headers=_PP_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = _json.load(r)
    data = payload.get("data", []) or []
    incl = {(d["type"], d["id"]): d for d in payload.get("included", [])}
    out: List[Dict] = []
    for d in data:
        a = d.get("attributes", {}) or {}
        stat_name = a.get("stat_type") or a.get("stat_display_name") or ""
        stat = _PP_STAT_MAP.get(stat_name)
        if not stat:
            continue
        line = a.get("line_score")
        if line is None:
            continue
        rel = d.get("relationships", {}) or {}
        ply_ref = ((rel.get("new_player") or rel.get("player") or {}).get("data") or {})
        ply_obj = (incl.get(("new_player", ply_ref.get("id"))) or
                   incl.get(("player", ply_ref.get("id"))) or {})
        pa = ply_obj.get("attributes", {}) or {}
        player = pa.get("display_name") or pa.get("name") or ""
        if not player:
            continue
        out.append({
            "player_name": player,
            "prop_type":   stat,      # already canonical short code
            "line":        float(line),
            # PP is fixed-payout - encode both sides as -119 (fair, juicy).
            "over_odds":   _PP_FAIR_PRICE,
            "under_odds":  _PP_FAIR_PRICE,
            "team":        pa.get("team", ""),
            "game_id":     "",
            "player_id":   "",
            "market_status": "open",
        })
    return out


def _prop_type_to_stat(prop_type: str) -> Optional[str]:
    """Normalise underlying scraper's prop_type strings to our 7 canonical stats."""
    if not prop_type:
        return None
    pt = prop_type.lower().strip()
    # Direct hits.
    if pt in _VALID_STATS:
        return pt
    # The Odds API + props_scraper use the long names.
    long_map = {
        "points":     "pts",
        "rebounds":   "reb",
        "assists":    "ast",
        "threes":     "fg3m",
        "three_pointers": "fg3m",
        "steals":     "stl",
        "blocks":     "blk",
        "turnovers":  "tov",
    }
    return long_map.get(pt)


def parse_props_for_book(raw: List[Dict],
                         book_short: str,
                         stats_filter: Optional[Set[str]] = None,
                         captured_at: Optional[str] = None,
                         ) -> List[Dict]:
    """Convert raw scraper records to canonical schema rows.

    Tolerates missing game_id / player_id / team (writes blank) - those are
    re-joined at backtest time by player_name + date via NBA Stats. Skips
    rows whose stat isn't in `stats_filter`, whose line is missing, or whose
    player_name is blank.
    """
    stats_filter = stats_filter or set(_VALID_STATS)
    captured_at = captured_at or _now_iso()
    book_full = _BOOK_MAP.get(book_short, book_short)

    rows: List[Dict] = []
    for r in raw:
        stat = _prop_type_to_stat(r.get("prop_type", ""))
        if stat is None or stat not in stats_filter:
            continue
        player = (r.get("player_name") or "").strip()
        if not player:
            log.debug("skip row missing player_name: %r", r)
            continue
        try:
            line = float(r.get("line", 0) or 0)
        except (TypeError, ValueError):
            continue
        if line <= 0:
            continue
        over = r.get("over_odds")
        under = r.get("under_odds")
        rows.append({
            "captured_at":   captured_at,
            "book":          book_full,
            "game_id":       str(r.get("game_id", "") or ""),
            "player_id":     str(r.get("player_id", "") or ""),
            "player_name":   player,
            "team":          str(r.get("team", "") or ""),
            "stat":          stat,
            "line":          f"{line:g}",
            "over_price":    "" if over is None else str(int(over)),
            "under_price":   "" if under is None else str(int(under)),
            "market_status": str(r.get("market_status", "open") or "open"),
        })
    return rows


# ── CSV append (with dedup) ───────────────────────────────────────────────────

def append_rows(rows: List[Dict], path: str) -> int:
    """Append `rows` to `path`, skipping any that duplicate an existing
    (player, stat, minute) key. Creates header row if file is new.
    Returns count actually written.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    existing = load_existing_keys(path)
    new_file = not os.path.exists(path)
    written = 0
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            key = (r["player_name"].lower().strip(), r["stat"],
                   _minute_key(r["captured_at"]))
            if key in existing:
                continue
            existing.add(key)  # block in-batch dups too
            w.writerow({k: r.get(k, "") for k in _FIELDS})
            written += 1
    return written


# ── orchestration ─────────────────────────────────────────────────────────────

def _expand_books(book_arg: str) -> List[str]:
    if book_arg == "both":
        return ["dk", "fd"]
    if book_arg == "all":
        return ["dk", "fd", "pp", "bov"]
    if book_arg not in _BOOK_MAP:
        raise SystemExit(
            f"--book must be dk, fd, pp, bov, both, or all (got {book_arg!r})"
        )
    return [book_arg]


def _expand_stats(stats_arg: str) -> Set[str]:
    parts = {s.strip().lower() for s in stats_arg.split(",") if s.strip()}
    bad = parts - set(_VALID_STATS)
    if bad:
        raise SystemExit(f"unknown stats: {sorted(bad)} (valid: {_VALID_STATS})")
    return parts or set(_VALID_STATS)


def fetch_once(books: List[str],
               stats_filter: Set[str],
               date_str: str,
               lines_dir: str = _LINES_DIR,
               fetch_fn=None,
               sleep_fn=time.sleep,
               ) -> Dict[str, int]:
    """Single fetch over all `books`. Returns {book_short: rows_written}.

    On 429 from underlying scraper: backoff `_RATE_429_BACKOFF_SEC` then retry
    ONCE. If still rate-limited, log + skip that book (does NOT crash sibling
    books or daemon mode).
    On 403 / IP block: log + skip + continue (BlockedByBook is caught inside
    `_fetch_book`).
    """
    captured_at = _now_iso()
    counts: Dict[str, int] = {}
    for i, book_short in enumerate(books):
        if i > 0:
            sleep_fn(_INTER_BOOK_PAUSE_SEC)
        try:
            raw = _fetch_book(book_short, fetch_fn=fetch_fn)
        except RateLimitExceeded:
            log.warning("%s rate-limited; backoff %ds + retry once",
                        book_short, int(_RATE_429_BACKOFF_SEC))
            sleep_fn(_RATE_429_BACKOFF_SEC)
            try:
                raw = _fetch_book(book_short, fetch_fn=fetch_fn)
            except RateLimitExceeded:
                log.error("%s still rate-limited after backoff; skipping",
                          book_short)
                counts[book_short] = 0
                continue
        rows = parse_props_for_book(raw, book_short,
                                     stats_filter=stats_filter,
                                     captured_at=captured_at)
        if not rows:
            log.info("%s: 0 props returned (blocked, off-season, or empty)",
                     book_short)
            counts[book_short] = 0
            continue
        out_path = os.path.join(lines_dir, f"{date_str}_{book_short}.csv")
        n = append_rows(rows, out_path)
        log.info("%s: wrote %d / %d new rows -> %s",
                 book_short, n, len(rows), out_path)
        counts[book_short] = n
    return counts


def run_daemon(books: List[str],
               stats_filter: Set[str],
               interval_min: int,
               lines_dir: str = _LINES_DIR,
               sleep_fn=time.sleep,
               max_iters: Optional[int] = None,
               clock_fn=_today_iso,
               ) -> int:
    """Forever-loop fetch every `interval_min` minutes. Returns iters run."""
    interval_sec = max(1, int(interval_min * 60))
    i = 0
    while True:
        date_str = clock_fn()
        try:
            fetch_once(books, stats_filter, date_str,
                       lines_dir=lines_dir, sleep_fn=sleep_fn)
        except Exception as e:  # noqa: BLE001 - never let daemon die
            log.error("fetch_once failed: %s", e)
        i += 1
        if max_iters is not None and i >= max_iters:
            return i
        sleep_fn(interval_sec)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="LIVE DraftKings + FanDuel player-prop snapshotter."
    )
    ap.add_argument("--book",
                    choices=["dk", "fd", "pp", "bov", "both", "all"],
                    default="all",
                    help="Which book(s) to scrape (default: all = dk+fd+pp+bov).")
    ap.add_argument("--date", default=None,
                    help="Schedule date YYYY-MM-DD (default: today).")
    ap.add_argument("--stats", default=",".join(_VALID_STATS),
                    help=f"Comma-separated stats. Valid: {','.join(_VALID_STATS)}")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true",
                       help="Single fetch + exit (default mode).")
    mode.add_argument("--interval-min", type=int, default=None,
                       help="Daemon mode: poll every N minutes.")
    args = ap.parse_args(argv)

    books = _expand_books(args.book)
    stats_filter = _expand_stats(args.stats)
    date_str = args.date or _today_iso()

    log.info("books=%s stats=%s date=%s",
             books, sorted(stats_filter), date_str)

    if args.interval_min:
        log.info("daemon mode: every %d min  (Ctrl-C to stop)",
                 args.interval_min)
        run_daemon(books, stats_filter, args.interval_min)
        return 0
    counts = fetch_once(books, stats_filter, date_str)
    total = sum(counts.values())
    log.info("done. total new rows: %d  per-book: %s", total, counts)
    return 0 if total > 0 else 0   # 0 even on empty - off-season is not a failure


if __name__ == "__main__":
    sys.exit(main())
