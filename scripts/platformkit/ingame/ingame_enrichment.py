"""scripts.platformkit.ingame.ingame_enrichment -- LANE 1 None-safe enrichment facade.

Given (sport, matchup, tick ts), looks up the LATEST already-written sidecar snapshot
from each wave-10 enrichment source and returns a flat, None-safe field dict. This module
NEVER fetches over the network itself -- it only READS sidecar files other modules (already
shipped this wave) already write:

  - domains.soccer.ingame_fotmob        -> data/domains/soccer_intl/fotmob_live/<matchId>.jsonl
  - scripts.platformkit.espn_wp_reference -> data/domains/<sport>/espn_wp/<event_id>.jsonl
  - scripts.platformkit.ingame.ingame_book_depth(_poller) -> data/cache/book_depth/<venue>/<date>.jsonl

CONTRACT (mirrors scripts/platformkit/ingame/ingame_sp_shadow.py's SpShadow EXACTLY):
  1. NEVER changes model_prob, the edge signal, or any bet/decision -- every lookup here is
     a pure, additive, side-read. Its only consumer is a handful of ADDITIONAL logged fields.
  2. Every path is wrapped so ANY exception yields None (+ one-time debug log per source),
     never a raised error into the capture path.
  3. A "poisoned build" (a source whose first read blows up -- bad file, bad JSON, import
     failure) makes that source return None for the REST of this process's life (permanent
     None), exactly like SpShadow._broken. It never retries mid-process and never raises.
  4. Missing inputs (no sidecar dir, no matching matchId/ticker/event, sport not covered) ->
     None. Honest absence, never a guess. An ABSENT sidecar directory (not-yet-run source) is
     the expected common case right now (none of these pollers has been restarted-on yet) and
     is treated identically to "no data for this matchup" -- both are just None.

LOOKUPS (each independently poisoned/cached; a break in one never affects another):
  fotmob_xg(matchup, cutoff_min)       -- soccer_intl only. Uses domains.soccer.ingame_fotmob's
    OWN match_to_fixture + asof_state_at helpers so the as-of/team-matching discipline is not
    re-derived here. Reads the LATEST jsonl line per matched matchId (sidecar is append-only;
    dedup is this reader's job, same convention the source module documents), then re-derives
    a cutoff-consistent asof_state_at() call is NOT re-run here -- the already-written snapshot
    row (which itself is one asof_state_at() dict, see ingame_fotmob.poll_once) is returned
    as-is, capped to fields xg_home/xg_away/xg_asof_min (renamed from its cutoff_min).
  book_depth(ticker)                   -- all sports with a depth sidecar. Scans
    data/cache/book_depth/{kalshi,polymarket}/*.jsonl for the LATEST row whose ticker/slug
    matches, returns {spread_bp, book_thinness, stale_quote_flag}.
  espn_wp(sport, event_id)             -- mlb/wnba only (SUPPORTED_SPORTS in
    espn_wp_reference.py). event_id must be cheaply available to the caller (ESPN numeric id);
    if the caller has none, record pending (see inplay_capture_loop wire spec below) rather
    than resolving one here (out of scope this lane).

CACHING: LRU-light (a small dict capped at _CACHE_MAX entries, evict-oldest) per source, keyed
by the lookup key; avoids re-reading/re-scanning the same sidecar file every tick. No TTL
beyond process lifetime -- these are append-only logs so re-reading only ever adds rows, and
staleness here is bounded by how often the wired caller invokes a lookup (in-game cadence, not
long-lived).

INVARIANTS: scripts/platformkit/ingame/ only; <=300 LOC; ASCII only; no writes; reads
data/domains/**/*.jsonl + data/cache/book_depth/**/*.jsonl (read-only, best-effort). Never
imports src/kernel/api. Measurement-only -- no $ / edge claim; decision paths untouched.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_enrichment.py -q
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
FOTMOB_SIDECAR_DIR = _REPO_ROOT / "data" / "domains" / "soccer_intl" / "fotmob_live"
ESPN_WP_DIR = _REPO_ROOT / "data" / "domains"  # + <sport>/espn_wp/<event_id>.jsonl
BOOK_DEPTH_DIR = _REPO_ROOT / "data" / "cache" / "book_depth"  # + <venue>/<date>.jsonl

_CACHE_MAX = 64


def _read_jsonl_lines(path: Path) -> List[Dict[str, Any]]:
    """Read every JSON line of *path*. [] if absent/unreadable/empty. Never raises."""
    try:
        if not path.is_file():
            return []
        out: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(row, dict):
                    out.append(row)
        return out
    except Exception as exc:  # noqa: BLE001 -- a bad sidecar file is an honest miss, not a crash
        logger.debug("ingame_enrichment: read failed for %s: %s", path, exc)
        return []


class _LruLight:
    """A tiny evict-oldest cache. Not thread-safe (single capture-loop process)."""

    def __init__(self, maxsize: int = _CACHE_MAX) -> None:
        self._maxsize = maxsize
        self._store: Dict[Any, Any] = {}

    def get(self, key: Any) -> Any:
        return self._store.get(key)

    def set(self, key: Any, value: Any) -> None:
        if key not in self._store and len(self._store) >= self._maxsize:
            oldest = next(iter(self._store))
            self._store.pop(oldest, None)
        self._store[key] = value


class EnrichmentFacade:
    """Lazy, once-per-process None-safe lookup facade. Each source independently
    poisoned-permanent-None (mirrors SpShadow._broken), never raises.

    Optional constructor args exist ONLY to make this hermetically testable (fake
    sidecar dirs / injected readers) -- production code should use the module-level
    get_facade(), which always uses the real repo paths.
    """

    def __init__(self, *, fotmob_dir: Optional[Path] = None,
                espn_wp_dir: Optional[Path] = None,
                book_depth_dir: Optional[Path] = None) -> None:
        self._fotmob_dir = fotmob_dir or FOTMOB_SIDECAR_DIR
        self._espn_wp_dir = espn_wp_dir or ESPN_WP_DIR
        self._book_depth_dir = book_depth_dir or BOOK_DEPTH_DIR
        self._broken: Dict[str, bool] = {}
        self._warned: Dict[str, bool] = {}
        self._cache = _LruLight()

    def _mark_broken(self, source: str, exc: Exception) -> None:
        self._broken[source] = True
        if not self._warned.get(source):
            logger.debug("ingame_enrichment: %s poisoned (permanent None this process): %s",
                        source, exc)
            self._warned[source] = True

    # ------------------------------------------------------------------ fotmob --
    def fotmob_xg(self, home_display: str, away_display: str,
                 cutoff_min: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Latest as-of FotMob xG snapshot for a matched soccer fixture. None if the
        source is poisoned, the sidecar dir is absent, or no unambiguous match."""
        source = "fotmob"
        if self._broken.get(source):
            return None
        cache_key = ("fotmob", home_display, away_display)
        cached = self._cache.get(cache_key)
        try:
            from domains.soccer.ingame_fotmob import match_to_fixture

            if not self._fotmob_dir.is_dir():
                return None
            matches: List[Dict[str, Any]] = []
            for jf in self._fotmob_dir.glob("*.jsonl"):
                rows = _read_jsonl_lines(jf)
                if not rows:
                    continue
                last = rows[-1]
                matches.append({
                    "id": jf.stem,
                    "home": {"name": last.get("home")},
                    "away": {"name": last.get("away")},
                    "_row": last,
                })
            if not matches:
                return None
            fx = match_to_fixture(matches, home_display, away_display)
            if fx is None:
                return None
            row = fx.get("_row") or {}
            out = {
                "xg_home": row.get("xg_home"),
                "xg_away": row.get("xg_away"),
                "xg_asof_min": row.get("cutoff_min"),
            }
            self._cache.set(cache_key, out)
            return out
        except Exception as exc:  # noqa: BLE001 -- a lookup failure never sinks a tick
            self._mark_broken(source, exc)
            return cached

    # --------------------------------------------------------------- book depth --
    def book_depth(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Latest depth snapshot fields for *ticker* (Kalshi ticker or Polymarket
        slug), searched across today's + yesterday's date-sharded sidecars. None if
        the source is poisoned, the sidecar tree is absent, or no row matches."""
        source = "book_depth"
        if self._broken.get(source):
            return None
        cache_key = ("book_depth", ticker)
        cached = self._cache.get(cache_key)
        try:
            if not self._book_depth_dir.is_dir():
                return None
            best: Optional[Dict[str, Any]] = None
            for venue_dir in self._book_depth_dir.iterdir():
                if not venue_dir.is_dir():
                    continue
                for jf in sorted(venue_dir.glob("*.jsonl")):
                    for row in _read_jsonl_lines(jf):
                        ref = row.get("ticker") or row.get("slug")
                        if ref == ticker:
                            best = row  # last match wins (rows are append-ordered)
            if best is None:
                return None
            out = {
                "spread_bp": best.get("spread_bp"),
                "book_thinness": best.get("book_thinness"),
                "stale_quote": best.get("stale_quote_flag"),
            }
            self._cache.set(cache_key, out)
            return out
        except Exception as exc:  # noqa: BLE001
            self._mark_broken(source, exc)
            return cached

    # ------------------------------------------------------------------ espn_wp --
    def espn_wp(self, sport: str, event_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Latest ESPN win-probability reference snapshot for (sport, event_id).
        mlb/wnba only (matches espn_wp_reference.SUPPORTED_SPORTS); None if event_id
        is absent (cheap id not available -- caller records pending), the source is
        poisoned, or no sidecar exists yet."""
        source = "espn_wp"
        if self._broken.get(source):
            return None
        if not event_id:
            return None  # honest "pending" case: no cheap event id available
        cache_key = ("espn_wp", sport, event_id)
        cached = self._cache.get(cache_key)
        try:
            from scripts.platformkit.espn_wp_reference import SUPPORTED_SPORTS

            if str(sport or "").lower() not in SUPPORTED_SPORTS:
                return None
            path = self._espn_wp_dir / str(sport).lower() / "espn_wp" / ("%s.jsonl" % event_id)
            rows = _read_jsonl_lines(path)
            if not rows:
                return None
            last = rows[-1]
            out = {"espn_wp": last.get("espn_wp_home")}
            self._cache.set(cache_key, out)
            return out
        except Exception as exc:  # noqa: BLE001
            self._mark_broken(source, exc)
            return cached


_SINGLETON: Optional[EnrichmentFacade] = None


def get_facade() -> EnrichmentFacade:
    """Module-level singleton so the capture loop reuses one cached facade per process."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = EnrichmentFacade()
    return _SINGLETON


__all__ = ["EnrichmentFacade", "get_facade", "FOTMOB_SIDECAR_DIR", "ESPN_WP_DIR", "BOOK_DEPTH_DIR"]
