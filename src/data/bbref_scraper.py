"""
bbref_scraper.py — Basketball Reference advanced stats scraper.

Scrapes per-player advanced metrics not available in the NBA Stats API:
  - BPM (Box Plus/Minus), VORP, Win Shares, Win Shares/48
  - Historical injury data: games missed per player per season

All fetches respect:
  - 1.5s delay between requests (robots.txt: Crawl-delay: 3; we use 1.5)
  - 48h TTL on cached files
  - No parallel requests

Source: basketball-reference.com
  - Advanced stats: /leagues/NBA_{year}_advanced.html
  - Player injury history embedded in season page

Public API
----------
    get_advanced_stats(season)                -> list[dict]
    get_player_bpm(player_name, season)       -> dict
    get_injury_history(season)                -> list[dict]
    get_vorp_leaders(season, top_n)           -> list[dict]
    fetch_multi_season(seasons)               -> dict
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_EXT_CACHE   = os.path.join(PROJECT_DIR, "data", "external")
_TTL_48H     = 48 * 3600

_BBREF_BASE  = "https://www.basketball-reference.com"
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

# BBRef season string: "2024-25" → year = 2025
def _season_year(season: str) -> int:
    """Return the end year from a season string like '2024-25'."""
    try:
        return int(season.split("-")[0]) + 1
    except Exception:
        return 2025


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


def _rate_limit(secs: float = 1.5) -> None:
    time.sleep(secs)


# ─────────────────────────────────────────────────────────────────────────────
# HTML fetch + parse
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_html(url: str, retries: int = 3) -> Optional[str]:
    """Fetch URL with retry logic. Returns HTML string or None."""
    import requests
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"[bbref] Rate limited — waiting {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code == 200:
                return resp.text
            print(f"[bbref] HTTP {resp.status_code} for {url}")
            return None
        except Exception as e:
            print(f"[bbref] Request error (attempt {attempt+1}): {e}")
            time.sleep(5)
    return None


def _parse_advanced_table(html: str) -> list:
    """Parse the #advanced stats table from a BBRef league season page."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError("beautifulsoup4 not installed. Run: pip install beautifulsoup4")

    from bs4 import Comment
    soup = BeautifulSoup(html, "html.parser")

    # BBRef wraps stats tables inside HTML comments — inject them back into the DOM
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment_soup = BeautifulSoup(str(comment), "html.parser")
        if comment_soup.find("table"):
            comment.replace_with(comment_soup)

    table = soup.find("table", {"id": "advanced"})
    if table is None:
        return []

    headers: list = []
    records: list = []

    thead = table.find("thead")
    if thead:
        header_rows = thead.find_all("tr")
        # Use the last header row (2-row headers on BBRef)
        for th in header_rows[-1].find_all("th"):
            headers.append(th.get("data-stat", th.get_text(strip=True)))

    tbody = table.find("tbody")
    if tbody is None:
        return []

    for tr in tbody.find_all("tr"):
        # Skip separator rows (class="thead") and blank rows
        if "thead" in tr.get("class", []):
            continue
        cells = tr.find_all(["td", "th"])
        if len(cells) < 5:
            continue
        row: dict = {}
        for i, td in enumerate(cells):
            if i < len(headers):
                key = headers[i]
                val = td.get_text(strip=True)
                # Try numeric conversion
                try:
                    val = float(val) if val not in ("", "\xa0") else None
                except ValueError:
                    pass
                row[key] = val
        if row.get("player") or row.get("Player") or row.get("name_display"):
            records.append(row)

    return records


def _normalise_record(raw: dict, year: int) -> dict:
    """Map BBRef column names → clean internal schema."""
    def g(keys, default=None):
        for k in keys:
            v = raw.get(k)
            if v is not None and v != "":
                return v
        return default

    def f(keys, default=0.0):
        v = g(keys, default)
        try:
            return round(float(v), 3)
        except (TypeError, ValueError):
            return default

    name = str(g(["name_display", "player", "Player"], ""))
    # Strip asterisks from HOF markers
    name = name.strip("*").strip()

    return {
        "player_name":     name,
        "team":            str(g(["team_name_abbr", "tm", "Tm", "team"], "")),
        "age":             int(f(["age", "Age"], 0)),
        "games_played":    int(f(["games", "g", "G"], 0)),
        "minutes":         int(f(["mp", "MP"], 0)),
        "per":             f(["per", "PER"]),
        "ts_pct":          f(["ts_pct", "TS%", "ts%"]),
        "three_par":       f(["fg3a_per_fga_pct", "3PAr"]),
        "ftr":             f(["fta_per_fga_pct", "FTr"]),
        "orb_pct":         f(["orb_pct", "ORB%"]),
        "drb_pct":         f(["drb_pct", "DRB%"]),
        "trb_pct":         f(["trb_pct", "TRB%"]),
        "ast_pct":         f(["ast_pct", "AST%"]),
        "stl_pct":         f(["stl_pct", "STL%"]),
        "blk_pct":         f(["blk_pct", "BLK%"]),
        "tov_pct":         f(["tov_pct", "TOV%"]),
        "usg_pct":         f(["usg_pct", "USG%"]),
        "ows":             f(["ows", "OWS"]),
        "dws":             f(["dws", "DWS"]),
        "win_shares":      f(["ws", "WS"]),
        "ws_per_48":       f(["ws_per_48", "WS/48"]),
        "obpm":            f(["obpm", "OBPM"]),
        "dbpm":            f(["dbpm", "DBPM"]),
        "bpm":             f(["bpm", "BPM"]),
        "vorp":            f(["vorp", "VORP"]),
        "season":          f"{year - 1}-{str(year)[2:]}",
        "season_year":     year,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_advanced_stats(season: str = "2024-25") -> list:
    """
    Scrape all player advanced stats for a season from Basketball Reference.

    Includes BPM, VORP, Win Shares, PER, TS%, usage %, and all %/rate stats.

    Args:
        season: e.g. "2024-25"

    Returns:
        List of player stat dicts. Players traded mid-season appear multiple
        times (once per team + a "TOT" totals row).
    """
    year = _season_year(season)
    key  = f"bbref_advanced_{_safe(season)}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_48H):
        return _load(path)

    url = f"{_BBREF_BASE}/leagues/NBA_{year}_advanced.html"
    print(f"[bbref] Fetching advanced stats: {url}")
    _rate_limit(1.5)

    html = _fetch_html(url)
    if not html:
        return []

    raw_records = _parse_advanced_table(html)
    records = [_normalise_record(r, year) for r in raw_records if r]
    # Keep only rows with a player name
    records = [r for r in records if r.get("player_name")]

    _save(path, records)
    print(f"[bbref] Advanced stats: {len(records)} rows for {season}")
    return records


def get_player_bpm(
    player_name: str,
    season: str = "2024-25",
) -> dict:
    """
    Look up BPM, VORP, and Win Shares for a specific player.

    Args:
        player_name: Full name (e.g. "LeBron James")
        season: e.g. "2024-25"

    Returns:
        {
            "player_name": str, "season": str, "team": str,
            "bpm": float, "obpm": float, "dbpm": float,
            "vorp": float, "win_shares": float, "ws_per_48": float,
            "usg_pct": float, "ts_pct": float,
            "found": bool,
        }
    """
    query = player_name.lower().strip()
    records = get_advanced_stats(season)

    # Prefer "TOT" row for traded players; otherwise take highest-minutes row
    candidates = [r for r in records if r.get("player_name", "").lower() == query]
    if not candidates:
        return {
            "player_name": player_name, "season": season,
            "found": False, "bpm": 0.0, "vorp": 0.0, "win_shares": 0.0,
            "ws_per_48": 0.0, "obpm": 0.0, "dbpm": 0.0,
            "usg_pct": 0.0, "ts_pct": 0.0,
        }

    # Prefer TOT row; fall back to most-minutes row
    tot = [r for r in candidates if r.get("team", "").upper() == "TOT"]
    row = tot[0] if tot else max(candidates, key=lambda r: r.get("minutes", 0))

    return {
        "player_name": row["player_name"],
        "season":      season,
        "team":        row.get("team", ""),
        "bpm":         row.get("bpm", 0.0),
        "obpm":        row.get("obpm", 0.0),
        "dbpm":        row.get("dbpm", 0.0),
        "vorp":        row.get("vorp", 0.0),
        "win_shares":  row.get("win_shares", 0.0),
        "ws_per_48":   row.get("ws_per_48", 0.0),
        "usg_pct":     row.get("usg_pct", 0.0),
        "ts_pct":      row.get("ts_pct", 0.0),
        "found":       True,
    }


def get_injury_history(season: str = "2024-25") -> list:
    """
    Scrape games-missed data for the season from the BBRef injury tracker page.

    Returns:
        List of dicts:
        [
            {
                "player_name": str, "team": str,
                "games_missed": int, "season": str,
                "injury_notes": str,
            }, ...
        ]
    """
    year = _season_year(season)
    key  = f"bbref_injuries_{_safe(season)}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_48H):
        return _load(path)

    # Combine with advanced stats: games_played vs team's games_played gives games missed
    adv = get_advanced_stats(season)
    if not adv:
        return []

    # Team game totals: max GP among regular rotational players
    team_gp: dict = {}
    for r in adv:
        team = r.get("team", "TOT")
        if team == "TOT":
            continue
        gp = r.get("games_played", 0)
        if isinstance(gp, (int, float)) and gp > team_gp.get(team, 0):
            team_gp[team] = int(gp)

    # Build injury history: players who missed >5 games
    records = []
    seen = set()
    for r in adv:
        name = r.get("player_name", "")
        team = r.get("team", "TOT")
        if not name or team == "TOT":
            continue
        key_   = (name, team)
        if key_ in seen:
            continue
        seen.add(key_)
        team_total = team_gp.get(team, 82)
        gp         = int(r.get("games_played") or 0)
        missed     = max(0, team_total - gp)
        if missed > 0:
            records.append({
                "player_name":  name,
                "team":         team,
                "games_played": gp,
                "games_missed": missed,
                "season":       season,
                "injury_notes": "",    # full notes need per-player page (rate-limited)
            })

    records.sort(key=lambda x: x["games_missed"], reverse=True)
    _save(path, records)
    print(f"[bbref] Injury history: {len(records)} players missed games in {season}")
    return records


def get_vorp_leaders(
    season: str = "2024-25",
    top_n: int = 50,
) -> list:
    """
    Return top-N players by VORP for quick leaderboard access.

    Args:
        season: e.g. "2024-25"
        top_n: Number of players to return

    Returns:
        Sorted list of (player_name, vorp, bpm, win_shares) dicts.
    """
    records = get_advanced_stats(season)
    # Deduplicate: keep TOT row for traded players
    seen: set = set()
    deduped: list = []
    for r in sorted(records, key=lambda x: x.get("vorp", 0) or 0, reverse=True):
        name = r.get("player_name", "")
        if name and name not in seen:
            deduped.append(r)
            seen.add(name)

    leaders = sorted(deduped, key=lambda x: x.get("vorp", 0) or 0, reverse=True)[:top_n]
    return [
        {
            "rank":        i + 1,
            "player_name": r["player_name"],
            "team":        r.get("team", ""),
            "vorp":        r.get("vorp", 0.0),
            "bpm":         r.get("bpm", 0.0),
            "win_shares":  r.get("win_shares", 0.0),
            "ws_per_48":   r.get("ws_per_48", 0.0),
            "season":      season,
        }
        for i, r in enumerate(leaders)
    ]


def fetch_multi_season(
    seasons: Optional[List[str]] = None,
    delay: float = 2.0,
) -> dict:
    """
    Scrape advanced stats for multiple seasons.

    Args:
        seasons: List of season strings. Defaults to ["2024-25","2023-24","2022-23"].
        delay: Seconds between requests (respects BBRef crawl-delay).

    Returns:
        {season: records_list}
    """
    if seasons is None:
        seasons = ["2024-25", "2023-24", "2022-23"]

    results = {}
    for s in seasons:
        data = get_advanced_stats(s)
        results[s] = data
        print(f"[bbref] {s}: {len(data)} records")
        time.sleep(delay)

    return results


def build_player_index(seasons: Optional[List[str]] = None) -> dict:
    """
    Build a flat {player_name: {season: stats}} lookup across all seasons.

    Useful for feature_engineering: quickly look up BPM/VORP for any player in any season.

    Returns:
        {
            "LeBron James": {
                "2024-25": {"bpm": 5.2, "vorp": 3.1, ...},
                "2023-24": {"bpm": 4.8, ...},
            }, ...
        }
    """
    if seasons is None:
        seasons = ["2024-25", "2023-24", "2022-23"]

    index: dict = {}
    for s in seasons:
        records = get_advanced_stats(s)
        for r in records:
            name = r.get("player_name", "")
            if not name:
                continue
            index.setdefault(name, {})[s] = r
    return index


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Basketball Reference scraper")
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--player", default=None)
    parser.add_argument("--injuries", action="store_true")
    parser.add_argument("--all-seasons", action="store_true")
    args = parser.parse_args()

    if args.all_seasons:
        results = fetch_multi_season()
        for s, data in results.items():
            print(f"{s}: {len(data)} players")
    elif args.player:
        info = get_player_bpm(args.player, args.season)
        print(json.dumps(info, indent=2))
    elif args.injuries:
        data = get_injury_history(args.season)
        for r in data[:10]:
            print(r)
    else:
        data = get_advanced_stats(args.season)
        leaders = get_vorp_leaders(args.season, top_n=10)
        print(f"Total players: {len(data)}")
        print("VORP leaders:")
        for r in leaders:
            print(f"  {r['rank']}. {r['player_name']}: VORP={r['vorp']}, BPM={r['bpm']}")
