"""parallel_scraper.py — async parallel sportsbook scraper for Live Engine v2.

Scrapes Pinnacle, Bovada, FanDuel, and PrizePicks IN PARALLEL via
aiohttp instead of serially. The legacy
``scripts/unified_scraper_orchestrator.py`` runs each book in its
own thread on its own interval (60s FD, 60s Bov, 30s Pin); this
poller does all four within a single async tick (default 30s) and
appends rows to the same ``data/lines/<date>_<book>.csv`` files
used by the rest of the system.

When a book's existing module already exists in `scripts/`, we
import its fetch helper (run in a threadpool when it isn't async)
so behavior matches the legacy daemon. When no helper exists, the
book is skipped with a log warning.

Emits ``lines.refreshed`` on the event bus after each tick with
counts per book so the decision engine can recompute edge.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.live.event_bus import TOPIC_LINES_REFRESHED, EventBus, get_bus  # noqa: E402
from src.live.time_utils import slate_date  # noqa: E402

log = logging.getLogger("parallel_scraper")

LINES_DIR = os.path.join(PROJECT_DIR, "data", "lines")
HEARTBEAT_PATH = os.path.join(
    PROJECT_DIR, "data", "cache", "daemon_heartbeats", "parallel_scraper.txt")

# Default columns we ALWAYS write — superset of the existing book CSVs.
_COLUMNS = [
    "captured_at", "book", "game_id", "player_id", "player_name",
    "team", "stat", "line", "over_price", "under_price",
    "market_status", "is_alt_line",
]


# ── per-book fetch adapters ─────────────────────────────────────────────
# Each adapter is `async def fetch(session) -> list[dict]` returning rows.
# When the legacy sync helper exists we wrap it via run_in_executor.

async def _fetch_pinnacle(session) -> List[Dict[str, Any]]:
    try:
        import scripts.pinnacle_scraper as _pin
    except Exception as exc:  # noqa: BLE001
        log.warning("pinnacle import failed: %s", exc)
        return []
    fn = getattr(_pin, "scrape_once", None) or getattr(_pin, "fetch_lines", None)
    if not callable(fn):
        log.warning("pinnacle: no scrape_once/fetch_lines entry point")
        return []
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, fn) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("pinnacle scrape failed: %s", exc)
        return []


async def _fetch_bovada(session) -> List[Dict[str, Any]]:
    try:
        import scripts.bov_scraper_daemon as _bov
    except Exception as exc:  # noqa: BLE001
        log.warning("bovada import failed: %s", exc)
        return []
    fn = getattr(_bov, "scrape_once", None) or getattr(_bov, "fetch_lines", None)
    if not callable(fn):
        log.warning("bovada: no scrape_once/fetch_lines entry point")
        return []
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, fn) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("bovada scrape failed: %s", exc)
        return []


async def _fetch_fanduel(session) -> List[Dict[str, Any]]:
    # The FD daemon (probe_R15_curl_cffi_fanduel.py) uses curl_cffi sync;
    # only invoke a fetcher if the module exposes one cleanly.
    try:
        import scripts.probe_R15_curl_cffi_fanduel as _fd  # noqa: N813
    except Exception as exc:  # noqa: BLE001
        log.warning("fanduel import failed: %s", exc)
        return []
    fn = getattr(_fd, "scrape_once", None) or getattr(_fd, "fetch_lines", None)
    if not callable(fn):
        log.warning("fanduel: no scrape_once/fetch_lines entry point")
        return []
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, fn) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("fanduel scrape failed: %s", exc)
        return []


async def _fetch_draftkings(session) -> List[Dict[str, Any]]:
    """Direct DK scrape via sportsbook-nash.draftkings.com + curl_cffi chrome120.
    The module writes its own CSV; we return [] so the orchestrator does not
    double-write."""
    try:
        import scripts.draftkings_scraper as _dk
    except Exception as exc:  # noqa: BLE001
        log.warning("draftkings import failed: %s", exc)
        return []
    fn = getattr(_dk, "scrape_once", None)
    if not callable(fn):
        log.warning("draftkings: no scrape_once entry point")
        return []
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, fn) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("draftkings scrape failed: %s", exc)
        return []


async def _fetch_pointsbet(session) -> List[Dict[str, Any]]:
    """Direct PointsBet AU scrape via api.au.pointsbet.com + curl_cffi chrome120.
    The module writes its own CSV; we return [] so the orchestrator does not
    double-write."""
    try:
        import scripts.pointsbet_scraper as _pb
    except Exception as exc:  # noqa: BLE001
        log.warning("pointsbet import failed: %s", exc)
        return []
    fn = getattr(_pb, "scrape_once", None)
    if not callable(fn):
        log.warning("pointsbet: no scrape_once entry point")
        return []
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, fn) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("pointsbet scrape failed: %s", exc)
        return []


async def _fetch_betrivers(session) -> List[Dict[str, Any]]:
    """Direct BetRivers scrape via KAMBI offering API + curl_cffi chrome120.
    The module writes its own CSV; we return [] so the orchestrator does not
    double-write."""
    try:
        import scripts.betrivers_scraper as _br
    except Exception as exc:  # noqa: BLE001
        log.warning("betrivers import failed: %s", exc)
        return []
    fn = getattr(_br, "scrape_once", None)
    if not callable(fn):
        log.warning("betrivers: no scrape_once entry point")
        return []
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, fn) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("betrivers scrape failed: %s", exc)
        return []


async def _fetch_draftkings_inplay(session) -> List[Dict[str, Any]]:
    """DK in-play milestone markets (subcategoryIds 16477/16478/16479/16480).

    Gates itself on live-game detection — returns [] with no HTTP calls when
    no NBA game is IN_PROGRESS. Writes data/lines/<date>_dk_inplay.csv.
    """
    try:
        import scripts.draftkings_inplay_scraper as _dki
    except Exception as exc:  # noqa: BLE001
        log.warning("draftkings_inplay import failed: %s", exc)
        return []
    fn = getattr(_dki, "scrape_once", None)
    if not callable(fn):
        log.warning("draftkings_inplay: no scrape_once entry point")
        return []
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, fn) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("draftkings_inplay scrape failed: %s", exc)
        return []


async def _fetch_fanduel_inplay(session) -> List[Dict[str, Any]]:
    """FD in-play props via same NJ endpoint + inPlayOnly=true.

    Returns [] (no write) when no markets have inPlay=True.
    Writes data/lines/<date>_fd_inplay.csv when games are live.
    """
    try:
        import scripts.fanduel_inplay_scraper as _fdi
    except Exception as exc:  # noqa: BLE001
        log.warning("fanduel_inplay import failed: %s", exc)
        return []
    fn = getattr(_fdi, "scrape_once", None)
    if not callable(fn):
        log.warning("fanduel_inplay: no scrape_once entry point")
        return []
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, fn) or []
    except Exception as exc:  # noqa: BLE001
        log.warning("fanduel_inplay scrape failed: %s", exc)
        return []


async def _fetch_prizepicks(session) -> List[Dict[str, Any]]:
    # PrizePicks has a public JSON API — fetch directly via aiohttp.
    url = "https://api.prizepicks.com/projections?league_id=7&per_page=250"
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                log.info("prizepicks HTTP %s", resp.status)
                return []
            payload = await resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("prizepicks fetch failed: %s", exc)
        return []
    rows: List[Dict[str, Any]] = []
    data = (payload or {}).get("data") or []
    included = {(i.get("type"), i.get("id")): i.get("attributes") or {}
                for i in (payload or {}).get("included") or []}
    captured = _now_iso()
    for proj in data:
        attrs = proj.get("attributes") or {}
        rels = proj.get("relationships") or {}
        player_ref = ((rels.get("new_player") or {}).get("data") or {})
        player_attrs = included.get(("new_player", player_ref.get("id")), {})
        rows.append({
            "captured_at": captured,
            "book": "pp",
            "game_id": attrs.get("game_id"),
            "player_id": player_ref.get("id"),
            "player_name": player_attrs.get("display_name"),
            "team": player_attrs.get("team"),
            "stat": (attrs.get("stat_type") or "").lower().replace(" ", "_"),
            "line": attrs.get("line_score"),
            "over_price": -119,   # standard PP juice convention
            "under_price": -119,
            "market_status": attrs.get("status"),
            "is_alt_line": False,
        })
    return rows


_LAST_ODDSAPI_TICK = 0.0  # epoch seconds
_ODDSAPI_INTERVAL_SEC = float(os.environ.get("ODDSAPI_INTERVAL_SEC", "300"))  # 5 min default


async def _fetch_oddsapi(session) -> List[Dict[str, Any]]:
    """Pull DraftKings, BetMGM, Caesars, PointsBet, BetRivers, Bet365, ESPN BET
    and more via the-odds-api.com. Env-gated by THE_ODDS_API_KEY. The scraper
    writes its own per-book CSVs, so we return [] (the orchestrator's row
    count log will read 0 for this book — the per-book CSVs grow regardless).

    Throttled to once per ODDSAPI_INTERVAL_SEC (default 300s = 5 min) to
    keep within the-odds-api quota: ~290 req/day at 5-min cadence over a
    10-game slate = well under the 20K/mo Starter tier.
    """
    global _LAST_ODDSAPI_TICK
    if not os.environ.get("THE_ODDS_API_KEY"):
        return []
    now = time.time()
    if now - _LAST_ODDSAPI_TICK < _ODDSAPI_INTERVAL_SEC:
        return []
    _LAST_ODDSAPI_TICK = now
    try:
        import scripts.the_odds_api_scraper as _oa  # noqa: N813
    except Exception as exc:  # noqa: BLE001
        log.warning("the_odds_api import failed: %s", exc)
        return []
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, _oa.scrape_once)
    except Exception as exc:  # noqa: BLE001
        log.warning("the_odds_api scrape failed: %s", exc)
        return []
    if isinstance(result, dict):
        log.info("the_odds_api: rows=%s per_book=%s",
                 result.get("rows"), result.get("per_book"))
    return []


_DEFAULT_BOOKS: Dict[str, Callable[[Any], Awaitable[List[Dict[str, Any]]]]] = {
    "pin":        _fetch_pinnacle,
    "bov":        _fetch_bovada,
    "fd":         _fetch_fanduel,
    "dk":         _fetch_draftkings,
    "betrivers":  _fetch_betrivers,
    "pointsbet":  _fetch_pointsbet,
    "oddsapi":    _fetch_oddsapi,   # no-op when THE_ODDS_API_KEY unset; ~10-15 books when set
    "dk_inplay":  _fetch_draftkings_inplay,
    "fd_inplay":  _fetch_fanduel_inplay,
}


# ── persistence ─────────────────────────────────────────────────────────
def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _append_csv(rows: List[Dict[str, Any]], book: str,
                date_str: str, lines_dir: str = LINES_DIR) -> str:
    """Append rows to ``<lines_dir>/<date>_<book>.csv``. Writes header
    only when the file is new. Returns the path written."""
    os.makedirs(lines_dir, exist_ok=True)
    path = os.path.join(lines_dir, f"{date_str}_{book}.csv")
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_COLUMNS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


# ── poller ──────────────────────────────────────────────────────────────
class ParallelScraper:
    """Parallel multi-book line scraper."""

    def __init__(self, *,
                 books: Optional[List[str]] = None,
                 interval_sec: float = 30.0,
                 bus: Optional[EventBus] = None,
                 lines_dir: str = LINES_DIR,
                 fetchers: Optional[Dict[str, Callable]] = None) -> None:
        self.books = books or list(_DEFAULT_BOOKS.keys())
        self.interval_sec = interval_sec
        self.bus = bus or get_bus()
        self.lines_dir = lines_dir
        self.fetchers = fetchers or dict(_DEFAULT_BOOKS)
        self._stopped = False

    async def tick_once(self) -> Dict[str, int]:
        """Scrape every book in parallel; return ``{book: row_count}``."""
        try:
            import aiohttp
        except ImportError:
            log.error("aiohttp not installed; cannot run parallel_scraper")
            return {}

        date_str = slate_date().isoformat()
        results: Dict[str, int] = {}

        async with aiohttp.ClientSession() as session:
            coros = []
            ordered_books: List[str] = []
            for book in self.books:
                fn = self.fetchers.get(book)
                if fn is None:
                    continue
                coros.append(fn(session))
                ordered_books.append(book)
            gathered = await asyncio.gather(*coros, return_exceptions=True)

        for book, payload in zip(ordered_books, gathered):
            if isinstance(payload, Exception):
                log.warning("%s scrape exception: %s", book, payload)
                results[book] = 0
                continue
            rows = list(payload or [])
            if rows:
                try:
                    _append_csv(rows, book, date_str, self.lines_dir)
                except OSError as exc:
                    log.warning("append_csv(%s) failed: %s", book, exc)
            results[book] = len(rows)

        # Surface per-tick CSV freshness so we can verify lines aren't going
        # stale on Railway. scrape_once functions write directly so 'rows=0
        # returned' isn't a failure signal — check mtime instead.
        freshness = {}
        for book in ordered_books:
            path = os.path.join(self.lines_dir, f"{date_str}_{book}.csv")
            if os.path.exists(path):
                age_s = int(time.time() - os.path.getmtime(path))
                freshness[book] = f"{age_s}s"
            else:
                freshness[book] = "absent"
        log.info("scrape tick: returned=%s csv_age=%s", results, freshness)

        # Notify the decision engine that fresh lines are on disk.
        await self.bus.publish(TOPIC_LINES_REFRESHED, {
            "date": date_str,
            "counts": results,
        })
        _write_heartbeat()
        return results

    async def run_forever(self) -> None:
        while not self._stopped:
            try:
                await self.tick_once()
            except Exception as exc:  # noqa: BLE001
                log.error("parallel_scraper crashed: %s", exc)
            await asyncio.sleep(self.interval_sec)

    def stop(self) -> None:
        self._stopped = True


def _write_heartbeat() -> None:
    try:
        os.makedirs(os.path.dirname(HEARTBEAT_PATH), exist_ok=True)
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as fh:
            fh.write(str(int(time.time())))
    except OSError:
        pass


def _parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--books", default="pin,bov,fd,dk,pp")
    ap.add_argument("--interval-sec", type=float, default=30.0)
    return ap.parse_args(argv)


async def _main(argv=None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    books = [b.strip() for b in args.books.split(",") if b.strip()]
    s = ParallelScraper(books=books, interval_sec=args.interval_sec)
    await s.run_forever()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except KeyboardInterrupt:
        sys.exit(0)
