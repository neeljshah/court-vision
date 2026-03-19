"""
contracts_scraper.py — NBA player contract and salary data from HoopsHype.

Scrapes current season salary, years remaining on contract, cap hit, and
contract type for every NBA player. Used for:
  - Contract-year effect model (M36): do players perform better in walk years?
  - Load management predictor: teams on cap-crunch rest veterans more
  - DNP predictor: players on minimum deals DNP more in blowouts

Rate limits:
  - 1.5s delay between requests
  - 7-day TTL on cached files

Public API
----------
    get_all_contracts(season)            -> list[dict]
    get_player_contract(player_name)     -> dict
    get_team_payroll(team_abbrev)        -> dict
    is_contract_year(player_name)        -> bool
    fetch_salary_index()                 -> dict   {player_name: contract_dict}
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

_EXT_CACHE = os.path.join(PROJECT_DIR, "data", "external")
_TTL_7D    = 7 * 24 * 3600

_BBREF_CONTRACTS_URL = "https://www.basketball-reference.com/contracts/players.html"
_SALARIES_URL        = _BBREF_CONTRACTS_URL   # kept for backward compat

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection":      "keep-alive",
    "Referer":         "https://www.basketball-reference.com/",
}

# NBA team pages on HoopsHype
_TEAM_SLUGS: dict = {
    "ATL": "atlanta-hawks", "BOS": "boston-celtics", "BKN": "brooklyn-nets",
    "CHA": "charlotte-hornets", "CHI": "chicago-bulls", "CLE": "cleveland-cavaliers",
    "DAL": "dallas-mavericks", "DEN": "denver-nuggets", "DET": "detroit-pistons",
    "GSW": "golden-state-warriors", "HOU": "houston-rockets", "IND": "indiana-pacers",
    "LAC": "la-clippers", "LAL": "los-angeles-lakers", "MEM": "memphis-grizzlies",
    "MIA": "miami-heat", "MIL": "milwaukee-bucks", "MIN": "minnesota-timberwolves",
    "NOP": "new-orleans-pelicans", "NYK": "new-york-knicks", "OKC": "oklahoma-city-thunder",
    "ORL": "orlando-magic", "PHI": "philadelphia-76ers", "PHX": "phoenix-suns",
    "POR": "portland-trail-blazers", "SAC": "sacramento-kings", "SAS": "san-antonio-spurs",
    "TOR": "toronto-raptors", "UTA": "utah-jazz", "WAS": "washington-wizards",
}

# NBA salary cap approximate (2024-25)
_CAP_APPROX = 141_000_000


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


def _rate_limit(secs: float = 1.5) -> None:
    time.sleep(secs)


# ─────────────────────────────────────────────────────────────────────────────
# HTML fetch + parse
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_html(url: str, retries: int = 3) -> Optional[str]:
    import requests
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=30)
            if resp.status_code == 429:
                time.sleep(20 * (attempt + 1))
                continue
            if resp.status_code == 200:
                return resp.text
            return None
        except Exception as e:
            print(f"[contracts] Request error: {e}")
            time.sleep(5)
    return None


def _parse_salary_value(text: str) -> Optional[int]:
    """Parse '$42,000,000' or '42M' → integer dollars."""
    text = text.strip().replace(",", "").replace("$", "")
    try:
        if "M" in text.upper():
            return int(float(text.upper().replace("M", "")) * 1_000_000)
        val = float(text)
        return int(val)
    except ValueError:
        return None


def _parse_years_remaining(option_text: str) -> int:
    """
    Infer years remaining from option column text on HoopsHype.
    e.g. "3/4" → 2 years remaining if on year 2 of 4-year deal.
    We count non-empty future-year salary columns.
    """
    try:
        return int(option_text.strip().split("/")[0])
    except Exception:
        return 0


def _parse_contract_type(option_text: str) -> str:
    """Map HoopsHype option column to contract type label."""
    text = option_text.lower()
    if "player" in text:
        return "player_option"
    if "team" in text:
        return "team_option"
    if "etm" in text or "trade" in text:
        return "no_trade"
    if "2way" in text or "two-way" in text:
        return "two_way"
    return "guaranteed"


def _parse_all_players_page(html: str) -> list:
    """
    Parse BBRef /contracts/players.html table (data-stat columns: ranker,
    player, team_id, y1, y2, y3, y4, y5).  y1 = current season; walk year =
    y1 has value but y2-y5 are all empty.
    """
    try:
        from bs4 import BeautifulSoup, Comment
    except ImportError:
        raise RuntimeError("beautifulsoup4 not installed.")

    soup = BeautifulSoup(html, "html.parser")

    # Inject comment-wrapped tables (BBRef pattern)
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        cs = BeautifulSoup(str(comment), "html.parser")
        if cs.find("table"):
            comment.replace_with(cs)

    table = soup.find("table", {"id": "player-contracts"})
    if table is None:
        # Fallback: find any table with a "player" data-stat column
        for t in soup.find_all("table"):
            if t.find(attrs={"data-stat": "player"}):
                table = t
                break
    if table is None:
        return []

    tbody = table.find("tbody")
    if tbody is None:
        return []

    records: list = []
    for tr in tbody.find_all("tr"):
        if "thead" in tr.get("class", []):
            continue
        cells = tr.find_all(["td", "th"])
        if len(cells) < 4:
            continue

        # Use data-stat for robust column lookup
        row: dict = {td.get("data-stat", ""): td.get_text(strip=True) for td in cells}

        name = row.get("player", "").strip("*").strip()
        if not name or not re.search(r"[A-Za-z]", name):
            continue

        team = row.get("team_id", "")
        y1 = _parse_salary_value(row.get("y1", ""))  # current season
        years_remaining = sum(
            1 for k in ("y2", "y3", "y4", "y5")
            if _parse_salary_value(row.get(k, ""))
        )

        cap_hit_pct = round(y1 / _CAP_APPROX, 4) if y1 else 0.0

        records.append({
            "player_name":     name,
            "team":            team,
            "current_salary":  y1,
            "years_remaining": years_remaining,
            "cap_hit":         y1,
            "cap_hit_pct":     cap_hit_pct,
            "contract_type":   "guaranteed",  # BBRef doesn't break out option type
            "contract_year":   y1 is not None and years_remaining == 0,
        })

    return records


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_all_contracts(season: str = "2024-25") -> list:
    """
    Scrape salary/contract data for all NBA players from HoopsHype.

    Args:
        season: e.g. "2024-25" (used for cache key; HoopsHype always shows current)

    Returns:
        List of contract dicts:
        [
            {
                "player_name":     str,
                "team":            str,       # 3-letter abbreviation when available
                "current_salary":  int | None,   # dollars
                "years_remaining": int,          # seasons left after this one
                "cap_hit":         int | None,
                "cap_hit_pct":     float,         # fraction of salary cap
                "contract_type":   str,           # "guaranteed","player_option","team_option","two_way"
                "contract_year":   bool,          # True if final year (walk year)
            }, ...
        ]
    """
    key  = f"contracts_{_safe(season)}"
    path = _cache_path(key)
    if _is_fresh(path, _TTL_7D):
        return _load(path)

    print(f"[contracts] Fetching HoopsHype salaries...")
    _rate_limit(1.5)
    html = _fetch_html(_SALARIES_URL)
    if not html:
        print("[contracts] Failed to fetch HoopsHype salary page")
        return []

    records = _parse_all_players_page(html)
    if not records:
        print("[contracts] No records parsed from salary page")
        return []

    _save(path, records)
    print(f"[contracts] Saved {len(records)} player contracts")
    return records


def get_player_contract(player_name: str, season: str = "2024-25") -> dict:
    """
    Look up contract details for a specific player.

    Args:
        player_name: Full name (case-insensitive)
        season: Season for cache key

    Returns:
        Contract dict, or empty dict with defaults if not found.
    """
    query   = player_name.lower().strip()
    records = get_all_contracts(season)

    for r in records:
        if r.get("player_name", "").lower() == query:
            return r

    # Partial match fallback
    for r in records:
        if query in r.get("player_name", "").lower():
            return r

    return {
        "player_name":    player_name,
        "team":           "",
        "current_salary": None,
        "years_remaining": 0,
        "cap_hit":        None,
        "cap_hit_pct":    0.0,
        "contract_type":  "unknown",
        "contract_year":  False,
        "found":          False,
    }


def get_team_payroll(team_abbrev: str, season: str = "2024-25") -> dict:
    """
    Return all contracts for players on a specific team, plus team totals.

    Args:
        team_abbrev: 3-letter abbreviation (e.g. "BOS")
        season: Season for cache key

    Returns:
        {
            "team": str,
            "total_payroll": int,
            "cap_hit_pct":   float,    # fraction of total cap
            "players": [contract_dict, ...]
        }
    """
    abbrev_upper = team_abbrev.upper()
    records = get_all_contracts(season)
    team_records = [
        r for r in records
        if r.get("team", "").upper() == abbrev_upper
        or abbrev_upper in r.get("team", "").upper()
    ]

    total = sum(r.get("current_salary", 0) or 0 for r in team_records)
    return {
        "team":          abbrev_upper,
        "total_payroll": total,
        "cap_hit_pct":   round(total / _CAP_APPROX, 4),
        "players":       sorted(team_records, key=lambda x: x.get("current_salary", 0) or 0, reverse=True),
    }


def is_contract_year(player_name: str, season: str = "2024-25") -> bool:
    """
    Return True if the player is in the final year of their contract
    (i.e. walk year — contract_year=True and no guaranteed extension).

    Players in their walk year historically over-perform by ~2-3%.

    Args:
        player_name: Full player name

    Returns:
        bool
    """
    contract = get_player_contract(player_name, season)
    return bool(contract.get("contract_year", False))


def fetch_salary_index(season: str = "2024-25") -> dict:
    """
    Build a fast-lookup dict: {player_name_lower: contract_dict}.

    Used by feature_engineering.py to add contract features to player rows.

    Returns:
        {player_name.lower(): contract_dict}
    """
    records = get_all_contracts(season)
    return {r["player_name"].lower(): r for r in records if r.get("player_name")}


if __name__ == "__main__":
    import argparse
    import sys
    # Fix Windows console encoding for special characters in player names
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Contract/salary scraper")
    parser.add_argument("--season", default="2024-25")
    parser.add_argument("--player", default=None)
    parser.add_argument("--team", default=None)
    parser.add_argument("--contract-years", action="store_true")
    args = parser.parse_args()

    if args.player:
        c = get_player_contract(args.player, args.season)
        print(json.dumps(c, indent=2))
    elif args.team:
        payroll = get_team_payroll(args.team, args.season)
        print(f"{args.team} payroll: ${payroll['total_payroll']:,} ({payroll['cap_hit_pct']*100:.1f}% of cap)")
        for p in payroll["players"][:10]:
            print(f"  {p['player_name']}: ${p.get('current_salary', 0):,} ({p.get('contract_type', '')})")
    elif args.contract_years:
        records = get_all_contracts(args.season)
        walk_years = [r for r in records if r.get("contract_year")]
        print(f"Players in walk year: {len(walk_years)}")
        for r in sorted(walk_years, key=lambda x: x.get("current_salary", 0) or 0, reverse=True)[:20]:
            print(f"  {r['player_name']} ({r['team']}): ${r.get('current_salary', 0):,}")
    else:
        records = get_all_contracts(args.season)
        print(f"Total contracts: {len(records)}")
