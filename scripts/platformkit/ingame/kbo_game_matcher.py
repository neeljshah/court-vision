"""scripts.platformkit.ingame.kbo_game_matcher -- Naver gameId lookup by (date, EN teams)
(kbo-alias-wire-soak lane).

Bridges an EN-team-coded matchup (e.g. home="KT", away="LOTTE") to its Naver gameId
(e.g. "20260705LTKT02026") via the CACHED daily slate JSON
(data/domains/kbo/slate_<date>.json, the same file shape kbo_relay_state_provider's
lane-55 probe already produces: {"date_kst","games":[{"game_id","home_team",
"away_team",...}]}, home_team/away_team being NAVER 2-letter codes). Re-fetches at most
ONCE (via kbo_naver_relay.fetch_slate) if the cache file is absent or its date is stale,
writing a fresh cache in the SAME shape so later same-date lookups need no network.

EXACT-match only (ALIAS RAIL): both sides must resolve through kbo_team_alias's
EN_TO_NAVER dict to a real Naver code, then match a slate game's (home_team,away_team)
EXACTLY (never swapped, never fuzzy). Ambiguity (a code pattern matching >1 slate game --
should not occur since Naver only ever schedules a repeat pairing at most once per date)
or an outright miss both degrade to None, with a one-line log naming the reason.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_kbo_game_matcher.py -q
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.ingame import kbo_team_alias as _alias
from scripts.platformkit.ingame.kbo_naver_relay import fetch_slate

logger = logging.getLogger(__name__)

# __file__ = scripts/platformkit/ingame/kbo_game_matcher.py -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SLATE_DIR = _REPO_ROOT / "data" / "domains" / "kbo"

# KXKBOGAME-<YY><MON><DD><HHMM><blob>, e.g. KXKBOGAME-26JUL070530NCDHAN. Kalshi does NOT
# fix away-then-home order for KBO the way KXMLBGAME does (verified live -- see
# kbo_team_alias's module docstring), so parse_kalshi_kbo_ticker only extracts the blob;
# the two teams inside it are resolved by trying every split point, never a positional
# assumption.
_TICKER_RE = re.compile(r"^KXKBOGAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})([A-Z]+)$", re.I)


def parse_kalshi_kbo_ticker(ticker: Any) -> Optional[Dict[str, str]]:
    """Parse a Kalshi KXKBOGAME ticker into its parts, or None if it is not one.

    Returns {yy, mon, dd, hhmm, blob} (blob = the raw concatenated two-team token, upper-
    case, order UNSPECIFIED). Never raises."""
    m = _TICKER_RE.match(str(ticker or "").strip())
    if not m:
        return None
    yy, mon, dd, hhmm, blob = m.groups()
    return {"yy": yy, "mon": mon.upper(), "dd": dd, "hhmm": hhmm, "blob": blob.upper()}


def teams_for_kalshi_blob(blob: str) -> Optional[Tuple[str, str]]:
    """A ticker blob (e.g. "NCDHAN") -> (en_code_1, en_code_2) UNORDERED pair, or None.

    Tries every split point of *blob* and accepts the FIRST split where BOTH halves are
    known Kalshi tokens (kbo_team_alias.en_from_kalshi_token) -- order is not assumed
    (see module docstring). Ambiguous blobs (more than one valid split) are rejected
    (None) rather than guessing which split is correct; a genuine 10-team alphabet with
    per-team token widths of 2-3 chars produces no such collision today, but the guard
    is cheap and keeps this fail-open rather than fail-silent-wrong. Never raises."""
    b = str(blob or "").strip().upper()
    if not b or len(b) < 4:
        return None
    hits = []
    for i in range(2, len(b) - 1):  # every team token seen so far is >=2 chars
        left, right = b[:i], b[i:]
        en_left = _alias.en_from_kalshi_token(left)
        en_right = _alias.en_from_kalshi_token(right)
        if en_left is not None and en_right is not None:
            hits.append((en_left, en_right))
    if len(hits) != 1:
        return None
    return hits[0]


def _slate_path(date: str, slate_dir: Optional[Path] = None) -> Path:
    base = Path(slate_dir) if slate_dir is not None else DEFAULT_SLATE_DIR
    return base / ("slate_%s.json" % str(date))


def _read_cached_slate(date: str, slate_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Cached slate_<date>.json contents, or None if absent/malformed/wrong date
    (STALE guard: a cache file whose own date_kst disagrees with *date* is treated as
    absent so a stale file never silently serves the wrong day). Never raises."""
    try:
        path = _slate_path(date, slate_dir)
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict) or payload.get("date_kst") != date:
            return None
        return payload
    except Exception as exc:  # noqa: BLE001 -- a bad cache file is no cache, never a crash
        logger.debug("kbo_game_matcher cached slate read failed date=%s: %s", date, exc)
        return None


def _write_slate_cache(date: str, games: List[Dict[str, Any]],
                       slate_dir: Optional[Path] = None) -> None:
    """Best-effort write of a freshly-fetched slate into the SAME cache shape (atomic
    .tmp+os.replace). A write failure is measurement loss, not a crash -- never raises."""
    try:
        path = _slate_path(date, slate_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"date_kst": date, "games_found": len(games), "games": games}
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=True)
        os.replace(str(tmp), str(path))
    except Exception as exc:  # noqa: BLE001 -- a cache-write miss just means next call refetches
        logger.debug("kbo_game_matcher slate cache write failed date=%s: %s", date, exc)


def _fetch_fresh_slate(date: str, http_get: Optional[Callable] = None) -> List[Dict[str, Any]]:
    """One live fetch of *date*'s slate mapped into the cache row shape
    {game_id, home_team, away_team, status}. [] on any failure -- never raises."""
    try:
        raw_games = fetch_slate(date, date, http_get=http_get)
    except Exception as exc:  # noqa: BLE001
        logger.debug("kbo_game_matcher slate fetch failed date=%s: %s", date, exc)
        return []
    games: List[Dict[str, Any]] = []
    for g in raw_games or []:
        if not isinstance(g, dict) or not g.get("gameId"):
            continue
        games.append({
            "game_id": str(g.get("gameId")),
            "home_team": str(g.get("homeTeamCode") or ""),
            "away_team": str(g.get("awayTeamCode") or ""),
            "status": str(g.get("statusCode") or ""),
        })
    return games


def _slate_games(date: str, slate_dir: Optional[Path],
                 http_get: Optional[Callable]) -> List[Dict[str, Any]]:
    """The date's slate rows: cached if present/fresh, else ONE live re-fetch (which is
    then cached for subsequent calls). [] if both the cache and the fetch come up empty."""
    cached = _read_cached_slate(date, slate_dir)
    if cached is not None:
        games = cached.get("games")
        if isinstance(games, list) and games:
            return games
    fetched = _fetch_fresh_slate(date, http_get)
    if fetched:
        _write_slate_cache(date, fetched, slate_dir)
    return fetched


def naver_game_id_for(date: str, home_code: str, away_code: str, *,
                      slate_dir: Optional[Path] = None,
                      http_get: Optional[Callable] = None
                      ) -> Optional[str]:
    """Naver gameId for the EN-coded matchup (home_code, away_code) on *date*
    (YYYY-MM-DD), or None on any miss/ambiguity/exception (fail-open, never a crash).

    home_code/away_code are EN canonical codes (e.g. "KT", "LOTTE") resolved through
    kbo_team_alias.EN_TO_NAVER; an unrecognized code -> None immediately (no fetch).
    Matches a slate row EXACTLY (home_team==naver(home_code) AND
    away_team==naver(away_code), never swapped/fuzzy); >1 exact match -> None (ambiguous,
    logged) rather than an arbitrary pick.
    """
    try:
        naver_home = _alias.naver_code_for(home_code)
        naver_away = _alias.naver_code_for(away_code)
        if naver_home is None or naver_away is None:
            logger.info(
                "kbo_game_matcher: unmapped EN code(s) home=%r->%r away=%r->%r",
                home_code, naver_home, away_code, naver_away)
            return None
        games = _slate_games(date, slate_dir, http_get)
        hits = [g for g in games
               if isinstance(g, dict)
               and g.get("home_team") == naver_home
               and g.get("away_team") == naver_away]
        if len(hits) != 1:
            logger.info(
                "kbo_game_matcher: %d exact slate hits date=%s home=%s away=%s (want 1)",
                len(hits), date, naver_home, naver_away)
            return None
        return str(hits[0].get("game_id") or "") or None
    except Exception as exc:  # noqa: BLE001 -- matching is best-effort; never raises
        logger.debug("kbo_game_matcher naver_game_id_for failed: %s", exc)
        return None


__all__ = [
    "DEFAULT_SLATE_DIR", "naver_game_id_for",
    "parse_kalshi_kbo_ticker", "teams_for_kalshi_blob",
]
