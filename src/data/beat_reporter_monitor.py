"""
beat_reporter_monitor.py — NBA beat reporter injury/lineup alert monitor.

Monitors ~30 NBA beat reporters on Twitter/X for injury and lineup news
posted within a configurable window (default 3 hours). Beat reporters
routinely break injury/DNP news 90–120 minutes before the official NBA
injury report updates.

Authentication strategy (in priority order):
  1. Twitter v2 API (Bearer token) — set TWITTER_BEARER_TOKEN env var
  2. Nitter scraping — public Twitter mirror, no auth required
     Nitter instances tried in order: nitter.net → nitter.1d4.us → others

Cache
-----
    data/nba/beat_reporter_alerts.json   (TTL: 10 minutes)

Environment
-----------
    TWITTER_BEARER_TOKEN — optional; enables Twitter v2 API (read-only)
    NITTER_HOST          — optional; override default Nitter instance

Public API
----------
    get_player_alerts(player_name, hours)  -> List[dict]
    has_injury_alert(player_name, hours)   -> bool
    refresh_alerts(force)                  -> List[dict]
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_PATH = os.path.join(PROJECT_DIR, "data", "nba", "beat_reporter_alerts.json")
_TTL_SEC    = 10 * 60   # 10 minutes

# ── Beat reporter list ────────────────────────────────────────────────────────
# Format: {handle: team_beat}
# Covers all 30 teams; known reliable injury sources first.
BEAT_REPORTERS: Dict[str, str] = {
    # Boston Celtics
    "adam_himmelsbach": "BOS",
    "gary_washburn":    "BOS",
    # Brooklyn Nets
    "kristianwinfield": "BKN",
    # New York Knicks
    "ianibello":        "NYK",
    "stephensabour":    "NYK",
    # Philadelphia 76ers
    "phlysportsmed":    "PHI",
    "keithpompeyjr":    "PHI",
    # Toronto Raptors
    "joshuabuetow":     "TOR",
    "mbobrowsky":       "TOR",
    # Chicago Bulls
    "kschoonover2":     "CHI",
    "kdotmitchell":     "CHI",
    # Cleveland Cavaliers
    "joefrisaro":       "CLE",
    # Detroit Pistons
    "vinniepasquini":   "DET",
    # Indiana Pacers
    "scottlago":        "IND",
    # Milwaukee Bucks
    "ericnedeljkovic":  "MIL",
    "mattvasgersian":   "MIL",
    # Atlanta Hawks
    "noahlevick":       "ATL",
    "bradforddoolittle":"ATL",
    # Charlotte Hornets
    "rodboone":         "CHA",
    # Miami Heat
    "ira_winderman":    "MIA",
    "anthonytellez":    "MIA",
    # Orlando Magic
    "joshuacohen":      "ORL",
    # Washington Wizards
    "etchbarfact":      "WAS",
    # Denver Nuggets
    "mikeaker":         "DEN",
    # Minnesota Timberwolves
    "jaredsnow":        "MIN",
    # Oklahoma City Thunder
    "joefrisaro":       "OKC",
    # Utah Jazz
    "jimfuchs":         "UTA",
    # Portland Trail Blazers
    "jaycooley_":       "POR",
    # Golden State Warriors
    "anthonyslater":    "GSW",
    "marcstein":        "GSW",
    # LA Clippers
    "lawrencefrank":    "LAC",
    # LA Lakers
    "billplascheck":    "LAL",
    "austinferguson":   "LAL",
    # Phoenix Suns
    "kellanolson":      "PHX",
    "karenfrankn":      "PHX",
    # Sacramento Kings
    "jasonjones_":      "SAC",
    # Dallas Mavericks
    "timmacmahonnba":   "DAL",
    # Houston Rockets
    "jonathanfeigen":   "HOU",
    # Memphis Grizzlies
    "ronniegunnell":    "MEM",
    # New Orleans Pelicans
    "andrewlopez":      "NOP",
    # San Antonio Spurs
    "mrcalvinwatkins":  "SAS",
}

# Injury/lineup keywords — match any of these in a tweet
_INJURY_KEYWORDS = [
    r"\bout\b",
    r"\bdnp\b",
    r"\bwon'?t play\b",
    r"\bwill not play\b",
    r"\bquestionable\b",
    r"\bdoubtful\b",
    r"\bprobable\b",
    r"\blimited\b",
    r"\bboot\b",
    r"\bsprain\b",
    r"\bfracture\b",
    r"\bsoreness\b",
    r"\bmanagement\b",
    r"\bscratch\b",
    r"\bgame-time decision\b",
    r"\bday-to-day\b",
    r"\bside-lined\b",
    r"\binjured\b",
    r"\brest\b",
    r"\bload management\b",
]
_KW_PATTERN = re.compile("|".join(_INJURY_KEYWORDS), re.IGNORECASE)

# Nitter fallback instances (tried in order)
_NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.1d4.us",
    "https://nitter.poast.org",
]


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_fresh() -> bool:
    if not os.path.exists(_CACHE_PATH):
        return False
    return (time.time() - os.path.getmtime(_CACHE_PATH)) < _TTL_SEC


def _load_cache() -> List[dict]:
    try:
        with open(_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_cache(alerts: List[dict]) -> None:
    os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
    with open(_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2)


def _norm(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


# ── Twitter v2 API fetcher ────────────────────────────────────────────────────

def _fetch_twitter_v2(handle: str, bearer_token: str, hours: float = 6.0) -> List[dict]:
    """
    Fetch recent tweets for a handle via Twitter v2 API.

    Returns list of {text, created_at} dicts.
    """
    try:
        import requests
    except ImportError:
        return []

    # First resolve handle → user ID
    url = f"https://api.twitter.com/2/users/by/username/{handle}"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        user_id = r.json()["data"]["id"]
    except Exception:
        return []

    # Fetch recent tweets
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        r = requests.get(
            f"https://api.twitter.com/2/users/{user_id}/tweets",
            headers=headers,
            params={
                "max_results":   10,
                "tweet.fields":  "created_at,text",
                "start_time":    since,
            },
            timeout=10,
        )
        r.raise_for_status()
        tweets = r.json().get("data", [])
        return [{"text": t.get("text", ""), "created_at": t.get("created_at", "")}
                for t in tweets]
    except Exception:
        return []


# ── Nitter fallback scraper ───────────────────────────────────────────────────

def _fetch_nitter(handle: str, hours: float = 6.0) -> List[dict]:
    """
    Scrape recent tweets for a handle via Nitter (no auth required).

    Returns list of {text, created_at} dicts.
    """
    try:
        import requests
        from html.parser import HTMLParser

        class _TweetParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.tweets: List[dict] = []
                self._in_content  = False
                self._in_datetime = False
                self._cur_text    = ""
                self._cur_dt      = ""

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                cls = attrs_dict.get("class", "")
                if "tweet-content" in cls:
                    self._in_content = True
                    self._cur_text   = ""
                if tag == "span" and "tweet-date" in cls:
                    self._in_datetime = True
                    self._cur_dt      = ""
                if tag == "a" and self._in_datetime:
                    title = attrs_dict.get("title", "")
                    if title:
                        self._cur_dt = title

            def handle_endtag(self, tag):
                if self._in_content and tag in ("div", "p"):
                    self._in_content = False
                    if self._cur_text.strip():
                        self.tweets.append({
                            "text":       self._cur_text.strip(),
                            "created_at": self._cur_dt,
                        })

            def handle_data(self, data):
                if self._in_content:
                    self._cur_text += data

    except ImportError:
        return []

    nitter_host = os.environ.get("NITTER_HOST", "")
    instances   = [nitter_host] + _NITTER_INSTANCES if nitter_host else _NITTER_INSTANCES

    for host in instances:
        try:
            url  = f"{host}/{handle}"
            resp = requests.get(url, timeout=10,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                continue
            parser = _TweetParser()
            parser.feed(resp.text)
            return parser.tweets[:20]
        except Exception:
            continue

    return []


# ── Keyword + name matcher ────────────────────────────────────────────────────

def _extract_player_name_mentions(text: str, player_name: str) -> bool:
    """Return True if the tweet mentions the player by last name or full name."""
    parts = player_name.split()
    last  = parts[-1] if parts else ""
    if not last:
        return False
    return bool(re.search(r"\b" + re.escape(last) + r"\b", text, re.IGNORECASE))


def _parse_tweet_time(created_at: str) -> Optional[datetime]:
    """Parse Twitter/Nitter timestamp string → timezone-aware datetime."""
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%b %d, %Y · %I:%M %p %Z",
        "%b %d, %Y %I:%M %p %Z",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(created_at.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, AttributeError):
            continue
    return None


# ── Main refresh ──────────────────────────────────────────────────────────────

def refresh_alerts(force: bool = False) -> List[dict]:
    """
    Scan all beat reporters for recent injury/lineup tweets.

    Uses Twitter v2 API when TWITTER_BEARER_TOKEN is set; otherwise
    falls back to Nitter scraping.

    Args:
        force: Bypass TTL and always re-scan.

    Returns:
        List of alert dicts:
        {
            "player_name":   str,          # extracted player name
            "reporter":      str,          # twitter handle
            "team_beat":     str,          # team abbreviation (beat assignment)
            "tweet":         str,
            "keywords":      List[str],    # matched keywords
            "posted_at":     str,          # ISO timestamp
            "hours_ago":     float,
        }
    """
    if not force and _cache_fresh():
        return _load_cache()

    bearer_token = os.environ.get("TWITTER_BEARER_TOKEN", "")
    alerts: List[dict] = []
    now = datetime.now(timezone.utc)

    for handle, team in BEAT_REPORTERS.items():
        # Choose fetch method
        if bearer_token:
            tweets = _fetch_twitter_v2(handle, bearer_token, hours=6.0)
        else:
            tweets = _fetch_nitter(handle, hours=6.0)
            time.sleep(0.5)   # be polite to Nitter instances

        for tweet in tweets:
            text       = tweet.get("text", "")
            created_at = tweet.get("created_at", "")

            # Check for injury keywords
            kw_matches = _KW_PATTERN.findall(text)
            if not kw_matches:
                continue

            # Parse tweet time
            dt = _parse_tweet_time(created_at)
            hours_ago = (now - dt).total_seconds() / 3600 if dt else 99.0

            # Attempt to extract player last name from tweet (heuristic: capitalised word near keyword)
            player_mention = _extract_likely_player(text)

            alerts.append({
                "player_name": player_mention,
                "reporter":    handle,
                "team_beat":   team,
                "tweet":       text[:280],
                "keywords":    list({kw.strip().lower() for kw in kw_matches}),
                "posted_at":   created_at,
                "hours_ago":   round(hours_ago, 2),
            })

    _save_cache(alerts)
    print(f"[beat_reporter_monitor] {len(alerts)} injury alerts from {len(BEAT_REPORTERS)} reporters")
    return alerts


def _extract_likely_player(text: str) -> str:
    """
    Heuristically extract the most likely player name from a tweet.

    Looks for sequences of 2+ consecutive Title-Cased words that aren't
    common English stopwords — a rough but fast NER proxy.
    """
    stopwords = {
        "The", "A", "An", "He", "She", "It", "They", "We", "Is", "Are", "Was",
        "Will", "Out", "Per", "At", "In", "On", "Of", "To", "For", "And",
        "But", "So", "Yet", "Nor", "Or", "As",
    }
    words  = re.findall(r"[A-Z][a-z']+", text)
    result = []
    for w in words:
        if w not in stopwords:
            result.append(w)
        else:
            if len(result) >= 2:
                break
            result = []

    return " ".join(result[:2]) if len(result) >= 2 else ""


# ── Public API ────────────────────────────────────────────────────────────────

def get_player_alerts(player_name: str, hours: float = 3.0) -> List[dict]:
    """
    Return all recent beat reporter alerts mentioning a specific player.

    Args:
        player_name: Full or partial player name (e.g. "Ja Morant", "Morant").
        hours:       How many hours back to search (default 3).

    Returns:
        List of alert dicts (may be empty). Sorted newest-first.
    """
    alerts = refresh_alerts()
    name_norm  = _norm(player_name)
    last_name  = player_name.split()[-1].lower() if player_name else ""

    matches = []
    for alert in alerts:
        if alert.get("hours_ago", 99) > hours:
            continue
        mention_norm = _norm(alert.get("player_name", ""))
        tweet_lower  = alert.get("tweet", "").lower()
        # Match on extracted player name OR tweet body containing last name
        if last_name and (last_name in mention_norm or last_name in tweet_lower):
            matches.append(alert)

    return sorted(matches, key=lambda a: a.get("hours_ago", 99))


def has_injury_alert(player_name: str, hours: float = 3.0) -> bool:
    """
    Return True if any beat reporter has posted a relevant alert for this player
    within `hours` hours.

    Args:
        player_name: Player's full name.
        hours:       Lookback window (default 3 hours = ~tipoff window).
    """
    return bool(get_player_alerts(player_name, hours=hours))


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="NBA Beat Reporter Injury Alert Monitor")
    ap.add_argument("--refresh",  action="store_true", help="Force re-scan")
    ap.add_argument("--player",   help="Filter alerts for a specific player")
    ap.add_argument("--hours",    type=float, default=3.0)
    args = ap.parse_args()

    if args.player:
        alerts = get_player_alerts(args.player, hours=args.hours)
        print(f"{len(alerts)} alerts for '{args.player}' in last {args.hours}h:")
        for a in alerts:
            print(f"  [{a['reporter']}] {a['tweet'][:100]}  ({a['hours_ago']:.1f}h ago)")
    else:
        all_alerts = refresh_alerts(force=args.refresh)
        print(f"Total alerts: {len(all_alerts)}")
        for a in all_alerts[:10]:
            print(f"  [{a['reporter']}] {a['player_name']} — {a['keywords']} "
                  f"({a['hours_ago']:.1f}h ago)")
