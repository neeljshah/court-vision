"""
historical_odds_backfill.py — Backfill NBA historical closing/opening lines into
the `odds_lines` DB table from free public sources.

Primary source: sportsoddshistory.com season pages (best-effort HTML table
parser — may need refinement against live HTML changes).
Documented future fallback: Wayback Machine snapshots of the same pages.

This module replaces paid historical-odds purchases for the CLV / model-
calibration pipeline. It caches parsed JSON locally (7-day TTL) to avoid
redundant fetches during development and re-runs.

Usage (CLI):
    python -m src.data.scrapers.historical_odds_backfill \\
        --seasons 2022-23 2023-24 2024-25 [--incremental] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import sys
import time
import uuid
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

# Add project root so `src.data.db` is importable when run directly.
PROJECT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.data.db import execute_batch, get_connection  # noqa: E402

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_RATE_LIMIT_S = 1.5
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}
_SOH_BASE = "https://www.sportsoddshistory.com"
_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "external")
_CACHE_TTL_S = 7 * 24 * 3600  # 7 days


# ── Parser ────────────────────────────────────────────────────────────────────


def parse_sportsoddshistory_table(html: str, season: str) -> List[Dict]:
    """
    Parse a sportsoddshistory NBA season page and return a list of record dicts.

    Each record covers one game with market="game", carrying both
    ``spread_home`` and ``total_over``.  Rows that cannot be parsed are
    skipped silently (best-effort against the site's evolving table layout).

    Args:
        html:   Raw HTML of the season page.
        season: Season string used to build the deterministic game_id
                (e.g. ``"2023-24"``).

    Returns:
        List of dicts with keys: game_id, game_date, home_team, away_team,
        bookmaker, market, spread_home, total_over, is_opening, is_closing.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        logger.warning("No <table> found on sportsoddshistory page for %s", season)
        return []

    records: List[Dict] = []
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        # Need at least 5 columns: date, away, home, spread, total
        if len(cells) < 5:
            continue
        texts = [c.get_text(strip=True) for c in cells]
        # Skip header-style rows
        if any(t.lower() in ("date", "away", "home", "spread", "total", "game") for t in texts[:3]):
            continue
        try:
            game_date = texts[0]
            away_team = texts[1]
            home_team = texts[2]
            spread_raw = texts[3]
            total_raw = texts[4]

            if not game_date or not away_team or not home_team:
                continue

            # Parse spread — may be "PK", "-3.5", "+2", etc.
            spread_home: Optional[float] = None
            spread_clean = spread_raw.replace("PK", "0").replace("+", "").strip()
            if spread_clean:
                spread_home = float(spread_clean)

            # Parse total — "O/U 224.5", "224", "OU 224.5", etc.
            total_over: Optional[float] = None
            total_clean = total_raw.upper().replace("O/U", "").replace("OU", "").strip()
            if total_clean:
                total_over = float(total_clean)

            game_id = f"{season}_{game_date}_{away_team}_{home_team}"
            records.append(
                {
                    "game_id": game_id,
                    "game_date": game_date,
                    "home_team": home_team,
                    "away_team": away_team,
                    "bookmaker": "consensus",
                    "market": "game",
                    "spread_home": spread_home,
                    "total_over": total_over,
                    "is_opening": False,
                    "is_closing": True,
                }
            )
        except (ValueError, IndexError):
            # Malformed row — skip without aborting the whole season.
            logger.debug("Skipping malformed row: %s", texts)
            continue

    return records


# ── Fetch + cache ─────────────────────────────────────────────────────────────


def _season_url(season: str) -> str:
    """Build the sportsoddshistory URL for a given NBA season string."""
    # e.g. 2023-24  →  /nba-odds-2023-24/
    return f"{_SOH_BASE}/nba-odds-{season}/"


def _cache_path(season: str) -> str:
    return os.path.join(_CACHE_DIR, f"odds_backfill_{season}.json")


def fetch_season(season: str, force: bool = False) -> List[Dict]:
    """
    Return parsed odds records for a single NBA season.

    File-caches results as JSON at ``data/external/odds_backfill_{season}.json``
    with a 7-day TTL (mtime-based).  On a cache miss the page is fetched via
    HTTP (rate-limited) and the result written to the cache.

    Args:
        season: Season string, e.g. ``"2023-24"``.
        force:  If True, ignore the cache and always re-fetch.

    Returns:
        List of record dicts as produced by
        :func:`parse_sportsoddshistory_table`.
    """
    cache = _cache_path(season)
    os.makedirs(_CACHE_DIR, exist_ok=True)

    # Use cached file if fresh enough
    if not force and os.path.exists(cache):
        age = time.time() - os.path.getmtime(cache)
        if age < _CACHE_TTL_S:
            with open(cache, "r", encoding="utf-8") as fh:
                return json.load(fh)

    url = _season_url(season)
    logger.info("Fetching %s", url)
    time.sleep(_RATE_LIMIT_S)
    resp = requests.get(url, headers=_HEADERS, timeout=30)
    resp.raise_for_status()

    records = parse_sportsoddshistory_table(resp.text, season)
    with open(cache, "w", encoding="utf-8") as fh:
        json.dump(records, fh)
    logger.info("Season %s: %d records fetched", season, len(records))
    return records


# ── Ingester ──────────────────────────────────────────────────────────────────

_INSERT_SQL = """
INSERT INTO odds_lines
    (id, sport, game_id, bookmaker, market, spread_home, total_over,
     is_opening, is_closing, recorded_at)
VALUES
    (%(id)s, %(sport)s, %(game_id)s, %(bookmaker)s, %(market)s,
     %(spread_home)s, %(total_over)s, %(is_opening)s, %(is_closing)s,
     %(recorded_at)s)
"""

_INSERT_RUN_SQL = """
INSERT INTO scraper_runs
    (id, sport, source, run_type, run_started_at, status)
VALUES
    (%(id)s, %(sport)s, %(source)s, %(run_type)s, %(run_started_at)s,
     %(status)s)
"""

_UPDATE_RUN_SQL = """
UPDATE scraper_runs
SET run_finished_at = %(run_finished_at)s,
    status          = %(status)s,
    rows_written    = %(rows_written)s,
    last_key        = %(last_key)s,
    error_message   = %(error_message)s
WHERE id = %(id)s
"""

_LAST_KEY_SQL = """
SELECT last_key FROM scraper_runs
WHERE sport = %(sport)s AND source = %(source)s
  AND status IN ('success', 'partial')
ORDER BY run_started_at DESC
LIMIT 1
"""


class OddsBackfillIngester:
    """Ingest historical NBA odds from sportsoddshistory into `odds_lines`."""

    def __init__(
        self,
        sport: str = "nba",
        source: str = "sportsoddshistory",
        rate_limit_s: float = _RATE_LIMIT_S,
    ) -> None:
        self.sport = sport
        self.source = source
        self.rate_limit_s = rate_limit_s

    # ── Run lifecycle helpers ─────────────────────────────────────────────────

    def _start_run(self, conn, run_type: str) -> str:
        run_id = uuid.uuid4().hex
        cur = conn.cursor()
        cur.execute(
            _INSERT_RUN_SQL,
            {
                "id": run_id,
                "sport": self.sport,
                "source": self.source,
                "run_type": run_type,
                "run_started_at": datetime.datetime.now().isoformat(),
                "status": "running",
            },
        )
        conn.commit()
        return run_id

    def _finish_run(
        self,
        conn,
        run_id: str,
        rows_written: int,
        status: str,
        last_key: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        cur = conn.cursor()
        cur.execute(
            _UPDATE_RUN_SQL,
            {
                "id": run_id,
                "run_finished_at": datetime.datetime.now().isoformat(),
                "status": status,
                "rows_written": rows_written,
                "last_key": last_key,
                "error_message": error,
            },
        )
        conn.commit()

    def _last_key(self, conn) -> Optional[str]:
        cur = conn.cursor()
        cur.execute(
            _LAST_KEY_SQL,
            {"sport": self.sport, "source": self.source},
        )
        row = cur.fetchone()
        if row is None:
            return None
        # Supports both sqlite3.Row (index) and tuple
        return row[0] if not hasattr(row, "keys") else row["last_key"]

    # ── Core operations ───────────────────────────────────────────────────────

    def backfill(
        self,
        seasons: List[str],
        resume_from: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict:
        """
        Backfill odds for the given seasons, writing to `odds_lines`.

        Args:
            seasons:     Ordered list of season strings, e.g. ``["2022-23", "2023-24"]``.
            resume_from: If set, skip all seasons up to *and including* this one
                         (list order determines "up to").
            limit:       Stop after this many total rows written (for testing / caps).

        Returns:
            Dict with keys ``seasons``, ``rows_written``, ``run_id``.
        """
        conn = get_connection()
        run_id = self._start_run(conn, "full" if resume_from is None else "incremental")

        total_written = 0
        last_good_season: Optional[str] = None
        final_status = "success"
        error_msg: Optional[str] = None

        # Build the effective season list (skip already-done seasons when resuming)
        effective_seasons = list(seasons)
        if resume_from and resume_from in effective_seasons:
            idx = effective_seasons.index(resume_from)
            effective_seasons = effective_seasons[idx + 1:]

        processed_seasons: List[str] = []
        try:
            for season in effective_seasons:
                if limit is not None and total_written >= limit:
                    break
                try:
                    records = fetch_season(season)
                except Exception as exc:
                    logger.error("fetch_season failed for %s: %s", season, exc)
                    final_status = "partial"
                    error_msg = str(exc)
                    continue

                # Build param dicts for execute_batch
                now = datetime.datetime.now().isoformat()
                params_list = [
                    {
                        "id": uuid.uuid4().hex,
                        "sport": self.sport,
                        "game_id": rec["game_id"],
                        "bookmaker": rec["bookmaker"],
                        "market": rec["market"],
                        "spread_home": rec.get("spread_home"),
                        "total_over": rec.get("total_over"),
                        "is_opening": rec.get("is_opening", False),
                        "is_closing": rec.get("is_closing", True),
                        "recorded_at": now,
                    }
                    for rec in records
                ]

                # Honour limit by truncating the batch
                if limit is not None:
                    remaining = limit - total_written
                    params_list = params_list[:remaining]

                if params_list:
                    cur = conn.cursor()
                    execute_batch(cur, _INSERT_SQL, params_list)
                    conn.commit()

                total_written += len(params_list)
                last_good_season = season
                processed_seasons.append(season)

        except Exception as exc:  # unexpected top-level error
            final_status = "error" if total_written == 0 else "partial"
            error_msg = str(exc)
            logger.exception("Unexpected error during backfill")

        if total_written == 0 and final_status == "success":
            # No seasons were processed (all skipped by resume_from or empty list)
            final_status = "success"

        self._finish_run(
            conn,
            run_id,
            rows_written=total_written,
            status=final_status,
            last_key=last_good_season,
            error=error_msg,
        )
        conn.close()
        return {"seasons": processed_seasons, "rows_written": total_written, "run_id": run_id}

    def incremental(self, seasons: List[str]) -> Dict:
        """
        Resume from the last successfully completed season.

        Reads the ``last_key`` from the most recent successful/partial
        ``scraper_runs`` row, then delegates to :meth:`backfill`.

        Args:
            seasons: Full ordered season list (same as for ``backfill``).

        Returns:
            Same dict as :meth:`backfill`.
        """
        conn = get_connection()
        last_key = self._last_key(conn)
        conn.close()
        return self.backfill(seasons, resume_from=last_key)


# ── CLI ───────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Backfill NBA historical odds into odds_lines from sportsoddshistory.com"
    )
    p.add_argument(
        "--seasons",
        nargs="+",
        default=["2022-23", "2023-24", "2024-25"],
        help="Season strings to ingest (default: 2022-23 2023-24 2024-25)",
    )
    p.add_argument(
        "--incremental",
        action="store_true",
        help="Resume from last successfully completed season",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Ignore local cache and re-fetch all pages",
    )
    p.add_argument("--limit", type=int, default=None, help="Max rows to write (testing cap)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch + parse only; print row counts without writing to DB",
    )
    return p


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_parser().parse_args()

    if args.dry_run:
        totals: Dict[str, int] = {}
        for season in args.seasons:
            recs = fetch_season(season, force=args.force)
            totals[season] = len(recs)
        print(json.dumps({"dry_run": True, "counts": totals}))
        sys.exit(0)

    ingester = OddsBackfillIngester()
    if args.incremental:
        result = ingester.incremental(args.seasons)
    else:
        result = ingester.backfill(args.seasons, limit=args.limit)

    print(json.dumps(result))
