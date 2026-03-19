"""
odds_scraper.py — Historical NBA closing lines scraper.

Scrapes OddsPortal for historical NBA game closing lines (spread + total)
to enable CLV (closing line value) backtesting against model predictions.

Rate limits:
  - 2s delay between page fetches
  - 7-day TTL on cached files
  - Historical data only — never scrape live odds

Public API
----------
    get_historical_lines(season)              -> list[dict]
    get_game_lines(home_team, away_team, date) -> dict
    fetch_multi_season(seasons)               -> dict
    match_lines_to_game_ids(lines, game_ids)  -> list[dict]
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, date
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_EXT_CACHE  = os.path.join(PROJECT_DIR, "data", "external")
_TTL_7D     = 7 * 24 * 3600

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection":      "keep-alive",
}


# ─────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(name: str) -> str:
    return os.path.join(_EXT_CACHE, f"{name}.json")


def _is_fresh(path: str, ttl: float) -> bool:
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) < ttl


def _load(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data) -> None:
    os.makedirs(_EXT_CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(s))


def _rate_limit(secs: float = 2.0) -> None:
    time.sleep(secs)


# ─────────────────────────────────────────────────────────────────────────────
# OddsPortal fetch + parse
# ─────────────────────────────────────────────────────────────────────────────

_OP_BASE = "https://www.oddsportal.com"

# Map display team names (OddsPortal) → NBA abbreviations
_TEAM_NAME_MAP: dict = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN",
    "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE",
    "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET",
    "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL",
    "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL",
    "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL",
    "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR",
    "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA", "Washington Wizards": "WAS",
    # Short names
    "Hawks": "ATL", "Celtics": "BOS", "Nets": "BKN", "Hornets": "CHA",
    "Bulls": "CHI", "Cavaliers": "CLE", "Mavericks": "DAL", "Nuggets": "DEN",
    "Pistons": "DET", "Warriors": "GSW", "Rockets": "HOU", "Pacers": "IND",
    "Clippers": "LAC", "Lakers": "LAL", "Grizzlies": "MEM", "Heat": "MIA",
    "Bucks": "MIL", "Timberwolves": "MIN", "Pelicans": "NOP", "Knicks": "NYK",
    "Thunder": "OKC", "Magic": "ORL", "76ers": "PHI", "Suns": "PHX",
    "Trail Blazers": "POR", "Kings": "SAC", "Spurs": "SAS", "Raptors": "TOR",
    "Jazz": "UTA", "Wizards": "WAS",
}


def _team_to_abbrev(name: str) -> str:
    for k, v in _TEAM_NAME_MAP.items():
        if k.lower() in name.lower():
            return v
    return name[:3].upper()


def _parse_odds_portal_page(html: str) -> list:
    """Parse game rows from an OddsPortal NBA results page."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError("beautifulsoup4 not installed.")

    soup = BeautifulSoup(html, "html.parser")
    records = []

    # OddsPortal uses a table with class "table-main"
    table = soup.find("table", {"class": re.compile(r"table-main")})
    if table is None:
        # Try JSON embedded in page scripts
        records = _parse_embedded_json(str(soup))
        return records

    for row in table.find_all("tr", {"class": re.compile(r"deactivate|odd")}):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        try:
            # Cell 0: date/time or match info
            # Cell 1: home vs away
            match_cell = cells[1] if len(cells) > 1 else cells[0]
            teams_text = match_cell.get_text(" ", strip=True)

            # Parse score and teams (format varies: "Home - Away 110-102")
            parts = re.split(r"\s+-\s+|\s*:\s*", teams_text)
            if len(parts) < 2:
                continue
            home_raw = parts[0].strip()
            away_raw = parts[1].strip() if len(parts) > 1 else ""

            # Extract score if present
            score_match = re.search(r"(\d+)[:\-](\d+)", teams_text)
            home_score = int(score_match.group(1)) if score_match else None
            away_score = int(score_match.group(2)) if score_match else None

            # Odds cells
            home_ml = _parse_odds_value(cells[2].get_text(strip=True) if len(cells) > 2 else "")
            away_ml = _parse_odds_value(cells[3].get_text(strip=True) if len(cells) > 3 else "")

            # Spread and total may be in additional cells
            spread = _parse_odds_value(cells[4].get_text(strip=True) if len(cells) > 4 else "")
            total  = _parse_odds_value(cells[5].get_text(strip=True) if len(cells) > 5 else "")

            # Date from first cell or row attribute
            date_str = cells[0].get_text(strip=True) if cells else ""

            records.append({
                "home_team":       _team_to_abbrev(home_raw),
                "away_team":       _team_to_abbrev(away_raw),
                "home_score":      home_score,
                "away_score":      away_score,
                "home_ml":         home_ml,
                "away_ml":         away_ml,
                "closing_spread":  spread,
                "closing_total":   total,
                "open_spread":     None,   # requires detail page
                "open_total":      None,
                "date":            date_str,
                "game_id":         None,   # populated by match_lines_to_game_ids
            })
        except Exception:
            continue

    return records


def _parse_embedded_json(html: str) -> list:
    """Try to extract game data from embedded JSON in the page script tags."""
    # OddsPortal sometimes embeds data as window.pageProps or similar
    matches = re.findall(r'"home"\s*:\s*"([^"]+)".*?"away"\s*:\s*"([^"]+)"', html)
    if not matches:
        return []
    records = []
    for home, away in matches:
        records.append({
            "home_team": _team_to_abbrev(home),
            "away_team": _team_to_abbrev(away),
            "home_score": None, "away_score": None,
            "home_ml": None, "away_ml": None,
            "closing_spread": None, "closing_total": None,
            "open_spread": None, "open_total": None,
            "date": "", "game_id": None,
        })
    return records


def _parse_odds_value(text: str) -> Optional[float]:
    """Parse a decimal or American odds string to float."""
    text = text.strip()
    if not text or text in ("-", "N/A", "—"):
        return None
    try:
        val = float(re.sub(r"[^\d.\-+]", "", text))
        return round(val, 2)
    except ValueError:
        return None


def _fetch_season_lines(season: str, page: int = 1) -> list:
    """Fetch one page of results from OddsPortal for an NBA season."""
    import requests

    # OddsPortal season URL format: /basketball/usa/nba-{year-year}/results/
    year_start = int(season.split("-")[0])
    year_end = year_start + 1
    url = f"{_OP_BASE}/basketball/usa/nba-{year_start}-{year_end}/results/"
    if page > 1:
        url += f"#/page/{page}/"

    _rate_limit(2.0)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        if resp.status_code == 200:
            return _parse_odds_portal_page(resp.text)
        print(f"[odds_scraper] HTTP {resp.status_code} for {url}")
        return []
    except Exception as e:
        print(f"[odds_scraper] Fetch error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_historical_lines(
    season: str = "2024-25",
    max_pages: int = 10,
) -> list:
    """
    Build historical game results for an NBA season using the NBA Stats API.

    OddsPortal and similar sites are JavaScript-rendered and require a browser
    to scrape.  This function fetches completed game results via LeagueGameFinder
    and stores them in the same schema so that backtest_clv() can compare the
    model's predicted spread against the actual margin.

    NOTE: ``closing_spread`` here is the actual game margin (home - away), not
    a bookmaker line.  True CLV against a sportsbook requires integration with
    a paid odds API (The Odds API, Pinnacle feed, etc.) and can be layered in
    once an API key is available.  For now the backtest measures how well the
    model predicted the outcome direction vs actual result — a useful pre-book
    accuracy baseline.

    Args:
        season: e.g. "2024-25"
        max_pages: Ignored (kept for API compat — LeagueGameFinder returns all
                   completed games in one call)

    Returns:
        List of game dicts with keys: game_id, home_team, away_team,
        home_score, away_score, closing_spread (actual margin), closing_total
        (actual combined score), date.
    """
    key  = f"historical_lines_{_safe(season)}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_7D):
        return _load(path)

    try:
        from nba_api.stats.endpoints import leaguegamefinder
    except ImportError:
        raise RuntimeError("nba_api not installed.")

    _rate_limit(0.8)
    try:
        resp = leaguegamefinder.LeagueGameFinder(
            season_nullable=season,
            season_type_nullable="Regular Season",
            league_id_nullable="00",
        )
        df = resp.get_data_frames()[0]
    except Exception as e:
        print(f"[odds_scraper] LeagueGameFinder error: {e}")
        _save(path, [])
        return []

    # Each game appears twice (once per team). Keep only home-team rows to
    # de-duplicate: MATCHUP contains "vs." for home games, "@" for away.
    home_df = df[df["MATCHUP"].str.contains(r"vs\.", na=False)].copy()

    import math

    def _safe_int(val, default: int = 0) -> int:
        """Convert pandas cell value to int, handling NaN and None."""
        if val is None:
            return default
        try:
            f = float(val)
            return default if math.isnan(f) else int(f)
        except (TypeError, ValueError):
            return default

    records: list = []
    for _, row in home_df.iterrows():
        try:
            home_abbr = str(row.get("TEAM_ABBREVIATION", ""))
            matchup   = str(row.get("MATCHUP", ""))
            away_abbr = matchup.split("vs.")[-1].strip() if "vs." in matchup else ""

            home_pts   = _safe_int(row.get("PTS"))
            plus_minus = _safe_int(row.get("PLUS_MINUS"))
            away_pts   = home_pts - plus_minus
            total      = home_pts + away_pts

            records.append({
                "game_id":        str(row.get("GAME_ID", "")),
                "home_team":      home_abbr,
                "away_team":      away_abbr,
                "home_score":     home_pts,
                "away_score":     away_pts,
                "closing_spread": float(plus_minus),
                "closing_total":  float(total),
                "open_spread":    None,
                "open_total":     None,
                "home_ml":        None,
                "away_ml":        None,
                "date":           str(row.get("GAME_DATE", "")),
                "source":         "nba_api_actual_margin",
            })
        except Exception as exc:
            print(f"[odds_scraper] row parse error: {exc}")
            continue

    _save(path, records)
    print(f"[odds_scraper] {season}: {len(records)} completed games (actual margins)")
    return records


def get_game_lines(
    home_team: str,
    away_team: str,
    game_date: Optional[str] = None,
    season: str = "2024-25",
) -> dict:
    """
    Look up closing lines for a specific game.

    Args:
        home_team: NBA abbreviation (e.g. "BOS")
        away_team: NBA abbreviation (e.g. "LAL")
        game_date: YYYY-MM-DD string, or None to find most recent matchup
        season: Season to search in

    Returns:
        Game line dict, or {} if not found.
    """
    lines = get_historical_lines(season)
    home_q = home_team.upper()
    away_q = away_team.upper()

    candidates = [
        r for r in lines
        if r.get("home_team", "").upper() == home_q
        and r.get("away_team", "").upper() == away_q
    ]

    if not candidates:
        return {}

    if game_date:
        exact = [r for r in candidates if game_date in r.get("date", "")]
        if exact:
            return exact[0]

    # Return most recent
    return candidates[-1]


def fetch_multi_season(
    seasons: Optional[List[str]] = None,
    delay: float = 3.0,
) -> dict:
    """
    Pull historical lines for multiple seasons.

    Args:
        seasons: List of season strings. Defaults to last 3.
        delay: Extra delay between season fetches.

    Returns:
        {season: records_list}
    """
    if seasons is None:
        seasons = ["2024-25", "2023-24", "2022-23"]

    results = {}
    for s in seasons:
        data = get_historical_lines(s)
        results[s] = data
        print(f"[odds_scraper] {s}: {len(data)} games")
        time.sleep(delay)

    return results


def match_lines_to_game_ids(
    lines: list,
    game_lookup: dict,
) -> list:
    """
    Attempt to match scraped lines to NBA Stats game IDs using date + teams.

    Args:
        lines: List of line dicts from get_historical_lines()
        game_lookup: Dict mapping "YYYY-MM-DD_HOME_AWAY" → game_id.
                     Build from nba_stats.fetch_game_ids() or schedule data.

    Returns:
        lines list with game_id field populated where matched.
    """
    matched = 0
    for r in lines:
        date_str = r.get("date", "")
        home = r.get("home_team", "")
        away = r.get("away_team", "")
        key = f"{date_str}_{home}_{away}"
        gid = game_lookup.get(key)
        if gid:
            r["game_id"] = gid
            matched += 1
    print(f"[odds_scraper] Matched {matched}/{len(lines)} lines to game IDs")
    return lines


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Historical odds scraper")
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--all-seasons", action="store_true")
    parser.add_argument("--home", default=None)
    parser.add_argument("--away", default=None)
    args = parser.parse_args()

    if args.all_seasons:
        results = fetch_multi_season()
        for s, data in results.items():
            print(f"{s}: {len(data)} games")
    elif args.home and args.away:
        lines = get_game_lines(args.home, args.away, season=args.season)
        print(json.dumps(lines, indent=2))
    else:
        data = get_historical_lines(args.season)
        print(f"Historical lines for {args.season}: {len(data)} games")
        if data:
            print(json.dumps(data[0], indent=2))
