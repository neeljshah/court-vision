"""nba_api_headers_patch.py — patch nba_api headers so calls succeed.

The `nba_api` library's default headers (set in `nba_api.stats.library.http`)
have stopped being accepted by stats.nba.com — production traffic now requires
a fuller browser-style header set (User-Agent, Referer, x-nba-stats-origin etc).
Calls otherwise fail with 30s read timeouts and `Max retries exceeded`.

Importing this module (at the very top of any code that subsequently imports
nba_api endpoints) overwrites the library-level `STATS_HEADERS` dict in place.
Patch is applied once on import; subsequent imports are no-ops because the
underlying dict has already been mutated.

Verified working against:
  - stats.nba.com/stats/leaguegamelog
  - stats.nba.com/stats/leaguedashteamstats
(both return 200 with full payload using the headers below; both return
read-timeout without).
"""
from __future__ import annotations

# Browser-style headers that pass NBA's bot detection (2026-05-23).
_WORKING_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Connection": "keep-alive",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


def apply_patch() -> None:
    """Patch nba_api's STATS_HEADERS in place. Safe to call multiple times."""
    try:
        from nba_api.stats.library import http as _nba_http
    except ImportError:
        return  # nba_api not installed — nothing to patch
    _nba_http.STATS_HEADERS.clear()
    _nba_http.STATS_HEADERS.update(_WORKING_HEADERS)
    # NBAStatsHTTP.headers also points to the same dict object, but be defensive
    # in case nba_api ever copies it.
    try:
        _nba_http.NBAStatsHTTP.headers = _nba_http.STATS_HEADERS
    except Exception:
        pass


# Apply on import.
apply_patch()
