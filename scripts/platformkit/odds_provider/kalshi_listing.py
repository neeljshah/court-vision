"""scripts.platformkit.odds_provider.kalshi_listing -- Kalshi-as-listing-source
for sports with NO ESPN/schedule feed (npb, kbo).

THE GAP THIS CLOSES
-------------------
live_board.todays_live_games is ESPN-shaped (_ESPN_ROUTES has no npb/kbo entry --
ESPN publishes no NPB/KBO scoreboard). But Kalshi's own OPEN KXNPBGAME/KXKBOGAME
markets already encode date + both teams in each market's per-leg ticker (see
scripts.platformkit.ingame.npb_outcome_resolver / kbo_outcome_resolver, wave 4),
so an open market IS a pregame listing row -- no ESPN, no live clock/score
needed. This module turns that ticker set into PREGAME-ONLY listing rows shaped
like live_board's game dict (state="pre", scores/clock=None), reusing the
resolvers' OWN ticker-parse + team-code maps (never a duplicated/hand-typed
team map -- import parse_npb_ticker/parse_kbo_ticker + the resolver's code
index builder directly). A Kalshi game holds TWO team-leg markets sharing the
same date+teams but DIFFERENT per-leg 'ticker' strings (a '-<SIDE>' suffix,
e.g. '...-NCD' / '...-KIA') -- rows_from_markets dedupes on the RESOLVED
(date, home, away) triple, not the raw ticker, so both legs collapse to ONE
listing row (mirrors kalshi.py's own event_ticker grouping, one level down).

WHY PREGAME-ONLY: Kalshi's public /markets listing has no live clock/score
field, and neither NPBAdapter nor KBOAdapter has a predict_live model (see
their adapter docstrings) -- there IS no live state to report. Honestly PRE
only, never a fabricated "in" tick.

Row shape (mirrors live_board.todays_live_games's per-game dict, the fields
run_paper_today/bet_board actually read):
    {"sport": str, "home": str, "away": str, "state": "pre",
     "home_score": None, "away_score": None, "clock": None,
     "event_id": str (the Kalshi ticker), "date": "YYYY-MM-DD"}
home/away are the PARQUET-NATIVE team-name spelling (NPB: kanji/katakana per
_CODE_TO_NAME; KBO: ASCII EN code per _KALSHI_TO_PARQUET) so a listing row can
be handed straight to predict_matchup / NPBAdapter.predict / KBOAdapter.predict
with NO further translation -- the exact seam wnba's ESPN displayName already
gets for free (see wnba_outcome_resolver / live_board.resolve_team's wnba
branch: "BUILT from the same feed, pass through unchanged").

HONESTY: an ambiguous/unresolvable ticker is DROPPED from the listing (never a
guessed team pairing) -- mirrors the resolvers' own honesty contract. No odds
math here (this is LISTING only; odds/EV live in bet_board via the existing
aggregate/Kalshi odds provider). Never raises; never writes data/registry/.

ODDS-ATTACHMENT NOTE (LANE 4): the Kalshi ODDS FEED (kalshi.py._team_label,
consumed by odds_provider.aggregate) labels each leg with the club's FULL
English name (yes_sub_title, e.g. "NC Dinos") -- NOT the ticker's 3-letter
tail code this module parses. For KBO, team_resolver._KBO_NAME_TO_CODE now
links that full name to the parquet's ASCII EN spelling (this lane's fix), so
a KBO listing row's home/away CAN find a live Kalshi book price via
aggregate.teams_match. For NPB, the odds feed's English full name ("Hanshin
Tigers") shares NO normalized token with the parquet's Japanese kanji/
katakana spelling ("阪神") -- there is no name-matching path that closes this
without a dedicated EN<->kanji club map, so NPB listing rows are honestly
PRICED NEVER (board shows a model view only, best_price=None) until that map
exists. Verified live 2026-07-06/07: aggregate('kbo') attaches kalshi prices
to all 10 clubs; aggregate('npb') returns 6 kalshi events with ZERO name
match against the parquet.

INVARIANTS: build only under scripts/platformkit/odds_provider/; <=300 LOC;
ASCII only; no secrets.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_listing.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .http_cache import http_get_json, disk_cache_get_meta
from .kalshi_series_spec import _GAME_SERIES

logger = logging.getLogger(__name__)

_BASE = "https://api.elections.kalshi.com/trade-api/v2/markets"

# sport -> (parse_ticker(ticker) -> (date, *tail_parts) | None,
#           build_code_index(names) -> {code: parquet_name},
#           results_parquet_path)
# Lazily imported inside _spec() so a resolver-module import error degrades
# this listing to [] rather than raising at module import time.


def _spec(sport: str) -> Optional[Dict[str, Any]]:
    s = sport.lower()
    try:
        if s == "npb":
            from scripts.platformkit.ingame.npb_outcome_resolver import (
                parse_npb_ticker, _build_code_index, _split_tail,
                DEFAULT_RESULTS_PARQUET)
            return {"parse": parse_npb_ticker, "code_index": _build_code_index,
                    "split": _split_tail, "parquet": DEFAULT_RESULTS_PARQUET,
                    "tail_is_prejoined": True}
        if s == "kbo":
            from scripts.platformkit.ingame.kbo_outcome_resolver import (
                parse_kbo_ticker, DEFAULT_RESULTS_PARQUET)
            return {"parse": parse_kbo_ticker, "parquet": DEFAULT_RESULTS_PARQUET,
                    "tail_is_prejoined": False}
    except Exception as exc:  # noqa: BLE001 -- a resolver import failure -> [] listing
        logger.debug("kalshi_listing spec(%s) failed: %s", sport, exc)
    return None


def _team_set(parquet_path: Any) -> Optional[set]:
    """All team names in the local results parquet, or None if unavailable."""
    try:
        import pandas as pd
        from pathlib import Path
        p = Path(parquet_path)
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        return set(df["home_team"].astype(str)) | set(df["away_team"].astype(str))
    except Exception as exc:  # noqa: BLE001 -- no parquet -> caller degrades to []
        logger.debug("kalshi_listing team_set(%s) failed: %s", parquet_path, exc)
        return None


def _row_from_ticker(sport: str, ticker: str, spec: Dict[str, Any],
                     names: set) -> Optional[Dict[str, Any]]:
    """One listing row from a single Kalshi event_ticker, or None (unresolvable
    / ambiguous split -- never a guess, mirrors the resolvers' own contract)."""
    if spec.get("tail_is_prejoined"):
        # NPB: parse -> (date, raw_tail); split against a code index built from
        # the parquet's own present team names (never a stale hand-typed map).
        parsed = spec["parse"](ticker)
        if parsed is None:
            return None
        date, tail = parsed
        code_index = spec["code_index"](names)
        split = spec["split"](tail, code_index)
        if split is None:
            return None
        away, home = split
    else:
        # KBO: parse takes the valid-code set directly and returns (date, away, home).
        parsed = spec["parse"](ticker, names | _kbo_alias_codes())
        if parsed is None:
            return None
        date, away, home = parsed
    return {"sport": sport, "home": home, "away": away, "state": "pre",
            "home_score": None, "away_score": None, "clock": None,
            "event_id": ticker, "date": date.isoformat()}


def _kbo_alias_codes() -> set:
    """Kalshi ticker codes for KBO that alias to a parquet code (see
    kbo_outcome_resolver._KALSHI_TO_PARQUET) -- included in the valid-code set
    passed to parse_kbo_ticker so an aliased split (e.g. 'KTW'->'KT') resolves."""
    try:
        from scripts.platformkit.ingame.kbo_outcome_resolver import _KALSHI_TO_PARQUET
        return set(_KALSHI_TO_PARQUET.keys())
    except Exception:  # noqa: BLE001
        return set()


def rows_from_markets(sport: str, markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pure: OPEN Kalshi market dicts -> deduped pregame listing rows for
    *sport*. Each Kalshi market carries a PER-LEG 'ticker' (with a '-<SIDE>'
    suffix, e.g. '...-NCD') AND a shared 'event_ticker' (without the suffix) --
    the resolvers parse the per-leg 'ticker' (see npb_outcome_resolver /
    kbo_outcome_resolver's own fixtures), so we do too, falling back to
    'event_ticker' only if 'ticker' is absent (defensive, mirrors
    inplay_kalshi's game_id fallback). Unresolvable tickers are dropped, never
    guessed. Deduped on the RESOLVED (date, home, away) triple -- not the raw
    ticker string -- so a game's two team-leg tickers (same date+teams,
    different '-<SIDE>' suffix) collapse to ONE listing row."""
    spec = _spec(sport)
    if spec is None:
        return []
    names = _team_set(spec["parquet"])
    if not names:
        return []
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for m in markets or []:
        ticker = str(m.get("ticker") or m.get("event_ticker") or "").strip()
        if not ticker:
            continue
        row = _row_from_ticker(sport, ticker, spec, names)
        if row is None:
            continue
        key = (row["date"], row["home"], row["away"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def todays_kalshi_games(sport: str, *,
                        http_get: Callable[[str], Any] = http_get_json,
                        use_cache: bool = True) -> Dict[str, Any]:
    """Shaped like live_board.todays_live_games's return, for a sport with NO
    ESPN feed. Fetches OPEN markets for *sport*'s GAME series (server-side
    scoped, mirroring KalshiProvider.fetch), parses them into pregame-only
    listing rows. Never raises; degrades to status='unavailable' on any error."""
    import datetime as _dt
    as_of = _dt.datetime.now(_dt.timezone.utc).isoformat()
    s = sport.lower()
    series = _GAME_SERIES.get(s)
    if not series:
        return {"sport": s, "status": "unknown_sport", "as_of": as_of, "games": [],
                "note": f"no Kalshi GAME series registered for '{s}'"}
    import urllib.parse
    params = {"series_ticker": series, "status": "open", "limit": 200}
    url = f"{_BASE}?" + urllib.parse.urlencode(params)
    try:
        if use_cache:
            body, _fetched_at, _hit = disk_cache_get_meta(url, http_get=http_get)
        else:
            body = http_get(url)
    except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
        logger.warning("kalshi_listing fetch failed for %s: %s", s, exc)
        return {"sport": s, "status": "unavailable", "as_of": as_of, "games": [],
                "note": f"Kalshi listing call failed ({type(exc).__name__})"}
    markets = body.get("markets") if isinstance(body, dict) else None
    if not isinstance(markets, list):
        return {"sport": s, "status": "unavailable", "as_of": as_of, "games": [],
                "note": "Kalshi: unexpected markets shape"}
    games = rows_from_markets(s, markets)
    return {"sport": s, "status": "ok", "as_of": as_of, "n_games": len(games),
            "n_live": 0, "predictor_available": None, "games": games,
            "honest_note": ("Kalshi OPEN-market ticker listing (no ESPN feed exists "
                            "for this sport); PREGAME ONLY -- no live clock/score, no "
                            "in-game model. Markets efficient -- NO $ edge.")}


__all__ = ["rows_from_markets", "todays_kalshi_games"]
