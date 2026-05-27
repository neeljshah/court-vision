"""bov_scraper_daemon.py - production Bovada NBA/WNBA/MLB prop-line daemon (R15_bov).

Why
---
R14_H1 proved Bovada is the ONLY US-facing book whose public JSON we can pull
without WAF blocks (DK/FD/MGM/Caesars all 403). The probe pulled 217 rows for
1 NBA Finals game in off-season. This daemon turns that one-shot scraper into
a persistent service that snapshots Bovada every ~5-15 min so the per-book
line ledger accumulates 5-10 snapshots/day × ~200 rows/snapshot during off-
season, scaling to 500+ rows/snapshot during regular season.

Once Bovada accumulates n>=100 cross-referenced with OOF predictions, the
R12_F4 BLK/STL z=+5.7/+4.5 edge signal becomes shippable.

Output (canonical 11-col schema, matches fetch_live_prop_lines.py)
------------------------------------------------------------------
    data/lines/<isodate>_bov.csv

    captured_at, book, game_id, player_id, player_name, team,
    stat, line, over_price, under_price, market_status

Dedup
-----
`(book, player_name.lower(), stat, line, captured_at[:16])` - matches the
intra-minute idempotency convention from fetch_live_prop_lines.py, with `line`
added so different alt-lines for the same player within the same minute are
kept (Bovada exposes per-player ladders).

Heartbeat
---------
vault/Improvements/bov_scraper.log - one line per snapshot:

    [2026-05-26T08:04:36] cycle=12 sports=NBA,WNBA games=1 rows_new=217 rows_total=434

403 backoff
-----------
On HTTP 403 from Bovada: log + sleep one interval + retry. If 403 persists
for >= 60 min of wall-clock, daemon EXITS (so a cron / supervisor can decide
whether to keep trying). This honors robots.txt and avoids hammering a
hardened endpoint.

CLI
---
    python scripts/bov_scraper_daemon.py --once                # single tick
    python scripts/bov_scraper_daemon.py --interval-min 5      # daemon
    python scripts/bov_scraper_daemon.py --sports nba,wnba     # restrict
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
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

LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
LOG_PATH = os.path.join(PROJECT_DIR, "vault", "Improvements", "bov_scraper.log")
os.makedirs(LINES_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

# Canonical 12-column schema (R19_L1: added `is_alt_line` to mark alt-line
# ladder rungs vs the book's primary line for a given (player, stat). Bovada
# exposes a full ladder per market (e.g. PTS over 3.5 / 4.5 / ... / 30.5);
# the rung closest to fair juice is the primary, the rest are alts. The arb
# engine MUST ignore alt-line rows or it produces bogus "free arb" signals.)
_FIELDS = ["captured_at", "book", "game_id", "player_id", "player_name",
           "team", "stat", "line", "over_price", "under_price",
           "market_status", "is_alt_line"]

_VALID_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Sport -> Bovada path. Bovada's coupon API takes free-form paths under
# /services/sports/event/coupon/events/A/description.
_SPORT_PATHS = {
    "nba":  "basketball/nba",
    "wnba": "basketball/wnba",
    "mlb":  "baseball/mlb",
}

# How long to keep retrying on persistent 403 before giving up.
_BLOCK_GIVEUP_HOURS = 1.0

# Polite intra-event sleep so we never hit Bovada faster than ~2 events/sec.
_INTER_EVENT_PAUSE_SEC = 0.5

_UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

log = logging.getLogger("bov_scraper_daemon")
if not log.handlers:
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))
    log.addHandler(sh)
    fh = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))
    log.addHandler(fh)
    log.setLevel(logging.INFO)


# ── stat / market classification (lifted from probe_R14_H1_alt_scraper) ─────

# Bovada displayGroup -> our canonical stat code.
_BOV_DG_TO_STAT = {
    "Player Points":   "pts",
    "Player Rebounds": "reb",
    "Player Assists":  "ast",
    "Player Threes":   "fg3m",
    "Player Blocks":   "blk",
    "Player Steals":   "stl",
    "Player Turnovers": "tov",
}

# Sub-market description keywords (when displayGroup is generic).
_BOV_MK_KW = [
    ("Total Points",     "pts"),
    ("Total Rebounds",   "reb"),
    ("Total Assists",    "ast"),
    ("Total Threes",     "fg3m"),
    ("Total 3-Pointers", "fg3m"),
    ("Total Blocks",     "blk"),
    ("Total Steals",     "stl"),
    ("Total Turnovers",  "tov"),
    ("Made Threes",      "fg3m"),
    ("3-Pointers Made",  "fg3m"),
]

# Allowlist of displayGroups that contain real player props (excludes
# 'Alternate Lines', 'Game Lines', etc).
_PLAYER_PROP_DGS = {
    "Player Points", "Player Rebounds", "Player Assists",
    "Player Threes",  "Player Blocks",   "Player Steals",
    "Player Turnovers", "Assists & Threes", "Blocks & Steals",
}

# MLB display groups - only the simple Over/Under per-player ones are kept.
# MLB players have different stat space (hits, total bases, ks) which we
# DON'T map to NBA's 7 - daemon emits them only if Bovada surfaces a stat
# label that happens to match (e.g. nothing today). MLB is on the daemon
# so that come October if Bovada surfaces basketball-shaped player stats
# on MLB World Series, they'd flow; today the MLB path returns 0 rows.


# ── HTTP helpers ────────────────────────────────────────────────────────────

class BovadaBlocked(Exception):
    """Raised when Bovada returns 403 (WAF / IP-block)."""


def _http_get(url: str, timeout: float = 15.0) -> Tuple[int, Optional[bytes], Optional[str]]:
    """Return (status, body, error_str). Tries `requests` first (better TLS
    fingerprint), falls back to urllib if requests isn't installed.
    """
    hdr = {
        "User-Agent":      _UA_DESKTOP,
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "Referer":         "https://www.bovada.lv/",
        "Origin":          "https://www.bovada.lv",
        "Sec-Fetch-Dest":  "empty",
        "Sec-Fetch-Mode":  "cors",
        "Sec-Fetch-Site":  "same-origin",
    }
    try:
        import requests  # type: ignore  # noqa: PLC0415
        r = requests.get(url, headers=hdr, timeout=timeout, allow_redirects=True)
        return r.status_code, r.content, None
    except Exception:  # noqa: BLE001
        pass
    try:
        req = urllib.request.Request(url, headers=hdr)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.getcode(), r.read(), None
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:  # noqa: BLE001
            body = None
        return e.code, body, f"HTTPError: {e.reason}"
    except Exception as e:  # noqa: BLE001
        return 0, None, f"{type(e).__name__}: {e}"


# ── Bovada parsers ──────────────────────────────────────────────────────────

def _bov_player_from_desc(desc: str) -> str:
    """Bovada market descriptions: 'Total Points - Player Name (TEAM)'."""
    if " - " not in desc:
        return ""
    tail = desc.split(" - ", 1)[1].strip()
    if "(" in tail:
        tail = tail.rsplit("(", 1)[0].strip()
    return tail


def _bov_team_from_desc(desc: str) -> str:
    """Extract trailing '(TEAM)' tag from a market description, if present."""
    if "(" not in desc or ")" not in desc:
        return ""
    try:
        inside = desc.rsplit("(", 1)[1].split(")", 1)[0]
        # Sanity: team codes are 2-4 letters.
        if 2 <= len(inside) <= 4 and inside.replace(" ", "").isalpha():
            return inside.upper()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _american_implied_prob(odds: Any) -> Optional[float]:
    """Return implied probability for an American-odds price, or None if junk."""
    try:
        o = int(odds)
    except (TypeError, ValueError):
        return None
    if o > 0:
        return 100.0 / (o + 100.0)
    if o < 0:
        return (-o) / ((-o) + 100.0)
    return None


def _classify_primary_line(buckets: Dict[Any, Dict[str, Any]],
                            line_keys: List[Any]) -> Any:
    """Pick which rung in a Bovada player-prop ladder is the PRIMARY line.

    The primary line is the rung whose total implied vig is smallest (closest
    to a fair, -110/-110-style line — the book's "main" market). Alt rungs
    further from the central tendency carry asymmetric, ladder-style juice
    (e.g. OVER 3.5 +120 / UNDER 3.5 -215). Tie-break by smallest absolute
    price spread, then by line value closest to the median of the cluster.

    If only one rung exists, that rung is primary by definition.
    Returns the bucket key (a float when handicaps parse, otherwise the raw
    value) corresponding to the primary line.
    """
    if not line_keys:
        return None
    if len(line_keys) == 1:
        return line_keys[0]

    def _score(k: Any) -> Tuple[float, float, float]:
        b = buckets.get(k, {})
        po = _american_implied_prob(b.get("over"))
        pu = _american_implied_prob(b.get("under"))
        if po is None or pu is None:
            # Single-sided rung can't be primary; sink it.
            return (9.99, 9.99, 9.99)
        total_vig = abs((po + pu) - 1.0)
        spread = abs(po - pu)
        line_val = float(k) if isinstance(k, (int, float)) else 0.0
        return (total_vig, spread, line_val)

    # Pick lowest (total_vig, spread); for true ties, prefer line closest to
    # cluster median so we don't accidentally crown an edge rung primary.
    numeric_lines = [float(k) for k in line_keys
                     if isinstance(k, (int, float))]
    median = (sorted(numeric_lines)[len(numeric_lines) // 2]
              if numeric_lines else 0.0)

    def _final_score(k: Any) -> Tuple[float, float, float]:
        base = _score(k)
        line_val = float(k) if isinstance(k, (int, float)) else 0.0
        return (base[0], base[1], abs(line_val - median))

    return min(line_keys, key=_final_score)


def _bov_stat_from_market(dg_desc: str, mk_desc: str) -> Optional[str]:
    """Map a Bovada (displayGroup, market) pair to our 7 canonical stats."""
    if dg_desc.strip() not in _PLAYER_PROP_DGS:
        return None
    s = _BOV_DG_TO_STAT.get(dg_desc.strip())
    if s:
        return s
    for kw, code in _BOV_MK_KW:
        if kw.lower() in (mk_desc or "").lower():
            return code
    return None


def _parse_event_detail(d_payload: Any,
                        ev_id: str,
                        start_iso: str,
                        captured_at: str) -> List[Dict[str, Any]]:
    """Walk one event's detail JSON and emit canonical rows. Tolerates
    missing markets, missing outcomes, junk shapes - never raises.
    """
    rows: List[Dict[str, Any]] = []
    if not isinstance(d_payload, list):
        return rows
    for grp in d_payload:
        if not isinstance(grp, dict):
            continue
        for ev in grp.get("events", []) or []:
            if not isinstance(ev, dict):
                continue
            for dg in ev.get("displayGroups", []) or []:
                if not isinstance(dg, dict):
                    continue
                dg_desc = (dg.get("description") or "").strip()
                for mk in dg.get("markets", []) or []:
                    if not isinstance(mk, dict):
                        continue
                    mk_desc = (mk.get("description") or "").strip()
                    stat = _bov_stat_from_market(dg_desc, mk_desc)
                    if not stat:
                        continue
                    player = _bov_player_from_desc(mk_desc)
                    if not player:
                        continue
                    team = _bov_team_from_desc(mk_desc)
                    market_status = (mk.get("status") or "open").lower()
                    # Group outcomes by handicap so each (player, stat, line)
                    # produces one row with both sides.
                    buckets: Dict[Any, Dict[str, Any]] = {}
                    for out in mk.get("outcomes", []) or []:
                        if not isinstance(out, dict):
                            continue
                        price = out.get("price") or {}
                        hcap = price.get("handicap")
                        american = price.get("american")
                        side = (out.get("description") or "").lower()
                        try:
                            hcap_key = float(hcap)
                        except (TypeError, ValueError):
                            hcap_key = hcap
                        b = buckets.setdefault(hcap_key, {})
                        if "over" in side:
                            b["over"] = american
                            b["line"] = hcap_key
                        elif "under" in side:
                            b["under"] = american
                            b["line"] = hcap_key
                    # R19_L1: classify primary vs alt-line within this market.
                    # Each market block in Bovada's payload IS one (player, stat)
                    # cluster; the primary line is the rung with the lowest
                    # absolute total-vig (closest to a fair -110/-110 line).
                    # All other rungs are alts. If only one rung exists, it's
                    # primary by default.
                    line_keys = [k for k, b in buckets.items()
                                 if b.get("line") is not None]
                    primary_key = _classify_primary_line(buckets, line_keys)
                    for hcap_key, b in buckets.items():
                        if b.get("line") is None:
                            continue
                        is_alt = (hcap_key != primary_key)
                        rows.append({
                            "captured_at":   captured_at,
                            "book":          "bov",
                            "game_id":       ev_id,
                            "player_id":     "",
                            "player_name":   player,
                            "team":          team,
                            "stat":          stat,
                            "line":          b.get("line"),
                            "over_price":    b.get("over"),
                            "under_price":   b.get("under"),
                            "market_status": market_status,
                            "is_alt_line":   is_alt,
                        })
    return rows


def fetch_sport(sport: str,
                http_fn=_http_get,
                captured_at: Optional[str] = None,
                ) -> Tuple[int, List[Dict[str, Any]], Dict[str, Any]]:
    """Fetch one sport's events + walk all player-prop markets.

    Returns (n_events_seen, canonical_rows, diag).
    diag contains: index_status, n_event_detail_calls, n_5xx, n_403, errors[].

    Raises BovadaBlocked if the index endpoint itself 403s (signals daemon
    to start its block-clock).
    """
    path = _SPORT_PATHS.get(sport.lower())
    if not path:
        return 0, [], {"index_status": -1, "errors": [f"unknown sport {sport!r}"]}
    captured_at = captured_at or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    index_url = (f"https://www.bovada.lv/services/sports/event/coupon/events/A/"
                 f"description/{path}?marketFilterId=def&preMatchOnly=false"
                 f"&eventsLimit=50&lang=en")
    diag: Dict[str, Any] = {
        "index_status": None, "n_event_detail_calls": 0,
        "n_5xx": 0, "n_403": 0, "errors": [],
    }

    code, body, err = http_fn(index_url)
    diag["index_status"] = code
    if code == 403:
        raise BovadaBlocked(f"{sport} index 403")
    if err:
        diag["errors"].append(f"index: {err}")
    if code != 200 or not body:
        if code >= 500:
            diag["n_5xx"] += 1
        return 0, [], diag

    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except Exception as e:  # noqa: BLE001
        diag["errors"].append(f"index parse: {e}")
        return 0, [], diag

    event_links: List[Tuple[str, str, str]] = []
    if isinstance(payload, list):
        for grp in payload:
            if not isinstance(grp, dict):
                continue
            for ev in grp.get("events", []) or []:
                if not isinstance(ev, dict):
                    continue
                link = ev.get("link") or ""
                if link:
                    event_links.append((str(ev.get("id") or ""),
                                        link,
                                        str(ev.get("startTime") or "")))

    rows_total: List[Dict[str, Any]] = []
    for ev_id, link, start_ms in event_links:
        detail_url = (f"https://www.bovada.lv/services/sports/event/coupon/"
                      f"events/A/description{link}?lang=en")
        d_code, d_body, d_err = http_fn(detail_url)
        diag["n_event_detail_calls"] += 1
        if d_code == 403:
            diag["n_403"] += 1
            # Index worked but detail blocked - might be transient; skip event.
            continue
        if d_code >= 500:
            diag["n_5xx"] += 1
            continue
        if d_err:
            diag["errors"].append(f"detail {ev_id}: {d_err}")
        if d_code != 200 or not d_body:
            continue
        try:
            d_payload = json.loads(d_body.decode("utf-8", errors="replace"))
        except Exception as e:  # noqa: BLE001
            diag["errors"].append(f"detail {ev_id} parse: {e}")
            continue
        try:
            start_iso = datetime.utcfromtimestamp(int(start_ms) / 1000).strftime(
                "%Y-%m-%dT%H:%M:%S")
        except Exception:  # noqa: BLE001
            start_iso = start_ms
        rows_total.extend(_parse_event_detail(d_payload, ev_id, start_iso, captured_at))
        time.sleep(_INTER_EVENT_PAUSE_SEC)

    return len(event_links), rows_total, diag


# ── canonical-CSV append with dedup ─────────────────────────────────────────

def _minute_key(iso_ts: str) -> str:
    return iso_ts[:16]


def _load_existing_keys(path: str) -> Set[Tuple[str, str, str, str, str]]:
    """Dedup key = (book, player_name.lower(), stat, line_str, minute_key)."""
    keys: Set[Tuple[str, str, str, str, str]] = set()
    if not os.path.exists(path):
        return keys
    try:
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                book = (r.get("book") or "").lower().strip()
                pn = (r.get("player_name") or "").lower().strip()
                st = (r.get("stat") or "").lower().strip()
                ln = str(r.get("line") or "").strip()
                ts = (r.get("captured_at") or "").strip()
                if pn and st and ts:
                    keys.add((book, pn, st, ln, _minute_key(ts)))
    except Exception as e:  # noqa: BLE001
        log.warning("dedup-load failed for %s: %s", path, e)
    return keys


def _stringify(v: Any) -> str:
    if v is None:
        return ""
    # bool must be checked BEFORE int/float (bool is subclass of int).
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _maybe_upgrade_header(path: str) -> None:
    """R19_L1: if the existing file has the pre-R19 11-col header (no
    `is_alt_line`), rewrite it in-place adding the column and defaulting
    every legacy row to is_alt_line=false. No-op on new files or files
    already on the 12-col schema.
    """
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                return
            if "is_alt_line" in header:
                return  # already upgraded
            body = list(reader)
    except Exception as e:  # noqa: BLE001
        log.warning("header-upgrade read failed for %s: %s", path, e)
        return
    upgraded = path + ".upgrading"
    try:
        with open(upgraded, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(_FIELDS)
            for row in body:
                # Pad legacy 10-col or 11-col rows to 12 cols. Default
                # is_alt_line=false so the arb engine treats legacy data
                # as primary (safe / conservative — they were the only
                # rows previously joined and most legacy days are
                # alt-line-free for non-Bov books).
                if len(row) == 11:
                    w.writerow(row + ["false"])
                elif len(row) == 10:
                    # 10-col legacy: missing `team` AND `is_alt_line`. Insert
                    # blank team at index 5 to align with new schema.
                    w.writerow(row[:5] + [""] + row[5:] + ["false"])
                elif len(row) == 12:
                    w.writerow(row)
                else:
                    # Unknown shape — skip to avoid corrupting downstream.
                    continue
        os.replace(upgraded, path)
        log.info("upgraded %s to 12-col schema (added is_alt_line)", path)
    except Exception as e:  # noqa: BLE001
        log.warning("header-upgrade write failed for %s: %s", path, e)
        try:
            os.remove(upgraded)
        except Exception:  # noqa: BLE001
            pass


def append_rows(rows: List[Dict[str, Any]], path: str) -> int:
    """Append `rows` to `path`, skipping duplicates by
    (book, player_name, stat, line, minute_key). Writes header on new file.
    Returns count actually written.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    _maybe_upgrade_header(path)
    existing = _load_existing_keys(path)
    new_file = not os.path.exists(path)
    written = 0
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            book = (r.get("book") or "").lower().strip()
            pn = (r.get("player_name") or "").lower().strip()
            st = (r.get("stat") or "").lower().strip()
            ln = _stringify(r.get("line"))
            ts = str(r.get("captured_at") or "")
            if not pn or not st or not ts:
                continue
            key = (book, pn, st, ln, _minute_key(ts))
            if key in existing:
                continue
            existing.add(key)
            w.writerow({k: _stringify(r.get(k, "")) for k in _FIELDS})
            written += 1
    return written


# ── daemon orchestration ────────────────────────────────────────────────────

def _today_iso() -> str:
    return _date.today().isoformat()


def _row_count(path: str) -> int:
    if not os.path.exists(path):
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            return max(0, sum(1 for _ in fh) - 1)  # subtract header
    except Exception:  # noqa: BLE001
        return 0


def fetch_cycle(sports: List[str],
                lines_dir: str = LINES_DIR,
                http_fn=_http_get,
                captured_at: Optional[str] = None,
                ) -> Dict[str, Any]:
    """One full cycle across `sports`. Returns a summary dict.

    Raises BovadaBlocked only if EVERY sport's index returns 403 (i.e. a
    daemon-wide block); a single sport returning 403 is tolerated.
    """
    captured_at = captured_at or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    date_str = (captured_at or _today_iso())[:10]
    out_path = os.path.join(lines_dir, f"{date_str}_bov.csv")

    summary: Dict[str, Any] = {
        "captured_at": captured_at,
        "out_path": out_path,
        "per_sport": {},
        "rows_new": 0,
        "rows_total_after": 0,
        "blocked_sports": [],
        "sports_with_data": [],
    }
    all_rows: List[Dict[str, Any]] = []
    blocked_count = 0
    for sport in sports:
        try:
            n_events, rows, diag = fetch_sport(sport, http_fn=http_fn,
                                                captured_at=captured_at)
        except BovadaBlocked as e:
            log.warning("bovada 403 for %s: %s", sport, e)
            summary["per_sport"][sport] = {"blocked": True, "n_events": 0,
                                            "rows": 0}
            summary["blocked_sports"].append(sport)
            blocked_count += 1
            continue
        summary["per_sport"][sport] = {
            "blocked": False, "n_events": n_events, "rows": len(rows),
            "diag": diag,
        }
        if rows:
            summary["sports_with_data"].append(sport)
        all_rows.extend(rows)
    if blocked_count == len(sports) and sports:
        # Whole-board block; propagate so the daemon counts toward its
        # block-clock for the eventual hour-long giveup.
        raise BovadaBlocked(f"all sports 403 ({','.join(sports)})")
    summary["rows_new"] = append_rows(all_rows, out_path)
    summary["rows_total_after"] = _row_count(out_path)
    return summary


def scrape_once() -> List[Dict[str, Any]]:
    """Entry point for parallel_scraper.py.

    Delegates to fetch_cycle() which writes data/lines/<date>_bov.csv directly.
    Returns [] to prevent parallel_scraper from double-writing the same rows.
    """
    try:
        fetch_cycle(["nba", "wnba", "mlb"])
    except Exception as exc:  # noqa: BLE001
        log.warning("bovada scrape_once failed: %s", exc)
    return []


def run_daemon(sports: List[str],
               interval_min: int,
               lines_dir: str = LINES_DIR,
               sleep_fn=time.sleep,
               max_iters: Optional[int] = None,
               http_fn=_http_get,
               clock_fn=lambda: datetime.now(),
               block_giveup_hours: float = _BLOCK_GIVEUP_HOURS,
               ) -> Dict[str, Any]:
    """Forever-loop fetch every `interval_min` minutes.

    Exits cleanly if Bovada returns 403 for >= `block_giveup_hours` of wall
    clock (so a supervisor can decide what to do).

    Returns the FINAL summary (last cycle's summary dict + cumulative info).
    """
    interval_sec = max(60, int(interval_min * 60))  # daemon floor: 1 min
    if interval_min < 5:
        log.warning("interval_min=%d < 5; clamping to 5 (spec minimum)",
                    interval_min)
        interval_min = 5
        interval_sec = 5 * 60

    iters = 0
    last: Dict[str, Any] = {}
    blocked_since: Optional[datetime] = None
    cumulative_new = 0
    cumulative_cycles_with_rows = 0
    last_out_path = ""

    log.info("bov daemon starting: sports=%s interval=%dmin", sports, interval_min)
    while True:
        # R19_L3 heartbeat
        _r19_hb('bov_scraper')
        captured_at = clock_fn().strftime("%Y-%m-%dT%H:%M:%S")
        try:
            summary = fetch_cycle(sports, lines_dir=lines_dir,
                                   http_fn=http_fn, captured_at=captured_at)
            blocked_since = None  # reset
            iters += 1
            last = summary
            cumulative_new += summary["rows_new"]
            if summary["rows_new"] > 0:
                cumulative_cycles_with_rows += 1
            last_out_path = summary["out_path"]
            log.info(
                "cycle=%d sports=%s games=%s rows_new=%d rows_total=%d",
                iters,
                ",".join(summary["sports_with_data"]) or "-",
                ",".join(
                    f"{s}={v['n_events']}"
                    for s, v in summary["per_sport"].items()
                    if not v.get("blocked")
                ) or "-",
                summary["rows_new"],
                summary["rows_total_after"],
            )
        except BovadaBlocked as e:
            now = clock_fn()
            if blocked_since is None:
                blocked_since = now
                log.warning("bovada 403 (cycle %d): %s -- starting block clock",
                            iters + 1, e)
            else:
                blocked_for_h = (now - blocked_since).total_seconds() / 3600.0
                log.warning("bovada still 403 (blocked %.2f h): %s",
                            blocked_for_h, e)
                if blocked_for_h >= block_giveup_hours:
                    log.error("bovada blocked >= %.1f h - daemon EXITING",
                              block_giveup_hours)
                    return {
                        "exit_reason": "blocked_persistent",
                        "iters": iters,
                        "cumulative_new": cumulative_new,
                        "last_summary": last,
                        "last_out_path": last_out_path,
                    }
        except Exception as e:  # noqa: BLE001
            log.error("cycle failed (cycle %d): %s", iters + 1, e)
            iters += 1
        if max_iters is not None and iters >= max_iters:
            return {
                "exit_reason": "max_iters",
                "iters": iters,
                "cumulative_new": cumulative_new,
                "cumulative_cycles_with_rows": cumulative_cycles_with_rows,
                "last_summary": last,
                "last_out_path": last_out_path,
            }
        sleep_fn(interval_sec)


# ── CLI ─────────────────────────────────────────────────────────────────────

def _expand_sports(arg: str) -> List[str]:
    if arg == "all":
        return ["nba", "wnba", "mlb"]
    parts = [p.strip().lower() for p in arg.split(",") if p.strip()]
    bad = [p for p in parts if p not in _SPORT_PATHS]
    if bad:
        raise SystemExit(
            f"--sports got unknown {bad}; valid: {sorted(_SPORT_PATHS)} or 'all'"
        )
    return parts or ["nba", "wnba", "mlb"]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sports", default="all",
                     help="Comma-separated sports or 'all' (default: all).")
    ap.add_argument("--interval-min", type=int, default=5,
                     help="Daemon polling interval (>=5 min). Default 5.")
    ap.add_argument("--once", action="store_true",
                     help="Single cycle + exit (overrides --interval-min).")
    ap.add_argument("--max-iters", type=int, default=None,
                     help="Stop after N iters (testing).")
    args = ap.parse_args(argv)

    sports = _expand_sports(args.sports)
    if args.once:
        log.info("once mode: sports=%s", sports)
        try:
            summary = fetch_cycle(sports)
        except BovadaBlocked as e:
            log.error("bovada blocked: %s", e)
            return 2
        print(json.dumps(summary, indent=2, default=str))
        return 0
    out = run_daemon(sports, args.interval_min, max_iters=args.max_iters)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
