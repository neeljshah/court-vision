"""scripts.platformkit.odds_provider.espn -- keyless ESPN public odds provider.

ESPN's free site API exposes a scoreboard per league and a per-event `summary`
endpoint whose `pickcenter[]` node republishes ONE sportsbook's moneyline
(American odds) plus a provider name. We read that public republished line; we do
NOT scrape the sportsbook. No key, no auth.

Flow per sport:
  1. GET scoreboard -> list of event ids + home/away names.
  2. GET summary?event=<id> -> pickcenter[].{provider.name, homeTeamOdds.moneyLine,
     awayTeamOdds.moneyLine} -> normalize to decimal odds.
Each summary call is wrapped in the TTL cache. A scoreboard/summary failure
degrades to UNAVAILABLE (scoreboard) or a skipped event (summary) -- never a fake.

Mapping our sport keys -> ESPN league paths:
  nba -> basketball/nba ; mlb -> baseball/mlb ;
  soccer -> soccer/eng.1 (EPL) ; soccer_intl -> soccer/fifa.world.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from .base import OddsEvent, american_to_decimal, unavailable
from .http_cache import disk_cache_get, http_get_json

logger = logging.getLogger(__name__)

_SITE = "https://site.api.espn.com/apis/site/v2/sports"
_LEAGUE_PATH: Dict[str, str] = {
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "soccer": "soccer/eng.1",
    "soccer_intl": "soccer/fifa.world",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _team_name(competitor: Dict[str, Any]) -> str:
    team = competitor.get("team") or {}
    return (team.get("displayName") or team.get("name")
            or team.get("abbreviation") or "").strip()


def parse_pickcenter(summary: Dict[str, Any], home: str, away: str,
                     ) -> Dict[str, Dict[str, Optional[float]]]:
    """Extract {provider_name: {"home": dec, "away": dec}} from a summary payload.

    Pure: safe to unit-test on a canned summary. Each pickcenter entry is a
    distinct sportsbook (a venue). American moneylines -> decimal; missing /
    unparseable sides are skipped, never guessed. Draw is omitted (ESPN
    pickcenter moneyline is two-way home/away).
    """
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for pc in summary.get("pickcenter", []) or []:
        provider = (pc.get("provider") or {}).get("name")
        if not provider:
            continue
        h = american_to_decimal((pc.get("homeTeamOdds") or {}).get("moneyLine"))
        a = american_to_decimal((pc.get("awayTeamOdds") or {}).get("moneyLine"))
        side: Dict[str, Optional[float]] = {}
        if h is not None:
            side["home"] = h
        if a is not None:
            side["away"] = a
        if side:
            out[f"espn:{provider}"] = side
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

    def _get(self, url: str) -> Any:
        if self._use_cache:
            return disk_cache_get(url, http_get=self._http_get)
        return self._http_get(url)

    def fetch(self, sport: str) -> Union[List[OddsEvent], Dict[str, str]]:
        sport = sport.lower()
        path = _LEAGUE_PATH.get(sport)
        if not path:
            return unavailable(f"espn: unsupported sport '{sport}'")
        try:
            board = self._get(f"{_SITE}/{path}/scoreboard")
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("espn scoreboard failed for %s: %s", sport, exc)
            return unavailable(f"espn scoreboard call failed ({type(exc).__name__})")
        events = board.get("events", []) if isinstance(board, dict) else None
        if not isinstance(events, list):
            return unavailable("espn: unexpected scoreboard shape")
        as_of = _now_iso()
        out: List[OddsEvent] = []
        for ev in events[: self._max_events]:
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
            summary = self._get(url)
        except Exception as exc:  # noqa: BLE001 -- one bad event must not sink the slate
            logger.debug("espn summary failed for %s: %s", eid, exc)
            return {}
        if not isinstance(summary, dict):
            return {}
        return parse_pickcenter(summary, home, away)


__all__ = ["EspnProvider", "parse_pickcenter"]
