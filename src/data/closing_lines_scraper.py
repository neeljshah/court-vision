"""
closing_lines_scraper.py — Free-source closing lines scraper for NBA games.

Priority order:
  1. The-Odds-API (free tier, requires THE_ODDS_API_KEY env var)
  2. Sportsbookreview.com historical archive (HTML scrape)
  3. OddsShark historical scores page (HTML scrape)

Each source returns normalized game-line dicts. Blocked sources are logged
and skipped — the whole run does not fail.

Public API
----------
    scrape_date(date_str)   -> list[dict]
    load_cached(date_str)   -> list[dict] | None
    canonical_record(...)   -> dict
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Optional

import urllib.robotparser

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_CACHE_DIR = os.path.join(PROJECT_DIR, "data", "cache", "closing_lines")
_UA = (
    "CourtVision-NBA-AI/1.0 (https://github.com/neel/nba-ai-system; "
    "research/non-commercial; neeljshah22@gmail.com)"
)
_DELAY = 2.5  # seconds between requests

log = logging.getLogger(__name__)


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_path(date_str: str) -> str:
    return os.path.join(_CACHE_DIR, f"{date_str}.json")


def load_cached(date_str: str) -> Optional[list]:
    """Return cached lines for date_str or None if not cached."""
    path = _cache_path(date_str)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("lines", [])
    return None


def _save_cache(date_str: str, lines: list, source: str) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = _cache_path(date_str)
    payload = {
        "date": date_str,
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "source": source,
        "lines": lines,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    log.info("[closing_lines] cached %d lines for %s → %s", len(lines), date_str, path)


# ── Robots.txt check ─────────────────────────────────────────────────────────

def _robots_allows(base_url: str, path: str = "/") -> bool:
    """Return True if robots.txt permits our UA to fetch path."""
    robots_url = base_url.rstrip("/") + "/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        allowed = rp.can_fetch(_UA, base_url.rstrip("/") + path)
        if not allowed:
            log.warning("[closing_lines] robots.txt disallows %s%s — skipping source", base_url, path)
        return allowed
    except Exception as exc:
        log.debug("[closing_lines] robots.txt fetch failed (%s) — assuming allowed", exc)
        return True


# ── Shared HTTP helper ────────────────────────────────────────────────────────

def _get(url: str, *, timeout: int = 30, json_mode: bool = False):
    """Rate-limited GET. Returns response or None on error."""
    import urllib.request
    import urllib.error

    time.sleep(_DELAY)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if json_mode:
                return json.loads(raw.decode("utf-8"))
            return raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        log.warning("[closing_lines] HTTP %s for %s", exc.code, url)
        return None
    except Exception as exc:
        log.warning("[closing_lines] fetch error %s: %s", url, exc)
        return None


# ── Canonical record factory ──────────────────────────────────────────────────

def canonical_record(
    *,
    date: str,
    home: str,
    away: str,
    game_id: Optional[str] = None,
    open_total: Optional[float] = None,
    close_total: Optional[float] = None,
    open_spread_home: Optional[float] = None,
    close_spread_home: Optional[float] = None,
    open_ml_home: Optional[int] = None,
    close_ml_home: Optional[int] = None,
    open_ml_away: Optional[int] = None,
    close_ml_away: Optional[int] = None,
    book: str = "consensus",
    scraped_at: Optional[str] = None,
) -> dict:
    return {
        "game_id": game_id,
        "date": date,
        "home": home,
        "away": away,
        "open_total": open_total,
        "close_total": close_total,
        "open_spread_home": open_spread_home,
        "close_spread_home": close_spread_home,
        "open_ml_home": open_ml_home,
        "close_ml_home": close_ml_home,
        "open_ml_away": open_ml_away,
        "close_ml_away": close_ml_away,
        "book": book,
        "scraped_at": scraped_at or (datetime.utcnow().isoformat() + "Z"),
    }


# ── Source 1: The-Odds-API (free tier) ───────────────────────────────────────

_ODDS_API_KEY = os.environ.get("THE_ODDS_API_KEY", "")
_ODDS_API_BASE = "https://api.the-odds-api.com/v4"


def _fetch_odds_api(date_str: str) -> list:
    """Fetch historical NBA lines from The-Odds-API (key required)."""
    if not _ODDS_API_KEY:
        log.info("[closing_lines/odds_api] THE_ODDS_API_KEY not set — skipping")
        return []

    # API uses ISO8601 commence_time filters
    iso_date = date_str + "T00:00:00Z"
    iso_end  = date_str + "T23:59:59Z"
    url = (
        f"{_ODDS_API_BASE}/historical/sports/basketball_nba/odds"
        f"?apiKey={_ODDS_API_KEY}"
        f"&regions=us"
        f"&markets=h2h,spreads,totals"
        f"&date={iso_date}"
        f"&commenceTimeFrom={iso_date}"
        f"&commenceTimeTo={iso_end}"
        f"&bookmakers=pinnacle,draftkings,fanduel"
    )

    data = _get(url, json_mode=True)
    if not data or "data" not in data:
        log.warning("[closing_lines/odds_api] no data returned for %s", date_str)
        return []

    records = []
    for event in data["data"]:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        rec = canonical_record(date=date_str, home=home, away=away,
                               game_id=event.get("id"), book="odds_api")

        for bm in event.get("bookmakers", []):
            for market in bm.get("markets", []):
                outcomes = {o["name"]: o for o in market.get("outcomes", [])}
                if market["key"] == "h2h":
                    home_out = outcomes.get(home, {})
                    away_out = outcomes.get(away, {})
                    rec["close_ml_home"] = _decimal_to_american(home_out.get("price"))
                    rec["close_ml_away"] = _decimal_to_american(away_out.get("price"))
                elif market["key"] == "spreads":
                    home_out = outcomes.get(home, {})
                    rec["close_spread_home"] = home_out.get("point")
                elif market["key"] == "totals":
                    over_out = outcomes.get("Over", {})
                    rec["close_total"] = over_out.get("point")
            break  # first bookmaker only

        records.append(rec)

    log.info("[closing_lines/odds_api] fetched %d events for %s", len(records), date_str)
    return records


def _decimal_to_american(decimal: Optional[float]) -> Optional[int]:
    """Convert decimal odds (European) to American format."""
    if decimal is None:
        return None
    try:
        d = float(decimal)
        if d >= 2.0:
            return int(round((d - 1) * 100))
        else:
            return int(round(-100 / (d - 1)))
    except (ZeroDivisionError, ValueError, TypeError):
        return None


# ── Source 2: Sportsbookreview.com ───────────────────────────────────────────

_SBR_BASE = "https://www.sportsbookreview.com"
_SBR_PATH = "/betting-odds/nba-basketball/"

_TEAM_ABBREV_MAP = {
    "hawks": "ATL", "celtics": "BOS", "nets": "BKN", "hornets": "CHA",
    "bulls": "CHI", "cavaliers": "CLE", "mavericks": "DAL", "nuggets": "DEN",
    "pistons": "DET", "warriors": "GSW", "rockets": "HOU", "pacers": "IND",
    "clippers": "LAC", "lakers": "LAL", "grizzlies": "MEM", "heat": "MIA",
    "bucks": "MIL", "timberwolves": "MIN", "pelicans": "NOP", "knicks": "NYK",
    "thunder": "OKC", "magic": "ORL", "76ers": "PHI", "suns": "PHX",
    "trail blazers": "POR", "kings": "SAC", "spurs": "SAS", "raptors": "TOR",
    "jazz": "UTA", "wizards": "WAS",
}


def _abbrev(name: str) -> str:
    name_l = name.lower().strip()
    for k, v in _TEAM_ABBREV_MAP.items():
        if k in name_l:
            return v
    return name[:3].upper()


def _parse_sbr_html(html: str, date_str: str) -> list:
    """Parse SBR NBA odds page. Returns list of canonical records.

    SBR structure (as of 2026):
      __NEXT_DATA__.props.pageProps.oddsTables[].oddsTableModel.gameRows[]
        .gameView   — teams
        .oddsViews[]  — per-book opening + current (closing) lines
        .openingLineViews[] — opening totals/ML per book (may overlap)
    We aggregate across all books, preferring the first pinny/consensus book.
    """
    records = []
    try:
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        if not m:
            return []
        data = json.loads(m.group(1))
        props = data.get("props", {}).get("pageProps", {})
        tables = props.get("oddsTables", props.get("events", []))

        for table in tables:
            game_rows = table.get("oddsTableModel", {}).get("gameRows", [])
            for row in game_rows:
                gm = row.get("gameView", {})
                home = _abbrev(gm.get("homeTeam", {}).get("fullName", ""))
                away = _abbrev(gm.get("awayTeam", {}).get("fullName", ""))
                if not home or not away:
                    continue

                # Collect open/close from oddsViews (per-sportsbook entries)
                # Prefer pinnacle → consensus → first available
                open_ml_h = open_ml_a = close_ml_h = close_ml_a = None
                open_spread = close_spread = open_total = close_total = None
                book_used = "sbr_consensus"

                odds_views = row.get("oddsViews", [])
                for ov in odds_views:
                    bk = ov.get("sportsbook", "").lower()
                    ol = ov.get("openingLine", {}) or {}
                    cl = ov.get("currentLine", {}) or {}

                    if open_ml_h is None and ol.get("homeOdds") is not None:
                        open_ml_h  = _to_int(ol.get("homeOdds"))
                        open_ml_a  = _to_int(ol.get("awayOdds"))
                        open_spread = _to_float(ol.get("homeSpread"))
                        open_total  = _to_float(ol.get("total"))
                        book_used   = bk or "sbr"

                    if close_ml_h is None and cl.get("homeOdds") is not None:
                        close_ml_h  = _to_int(cl.get("homeOdds"))
                        close_ml_a  = _to_int(cl.get("awayOdds"))
                        close_spread = _to_float(cl.get("homeSpread"))
                        close_total  = _to_float(cl.get("total"))

                    # Also look for totals in separate market columns
                    if open_total is None:
                        open_total = _to_float(ol.get("overOdds"))  # not ideal but fallback
                    if close_total is None:
                        close_total = _to_float(cl.get("overOdds"))

                    if open_ml_h is not None and close_ml_h is not None:
                        break  # found both, stop

                # Also check openingLineViews for totals
                for olv in row.get("openingLineViews", []):
                    ol = olv.get("openingLine", {}) or {}
                    if open_total is None:
                        open_total = _to_float(ol.get("total"))
                    if open_ml_h is None:
                        open_ml_h = _to_int(ol.get("homeOdds"))
                        open_ml_a = _to_int(ol.get("awayOdds"))
                    break

                rec = canonical_record(
                    date=date_str, home=home, away=away, book=book_used,
                    open_total=open_total,
                    close_total=close_total,
                    open_spread_home=open_spread,
                    close_spread_home=close_spread,
                    open_ml_home=open_ml_h,
                    close_ml_home=close_ml_h,
                    open_ml_away=open_ml_a,
                    close_ml_away=close_ml_a,
                )
                records.append(rec)
    except Exception as exc:
        log.debug("[closing_lines/sbr] parse error: %s", exc)
    return records


def _fetch_sbr(date_str: str) -> list:
    if not _robots_allows(_SBR_BASE, _SBR_PATH):
        return []
    url = f"{_SBR_BASE}{_SBR_PATH}?date={date_str}"
    html = _get(url)
    if not html:
        log.warning("[closing_lines/sbr] blocked or no response for %s", date_str)
        return []
    records = _parse_sbr_html(html, date_str)
    log.info("[closing_lines/sbr] parsed %d records for %s", len(records), date_str)
    return records


# ── Source 3: OddsShark ───────────────────────────────────────────────────────

_OS_BASE = "https://www.oddsshark.com"
_OS_PATH = "/nba/scores"


def _parse_oddsshark_html(html: str, date_str: str) -> list:
    """Parse OddsShark NBA scores page for opening/closing lines."""
    records = []
    try:
        # OddsShark embeds data in script tags as window.pageDataJSON or similar
        m = re.search(r'var\s+(?:pageData|oddsData)\s*=\s*(\{.*?\});', html, re.S)
        if not m:
            # Try JSON-LD or embedded JSON
            m = re.search(r'"games"\s*:\s*(\[.*?\])', html, re.S)
            if not m:
                return []
            games = json.loads(m.group(1))
        else:
            data = json.loads(m.group(1))
            games = data.get("games", [])

        for g in games:
            home = _abbrev(g.get("homeTeam", g.get("home_team", "")))
            away = _abbrev(g.get("awayTeam", g.get("away_team", "")))
            if not home or not away:
                continue
            rec = canonical_record(
                date=date_str, home=home, away=away, book="oddsshark",
                open_total=_to_float(g.get("openTotal", g.get("open_total"))),
                close_total=_to_float(g.get("closeTotal", g.get("close_total"))),
                open_spread_home=_to_float(g.get("openSpread", g.get("open_spread"))),
                close_spread_home=_to_float(g.get("closeSpread", g.get("close_spread"))),
                open_ml_home=_to_int(g.get("homeOpenML", g.get("open_ml_home"))),
                close_ml_home=_to_int(g.get("homeCloseML", g.get("close_ml_home"))),
                open_ml_away=_to_int(g.get("awayOpenML", g.get("open_ml_away"))),
                close_ml_away=_to_int(g.get("awayCloseML", g.get("close_ml_away"))),
            )
            records.append(rec)
    except Exception as exc:
        log.debug("[closing_lines/oddsshark] parse error: %s", exc)
    return records


def _fetch_oddsshark(date_str: str) -> list:
    if not _robots_allows(_OS_BASE, _OS_PATH):
        return []
    url = f"{_OS_BASE}{_OS_PATH}?date={date_str}"
    html = _get(url)
    if not html:
        log.warning("[closing_lines/oddsshark] blocked or no response for %s", date_str)
        return []
    records = _parse_oddsshark_html(html, date_str)
    log.info("[closing_lines/oddsshark] parsed %d records for %s", len(records), date_str)
    return records


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace("+", "").strip())
    except (ValueError, TypeError):
        return None


def _to_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(str(v).replace("+", "").strip())
    except (ValueError, TypeError):
        return None


# ── Main entry point ─────────────────────────────────────────────────────────

def scrape_date(date_str: str, *, force: bool = False) -> list:
    """Scrape all sources for date_str (YYYY-MM-DD). Returns merged line list.

    Uses cache if available unless force=True.
    """
    if not force:
        cached = load_cached(date_str)
        if cached is not None:
            log.info("[closing_lines] cache hit for %s (%d records)", date_str, len(cached))
            return cached

    lines: list = []
    source_used = "none"

    # Source 1: The-Odds-API (most reliable, free tier)
    try:
        records = _fetch_odds_api(date_str)
        if records:
            lines.extend(records)
            source_used = "odds_api"
    except Exception as exc:
        log.warning("[closing_lines/odds_api] error: %s — skipping", exc)

    # Source 2: SBR (fallback)
    if not lines:
        try:
            records = _fetch_sbr(date_str)
            if records:
                lines.extend(records)
                source_used = "sbr"
        except Exception as exc:
            log.warning("[closing_lines/sbr] error: %s — skipping", exc)

    # Source 3: OddsShark (second fallback)
    if not lines:
        try:
            records = _fetch_oddsshark(date_str)
            if records:
                lines.extend(records)
                source_used = "oddsshark"
        except Exception as exc:
            log.warning("[closing_lines/oddsshark] error: %s — skipping", exc)

    _save_cache(date_str, lines, source_used)
    return lines


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Scrape NBA closing lines for a date")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--force", action="store_true", help="Bypass cache")
    args = ap.parse_args()

    result = scrape_date(args.date, force=args.force)
    print(json.dumps({"date": args.date, "n": len(result), "lines": result[:3]}, indent=2))
