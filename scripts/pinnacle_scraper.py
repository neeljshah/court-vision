"""pinnacle_scraper.py - Pinnacle NBA mainline + player-prop scraper (R15).

Why Pinnacle
------------
Pinnacle is the sharpest sportsbook (lowest vig, highest limits, most
market-efficient). For CLV measurement, Pinnacle's closing line is the closest
thing to a "true" market price: comparing our model's q50 to Pinnacle's close
gives a much cleaner edge signal than DraftKings (higher vig, slower moves).

Public guest API
----------------
`guest.api.arcadia.pinnacle.com` is unauthenticated. Two endpoint groups:

    /0.1/leagues/487/matchups                        -> game + special metadata
    /0.1/leagues/487/markets/straight                -> mainline prices (parent games)
    /0.1/matchups/<parent_id>/markets/related/straight -> ALL markets for a game
                                                       (mainline + ALL player props
                                                        for that game in one call)

NBA league ID = 487. Sport ID = 4.

`matchups` returns ~60 records per slate: a few parent (game-level) matchups
and many derived "special" matchups (one per player-prop OU). For each derived
matchup with `type=="special"` and `special.category=="Player Props"`, the
`special.description` is "<Player Name> Total <Stat>" and the `units` field
gives the stat (Points / Rebounds / Assists / Threes / Blocks / Steals /
Turnovers). The parent game is reachable via `parent.id`.

Schemas (two output files per run)
----------------------------------
A) `data/lines/<date>_pin.csv`  (player props -- canonical 10-col)
   captured_at, book, game_id, player_id, player_name, stat, line,
   over_price, under_price, start_time

B) `data/lines/<date>_pin_mainline.csv` (game lines -- extended)
   captured_at, book, game_id, market_type, side, line, price,
   home_team, away_team, start_time

CLI
---
    python scripts/pinnacle_scraper.py --once
    python scripts/pinnacle_scraper.py --interval-min 10        # daemon
    python scripts/pinnacle_scraper.py --once --no-props        # mainline only

Daemon launch:
    nohup python scripts/pinnacle_scraper.py --interval-min 10 \\
        > vault/Improvements/pinnacle_scraper.log 2>&1 &
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
from typing import Any, Dict, List, Optional, Set, Tuple

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


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

log = logging.getLogger("pinnacle_scraper")
if not log.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] %(message)s",
                                     datefmt="%Y-%m-%dT%H:%M:%S"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


# ── constants ────────────────────────────────────────────────────────────────

NBA_LEAGUE_ID = 487
_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"

# Canonical player-prop schema (matches data/lines/<date>_pp.csv etc.)
# book_selection_id_* added for deeplink parity with DK/FD scrapers.
# Pinnacle's public API does not expose per-outcome IDs, so these are
# always empty strings — the event-page deeplink uses game_id instead.
PROP_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
    "book_selection_id_over", "book_selection_id_under",
]

# Mainline schema (separate because mainline is not player-keyed).
MAINLINE_FIELDS = [
    "captured_at", "book", "game_id", "market_type", "side", "line", "price",
    "home_team", "away_team", "start_time",
]

# Pinnacle "units" string -> canonical stat code.
_UNITS_TO_STAT = {
    "points":     "pts",
    "rebounds":   "reb",
    "assists":    "ast",
    "threes":     "fg3m",
    "3-pointers": "fg3m",
    "3 pointers": "fg3m",
    "made threes": "fg3m",
    "blocks":     "blk",
    "steals":     "stl",
    "turnovers":  "tov",
}

# Fallback: scan special.description for keyword if units is missing/odd.
_DESC_KW_STAT: List[Tuple[str, str]] = [
    ("total points",     "pts"),
    ("total rebounds",   "reb"),
    ("total assists",    "ast"),
    ("total threes",     "fg3m"),
    ("total 3-pointers", "fg3m"),
    ("total blocks",     "blk"),
    ("total steals",     "stl"),
    ("total turnovers",  "tov"),
]

_LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache")


# ── HTTP ─────────────────────────────────────────────────────────────────────

# R23_P4: persistent sessions for connection / TLS reuse. The original
# implementation called `cr.get(...)` per request, which forced a fresh TLS
# handshake (and often a fresh DNS lookup) for every endpoint hit. On a 5-min
# capture L6 measured p99 going from 886ms -> 2389ms (+170%); the cold-call
# tail is dominated by the handshake (~120-170ms locally vs ~50-65ms warm).
# A module-scoped Session keeps the connection pool hot and amortises the
# handshake across all calls in a tick (and across ticks too).

_CURL_SESSION: Any = None
_REQ_SESSION: Any = None
# Default headers that match a real browser; sent on every request.
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


def _get_curl_session() -> Any:
    """Lazily build and reuse a curl_cffi Session with chrome120 impersonation.

    Returns None if curl_cffi is unavailable so callers can fall back.
    """
    global _CURL_SESSION
    if _CURL_SESSION is not None:
        return _CURL_SESSION
    try:
        from curl_cffi import requests as cr  # type: ignore
        s = cr.Session()
        # Impersonation on session means every request shares the same JA3
        # fingerprint without re-negotiating the impersonation profile.
        try:
            s.impersonate = "chrome120"  # type: ignore[attr-defined]
        except Exception:                                           # noqa: BLE001
            pass
        try:
            s.headers.update(_DEFAULT_HEADERS)
        except Exception:                                           # noqa: BLE001
            pass
        _CURL_SESSION = s
        return _CURL_SESSION
    except Exception as e:                                          # noqa: BLE001
        log.warning("curl_cffi unavailable: %s", e)
        _CURL_SESSION = False  # sentinel: don't retry import every call
        return None


def _get_requests_session() -> Any:
    """Lazily build a persistent `requests` Session as the fallback transport."""
    global _REQ_SESSION
    if _REQ_SESSION is not None:
        return _REQ_SESSION
    try:
        import requests
        from requests.adapters import HTTPAdapter
        s = requests.Session()
        # Bump pool size so concurrent ticks don't churn connections.
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=10)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers.update(_DEFAULT_HEADERS)
        _REQ_SESSION = s
        return _REQ_SESSION
    except Exception as e:                                          # noqa: BLE001
        log.error("requests unavailable: %s", e)
        _REQ_SESSION = False
        return None


def _reset_sessions() -> None:
    """Test / probe helper: drop the cached sessions so a cold path can be
    re-measured. Not used in production code paths."""
    global _CURL_SESSION, _REQ_SESSION
    for s in (_CURL_SESSION, _REQ_SESSION):
        if s and s is not False:
            try:
                s.close()
            except Exception:                                       # noqa: BLE001
                pass
    _CURL_SESSION = None
    _REQ_SESSION = None


def _http_get_json(url: str, timeout: float = 12.0) -> Tuple[int, Any]:
    """GET url and JSON-parse. Uses a persistent curl_cffi Session
    (chrome120 fingerprint) so TLS + TCP are amortised across calls; falls
    back to a persistent `requests` Session on curl_cffi failure.
    Returns (status_code, parsed_or_None).
    """
    sess = _get_curl_session()
    if sess is not None and sess is not False:
        try:
            # Per-request impersonate keeps backward-compatible with older
            # curl_cffi builds where Session.impersonate attribute is ignored.
            r = sess.get(url, impersonate="chrome120", timeout=timeout)
            if r.status_code == 200:
                try:
                    return 200, r.json()
                except Exception:                                   # noqa: BLE001
                    return 200, None
            return r.status_code, None
        except Exception as e:                                      # noqa: BLE001
            log.warning("curl_cffi session failed for %s: %s -- falling back", url, e)

    # Vanilla requests fallback (also session-pooled).
    req_sess = _get_requests_session()
    if req_sess is None or req_sess is False:
        return 0, None
    try:
        r = req_sess.get(url, timeout=timeout)
        if r.status_code == 200:
            try:
                return 200, r.json()
            except Exception:                                       # noqa: BLE001
                return 200, None
        return r.status_code, None
    except Exception as e:                                          # noqa: BLE001
        log.error("requests session failed for %s: %s", url, e)
        return 0, None


# ── time helpers ─────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _today_iso() -> str:
    return _date.today().isoformat()


# ── parsing ──────────────────────────────────────────────────────────────────

def _stat_from_units_and_desc(units: Optional[str], desc: Optional[str]) -> Optional[str]:
    u = (units or "").lower().strip()
    if u in _UNITS_TO_STAT:
        return _UNITS_TO_STAT[u]
    d = (desc or "").lower()
    for kw, code in _DESC_KW_STAT:
        if kw in d:
            return code
    return None


def _player_from_description(desc: Optional[str], units: Optional[str]) -> str:
    """Pinnacle special.description = '<Player Name> Total <Stat>' typically.
    Strip the trailing 'Total <units>' suffix to recover the player.
    """
    if not desc:
        return ""
    d = desc.strip()
    # Try '<name> Total <units>' first.
    if units:
        tail = f" Total {units}"
        if d.lower().endswith(tail.lower()):
            return d[: -len(tail)].strip()
    # Generic 'Total <something>' tail stripper.
    low = d.lower()
    idx = low.rfind(" total ")
    if idx > 0:
        return d[:idx].strip()
    return d


def _team_names(participants: List[Dict[str, Any]]) -> Tuple[str, str]:
    home, away = "", ""
    for p in participants or []:
        align = (p.get("alignment") or "").lower()
        name = p.get("name") or ""
        if align == "home":
            home = name
        elif align == "away":
            away = name
    return home, away


# ── canonical row builders ───────────────────────────────────────────────────

def _build_prop_row(
    *,
    captured_at: str,
    game_id: str,
    player_name: str,
    stat: str,
    line: Any,
    over_price: Any,
    under_price: Any,
    start_time: str,
) -> Dict[str, Any]:
    # Pinnacle's public API does not expose per-outcome/selection IDs.
    # The event-page deeplink uses game_id (parent matchup ID) instead.
    return {
        "captured_at":             captured_at,
        "book":                    "pin",
        "game_id":                 game_id,
        "player_id":               "",
        "player_name":             player_name,
        "stat":                    stat,
        "line":                    line,
        "over_price":              over_price,
        "under_price":             under_price,
        "start_time":              start_time,
        "book_selection_id_over":  "",
        "book_selection_id_under": "",
    }


def _build_mainline_row(
    *,
    captured_at: str,
    game_id: str,
    market_type: str,
    side: str,
    line: Any,
    price: Any,
    home: str,
    away: str,
    start_time: str,
) -> Dict[str, Any]:
    return {
        "captured_at": captured_at,
        "book":        "pin",
        "game_id":     game_id,
        "market_type": market_type,
        "side":        side,
        "line":        line if line is not None else "",
        "price":       price,
        "home_team":   home,
        "away_team":   away,
        "start_time":  start_time,
    }


# ── core scrape ──────────────────────────────────────────────────────────────

def fetch_matchups() -> Tuple[int, List[Dict[str, Any]]]:
    """Return (status_code, matchups_list) for league 487."""
    code, data = _http_get_json(f"{_BASE}/leagues/{NBA_LEAGUE_ID}/matchups")
    if code != 200 or not isinstance(data, list):
        return code, []
    return code, data


def fetch_league_straight_markets() -> Tuple[int, List[Dict[str, Any]]]:
    """Return (status_code, markets_list) for the parent-game mainline markets."""
    code, data = _http_get_json(f"{_BASE}/leagues/{NBA_LEAGUE_ID}/markets/straight")
    if code != 200 or not isinstance(data, list):
        return code, []
    return code, data


def fetch_related_markets(parent_id: int) -> Tuple[int, List[Dict[str, Any]]]:
    """Return (status_code, markets_list) for one parent game + all its props."""
    code, data = _http_get_json(
        f"{_BASE}/matchups/{parent_id}/markets/related/straight"
    )
    if code != 200 or not isinstance(data, list):
        return code, []
    return code, data


def parse_player_props(
    matchups: List[Dict[str, Any]],
    related_markets_by_parent: Dict[int, List[Dict[str, Any]]],
    captured_at: str,
) -> List[Dict[str, Any]]:
    """Build canonical prop rows from matchups + per-parent related markets."""
    # Build matchupId -> markets index (we'll use the s;0;ou totals).
    market_by_matchup: Dict[int, Dict[str, Any]] = {}
    for parent_id, markets in related_markets_by_parent.items():
        for m in markets:
            mid = m.get("matchupId")
            # Player props are always type=total with key starting s;0;ou
            if (m.get("type") == "total"
                    and str(m.get("key", "")).startswith("s;0;ou")
                    and mid is not None):
                # Prefer non-alternate primary line; keep first seen otherwise.
                if mid not in market_by_matchup or not m.get("isAlternate", False):
                    market_by_matchup[mid] = m

    rows: List[Dict[str, Any]] = []
    for mu in matchups:
        if mu.get("type") != "special":
            continue
        special = mu.get("special") or {}
        if (special.get("category") or "").lower() != "player props":
            continue
        units = mu.get("units")
        desc = special.get("description")
        stat = _stat_from_units_and_desc(units, desc)
        if not stat:
            continue
        player = _player_from_description(desc, units)
        if not player:
            continue
        mid = mu.get("id")
        parent_id = mu.get("parentId")
        start_time = mu.get("startTime") or ""
        mk = market_by_matchup.get(mid)
        if not mk:
            continue
        prices = mk.get("prices") or []
        if len(prices) < 2:
            continue
        # Over/under: participants in matchup tell us which participantId is which.
        over_pid: Optional[int] = None
        under_pid: Optional[int] = None
        for p in mu.get("participants") or []:
            nm = (p.get("name") or "").lower()
            if nm == "over":
                over_pid = p.get("id")
            elif nm == "under":
                under_pid = p.get("id")
        over_price: Optional[int] = None
        under_price: Optional[int] = None
        line: Any = None
        for pr in prices:
            pid = pr.get("participantId")
            pts = pr.get("points")
            if line is None and pts is not None:
                line = pts
            if pid == over_pid:
                over_price = pr.get("price")
            elif pid == under_pid:
                under_price = pr.get("price")
        if over_price is None or under_price is None or line is None:
            continue
        rows.append(_build_prop_row(
            captured_at=captured_at,
            game_id=str(parent_id) if parent_id is not None else "",
            player_name=player,
            stat=stat,
            line=line,
            over_price=over_price,
            under_price=under_price,
            start_time=start_time,
        ))
    return rows


def parse_mainline(
    matchups: List[Dict[str, Any]],
    league_markets: List[Dict[str, Any]],
    captured_at: str,
) -> List[Dict[str, Any]]:
    """Build mainline rows (moneyline/spread/total) from league straight markets."""
    # parent matchups carry team names; index by id.
    parent_by_id: Dict[int, Dict[str, Any]] = {}
    for mu in matchups:
        if mu.get("type") != "special" and mu.get("parentId") is None:
            mid = mu.get("id")
            if mid is not None:
                parent_by_id[mid] = mu
    rows: List[Dict[str, Any]] = []
    for mk in league_markets:
        matchup_id = mk.get("matchupId")
        parent = parent_by_id.get(matchup_id)
        if not parent:
            continue
        # Skip non-zero periods (Q1/H1 etc.) -- mainline = period 0 only.
        if mk.get("period") != 0:
            continue
        home, away = _team_names(parent.get("participants") or [])
        start_time = parent.get("startTime") or ""
        mtype = mk.get("type")
        prices = mk.get("prices") or []
        if mtype == "moneyline":
            for pr in prices:
                rows.append(_build_mainline_row(
                    captured_at=captured_at,
                    game_id=str(matchup_id),
                    market_type="moneyline",
                    side=(pr.get("designation") or ""),
                    line=None,
                    price=pr.get("price"),
                    home=home, away=away,
                    start_time=start_time,
                ))
        elif mtype == "total":
            # totals: 2 prices, one Over (participants order=0) one Under (order=1).
            # `designation` is missing for totals; use participant order via matchup.
            # Simpler: pair by index — first price is over, second under, per Pinnacle.
            for idx, pr in enumerate(prices):
                rows.append(_build_mainline_row(
                    captured_at=captured_at,
                    game_id=str(matchup_id),
                    market_type="total",
                    side="over" if idx == 0 else "under",
                    line=pr.get("points"),
                    price=pr.get("price"),
                    home=home, away=away,
                    start_time=start_time,
                ))
        elif mtype == "spread":
            for pr in prices:
                rows.append(_build_mainline_row(
                    captured_at=captured_at,
                    game_id=str(matchup_id),
                    market_type="spread",
                    side=(pr.get("designation") or ""),
                    line=pr.get("points"),
                    price=pr.get("price"),
                    home=home, away=away,
                    start_time=start_time,
                ))
        # team_total and other types are skipped from the mainline file.
    return rows


# ── IO ───────────────────────────────────────────────────────────────────────

# R23_P4: per-path dedup-key cache. The original implementation re-read the
# entire CSV from disk on every `_write_csv` call to rebuild the dedup set.
# As the daily pin.csv grows (250+ rows after a few hours, ~1500+ by EoD),
# that O(N) read+parse fired on every tick and was a silent p99 contributor
# under filesystem contention with other writers.
_DEDUP_CACHE: Dict[str, Set[Tuple[Any, ...]]] = {}


def _load_dedup_keys(path: str, dedup_key: Tuple[str, ...]) -> Set[Tuple[Any, ...]]:
    """Return the cached set of existing dedup-tuples for `path`.
    Bootstraps from disk on the first call per (process, path)."""
    cached = _DEDUP_CACHE.get(path)
    if cached is not None:
        return cached
    keys: Set[Tuple[Any, ...]] = set()
    if os.path.exists(path):
        try:
            with open(path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    keys.add(tuple(r.get(k, "") for k in dedup_key))
        except Exception as e:                                      # noqa: BLE001
            log.warning("dedup cache bootstrap failed for %s: %s", path, e)
            keys = set()
    _DEDUP_CACHE[path] = keys
    return keys


def _write_csv(path: str, fields: List[str], rows: List[Dict[str, Any]],
               dedup_key: Optional[Tuple[str, ...]] = None) -> int:
    """Append rows to path; create with header if missing. Returns rows written.
    Optionally deduplicates against existing keys when dedup_key is provided.

    R23_P4 changes:
      - dedup keys are cached in-process per path (no per-tick CSV re-read)
      - the appended payload is staged into the live file via a buffered write
        and an explicit flush+fsync of the appended bytes, so a concurrent
        reader never sees a torn row mid-line. (We append rather than full
        rewrite-and-replace because pin*.csv is append-only and a full
        rewrite would balloon write cost as the file grows.)
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing_keys: Set[Tuple[Any, ...]]
    if dedup_key:
        existing_keys = _load_dedup_keys(path, dedup_key)
    else:
        existing_keys = set()
    new_file = not os.path.exists(path)

    # Build the rows-to-write list off-line so we hold the file open as
    # briefly as possible (less contention window with concurrent readers).
    to_write: List[Dict[str, Any]] = []
    for row in rows:
        if dedup_key:
            k = tuple(str(row.get(c, "")) for c in dedup_key)
            if k in existing_keys:
                continue
            existing_keys.add(k)
        to_write.append(row)

    if not to_write and not new_file:
        return 0

    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for row in to_write:
            w.writerow(row)
        try:
            f.flush()
            os.fsync(f.fileno())
        except (OSError, ValueError):
            # fsync may fail on some Windows handles; safe to skip.
            pass
    return len(to_write)


# ── public top-level: one tick ───────────────────────────────────────────────

def run_once(*, fetch_props: bool = True) -> Dict[str, Any]:
    """Execute one scrape tick. Returns a summary dict for logging/probe results."""
    captured_at = _now_iso()
    today = _today_iso()
    summary: Dict[str, Any] = {
        "captured_at": captured_at,
        "endpoints_tried": [],
        "status_codes": {},
        "n_matchups": 0,
        "n_parent_games": 0,
        "n_player_props": 0,
        "n_mainline_rows_written": 0,
        "n_prop_rows_written": 0,
        "errors": [],
    }
    # 1. matchups
    summary["endpoints_tried"].append("matchups")
    code_mu, matchups = fetch_matchups()
    summary["status_codes"]["matchups"] = code_mu
    summary["n_matchups"] = len(matchups)
    if not matchups:
        summary["errors"].append("matchups empty or failed")
        return summary

    # 2. mainline league markets
    summary["endpoints_tried"].append("league_markets_straight")
    code_lm, league_markets = fetch_league_straight_markets()
    summary["status_codes"]["league_markets_straight"] = code_lm

    mainline_rows = parse_mainline(matchups, league_markets, captured_at)
    summary["n_parent_games"] = len({m.get("game_id") for m in mainline_rows})

    if mainline_rows:
        mainline_path = os.path.join(_LINES_DIR, f"{today}_pin_mainline.csv")
        # Dedup at minute resolution on (game_id, market_type, side, line, captured_at).
        for r in mainline_rows:
            r["captured_at"] = r["captured_at"][:16]  # YYYY-MM-DDTHH:MM
        n = _write_csv(mainline_path, MAINLINE_FIELDS, mainline_rows,
                       dedup_key=("captured_at", "game_id", "market_type", "side", "line"))
        summary["n_mainline_rows_written"] = n
        log.info("mainline: wrote %d rows -> %s", n, mainline_path)

    # 3. player props -- fetch per-parent related markets.
    if fetch_props:
        parent_ids = sorted({mu.get("id") for mu in matchups
                             if mu.get("type") != "special" and mu.get("id") is not None})
        related_by_parent: Dict[int, List[Dict[str, Any]]] = {}
        for pid in parent_ids:
            summary["endpoints_tried"].append(f"related/{pid}")
            code_rel, related = fetch_related_markets(pid)
            summary["status_codes"][f"related/{pid}"] = code_rel
            if related:
                related_by_parent[pid] = related
            # be polite -- public API but we don't need to hammer.
            time.sleep(0.4)
        prop_rows = parse_player_props(matchups, related_by_parent, captured_at)
        summary["n_player_props"] = len(prop_rows)
        if prop_rows:
            prop_path = os.path.join(_LINES_DIR, f"{today}_pin.csv")
            for r in prop_rows:
                r["captured_at"] = r["captured_at"][:16]
            n = _write_csv(prop_path, PROP_FIELDS, prop_rows,
                           dedup_key=("captured_at", "player_name", "stat", "line"))
            summary["n_prop_rows_written"] = n
            log.info("props: wrote %d rows -> %s", n, prop_path)
    return summary


def scrape_once() -> List[Dict[str, Any]]:
    """Entry point for parallel_scraper.py.

    Delegates to run_once() which writes data/lines/<date>_pin.csv directly.
    Returns [] to prevent parallel_scraper from double-writing the same rows.
    """
    try:
        run_once(fetch_props=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("pinnacle scrape_once failed: %s", exc)
    return []


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true",
                   help="single fetch and exit")
    p.add_argument("--interval-min", type=float, default=10.0,
                   help="daemon poll interval (minutes); ignored if --once")
    p.add_argument("--no-props", action="store_true",
                   help="skip player-prop fetching (mainline only)")
    args = p.parse_args(argv)

    if args.once:
        summary = run_once(fetch_props=not args.no_props)
        log.info("summary: %s", {k: v for k, v in summary.items()
                                 if k in ("n_matchups", "n_player_props",
                                          "n_prop_rows_written",
                                          "n_mainline_rows_written")})
        return 0

    log.info("Pinnacle scraper daemon -- interval %.1f min", args.interval_min)
    while True:
        # R19_L3 heartbeat
        _r19_hb('pinnacle_scraper')
        try:
            run_once(fetch_props=not args.no_props)
        except Exception as e:                                      # noqa: BLE001
            log.exception("tick failed: %s", e)
        time.sleep(max(60.0, args.interval_min * 60.0))


if __name__ == "__main__":
    sys.exit(main())
