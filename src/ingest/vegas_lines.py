"""
Ingest: opener / closer lines from sportsbookreview (SBR).

Respects robots.txt — SBR allows crawling their odds history pages.
Caches to data/vegas_lines.parquet. Logs + continues if scrape fails.

Columns: game_date, home_team, away_team, book, open_spread, close_spread,
         open_total, close_total, open_ml_home, close_ml_home.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

log = logging.getLogger(__name__)

_CACHE_PATH = Path("data/vegas_lines.parquet")
_SLEEP_S    = 2.0   # polite delay between requests
_HEADERS    = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; NBAResearchBot/1.0; +research-use)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# SBR NBA odds page template
_SBR_URL = "https://www.sportsbookreview.com/betting-odds/nba-basketball/money-line/full-game/?date={date}"


def _check_robots(base_url: str = "https://www.sportsbookreview.com") -> bool:
    """Return True if crawling is allowed by robots.txt."""
    try:
        import urllib.robotparser
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{base_url}/robots.txt")
        rp.read()
        return rp.can_fetch("*", f"{base_url}/betting-odds/")
    except Exception as exc:
        log.debug("robots.txt check failed: %s", exc)
        return True   # assume allowed if check fails


def _scrape_sbr_date(game_date: str) -> List[dict]:
    """
    Scrape SBR odds for a single date (YYYY-MM-DD).
    Returns list of line dicts.
    """
    try:
        import urllib.request
        url = _SBR_URL.format(date=game_date.replace("-", ""))
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        log.warning("SBR scrape failed for %s: %s", game_date, exc)
        return []

    records: List[dict] = []
    try:
        # SBR embeds __NEXT_DATA__ JSON with odds
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
        if not match:
            log.debug("SBR: __NEXT_DATA__ not found for %s", game_date)
            return []
        data = json.loads(match.group(1))

        # Navigate to events — path may vary with SBR site updates
        events = (
            data.get("props", {})
                .get("pageProps", {})
                .get("oddsTables", [{}])[0]
                .get("oddsTableModel", {})
                .get("gameRows", [])
        )
        for event in events:
            game_view = event.get("gameView", {})
            home = game_view.get("homeTeam", {}).get("shortName", "")
            away = game_view.get("awayTeam", {}).get("shortName", "")
            for book_row in event.get("oddsViews", []):
                if not book_row:
                    continue
                book = book_row.get("sportsbook", "")
                curr = book_row.get("currentLine", {}) or {}
                open_ = book_row.get("openingLine", {}) or {}
                records.append({
                    "game_date":      game_date,
                    "home_team":      home,
                    "away_team":      away,
                    "book":           book,
                    "open_spread":    open_.get("homeSpread"),
                    "close_spread":   curr.get("homeSpread"),
                    "open_total":     open_.get("total"),
                    "close_total":    curr.get("total"),
                    "open_ml_home":   open_.get("homeOdds"),
                    "close_ml_home":  curr.get("homeOdds"),
                })
    except Exception as exc:
        log.warning("SBR parse failed for %s: %s", game_date, exc)

    return records


def ingest_vegas_lines(
    game_dates: List[str],
    cache_path: Path = _CACHE_PATH,
    sleep_s: float = _SLEEP_S,
) -> pd.DataFrame:
    """
    Fetch opener/closer lines for a list of game dates (YYYY-MM-DD).

    Respects robots.txt. Caches results. Safe to call repeatedly.
    """
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    cached_dates: set = set()
    frames: List[pd.DataFrame] = []

    if cache_path.exists():
        try:
            cached = pd.read_parquet(cache_path)
            cached_dates = set(cached["game_date"].astype(str))
            frames.append(cached)
            log.info("vegas_lines: %d dates cached", len(cached_dates))
        except Exception as exc:
            log.warning("vegas_lines cache read failed: %s", exc)

    new_dates = [d for d in game_dates if d not in cached_dates]

    if new_dates and not _check_robots():
        log.warning("vegas_lines: robots.txt disallows crawling — skipping scrape")
        return pd.concat(frames) if frames else pd.DataFrame()

    log.info("vegas_lines: scraping %d new dates", len(new_dates))
    for gd in new_dates:
        rows = _scrape_sbr_date(gd)
        if rows:
            frames.append(pd.DataFrame(rows))
            log.debug("vegas_lines: %d rows for %s", len(rows), gd)
        else:
            log.info("vegas_lines: no data for %s (logged, continuing)", gd)
        time.sleep(sleep_s)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)

    try:
        result.to_parquet(cache_path, index=False)
        log.info("vegas_lines: saved %d rows to %s", len(result), cache_path)
    except Exception as exc:
        log.error("vegas_lines cache write failed: %s", exc)

    return result
