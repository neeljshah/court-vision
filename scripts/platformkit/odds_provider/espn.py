"""scripts.platformkit.odds_provider.espn -- keyless ESPN public odds provider.

ESPN's free site API exposes a scoreboard per league and a per-event `summary`
endpoint whose `pickcenter[]` node republishes ONE sportsbook's moneyline
(American odds) plus a provider name. We read that public republished line; we do
NOT scrape the sportsbook. No key, no auth.

Flow per sport:
  1. GET scoreboard -> list of event ids + home/away names.
  2. GET summary?event=<id> -> pickcenter[].{provider.name, homeTeamOdds.moneyLine,
     awayTeamOdds.moneyLine, spread, overUnder, overOdds, underOdds}
     -> normalize to decimal odds.
Each summary call is wrapped in the TTL cache. A scoreboard/summary failure
degrades to UNAVAILABLE (scoreboard) or a skipped event (summary) -- never a fake.

Mapping our sport keys -> ESPN league paths:
  nba -> basketball/nba ; mlb -> baseball/mlb ;
  soccer -> soccer/eng.1 (EPL) ; soccer_intl -> soccer/fifa.world ;
  wnba -> basketball/wnba (probed live 2026-07-03: scoreboard + pickcenter both
  carry real DraftKings moneyline/spread/total, same shape as nba -- LANE 2).

SPREAD SOURCE: pickcenter[].spread is the home-team handicap (e.g. -5.5). The
away line is its negation. Per-provider spread ODDS are sourced from
homeTeamOdds.spreadOdds / awayTeamOdds.spreadOdds (American, present only on
some books). When those fields are absent the spread is OMITTED rather than
assumed -- we NEVER fabricate a price.

TOTAL SOURCE: pickcenter[].overUnder is the O/U line. Prices come from the
top-level overOdds / underOdds fields (American, present on some books). When
those fields are absent the total is OMITTED -- never assumed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .base import OddsEvent, american_to_decimal, unavailable
from .http_cache import disk_cache_get_meta, http_get_json

logger = logging.getLogger(__name__)

_SITE = "https://site.api.espn.com/apis/site/v2/sports"
_LEAGUE_PATH: Dict[str, str] = {
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "soccer": "soccer/eng.1",
    "soccer_intl": "soccer/fifa.world",
    "tennis": "tennis/atp",
    "wnba": "basketball/wnba",
}

# STALE-SCOREBOARD GUARD: an event whose commence_time is older than this is a
# stale echo, not a live/current slate entry. Root cause (2026-07-11): ESPN's
# scoreboard, called with no "dates=" param, falls back to re-serving the LAST
# KNOWN event when there is nothing scheduled "today" (proven live: NBA
# offseason -> the same June-14 game kept coming back verbatim every poll for
# 25+ days, ballooning data/cache/line_history/nba/*.jsonl with duplicate
# rows). Not offseason-only: the identical mechanism would just as happily
# re-serve yesterday's finished slate during any in-season lull (all-star
# break, a quiet feed hiccup) -- there is no upstream recency filter without
# this guard. 30h covers a same-day doubleheader + timezone slop while
# rejecting anything ESPN echoes back days later. ponytail: a flat age cutoff,
# not a real "is this slate current" check -- tighten if a legit same-day
# capture ever needs a longer look-back.
_MAX_EVENT_AGE_HOURS = 30


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _team_name(competitor: Dict[str, Any]) -> str:
    team = competitor.get("team") or {}
    return (team.get("displayName") or team.get("name")
            or team.get("abbreviation") or "").strip()


def _is_stale_echo(commence_raw: Any, now: datetime) -> bool:
    """True if *commence_raw* (ESPN's event "date") is older than the stale-echo
    guard (_MAX_EVENT_AGE_HOURS) -- i.e. this event is not part of today's live
    slate, just a re-served completed game. Unparseable/missing -> not stale
    (never drop an event on a parse miss; that would be its own fabrication)."""
    try:
        dt = datetime.fromisoformat(str(commence_raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_hours = (now - dt.astimezone(timezone.utc)).total_seconds() / 3600.0
    return age_hours > _MAX_EVENT_AGE_HOURS


def _safe_float(value: Any) -> Optional[float]:
    """Parse a float from an ESPN field; None on missing / non-numeric."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _spread_node(pc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a spread sub-node if BOTH the line AND per-side odds are present.

    ESPN pickcenter carries the home spread line at pc["spread"] (a float,
    e.g. -5.5). The per-provider spread prices live at:
      pc["homeTeamOdds"]["spreadOdds"]  (American, e.g. -110)
      pc["awayTeamOdds"]["spreadOdds"]
    When EITHER the line or EITHER side's price is absent the whole spread
    node is omitted -- we NEVER fabricate a line or a price.
    """
    line_home = _safe_float(pc.get("spread"))
    if line_home is None:
        return None
    line_away = -line_home
    hto = pc.get("homeTeamOdds") or {}
    ato = pc.get("awayTeamOdds") or {}
    odds_h = american_to_decimal(hto.get("spreadOdds"))
    odds_a = american_to_decimal(ato.get("spreadOdds"))
    if odds_h is None or odds_a is None:
        return None
    return {
        "home": {"line": line_home, "odds": odds_h},
        "away": {"line": line_away, "odds": odds_a},
    }


def _total_node(pc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a total sub-node if BOTH the line AND per-side odds are present.

    ESPN pickcenter carries the O/U line at pc["overUnder"] (a float,
    e.g. 220.5). The prices live at the top-level fields:
      pc["overOdds"]  (American, e.g. -110)
      pc["underOdds"]
    When EITHER the line or EITHER price is absent the whole total node is
    omitted -- we NEVER fabricate a line or a price.
    """
    line = _safe_float(pc.get("overUnder"))
    if line is None:
        return None
    odds_o = american_to_decimal(pc.get("overOdds"))
    odds_u = american_to_decimal(pc.get("underOdds"))
    if odds_o is None or odds_u is None:
        return None
    return {
        "over":  {"line": line, "odds": odds_o},
        "under": {"line": line, "odds": odds_u},
    }


def parse_pickcenter(summary: Dict[str, Any], home: str, away: str,
                     ) -> Dict[str, Dict[str, Any]]:
    """Extract per-venue price dicts from a summary payload.

    Each pickcenter entry maps to one sportsbook (venue) keyed
    "espn:<ProviderName>". The returned dict has the extended shape that
    markets.quotes_from_aggregate expects:

      {venue: {"home": dec, "away": dec,         # moneyline (always present when ML quoted)
               "spread": {...} | absent,          # only when line+odds both present
               "total":  {...} | absent}}         # only when line+odds both present

    Moneyline behaviour is byte-identical to before. Spread/total nodes are
    ADDED only when ESPN provides all required fields (line + both-side odds).
    A malformed pickcenter never contaminates existing moneyline output.
    Pure: safe to unit-test on a canned summary.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for pc in summary.get("pickcenter", []) or []:
        try:
            provider = (pc.get("provider") or {}).get("name")
            if not provider:
                continue
            h = american_to_decimal((pc.get("homeTeamOdds") or {}).get("moneyLine"))
            a = american_to_decimal((pc.get("awayTeamOdds") or {}).get("moneyLine"))
            side: Dict[str, Any] = {}
            if h is not None:
                side["home"] = h
            if a is not None:
                side["away"] = a
            # Spread and total: additive, guarded -- a missing/malformed field
            # never touches the moneyline path above.
            spread = _spread_node(pc)
            if spread is not None:
                side["spread"] = spread
            total = _total_node(pc)
            if total is not None:
                side["total"] = total
            if side:
                out[f"espn:{provider}"] = side
        except Exception:  # noqa: BLE001 -- one bad pc entry must not abort the rest
            continue
    return out


class EspnProvider:
    """Keyless ESPN odds provider. fetch(sport) -> list[OddsEvent] | UNAVAILABLE."""

    name = "espn"

    def __init__(self,
                 http_get: Callable[[str], Any] = http_get_json,
                 *, use_cache: bool = True, max_events: int = 20) -> None:
        self._http_get = http_get
        self._use_cache = use_cache
        self._max_events = max_events

    def _get(self, url: str) -> Tuple[Any, str]:
        """Return (body, fetched_at_iso). fetched_at is the TRUE network fetch time
        of the body -- the ORIGINAL fetch time on a cache hit, never now() -- so a
        cached/dead feed cannot re-stamp itself fresh (stale-never-green)."""
        if self._use_cache:
            body, fetched_at, _hit = disk_cache_get_meta(url, http_get=self._http_get)
            return body, fetched_at
        return self._http_get(url), _now_iso()

    def fetch(self, sport: str, *, now: Optional[datetime] = None
             ) -> Union[List[OddsEvent], Dict[str, str]]:
        """*now* is injectable (offline-testable); defaults to the real UTC clock.
        It is used ONLY for the stale-echo guard below -- never stamped as as_of."""
        sport = sport.lower()
        path = _LEAGUE_PATH.get(sport)
        if not path:
            return unavailable(f"espn: unsupported sport '{sport}'")
        try:
            board, as_of = self._get(f"{_SITE}/{path}/scoreboard")
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("espn scoreboard failed for %s: %s", sport, exc)
            return unavailable(f"espn scoreboard call failed ({type(exc).__name__})")
        events = board.get("events", []) if isinstance(board, dict) else None
        if not isinstance(events, list):
            return unavailable("espn: unexpected scoreboard shape")
        # as_of is the scoreboard's TRUE fetched-at (cache-honest), NOT now().
        nowdt = now if now is not None else datetime.now(timezone.utc)
        out: List[OddsEvent] = []
        for ev in events[: self._max_events]:
            if _is_stale_echo(ev.get("date"), nowdt):
                continue
            comp = (ev.get("competitions") or [{}])[0]
            home = away = ""
            for c in comp.get("competitors", []) or []:
                if c.get("homeAway") == "home":
                    home = _team_name(c)
                elif c.get("homeAway") == "away":
                    away = _team_name(c)
            eid = str(ev.get("id") or "")
            if not eid or not home or not away:
                continue
            prices = self._event_prices(path, eid, home, away)
            out.append(OddsEvent(
                event_id=eid, sport=sport, home=home, away=away,
                commence_time=ev.get("date"), prices=prices,
                source=self.name, as_of=as_of))
        return out

    def _event_prices(self, path: str, eid: str, home: str, away: str,
                      ) -> Dict[str, Dict[str, Optional[float]]]:
        url = f"{_SITE}/{path}/summary?event={eid}"
        try:
            summary, _fetched_at = self._get(url)
        except Exception as exc:  # noqa: BLE001 -- one bad event must not sink the slate
            logger.debug("espn summary failed for %s: %s", eid, exc)
            return {}
        if not isinstance(summary, dict):
            return {}
        return parse_pickcenter(summary, home, away)


__all__ = ["EspnProvider", "parse_pickcenter"]
