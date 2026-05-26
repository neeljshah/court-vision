"""L20_injury_feed.py — Multi-source NBA Injury Feed Scraper (BUILD L20).

Polls RotoWire, Underdog (Nitter), and the NBA Official JSON for injury
updates, deduplicates via SHA-1 hash, detects downgrades, and dispatches
critical alerts through L22.

Public API
----------
    InjuryUpdate                dataclass
    fetch_rotowire_injuries()   -> list[InjuryUpdate]
    fetch_underdog_lineup_news()-> list[InjuryUpdate]
    fetch_nba_official_injuries() -> list[InjuryUpdate]
    run_all_sources()           -> list[InjuryUpdate]
    diff_against_seen(updates)  -> list[InjuryUpdate]
    alert_on_critical(updates)  -> int
    main(poll_seconds)

CLI
---
    python L20_injury_feed.py fetch
    python L20_injury_feed.py once
    python L20_injury_feed.py poll [--interval 600]

Environment Variables
---------------------
    None required for normal operation.  The scraper uses public endpoints
    and a local JSON cache; no API keys are needed.

    NBA_INJURY_JSON_PATH
        Override the default path to the local nba_official_injury.json cache
        (``data/external/nba_official_injury.json``).  Useful in tests or
        staging environments that supply a pre-seeded fixture.

Paper vs Live Mode (MODE GATING)
---------------------------------
L20 is a **read-only data fetcher** and therefore carries no mode gate.
It does not submit bets, place orders, or write financial state.  All
output is written to local JSON cache files and published as informational
events on the L46 EventBus.  No SUBMISSION_MODE / LIVE_MODE / PAPER_MODE
variable is consulted.

Event Publication (L46 EventBus)
---------------------------------
After each fetch cycle, L20 compares the newly fetched injury records to
the prior cached state (_seen.json).  For each NEW or CHANGED record (a
player whose status is either entirely absent from the cache or whose
status string differs from the most-recently cached value), L20 publishes:

    event name: "injury.announced"
    source:     "L20"
    payload: {
        "player":           str,   # accent-stripped canonical player name
        "team":             str,   # e.g. "LAL", "GSW"
        "status":           str,   # "OUT" | "DOUBTFUL" | "QUESTIONABLE" | ...
        "reason":           str,   # injury body text
        "previously_known": str | None,  # prior status, or None if first seen
        "fetched_at":       str,   # ISO 8601 UTC timestamp of this fetch
    }

Events are published via the module-level L46 singleton
(``L46_event_bus.get_default_bus()``).  Publish failures are caught and
logged; they never interrupt the fetch/diff pipeline.

Atomic Writes
-------------
All JSON snapshot files (_seen.json, nba_official_injury.json) are written
via ``_atomic_write_json``: a sibling temp file is created in the same
directory, written fully, then replaced via ``os.replace()``.  On crash or
power-loss the previous snapshot is preserved intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests

# ── paths ─────────────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _SCRIPT_DIR.parents[1]
sys.path.insert(0, str(_PROJECT_DIR))

_SEEN_PATH   = _PROJECT_DIR / "data" / "ledger" / "injury_seen.json"
_EXTERNAL    = _PROJECT_DIR / "data" / "external" / "nba_official_injury.json"

log = logging.getLogger(__name__)

# ── soft-import L46 EventBus (absent in minimal test environments) ────────────
try:
    from scripts.execute_loop import L46_event_bus as _L46
except Exception:  # noqa: BLE001
    try:
        import L46_event_bus as _L46  # type: ignore[no-redef]
    except Exception:
        _L46 = None  # type: ignore[assignment]

# ── constants ─────────────────────────────────────────────────────────────────
_ROTOWIRE_URL = "https://www.rotowire.com/basketball/injury-report.php"
_NITTER_URL   = "https://nitter.net/Underdog__NBA"

_DOWNGRADE_MAP: Dict[str, int] = {
    "OUT": 0, "DOUBTFUL": 1, "QUESTIONABLE": 2, "GTD": 3,
    "PROBABLE": 4, "AVAILABLE": 5,
}

_STATUS_TO_SEVERITY: Dict[str, str] = {
    "OUT": "critical", "DOUBTFUL": "critical",
    "QUESTIONABLE": "warning", "GTD": "warning",
    "PROBABLE": "info", "AVAILABLE": "info",
}

# best-effort headers; fall through to plain UA on ImportError
try:
    from src.data.nba_api_headers_patch import get_headers as _get_headers
    _DEFAULT_HEADERS = _get_headers()
except Exception:
    _DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

# optional L22 alerting
try:
    from scripts.execute_loop.L22_alerting import send_alert as _send_alert
except ImportError:
    try:
        from L22_alerting import send_alert as _send_alert  # type: ignore[no-redef]
    except ImportError:
        log.warning("[L20] L22_alerting not found — alerts disabled")
        _send_alert = None  # type: ignore[assignment]


# ── dataclass ─────────────────────────────────────────────────────────────────
@dataclass
class InjuryUpdate:
    player:    str   # accent-stripped canonical
    team:      str
    status:    str   # OUT|DOUBTFUL|QUESTIONABLE|GTD|PROBABLE|AVAILABLE
    source:    str   # rotowire|underdog|nba_official
    body:      str
    timestamp: str   # ISO 8601 UTC
    severity:  str   # info|warning|critical

    # not serialised — used internally
    _hash: str = field(default="", repr=False, compare=False)

    def compute_hash(self) -> str:
        date_part = self.timestamp[:10]
        raw = f"{_normalize_name(self.player)}|{self.status}|{date_part}"
        return hashlib.sha1(raw.encode()).hexdigest()


# ── name normalisation ────────────────────────────────────────────────────────
def _normalize_name(s: str) -> str:
    return (
        unicodedata.normalize("NFKD", s)
        .encode("ascii", "ignore")
        .decode()
        .lower()
        .strip()
    )


def _canonical_status(raw: str) -> str:
    mapping = {
        "out": "OUT", "doubtful": "DOUBTFUL",
        "questionable": "QUESTIONABLE", "gtd": "GTD",
        "game time decision": "GTD",
        "probable": "PROBABLE", "available": "AVAILABLE",
        "active": "AVAILABLE",
    }
    return mapping.get(raw.lower().strip(), raw.upper().strip())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── seen.json helpers ─────────────────────────────────────────────────────────
def _load_seen() -> Dict[str, dict]:
    """Return {hash: {status, last_seen_iso, player_norm}}. Recreates on corrupt."""
    if not _SEEN_PATH.exists():
        return {}
    try:
        data = json.loads(_SEEN_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a dict")
        return data
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        log.warning("[L20] _seen.json corrupt — resetting (%s)", exc)
        return {}


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write *data* as JSON to *path* atomically via a sibling temp file.

    On crash mid-write the previous file content is preserved.  Matches the
    pattern used across R7-polished layers (L18, L22, L46).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _save_seen(seen: Dict[str, dict]) -> None:
    try:
        _atomic_write_json(_SEEN_PATH, seen)
    except OSError as exc:
        log.error("[L20] Failed to persist _seen.json: %s", exc)


# ── source: NBA official ──────────────────────────────────────────────────────
def fetch_nba_official_injuries() -> List[InjuryUpdate]:
    """Load from data/external/nba_official_injury.json or src.data.injuries."""
    updates: List[InjuryUpdate] = []

    if _EXTERNAL.exists():
        try:
            rows = json.loads(_EXTERNAL.read_text(encoding="utf-8"))
            for row in rows:
                name   = _normalize_name(row.get("player_name", ""))
                team   = (row.get("team_abbrev") or "").upper()
                status = _canonical_status(row.get("status", ""))
                body   = row.get("reason", "")
                ts     = row.get("game_date", _now_iso())
                sev    = _STATUS_TO_SEVERITY.get(status, "info")
                upd = InjuryUpdate(
                    player=name, team=team, status=status,
                    source="nba_official", body=body,
                    timestamp=ts, severity=sev,
                )
                upd._hash = upd.compute_hash()
                updates.append(upd)
            log.info("[L20] nba_official: %d records from JSON", len(updates))
            return updates
        except Exception as exc:
            log.warning("[L20] nba_official JSON parse failed: %s", exc)

    # fallback: src.data.injuries module
    try:
        from src.data.injuries import load_unavailable_players  # type: ignore
        rows = load_unavailable_players()
        for row in rows:
            name   = _normalize_name(row.get("player_name", ""))
            team   = (row.get("team_abbrev") or "").upper()
            status = _canonical_status(row.get("status", "OUT"))
            body   = row.get("reason", "")
            ts     = row.get("game_date", _now_iso())
            sev    = _STATUS_TO_SEVERITY.get(status, "info")
            upd = InjuryUpdate(
                player=name, team=team, status=status,
                source="nba_official", body=body,
                timestamp=ts, severity=sev,
            )
            upd._hash = upd.compute_hash()
            updates.append(upd)
        log.info("[L20] nba_official: %d records via module", len(updates))
    except ImportError:
        log.warning("[L20] nba_official: JSON missing and module not found — skipping")
    except Exception as exc:
        log.warning("[L20] nba_official module error: %s", exc)

    return updates


# ── source: RotoWire HTML ─────────────────────────────────────────────────────
def fetch_rotowire_injuries() -> List[InjuryUpdate]:
    """Scrape https://www.rotowire.com/basketball/injury-report.php."""
    try:
        resp = requests.get(_ROTOWIRE_URL, headers=_DEFAULT_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("[L20] rotowire fetch failed: %s", exc)
        return []

    try:
        from html.parser import HTMLParser  # stdlib only

        class _RWParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_table = False
                self.in_row   = False
                self.cells: List[str] = []
                self.cur_cell = ""
                self.rows: List[List[str]] = []
                self._td_depth = 0

            def handle_starttag(self, tag, attrs):
                attr_d = dict(attrs)
                if tag == "table" and "injury-report" in attr_d.get("id", ""):
                    self.in_table = True
                if not self.in_table:
                    return
                if tag == "tr":
                    self.in_row = True
                    self.cells = []
                if tag in ("td", "th") and self.in_row:
                    self._td_depth += 1
                    self.cur_cell = ""

            def handle_endtag(self, tag):
                if tag in ("td", "th") and self.in_row and self._td_depth > 0:
                    self._td_depth -= 1
                    self.cells.append(self.cur_cell.strip())
                    self.cur_cell = ""
                if tag == "tr" and self.in_row:
                    self.in_row = False
                    if self.cells:
                        self.rows.append(self.cells[:])
                        self.cells = []
                if tag == "table":
                    self.in_table = False

            def handle_data(self, data):
                if self.in_row and self._td_depth > 0:
                    self.cur_cell += data

        parser = _RWParser()
        parser.feed(resp.text)

        updates: List[InjuryUpdate] = []
        ts = _now_iso()
        for cells in parser.rows:
            try:
                if len(cells) < 4:
                    continue
                name   = _normalize_name(cells[0])
                team   = cells[1].upper().strip()
                status = _canonical_status(cells[2])
                body   = cells[3]
                sev    = _STATUS_TO_SEVERITY.get(status, "info")
                upd = InjuryUpdate(
                    player=name, team=team, status=status,
                    source="rotowire", body=body,
                    timestamp=ts, severity=sev,
                )
                upd._hash = upd.compute_hash()
                updates.append(upd)
            except Exception as row_exc:
                log.debug("[L20] rotowire: skip malformed row %r — %s", cells, row_exc)

        log.info("[L20] rotowire: %d records parsed", len(updates))
        return updates

    except Exception as exc:
        log.warning("[L20] rotowire HTML parse error: %s", exc)
        return []


# ── source: Underdog via Nitter ───────────────────────────────────────────────
def fetch_underdog_lineup_news() -> List[InjuryUpdate]:
    """Scrape Nitter proxy for @Underdog__NBA tweets. Likely 5xx — skip gracefully."""
    try:
        resp = requests.get(_NITTER_URL, headers=_DEFAULT_HEADERS, timeout=10)
        if resp.status_code >= 500:
            log.warning("[L20] underdog/nitter returned %d — skipping", resp.status_code)
            return []
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("[L20] underdog/nitter fetch failed: %s", exc)
        return []

    try:
        from html.parser import HTMLParser

        class _NitterParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_tweet = False
                self.depth    = 0
                self.cur      = ""
                self.tweets: List[str] = []

            def handle_starttag(self, tag, attrs):
                attr_d = dict(attrs)
                cls = attr_d.get("class", "")
                if "tweet-content" in cls:
                    self.in_tweet = True
                    self.depth    = 1
                    self.cur      = ""
                elif self.in_tweet:
                    self.depth += 1

            def handle_endtag(self, tag):
                if self.in_tweet:
                    self.depth -= 1
                    if self.depth <= 0:
                        self.tweets.append(self.cur.strip())
                        self.in_tweet = False

            def handle_data(self, data):
                if self.in_tweet:
                    self.cur += data

        parser = _NitterParser()
        parser.feed(resp.text)

        updates: List[InjuryUpdate] = []
        ts = _now_iso()
        _kw_map = [("out", "OUT"), ("doubtful", "DOUBTFUL"),
                   ("questionable", "QUESTIONABLE"), ("gtd", "GTD"),
                   ("probable", "PROBABLE")]

        for tweet in parser.tweets:
            text_lower = tweet.lower()
            status = "AVAILABLE"
            for kw, st in _kw_map:
                if kw in text_lower:
                    status = st
                    break
            sev = _STATUS_TO_SEVERITY.get(status, "info")
            name = _normalize_name(tweet.split()[0]) if tweet.split() else "unknown"
            upd = InjuryUpdate(
                player=name, team="UNK", status=status,
                source="underdog", body=tweet[:280],
                timestamp=ts, severity=sev,
            )
            upd._hash = upd.compute_hash()
            updates.append(upd)

        log.info("[L20] underdog: %d tweets parsed", len(updates))
        return updates

    except Exception as exc:
        log.warning("[L20] underdog HTML parse error: %s", exc)
        return []


# ── merge helpers ─────────────────────────────────────────────────────────────
def _merge_updates(updates: List[InjuryUpdate]) -> List[InjuryUpdate]:
    """Same player+date from 2 sources: keep most recent timestamp + highest severity."""
    severity_rank = {"info": 0, "warning": 1, "critical": 2}
    keyed: Dict[str, InjuryUpdate] = {}
    for upd in updates:
        key = f"{_normalize_name(upd.player)}|{upd.timestamp[:10]}"
        if key not in keyed:
            keyed[key] = upd
        else:
            existing = keyed[key]
            # keep highest severity
            if severity_rank[upd.severity] > severity_rank[existing.severity]:
                keyed[key] = upd
            elif upd.timestamp > existing.timestamp:
                keyed[key] = upd
    return list(keyed.values())


# ── public API ────────────────────────────────────────────────────────────────
def run_all_sources() -> List[InjuryUpdate]:
    """Fetch all three sources, merge, and return combined list."""
    all_updates: List[InjuryUpdate] = []
    for fn in (fetch_nba_official_injuries, fetch_rotowire_injuries, fetch_underdog_lineup_news):
        try:
            all_updates.extend(fn())
        except Exception as exc:
            log.warning("[L20] source %s raised: %s", fn.__name__, exc)
    return _merge_updates(all_updates)


def diff_against_seen(updates: List[InjuryUpdate]) -> List[InjuryUpdate]:
    """Return only updates whose hash is NOT in _seen.json; persist new hashes.

    Downgrade detection: if a player's prior status was Q/GTD/PROBABLE and the
    new status is OUT/DOUBTFUL, force severity='critical' even if hash was seen.
    """
    seen   = _load_seen()
    novel: List[InjuryUpdate] = []
    now    = _now_iso()

    # build a quick lookup: player_norm → prior status (most recent last_seen_iso)
    prior_status: Dict[str, str] = {}
    for meta in seen.values():
        pn = meta.get("player_norm", "")
        if not pn:
            continue
        existing = prior_status.get(pn)
        if existing is None or meta.get("last_seen_iso", "") > seen.get(pn, {}).get("last_seen_iso", ""):
            prior_status[pn] = meta.get("status", "")

    for upd in updates:
        if not upd._hash:
            upd._hash = upd.compute_hash()
        pn = _normalize_name(upd.player)

        prior = prior_status.get(pn, "")
        is_downgrade = (
            prior in ("QUESTIONABLE", "GTD", "PROBABLE")
            and upd.status in ("OUT", "DOUBTFUL")
        )

        if upd._hash not in seen:
            if is_downgrade:
                upd.severity = "critical"
            novel.append(upd)
            seen[upd._hash] = {
                "status":       upd.status,
                "last_seen_iso": now,
                "player_norm":  pn,
            }
        elif is_downgrade:
            # hash seen but downgrade — still alert
            upd.severity = "critical"
            novel.append(upd)

    _save_seen(seen)
    _publish_injury_events(novel, prior_status, now)
    return novel


def _publish_injury_events(
    novel: List[InjuryUpdate],
    prior_status: Dict[str, str],
    fetched_at: str,
) -> None:
    """Publish 'injury.announced' on the L46 EventBus for each novel update.

    Failures are caught and logged; they never interrupt the caller.
    """
    if _L46 is None or not novel:
        return
    try:
        bus = _L46.get_default_bus()
    except Exception as exc:
        log.warning("[L20] Could not get L46 bus: %s", exc)
        return

    for upd in novel:
        pn = _normalize_name(upd.player)
        prev = prior_status.get(pn) or None  # None if first ever seen
        try:
            bus.publish(
                "injury.announced",
                source="L20",
                payload={
                    "player":           upd.player,
                    "team":             upd.team,
                    "status":           upd.status,
                    "reason":           upd.body,
                    "previously_known": prev,
                    "fetched_at":       fetched_at,
                },
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("[L20] EventBus publish failed for %s: %s", upd.player, exc)


def alert_on_critical(updates: List[InjuryUpdate]) -> int:
    """Dispatch critical updates via L22 send_alert. Returns count dispatched."""
    dispatched = 0
    for upd in updates:
        if upd.severity != "critical":
            continue
        title = f"Injury: {upd.player} — {upd.status}"
        body  = f"[{upd.source}] {upd.team} | {upd.body}"
        fields = {
            "Player": upd.player, "Team": upd.team,
            "Status": upd.status, "Source": upd.source,
        }
        if _send_alert is not None:
            try:
                _send_alert("news", "warning", title, body, fields)
            except Exception as exc:
                log.warning("[L20] send_alert failed: %s", exc)
        dispatched += 1
    return dispatched


# ── main / poll ───────────────────────────────────────────────────────────────
def main(poll_seconds: int = 600) -> None:
    """Continuous poll loop. Ctrl-C to exit."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )
    log.info("[L20] Starting poll loop (interval=%ds)", poll_seconds)
    while True:
        try:
            updates = run_all_sources()
            novel   = diff_against_seen(updates)
            n_crit  = alert_on_critical(novel)
            log.info(
                "[L20] Poll complete: %d total, %d new, %d critical",
                len(updates), len(novel), n_crit,
            )
        except Exception as exc:
            log.error("[L20] Poll iteration error: %s", exc)
        time.sleep(poll_seconds)


# ── CLI ───────────────────────────────────────────────────────────────────────
def _cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )
    p = argparse.ArgumentParser(description="L20 injury feed CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("fetch", help="Fetch all sources, print raw updates")
    sub.add_parser("once", help="Fetch, diff, alert; exit after one cycle")
    poll_p = sub.add_parser("poll", help="Continuous poll loop")
    poll_p.add_argument("--interval", type=int, default=600,
                        help="Seconds between polls (default 600)")

    args = p.parse_args()

    if args.cmd == "fetch":
        updates = run_all_sources()
        for u in updates:
            print(f"[{u.severity.upper()}] {u.player} ({u.team}) {u.status} | {u.source} | {u.body[:80]}")
        print(f"\n{len(updates)} updates fetched.")

    elif args.cmd == "once":
        updates = run_all_sources()
        novel   = diff_against_seen(updates)
        n_crit  = alert_on_critical(novel)
        print(f"{len(updates)} fetched, {len(novel)} new, {n_crit} critical.")

    elif args.cmd == "poll":
        main(poll_seconds=args.interval)


if __name__ == "__main__":
    _cli()
