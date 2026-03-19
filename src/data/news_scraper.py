"""
news_scraper.py — ESPN NBA headline monitor (Phase 5).

Polls the ESPN public news API every 30 minutes, extracts player names and
keywords (injury, trade, suspension, rest), and caches results to
data/nba/news_cache.json with a configurable TTL.

Cache schema
------------
{
  "fetched_at": float,          # Unix timestamp of last fetch
  "articles": [
    {
      "id":          str,        # ESPN article ID
      "headline":    str,
      "published":   str,        # ISO-8601 timestamp
      "url":         str,
      "players":     List[str],  # player names found in headline/desc
      "keywords":    List[str],  # matched keywords from _KEYWORDS
      "description": str,
    },
    ...
  ]
}

Public API
----------
    fetch_news(force)           -> List[dict]   (fresh or cached articles)
    get_player_alerts(player)   -> List[dict]   (articles mentioning a player)
    get_keyword_alerts(keyword) -> List[dict]   (articles matching a keyword)
    has_injury_alert(player)    -> bool
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_PATH = os.path.join(PROJECT_DIR, "data", "nba", "news_cache.json")
_CACHE_TTL  = 30 * 60   # 30 minutes
_ESPN_URL   = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news"

# Keywords to flag — tuned to injury/availability signals
_KEYWORDS = [
    "injury", "injured", "out", "doubtful", "questionable", "day-to-day",
    "ruled out", "knee", "ankle", "hamstring", "back", "shoulder", "wrist",
    "trade", "traded", "waived", "suspended", "suspension", "rest",
    "dnp", "probable", "return", "listed",
]

# Basic NBA player name dictionary for fast matching — first/last name fragments
# The scraper does fuzzy matching against article text so this is a seed list.
# Populated from nba_api stats.static.players at runtime when available.
_PLAYER_NAME_PATTERNS: Optional[List[re.Pattern]] = None


def _load_player_patterns() -> List[re.Pattern]:
    """Build regex patterns for active NBA player names."""
    global _PLAYER_NAME_PATTERNS
    if _PLAYER_NAME_PATTERNS is not None:
        return _PLAYER_NAME_PATTERNS
    try:
        from nba_api.stats.static import players as nba_players
        active = [p["full_name"] for p in nba_players.get_active_players()]
    except Exception:
        active = []

    patterns = []
    for name in active:
        parts = name.split()
        if len(parts) >= 2:
            last = re.escape(parts[-1])
            first = re.escape(parts[0])
            patterns.append(re.compile(
                rf"\b{first}\s+{last}\b|\b{last}\b(?=[,\s.']|$)",
                re.IGNORECASE,
            ))
    _PLAYER_NAME_PATTERNS = patterns
    return patterns


def _extract_players(text: str) -> List[str]:
    """Return player names found in text using pattern matching."""
    if not text:
        return []
    found: list[str] = []
    try:
        from nba_api.stats.static import players as nba_players
        active = {p["full_name"]: p for p in nba_players.get_active_players()}
    except Exception:
        return []
    for name in active:
        parts = name.split()
        if len(parts) >= 2 and parts[-1].lower() in text.lower():
            if name.lower() in text.lower():
                found.append(name)
            elif len(parts[-1]) > 5 and parts[-1].lower() in text.lower():
                # Last-name-only match for long surnames
                found.append(name)
    return list(dict.fromkeys(found))  # deduplicate, preserve order


def _extract_keywords(text: str) -> List[str]:
    """Return matched keywords from text."""
    text_lower = text.lower()
    return [kw for kw in _KEYWORDS if kw in text_lower]


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _cache_is_fresh() -> bool:
    """Return True if cache exists and is younger than TTL."""
    if not os.path.exists(_CACHE_PATH):
        return False
    return (time.time() - os.path.getmtime(_CACHE_PATH)) < _CACHE_TTL


def _load_cache() -> dict:
    with open(_CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_cache(data: dict) -> None:
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── Fetcher ────────────────────────────────────────────────────────────────────

def _fetch_from_espn(limit: int = 50) -> List[dict]:
    """
    Hit the ESPN public news API and return raw article list.

    Args:
        limit: Max articles to fetch per call.

    Returns:
        List of article dicts (id, headline, published, url, description).
    """
    url = f"{_ESPN_URL}?limit={limit}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (NBA-AI-System/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[news_scraper] ESPN fetch failed: {e}")
        return []

    articles = []
    for item in raw.get("articles", []):
        articles.append({
            "id":          str(item.get("id", "")),
            "headline":    item.get("headline", ""),
            "published":   item.get("published", ""),
            "url":         item.get("links", {}).get("web", {}).get("href", ""),
            "description": item.get("description", ""),
        })
    return articles


def fetch_news(force: bool = False) -> List[dict]:
    """
    Return the latest NBA news articles, enriched with player names and keywords.

    Uses cached data if fresh (< 30 min old). Fetches from ESPN otherwise.

    Args:
        force: If True, skip cache and re-fetch from ESPN.

    Returns:
        List of enriched article dicts with "players" and "keywords" fields.
    """
    if not force and _cache_is_fresh():
        return _load_cache().get("articles", [])

    raw_articles = _fetch_from_espn()
    if not raw_articles:
        if os.path.exists(_CACHE_PATH):
            print("[news_scraper] Returning stale cache (ESPN unavailable)")
            return _load_cache().get("articles", [])
        return []

    enriched = []
    for art in raw_articles:
        text = f"{art['headline']} {art['description']}"
        enriched.append({
            **art,
            "players":  _extract_players(text),
            "keywords": _extract_keywords(text),
        })

    payload = {"fetched_at": time.time(), "articles": enriched}
    _save_cache(payload)
    print(f"[news_scraper] Cached {len(enriched)} articles -> {_CACHE_PATH}")
    return enriched


# ── Query helpers ──────────────────────────────────────────────────────────────

def get_player_alerts(player_name: str) -> List[dict]:
    """
    Return articles mentioning a specific player.

    Args:
        player_name: Full or partial player name (case-insensitive).

    Returns:
        List of matching article dicts.
    """
    articles = fetch_news()
    name_lower = player_name.lower()
    return [
        a for a in articles
        if name_lower in a.get("headline", "").lower()
        or name_lower in a.get("description", "").lower()
        or any(name_lower in p.lower() for p in a.get("players", []))
    ]


def get_keyword_alerts(keyword: str) -> List[dict]:
    """
    Return articles matching a specific keyword.

    Args:
        keyword: Keyword to match (e.g. "injury", "trade").

    Returns:
        List of matching article dicts.
    """
    articles = fetch_news()
    kw_lower = keyword.lower()
    return [a for a in articles if kw_lower in a.get("keywords", [])]


def has_injury_alert(player_name: str) -> bool:
    """
    Return True if any recent article mentions a player alongside injury keywords.

    Args:
        player_name: Player full name.

    Returns:
        True if an injury-related article mentioning the player was found.
    """
    injury_kws = {
        "injury", "injured", "out", "doubtful", "ruled out", "knee", "ankle",
        "hamstring", "back", "shoulder", "wrist", "dnp",
    }
    alerts = get_player_alerts(player_name)
    return any(bool(set(a.get("keywords", [])) & injury_kws) for a in alerts)


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="ESPN NBA News Scraper")
    ap.add_argument("--fetch",   action="store_true", help="Fetch and cache latest news")
    ap.add_argument("--player",  default=None, help="Show alerts for a specific player")
    ap.add_argument("--keyword", default=None, help="Show articles matching a keyword")
    ap.add_argument("--force",   action="store_true", help="Ignore cache and re-fetch")
    args = ap.parse_args()

    if args.player:
        alerts = get_player_alerts(args.player)
        print(f"{len(alerts)} article(s) mentioning '{args.player}':")
        for a in alerts[:10]:
            print(f"  [{', '.join(a['keywords']) or 'no keywords'}] {a['headline']}")
    elif args.keyword:
        alerts = get_keyword_alerts(args.keyword)
        print(f"{len(alerts)} article(s) with keyword '{args.keyword}':")
        for a in alerts[:10]:
            print(f"  {a['headline']}")
    else:
        articles = fetch_news(force=args.force)
        print(f"Fetched {len(articles)} articles")
        for a in articles[:5]:
            players = ", ".join(a["players"][:3]) if a["players"] else "none"
            kws     = ", ".join(a["keywords"][:3]) if a["keywords"] else "none"
            print(f"  [{kws}] {a['headline']} | players: {players}")
