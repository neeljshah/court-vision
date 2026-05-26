"""probe_R9_C1_historical_line_backfill.py - Round 9 / CLV pivot / probe C1.

Goal: backfill 2024-25 historical NBA player-prop sportsbook lines into
``data/lines/<date>_<book>.csv`` so the CLV pipeline
(:func:`src.betting.clv.find_closing_line`) can resolve a non-None closing
line for the ledger bets.

Spec: ``scripts/_results/improve_R9_C1_historical_line_backfill_spec.md``.

Acquisition algorithm (in order):

1.  **Primary - the-odds-api.com /v4/historical** (requires ``ODDS_API_KEY``).
    Iterates the 2024-25 regular-season game-dates, fetches the historical
    events + per-event prop snapshots ~35 min pre-tip across DK / FD / MGM
    for the 7 canonical stats, and writes them into the per-date / per-book
    CSVs in the schema ``clv.py`` already globs.

2.  **Fallback - SBR GitHub archive (flancast90/sportsbookreview-scraper).**
    The published archive only carries *game lines* (spread/total/ML),
    **not** player props.  The probe still records the attempt for
    auditability so a future operator can see the fallback was tried.  Game
    lines do not satisfy the per-stat gate (the 7 stats are player counters),
    so this fallback alone can never SHIP - it only prevents BLOCKED when at
    least 1000 game-line rows are persisted, allowing the orchestrator to
    follow up with C3 (synthetic CLV).

The probe is **idempotent**: rerunning it overwrites the per-(date, book) CSV
files keyed on ``(book, player_name, stat, captured_at[:16])`` so a partial
run can be resumed without producing duplicates.

The probe ALWAYS writes its result JSON, even on REJECT / BLOCKED, so the
orchestrator can read a deterministic decision.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

import urllib.error
import urllib.request

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------
LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")
PROGRESS_PATH = os.path.join(CACHE_DIR, "clv_backfill_progress.json")
RESULT_PATH = os.path.join(
    CACHE_DIR, "probe_R9_C1_historical_line_backfill_results.json"
)
LOG_PATH = os.path.join(
    PROJECT_DIR, "vault", "Improvements", "clv_backfill.log"
)
PNL_PATH = os.path.join(PROJECT_DIR, "data", "pnl_ledger.csv")
SEASON_GAMES_PATH = os.path.join(
    PROJECT_DIR, "data", "nba", "season_games_2024-25.json"
)
PLAYER_ID_MAP_PATH = os.path.join(CACHE_DIR, "player_id_map.json")

# Canonical 7 stats the rest of the prop stack tracks.
STATS_CANON = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# the-odds-api market keys -> our canonical stat code.
ODDS_API_MARKET_MAP = {
    "player_points":     "pts",
    "player_rebounds":   "reb",
    "player_assists":    "ast",
    "player_threes":     "fg3m",
    "player_steals":     "stl",
    "player_blocks":     "blk",
    "player_turnovers":  "tov",
}

# bookmaker -> canonical book code used by clv._BOOK_ALIASES.
BOOK_CANON = {
    "draftkings":  "draftkings",
    "fanduel":     "fanduel",
    "betmgm":      "betmgm",
}

# Ship-gate thresholds from spec section 8.
GATE_MIN_ROWS         = 10_000
GATE_MIN_BOOKS        = 2
GATE_MIN_DATES        = 150
GATE_MIN_PER_STAT     = 1_000
GATE_MIN_JOIN_PCT     = 30.0   # %

SBR_NBA_ARCHIVE_URL = (
    "https://raw.githubusercontent.com/flancast90/sportsbookreview-scraper"
    "/main/data/nba_archive_10Y.json"
)
ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Polite request cadence (the odds-api documents per-second limits).
ODDS_API_SLEEP_SEC = 0.4

# Per-event regular-season window (2024-10-22 -> 2025-04-13).
SEASON_START = datetime(2024, 10, 22, tzinfo=timezone.utc)
SEASON_END   = datetime(2025, 4, 13,  tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Tiny logging helper - writes to stdout + vault log (best-effort).
# ---------------------------------------------------------------------------
def _log(msg: str) -> None:
    ts = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Player-name normalisation (matches clv._name_key exactly).
# ---------------------------------------------------------------------------
def _name_key(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


# ---------------------------------------------------------------------------
# Game-id resolution from 2024-25 season-games index.
# ---------------------------------------------------------------------------
def _load_game_index() -> Dict[Tuple[str, str, str], str]:
    """Return {(date_iso, home_abbr, away_abbr): game_id} for 2024-25."""
    if not os.path.exists(SEASON_GAMES_PATH):
        return {}
    try:
        with open(SEASON_GAMES_PATH, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    out: Dict[Tuple[str, str, str], str] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        gid = str(r.get("game_id") or "")
        dt  = str(r.get("game_date") or "")[:10]
        home = str(r.get("home_team") or "")
        away = str(r.get("away_team") or "")
        if gid and dt and home and away:
            out[(dt, home, away)] = gid
    return out


def _load_player_id_map() -> Dict[str, str]:
    """Best-effort name->player_id map; empty if file is absent."""
    if not os.path.exists(PLAYER_ID_MAP_PATH):
        return {}
    try:
        with open(PLAYER_ID_MAP_PATH, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(d, dict):
        return {_name_key(k): str(v) for k, v in d.items()}
    return {}


# ---------------------------------------------------------------------------
# Output schema - mirrors fetch_live_prop_lines convention exactly.
# ---------------------------------------------------------------------------
OUTPUT_COLUMNS = [
    "captured_at", "book", "game_id", "player_id", "player_name", "team",
    "stat", "line", "over_price", "under_price", "market_status",
]


def _row_dedup_key(row: Dict) -> Tuple[str, str, str, str]:
    """Match clv.py dedup semantics: (book, player_name, stat, captured_at[:16])."""
    return (
        (row.get("book") or "").lower(),
        _name_key(row.get("player_name", "")),
        (row.get("stat") or "").lower(),
        (row.get("captured_at") or "")[:16],
    )


def _persist_rows_for_date_book(
    date_iso: str, book: str, rows: List[Dict]
) -> int:
    """Write rows for one (date, book) CSV, dedup-merging with anything already on disk.

    Returns number of unique rows now in the file.
    """
    if not rows:
        return 0
    os.makedirs(LINES_DIR, exist_ok=True)
    path = os.path.join(LINES_DIR, f"{date_iso}_{book}.csv")
    existing: Dict[Tuple[str, str, str, str], Dict] = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                for r in csv.DictReader(fh):
                    existing[_row_dedup_key(r)] = r
        except (OSError, csv.Error):
            existing = {}
    for r in rows:
        existing[_row_dedup_key(r)] = r
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in existing.values():
            w.writerow(r)
    return len(existing)


# ---------------------------------------------------------------------------
# the-odds-api primary path.
# ---------------------------------------------------------------------------
def _odds_api_get(url: str) -> Tuple[int, Optional[dict]]:
    req = urllib.request.Request(url, headers={"User-Agent": "courtvision/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            try:
                return r.status, json.loads(body)
            except json.JSONDecodeError:
                return r.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError):
        return -1, None


def _odds_api_enumerate_dates() -> List[str]:
    """Generate 2024-25 regular-season game-dates."""
    out: List[str] = []
    d = SEASON_START
    while d <= SEASON_END:
        out.append(d.date().isoformat())
        d += timedelta(days=1)
    return out


def _flatten_event_payload(
    event_payload: dict,
    game_id_lookup: Dict[Tuple[str, str, str], str],
    player_id_map: Dict[str, str],
) -> List[Dict]:
    """Walk an /events/{id}/odds payload into our 11-column rows."""
    rows: List[Dict] = []
    commence_iso = event_payload.get("commence_time", "") or ""
    home_team    = event_payload.get("home_team", "") or ""
    away_team    = event_payload.get("away_team", "") or ""
    # Snapshot iso = commence_time - 35min if we have it, else "".
    snap_iso = commence_iso
    try:
        dt = datetime.fromisoformat(commence_iso.replace("Z", "+00:00"))
        snap_iso = (dt - timedelta(minutes=35)).isoformat()
    except (TypeError, ValueError):
        pass

    date_iso = commence_iso[:10]
    gid = game_id_lookup.get((date_iso, home_team, away_team), "")

    for bm in event_payload.get("bookmakers") or []:
        book_key = (bm.get("key") or "").lower()
        book_canon = BOOK_CANON.get(book_key)
        if not book_canon:
            continue
        for mkt in bm.get("markets") or []:
            mkey = (mkt.get("key") or "").lower()
            stat = ODDS_API_MARKET_MAP.get(mkey)
            if not stat:
                continue
            # Two outcomes per (player, market): Over + Under.
            by_player: Dict[str, Dict] = {}
            for oc in mkt.get("outcomes") or []:
                pname = str(oc.get("description") or "").strip()
                side  = str(oc.get("name") or "").strip().lower()
                if not pname or side not in ("over", "under"):
                    continue
                slot = by_player.setdefault(pname, {})
                slot["line"] = oc.get("point")
                price_key = "over_price" if side == "over" else "under_price"
                slot[price_key] = oc.get("price")
            for pname, slot in by_player.items():
                if slot.get("line") is None:
                    continue
                rows.append({
                    "captured_at":  snap_iso,
                    "book":         book_canon,
                    "game_id":      gid,
                    "player_id":    player_id_map.get(_name_key(pname), ""),
                    "player_name":  pname,
                    "team":         "",
                    "stat":         stat,
                    "line":         slot.get("line"),
                    "over_price":   slot.get("over_price", ""),
                    "under_price":  slot.get("under_price", ""),
                    "market_status": "closed",
                })
    return rows


def _odds_api_backfill(api_key: str) -> Dict:
    """Walk dates -> events -> per-event odds.  Returns counters."""
    game_id_lookup = _load_game_index()
    player_id_map  = _load_player_id_map()
    dates = _odds_api_enumerate_dates()
    markets_q = ",".join(ODDS_API_MARKET_MAP.keys())
    books_q   = ",".join(BOOK_CANON.keys())

    written_total = 0
    consecutive_429 = 0
    dates_with_data: List[str] = []

    for date_iso in dates:
        # First the events list at midday-UTC; the odds-api historical /events
        # endpoint expects an ISO-8601 timestamp.
        date_ts = f"{date_iso}T12:00:00Z"
        events_url = (
            f"{ODDS_API_BASE}/historical/sports/basketball_nba/events"
            f"?apiKey={api_key}&date={date_ts}"
        )
        status, payload = _odds_api_get(events_url)
        if status == 401:
            _log(f"odds-api 401 invalid key on {date_iso} - aborting primary")
            return {
                "status": "QUOTA",
                "reason": "invalid_key",
                "rows_written": written_total,
                "dates_with_data": dates_with_data,
            }
        if status == 402:
            _log(f"odds-api 402 quota exhausted on {date_iso} - stopping")
            return {
                "status": "QUOTA",
                "reason": "quota_exhausted",
                "rows_written": written_total,
                "dates_with_data": dates_with_data,
            }
        if status == 429:
            consecutive_429 += 1
            if consecutive_429 >= 3:
                _log(f"odds-api 429 x3 on {date_iso} - aborting primary")
                return {
                    "status": "RATE_LIMIT",
                    "reason": "rate_limit_3x",
                    "rows_written": written_total,
                    "dates_with_data": dates_with_data,
                }
            time.sleep(min(60.0, 2 ** consecutive_429))
            continue
        if status != 200 or payload is None:
            time.sleep(ODDS_API_SLEEP_SEC)
            continue
        consecutive_429 = 0
        time.sleep(ODDS_API_SLEEP_SEC)

        events = payload.get("data") or payload  # /historical wraps in {"data": [...]}
        if not isinstance(events, list):
            continue
        if not events:
            continue

        date_rows_by_book: Dict[str, List[Dict]] = {}
        for ev in events:
            ev_id = ev.get("id")
            commence_iso = ev.get("commence_time", "") or ""
            if not ev_id or not commence_iso:
                continue
            try:
                tip_dt = datetime.fromisoformat(commence_iso.replace("Z", "+00:00"))
            except ValueError:
                continue
            snap_dt = tip_dt - timedelta(minutes=35)
            snap_iso = snap_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            odds_url = (
                f"{ODDS_API_BASE}/historical/sports/basketball_nba/events/{ev_id}/odds"
                f"?apiKey={api_key}&regions=us"
                f"&bookmakers={books_q}&markets={markets_q}"
                f"&oddsFormat=american&date={snap_iso}"
            )
            ostat, opay = _odds_api_get(odds_url)
            time.sleep(ODDS_API_SLEEP_SEC)
            if ostat != 200 or opay is None:
                continue
            ev_payload = opay.get("data") or opay
            if not isinstance(ev_payload, dict):
                continue
            rows = _flatten_event_payload(ev_payload, game_id_lookup, player_id_map)
            for r in rows:
                date_rows_by_book.setdefault(r["book"], []).append(r)

        for book, brows in date_rows_by_book.items():
            n_after = _persist_rows_for_date_book(date_iso, book, brows)
            written_total += len(brows)
            _log(f"odds-api wrote {len(brows)} rows ({n_after} total) "
                 f"-> {date_iso}_{book}.csv")
        if date_rows_by_book:
            dates_with_data.append(date_iso)

    return {
        "status": "OK",
        "rows_written": written_total,
        "dates_with_data": dates_with_data,
    }


# ---------------------------------------------------------------------------
# SBR archive fallback - GAME LINES only.  Cannot satisfy the player-prop
# gate, but we still capture into the per-date/per-book files so the
# orchestrator has a deterministic audit trail of the attempt.
# ---------------------------------------------------------------------------
def _sbr_fallback() -> Dict:
    """Pull the public SBR 10Y NBA archive.  Returns counters."""
    _log("attempting SBR GitHub fallback (game lines only, no player props)")
    req = urllib.request.Request(
        SBR_NBA_ARCHIVE_URL, headers={"User-Agent": "courtvision/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.loads(r.read())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            TimeoutError, OSError) as e:
        _log(f"SBR fallback failed to fetch: {type(e).__name__}: {e}")
        return {"status": "FAIL", "rows_written": 0, "reason": "fetch_error"}
    if not isinstance(payload, list):
        _log("SBR fallback payload is not a list")
        return {"status": "FAIL", "rows_written": 0, "reason": "bad_payload"}

    # Filter to season=2024 (the SBR archive labels seasons by starting year).
    rows_2024 = [r for r in payload if isinstance(r, dict)
                 and int(r.get("season") or 0) == 2024]
    _log(f"SBR fallback: {len(rows_2024)} game-line rows for 2024 season")

    if not rows_2024:
        return {"status": "FAIL", "rows_written": 0, "reason": "no_2024_rows"}

    # The SBR archive has game-level lines; this NEVER satisfies the player
    # prop stat gate (the 7 stats are player counters).  We persist for
    # auditability but do NOT count it toward the prop-line gate.
    n_persisted = 0
    for r in rows_2024:
        raw_date = r.get("date")
        if raw_date is None:
            continue
        try:
            dstr = str(int(raw_date))
            date_iso = f"{dstr[:4]}-{dstr[4:6]}-{dstr[6:8]}"
        except (TypeError, ValueError):
            continue
        n_persisted += 1
    _log(f"SBR fallback: would archive {n_persisted} game-line rows but "
         f"none satisfy the player-prop schema - skipping persistence")
    return {
        "status": "PARTIAL",
        "rows_written": 0,            # zero rows added to player-prop schema
        "reason": "sbr_has_game_lines_only_not_player_props",
        "sbr_rows_available": n_persisted,
    }


# ---------------------------------------------------------------------------
# Ledger join measurement
# ---------------------------------------------------------------------------
def _measure_ledger_join_pct() -> Tuple[float, int, int]:
    """Return (pct, n_resolved, n_total) of ledger bets resolving a closing line.

    Uses clv.find_closing_line so we're measuring exactly what downstream
    consumers will see.  Operates over `data/pnl_ledger.csv` regardless of
    its size.
    """
    if not os.path.exists(PNL_PATH):
        return 0.0, 0, 0
    try:
        from src.betting.clv import find_closing_line, _load_snapshots, _parse_iso
    except ImportError as e:
        _log(f"ledger-join: clv import failed: {e}")
        return 0.0, 0, 0

    snaps = _load_snapshots(LINES_DIR)
    if not snaps:
        with open(PNL_PATH, encoding="utf-8") as fh:
            n_total = sum(1 for _ in csv.DictReader(fh))
        return 0.0, 0, n_total

    n_resolved = 0
    n_total = 0
    with open(PNL_PATH, encoding="utf-8") as fh:
        for bet in csv.DictReader(fh):
            n_total += 1
            placed = _parse_iso(bet.get("placed_at", ""))
            if placed is None:
                continue
            asof = placed + timedelta(minutes=30)
            res = find_closing_line(
                book=bet.get("book", ""),
                game_id=bet.get("game_id", ""),
                player_id=bet.get("player_id", ""),
                stat=bet.get("stat", ""),
                side=bet.get("side", ""),
                asof=asof,
                snapshots=snaps,
                player_name=bet.get("player", ""),
            )
            if res is not None:
                n_resolved += 1
    pct = 100.0 * n_resolved / n_total if n_total else 0.0
    return pct, n_resolved, n_total


# ---------------------------------------------------------------------------
# Output inventory - count what is on disk under data/lines/*.csv.
# ---------------------------------------------------------------------------
def _inventory_lines_dir() -> Dict:
    inv = {
        "rows_total": 0,
        "rows_player_prop": 0,
        "books": set(),
        "dates": set(),
        "per_stat": {s: 0 for s in STATS_CANON},
    }
    if not os.path.isdir(LINES_DIR):
        return inv
    import glob as _glob
    for path in _glob.glob(os.path.join(LINES_DIR, "*.csv")):
        fname = os.path.basename(path)
        # Expected pattern: YYYY-MM-DD_book.csv
        stem = fname.rsplit(".", 1)[0]
        parts = stem.split("_", 1)
        if len(parts) != 2:
            continue
        date_iso, book = parts
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
        except (OSError, csv.Error):
            continue
        if not rows:
            continue
        inv["books"].add(book)
        inv["dates"].add(date_iso)
        for r in rows:
            inv["rows_total"] += 1
            stat = (r.get("stat") or "").lower().strip()
            if stat in STATS_CANON:
                inv["rows_player_prop"] += 1
                inv["per_stat"][stat] += 1
    # Make JSON-serialisable.
    inv["books"] = sorted(inv["books"])
    inv["dates"] = sorted(inv["dates"])
    return inv


# ---------------------------------------------------------------------------
# Ship-gate evaluation
# ---------------------------------------------------------------------------
def _evaluate_gate(inv: Dict, join_pct: float) -> Tuple[str, str, Dict]:
    """Return (status, ship_reason, gate_dict)."""
    n_rows = inv.get("rows_player_prop", 0)
    n_books = len(inv.get("books", []))
    n_dates = len(inv.get("dates", []))
    per_stat = inv.get("per_stat", {})
    min_per_stat = min(per_stat.values()) if per_stat else 0

    pass_rows      = n_rows >= GATE_MIN_ROWS
    pass_books     = n_books >= GATE_MIN_BOOKS
    pass_dates     = n_dates >= GATE_MIN_DATES
    pass_per_stat  = min_per_stat >= GATE_MIN_PER_STAT
    pass_join      = join_pct >= GATE_MIN_JOIN_PCT

    gate = {
        "rows":      {"value": n_rows,        "min": GATE_MIN_ROWS,     "pass": pass_rows},
        "books":     {"value": n_books,       "min": GATE_MIN_BOOKS,    "pass": pass_books},
        "dates":     {"value": n_dates,       "min": GATE_MIN_DATES,    "pass": pass_dates},
        "per_stat":  {"value": min_per_stat,  "min": GATE_MIN_PER_STAT, "pass": pass_per_stat},
        "join_pct":  {"value": round(join_pct, 2), "min": GATE_MIN_JOIN_PCT, "pass": pass_join},
    }
    failures = [k for k, v in gate.items() if not v["pass"]]
    if not failures:
        return "SHIP", "all gates passed", gate

    # If we have no rows at all, that's BLOCKED, not just REJECT.
    if n_rows == 0:
        return "BLOCKED", "no prop-line rows persisted (primary + fallback both failed)", gate

    if n_rows < 1000:
        return "BLOCKED", f"only {n_rows} rows persisted (<1000 - both paths failed)", gate

    reason = f"failed gates: {','.join(failures)}"
    return "REJECT", reason, gate


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_probe() -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(LINES_DIR, exist_ok=True)

    primary_summary: Dict = {"status": "SKIPPED", "rows_written": 0,
                              "reason": "no_api_key"}
    fallback_summary: Dict = {"status": "SKIPPED", "rows_written": 0}

    api_key = os.environ.get("ODDS_API_KEY") or ""
    if api_key:
        _log("ODDS_API_KEY present; attempting odds-api primary backfill")
        try:
            primary_summary = _odds_api_backfill(api_key)
        except Exception as e:  # noqa: BLE001 - never crash, write JSON instead
            _log(f"odds-api primary raised: {type(e).__name__}: {e}")
            primary_summary = {
                "status": "EXCEPTION",
                "rows_written": 0,
                "reason": f"{type(e).__name__}: {e}",
            }
    else:
        _log("ODDS_API_KEY absent - skipping primary path, using fallback only")

    # If primary path didn't acquire anything, try fallback.  Even if primary
    # ran successfully we still record a fallback attempt only if it actually
    # added rows (it never does for player props, so this is a no-op in
    # practice but keeps the code honest).
    if primary_summary.get("rows_written", 0) == 0:
        try:
            fallback_summary = _sbr_fallback()
        except Exception as e:  # noqa: BLE001
            _log(f"SBR fallback raised: {type(e).__name__}: {e}")
            fallback_summary = {
                "status": "EXCEPTION",
                "rows_written": 0,
                "reason": f"{type(e).__name__}: {e}",
            }

    # ---- Inventory on disk + gate evaluation -------------------------------
    inv = _inventory_lines_dir()
    join_pct, n_resolved, n_total_ledger = _measure_ledger_join_pct()
    status, ship_reason, gate = _evaluate_gate(inv, join_pct)

    # Rows THIS probe contributed (vs total already on disk from prior cycles)
    rows_contributed = (
        primary_summary.get("rows_written", 0)
        + fallback_summary.get("rows_written", 0)
    )

    # If neither acquisition path produced ANY player-prop rows in the
    # 2024-25 schema, the spec's BLOCKED condition is met regardless of
    # what stale data sits on disk from earlier cycles (PrizePicks intraday
    # snapshots from 2026-05-25, etc.).
    if rows_contributed < 1000 and status != "SHIP":
        status = "BLOCKED"
        reasons = []
        if not api_key:
            reasons.append("ODDS_API_KEY env var absent")
        else:
            reasons.append(
                f"odds-api primary: {primary_summary.get('status', '?')} "
                f"({primary_summary.get('reason', 'unknown')})"
            )
        reasons.append(
            f"SBR fallback: {fallback_summary.get('status', '?')} - "
            f"{fallback_summary.get('reason', 'unknown')} "
            f"(public archive only carries game lines through 2021 season "
            f"and has no player props for any season)"
        )
        ship_reason = (
            f"both acquisition paths failed to produce >=1000 player-prop "
            f"rows this run (contributed={rows_contributed}). "
            + " | ".join(reasons)
        )

    result = {
        "probe": "R9_C1_historical_line_backfill",
        "status": status,
        "ship_reason": ship_reason,
        "rows_written": rows_contributed,
        "rows_on_disk_total": inv.get("rows_player_prop", 0),
        "books_covered": inv.get("books", []),
        "dates_covered": len(inv.get("dates", [])),
        "ledger_join_pct": round(join_pct, 2),
        "ledger_join_detail": {
            "n_total":    n_total_ledger,
            "n_resolved": n_resolved,
        },
        "per_stat_rows": inv.get("per_stat", {}),
        "gate": gate,
        "primary_path":  primary_summary,
        "fallback_path": fallback_summary,
        "odds_api_key_present": bool(api_key),
        "lines_dir":     LINES_DIR,
        "ran_at":        datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }

    with open(RESULT_PATH, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    _log(f"result -> {RESULT_PATH} (status={status})")

    print("\n=== R9_C1_historical_line_backfill RESULT ===")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    run_probe()
