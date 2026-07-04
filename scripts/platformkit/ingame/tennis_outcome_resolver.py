"""scripts.platformkit.ingame.tennis_outcome_resolver -- OFFLINE-first, ESPN-fallback
outcome resolver for Kalshi ATP/WTA in-play tickers (the tennis counterpart to
ingame_outcome_label.MlbOutcomeResolver / soccer_outcome.SoccerOutcomeResolver).

THE GAP THIS CLOSES
-------------------
Tennis in-play tick capture never started (inplay_capture_loop.DEFAULT_SPORTS was
mlb+soccer_intl only) AND no tennis outcome resolver existed, so even a captured
tennis game could never grade a held-out label. This module supplies
`home_win(ticker) -> {0,1}|None` keyed DIRECTLY off the Kalshi ticker (no ESPN
numeric id needed), mirroring the MLB/soccer resolver contract.

TICKER SHAPE (verified live 2026-07-03 against the Kalshi public API):
  KX(ATP|WTA)MATCH-<YY><MON><DD><TAIL>[-<SIDE>]
e.g. KXATPMATCH-26JUL05AUGDAV-DAV (Auger-Aliassime vs Davidovich Fokina). *TAIL*
concatenates both players' codes with NO delimiter and is VARIABLE WIDTH (most
often 3+3, but a short surname widens ('Kwon' -> KWON, 4) and a particle surname
narrows ('de Minaur' -> DE, 2) -- both seen live). `event_ticker` (the grade-file
stem / game_id) is the ticker WITHOUT the trailing "-<SIDE>". Ticker parsing +
the split/name-match search live in tennis_ticker_match.py (split out to keep
this module under the 300 LOC cap, same pattern as kalshi_series_spec.py).

CODE -> PLAYER MATCHING
------------------------
A lone 3-letter code is frequently AMBIGUOUS across the whole player pool (SIN =
Sinner OR Siniakova; BER = Berrettini OR Bergs -- both verified live), and the
tail's split point is not fixed either (see above). So the split and the name
match are resolved JOINTLY: for the ticker's date (+/-1 day grace) and league
(atp/wta, from the ticker prefix), try every valid 2-way split of the tail
against every completed match's two competitors' candidate codes, keeping only a
(split, match) pairing that is the UNIQUE one consistent across the whole search.
Verified against 100 real settled tickers fetched live (2026-06-29..07-03):
92/100 resolved, 0 mismatches vs Kalshi's own settlement result.

DATA SOURCE (leak-free order of preference)
--------------------------------------------
1. On-disk data/domains/tennis/espn_matches.parquet IF its max completed-match
   date is within FRESHNESS_DAYS of `now` (checked live 2026-07-03: max STATUS_FINAL
   date is 2026-06-14 -- STALE, correctly skipped in favor of tier 2 during
   Wimbledon).
2. Live ESPN site.api tennis scoreboard (keyless, same provider/shape ingest_espn.py
   already parses offline) -- probed live 2026-07-03: returns the FULL current
   tournament draw (the `dates` query param does not filter it), including
   STATUS_FINAL/STATUS_RETIRED/STATUS_WALKOVER completed matches.

WINNER DETERMINATION: a completed match (STATUS_FINAL/STATUS_RETIRED/
STATUS_WALKOVER, `completed=True`) reports one competitor `winner=True` -- this is
honored AS-IS (a retirement/walkover still counts, per ESPN's own winner flag; we
never re-derive a winner from set scores). No competitor flagged winner (still live,
suspended, or a walkover with both names blank so the match can't be identified) ->
None, never guessed.

HONESTY: probability/label space only; no $ field; unresolvable/ambiguous/live
returns None (never fabricated). This only supplies the held-out target for a
CALIBRATION verdict, never an edge or ROI.

INVARIANTS: build under scripts/platformkit/ingame/; <=300 LOC; ASCII only;
network only in the ESPN fallback tier (injectable http_get for offline tests);
never writes data/registry/; never raises out.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_tennis_outcome_resolver.py -q
"""
from __future__ import annotations

import logging
from datetime import date as _date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.ingame.tennis_ticker_match import match_tail, parse_tennis_ticker

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ESPN_PARQUET = _REPO_ROOT / "data" / "domains" / "tennis" / "espn_matches.parquet"

# A stale on-disk snapshot must never silently satisfy a query for a game played
# after its coverage ends -- past this many days old (vs `now`) we skip straight
# to the live ESPN fallback for that ticker's date.
FRESHNESS_DAYS = 3

_SITE = "https://site.api.espn.com/apis/site/v2/sports/tennis"
_FINAL_STATES = frozenset({"STATUS_FINAL", "STATUS_RETIRED", "STATUS_WALKOVER"})

# One completed match: (name_a, name_b, winner_name).
_MatchRow = Tuple[str, str, str]


class TennisOutcomeResolver:
    """Resolve home_win for a Kalshi ATP/WTA ticker: on-disk parquet if fresh
    enough, else the live ESPN scoreboard (keyless). "home" = whichever half of
    the ticker tail's UNIQUE split wins the split+match search (see module
    docstring) -- an arbitrary but CONSISTENT convention (the caller only needs
    a stable, well-defined binary label per ticker; tennis has no real home/away)."""

    def __init__(self, espn_df: Any = None, espn_parquet: Optional[Path] = None,
                 http_get: Optional[Callable[[str], Any]] = None,
                 now: Optional[datetime] = None) -> None:
        self._http_get = http_get or _default_http_get
        self._now = now or datetime.now(timezone.utc)
        self._disk_ok = False
        self._disk_matches: Dict[Tuple[str, _date], List[_MatchRow]] = {}
        # league -> {date -> [match_row,...]} (see _live_board: fetched ONCE per
        # league, bucketed by each row's own date -- ESPN ignores `dates=`).
        self._live_cache: Dict[str, Dict[_date, List[_MatchRow]]] = {}
        try:
            df = espn_df
            if df is None:
                import pandas as pd
                p = Path(espn_parquet) if espn_parquet is not None else DEFAULT_ESPN_PARQUET
                if p.exists():
                    df = pd.read_parquet(p)
            if df is not None:
                self._ingest_disk(df)
        except Exception as exc:  # noqa: BLE001 -- no parquet -> disk tier just empty
            logger.debug("TennisOutcomeResolver disk ingest failed: %s", exc)

    # ---------------------------------------------------------------- disk tier
    def _ingest_disk(self, df: Any) -> None:
        import pandas as pd
        d = df[df["status"].astype(str).isin(_FINAL_STATES)].copy()
        if d.empty:
            return
        d["_dt"] = pd.to_datetime(d["date"], errors="coerce", utc=True)
        max_dt = d["_dt"].max()
        if pd.isna(max_dt):
            return
        age_days = (self._now - max_dt.to_pydatetime()).days
        if age_days > FRESHNESS_DAYS:
            logger.debug("tennis espn_matches.parquet stale (%d days) -- skipping disk tier",
                        age_days)
            return  # stale snapshot: fall through to live ESPN for every ticker
        by_comp: Dict[Any, List[Tuple[str, bool]]] = {}
        comp_date: Dict[Any, Any] = {}
        comp_league: Dict[Any, str] = {}
        for _, r in d.iterrows():
            cid = r.get("comp_id")
            name = str(r.get("player_name") or "").strip()
            if not name:
                continue
            by_comp.setdefault(cid, []).append((name, bool(r.get("winner"))))
            comp_date[cid] = r["_dt"]
            comp_league[cid] = str(r.get("league") or "").lower()
        for cid, players in by_comp.items():
            if len(players) != 2:
                continue
            (na, wa), (nb, wb) = players
            winner = na if wa else (nb if wb else None)
            if winner is None:
                continue
            key = (comp_league.get(cid, ""), comp_date[cid].date())
            self._disk_matches.setdefault(key, []).append((na, nb, winner))
        self._disk_ok = bool(self._disk_matches)

    # ---------------------------------------------------------------- live tier
    def _live_board(self, league: str) -> Dict[_date, List[_MatchRow]]:
        """The FULL tournament draw for *league*, bucketed by each competition's
        OWN scheduled date, cached ONCE per league for this resolver instance.

        ESPN's tennis scoreboard ignores the `dates` query param entirely and
        always returns the whole current tournament (verified live 2026-07-03)
        -- so re-querying per date would silently pool EVERY date's matches
        into each day's candidate set, inflating collisions (e.g. a player who
        played 4 different opponents across the draw all becoming same-day
        "candidates"). We fetch once and bucket by each row's real `date`.
        SINGLES-only (Men's/Women's Singles `type.slug`): the WTA/ATP league
        endpoints were observed to also surface the OTHER tour's/doubles'
        competitions in the same payload, which would otherwise let a men's
        'Zhang Zhizhen' collide with women's 'Zhang Shuai'."""
        if league in self._live_cache:
            return self._live_cache[league]
        by_date: Dict[_date, List[_MatchRow]] = {}
        want_slug = "womens-singles" if league == "wta" else "mens-singles"
        try:
            url = "%s/%s/scoreboard?dates=%s" % (
                _SITE, league, self._now.strftime("%Y%m%d"))
            board = self._http_get(url)
            events = (board or {}).get("events") or []
            for ev in events:
                for g in ev.get("groupings", []) or []:
                    for c in g.get("competitions", []) or []:
                        slug = ((c.get("type") or {}).get("slug") or "")
                        if slug and slug != want_slug:
                            continue
                        cdate = _parse_espn_date(c.get("date"))
                        if cdate is None:
                            continue
                        row = _match_from_competition(c)
                        if row is not None:
                            by_date.setdefault(cdate, []).append(row)
        except Exception as exc:  # noqa: BLE001 -- a feed error -> {} for this league
            logger.debug("tennis live scoreboard fetch failed (%s): %s", league, exc)
        self._live_cache[league] = by_date
        return by_date

    def _candidates(self, league: str, d: _date) -> List[_MatchRow]:
        """Completed-match candidates for (league,date), disk first, else live."""
        if self._disk_ok:
            hit = self._disk_matches.get((league, d))
            if hit:
                return hit
        return self._live_board(league).get(d, [])

    @property
    def available(self) -> bool:
        return True  # always attempts the live fallback; never "unavailable" up-front

    def home_win(self, ticker: str) -> Optional[int]:
        """1 if the ticker tail's UNIQUE split's first half won, 0 if the second
        half won, None if unresolved/ambiguous/not-yet-final. Never raises."""
        parsed = parse_tennis_ticker(ticker)
        if parsed is None:
            return None
        league, d, tail = parsed
        for delta in (0, -1, 1):
            day = d + timedelta(days=delta)
            hit = match_tail(self._candidates(league, day), tail)
            if hit is not None:
                return 1 if hit else 0
        return None


def _parse_espn_date(raw: Any) -> Optional[_date]:
    """ESPN's competition `date` ('2026-07-01T12:30Z') -> a date, or None if
    unparseable (the row is then skipped, never mis-bucketed). Never raises."""
    try:
        s = str(raw or "").strip()
        if not s:
            return None
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        return None


def _match_from_competition(c: Dict[str, Any]) -> Optional[_MatchRow]:
    """One completed singles match's (name_a, name_b, winner_name), or None if
    not a completed 2-competitor match with an identifiable winner."""
    status = ((c.get("status") or {}).get("type") or {})
    if str(status.get("name") or "") not in _FINAL_STATES and not status.get("completed"):
        return None
    comps = c.get("competitors") or []
    if len(comps) != 2:
        return None
    players = []
    for comp in comps:
        name = str((comp.get("athlete") or {}).get("displayName") or "").strip()
        players.append((name, bool(comp.get("winner"))))
    (na, wa), (nb, wb) = players
    if not na or not nb:
        return None  # walkover with blank names -- unresolvable, never guessed
    winner = na if wa else (nb if wb else None)
    if winner is None:
        return None
    return (na, nb, winner)


def _default_http_get(url: str) -> Any:
    from scripts.platformkit.odds_provider.http_cache import http_get_json
    return http_get_json(url)


__all__ = [
    "DEFAULT_ESPN_PARQUET", "FRESHNESS_DAYS", "TennisOutcomeResolver",
    "parse_tennis_ticker",
]
