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

# Canonical 10-col player-prop schema (matches data/lines/<date>_pp.csv etc.)
PROP_FIELDS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "stat", "line", "over_price", "under_price", "start_time",
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

def _http_get_json(url: str, timeout: float = 12.0) -> Tuple[int, Any]:
    """GET url and JSON-parse. Try curl_cffi first (browser-impersonating);
    fall back to vanilla requests. Returns (status_code, parsed_or_None).
    """
    # Try curl_cffi with chrome120 impersonation.
    try:
        from curl_cffi import requests as cr  # type: ignore
        r = cr.get(url, impersonate="chrome120", timeout=timeout)
        if r.status_code == 200:
            try:
                return 200, r.json()
            except Exception:                                       # noqa: BLE001
                return 200, None
        return r.status_code, None
    except Exception as e:                                          # noqa: BLE001
        log.warning("curl_cffi failed for %s: %s -- falling back to requests", url, e)

    # Vanilla requests fallback.
    try:
        import requests
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 (compatible; pinnacle-scraper/1.0)"})
        if r.status_code == 200:
            try:
                return 200, r.json()
            except Exception:                                       # noqa: BLE001
                return 200, None
        return r.status_code, None
    except Exception as e:                                          # noqa: BLE001
        log.error("requests also failed for %s: %s", url, e)
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
    return {
        "captured_at": captured_at,
        "book":        "pin",
        "game_id":     game_id,
        "player_id":   "",
        "player_name": player_name,
        "stat":        stat,
        "line":        line,
        "over_price":  over_price,
        "under_price": under_price,
        "start_time":  start_time,
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

def _write_csv(path: str, fields: List[str], rows: List[Dict[str, Any]],
               dedup_key: Optional[Tuple[str, ...]] = None) -> int:
    """Append rows to path; create with header if missing. Returns rows written.
    Optionally deduplicates against existing keys when dedup_key is provided.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing_keys: Set[Tuple[Any, ...]] = set()
    if dedup_key and os.path.exists(path):
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                existing_keys.add(tuple(r.get(k, "") for k in dedup_key))
    new_file = not os.path.exists(path)
    written = 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for row in rows:
            if dedup_key:
                k = tuple(str(row.get(c, "")) for c in dedup_key)
                # Match the file read which produces strings; ensure same shape.
                if k in existing_keys:
                    continue
                existing_keys.add(k)
            w.writerow(row)
            written += 1
    return written


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
        try:
            run_once(fetch_props=not args.no_props)
        except Exception as e:                                      # noqa: BLE001
            log.exception("tick failed: %s", e)
        time.sleep(max(60.0, args.interval_min * 60.0))


if __name__ == "__main__":
    sys.exit(main())
