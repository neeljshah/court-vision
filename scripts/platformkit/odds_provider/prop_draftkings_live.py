"""scripts.platformkit.odds_provider.prop_draftkings_live -- LIVE (in-play) DK player props.

The pregame adapter (prop_draftkings_v2) reads DK's pregame league/subcategory catalog --
which DROPS a game at first pitch. DK keeps serving the game's player props IN-PLAY, but
through the EVENT endpoint instead:

    /leagues/{league_id}                  -> events[] (find status == "STARTED")
    /events/{event_id}/categories         -> markets[] + selections[] for that live game

Those markets include live-updating full-game player props ("Wyatt Langford Hits + Runs +
RBIs O/U", "Jacob deGrom Strikeouts Thrown O/U", ...). This adapter pulls the TWO-WAY O/U
ones (Over + Under -> devig-able) as PropLine rows so the in-game prop trader can re-price
them on realized state and compare to the live line.

HONEST RAILS: keyless public DK API; UNITS/probability work happens downstream; this only
supplies the live price. NEVER fabricates -- a one-sided/milestone market or a missing
price is skipped, never half-filled. ASCII; <=300 LOC; fetch errors -> UNAVAILABLE.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/odds_provider/test_prop_draftkings_live.py -q
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Union

from .base import unavailable
from .prop_base import PropLine, canon_stat
from .prop_draftkings_v2 import _BASE, _default_http_get, _now_iso

logger = logging.getLogger(__name__)

# sport -> DK league id (same ids the pregame adapter uses). The soccer / World Cup live
# league id is NOT hard-coded: DK's WC id is not in the repo and must be CONFIRMED against
# the live event endpoint during a live match. Set DK_SOCCER_INTL_LEAGUE_ID (and/or
# DK_SOCCER_LEAGUE_ID) once verified -> the soccer path lights up; absent -> honest no-op.
_LEAGUE: Dict[str, str] = {"mlb": "84240"}
for _sp, _env in (("soccer_intl", "DK_SOCCER_INTL_LEAGUE_ID"),
                  ("soccer", "DK_SOCCER_LEAGUE_ID")):
    _val = os.environ.get(_env)
    if _val:
        _LEAGUE[_sp] = _val.strip()

# Two-way O/U stat phrases as they appear in DK live market names, longest-first so
# multi-word phrases match before their prefixes. Value = our canonical stat (the box
# reader + repricer key). canon_stat handles most; we override only what it leaves raw.
_STAT_FIX: Dict[str, str] = {"Strikeouts Thrown": "Pitcher Strikeouts",
                             "Shots on Goal": "Shots On Target"}
_STAT_PHRASES_BY_SPORT: Dict[str, List[str]] = {
    "mlb": ["Hits + Runs + RBIs", "Strikeouts Thrown", "Total Bases", "Stolen Bases",
            "Hits Allowed", "Walks Allowed", "Earned Runs", "Pitching Outs", "Home Runs",
            "Hits", "RBIs", "Runs", "Walks", "Outs"],
    # soccer / WC: only the families the keyless realized reader can grade in-game
    # (goals/assists/cards) plus shots phrasing for completeness; SOT stays un-pricable
    # in-game (no per-player realized feed) and is skipped by the trader's is_known_stat.
    "soccer_intl": ["Shots on Goal", "Shots On Target", "Goals + Assists", "Shots",
                    "Goals", "Assists", "Cards"],
}
_STAT_PHRASES_BY_SPORT["soccer"] = _STAT_PHRASES_BY_SPORT["soccer_intl"]
_OU = " O/U"


def _to_dec(sel: Dict[str, Any]) -> Optional[float]:
    """Decimal odds from a DK selection's displayOdds, or None."""
    try:
        d = (sel.get("displayOdds") or {}).get("decimal")
        return float(d) if d is not None else None
    except (TypeError, ValueError):
        return None


def _split_player_stat(market_name: str, sport: str = "mlb") -> Optional[tuple]:
    """('Wyatt Langford', 'Hits+Runs+RBIs') from 'Wyatt Langford Hits + Runs + RBIs O/U'.

    Returns (player, canonical_stat) or None when the trailing stat is not a known O/U
    phrase for *sport* (so we never guess a player/stat split)."""
    name = str(market_name or "").strip()
    if name.endswith(_OU):
        name = name[: -len(_OU)].rstrip()
    phrases = _STAT_PHRASES_BY_SPORT.get(str(sport).lower(), _STAT_PHRASES_BY_SPORT["mlb"])
    for ph in sorted(phrases, key=len, reverse=True):
        if name.endswith(" " + ph):
            player = name[: -len(ph) - 1].strip()
            if not player:
                return None
            stat = _STAT_FIX.get(ph) or canon_stat(ph) or ph
            return player, stat
    return None


def live_event_ids(sport: str,
                   *, http_get: Optional[Callable[[str], Dict[str, Any]]] = None
                   ) -> List[str]:
    """DK event ids for *sport* games that are LIVE (status STARTED). [] on failure."""
    get = http_get or _default_http_get
    lid = _LEAGUE.get(sport.lower())
    if not lid:
        return []
    d = get(_BASE + "/leagues/" + lid) or {}
    return [str(e.get("id")) for e in (d.get("events") or [])
            if str(e.get("status")) == "STARTED" and e.get("id") is not None]


def _parse_event(payload: Dict[str, Any], event_id: str,
                 sport: str = "mlb", match: Optional[str] = None) -> List[PropLine]:
    """Two-way O/U player props for one live event payload -> PropLine rows."""
    selby: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for s in payload.get("selections") or []:
        mid = str(s.get("marketId"))
        lab = str(s.get("label"))
        if lab in ("Over", "Under"):
            selby.setdefault(mid, {})[lab] = s
    out: List[PropLine] = []
    for m in payload.get("markets") or []:
        mid = str(m.get("id"))
        sides = selby.get(mid)
        if not sides or "Over" not in sides or "Under" not in sides:
            continue                      # not a two-way O/U (milestone/other) -> skip
        ps = _split_player_stat(m.get("name"), sport)
        if ps is None:
            continue
        player, stat = ps
        over, under = sides["Over"], sides["Under"]
        line = over.get("points")
        if line is None:
            line = under.get("points")
        od, ud = _to_dec(over), _to_dec(under)
        if line is None or od is None or ud is None or od <= 1.0 or ud <= 1.0:
            continue                      # never half-fill a price we cannot read
        try:
            line_f = float(line)
        except (TypeError, ValueError):
            continue
        out.append(PropLine(
            sport=sport, event_id=str(event_id), match=match, player=player,
            team=None, stat=stat, line=line_f, over_price=od, under_price=ud,
            payout_type="sportsbook", source="draftkings_live", as_of=_now_iso()))
    return out


def fetch_props(sport: str,
                *, http_get: Optional[Callable[[str], Dict[str, Any]]] = None
                ) -> Union[List[PropLine], Dict[str, str]]:
    """LIVE in-play two-way player props across all of *sport*'s in-progress games.

    Returns a PropLine list (possibly empty when no game is live) or an UNAVAILABLE dict
    on an unsupported sport. NEVER raises."""
    get = http_get or _default_http_get
    if sport.lower() not in _LEAGUE:
        return unavailable("draftkings_live: unsupported sport %r" % sport)
    try:
        lg = get(_BASE + "/leagues/" + _LEAGUE[sport.lower()]) or {}
        names = {str(e.get("id")): e.get("name") for e in (lg.get("events") or [])}
        started = [eid for eid, e in
                   ((str(e.get("id")), e) for e in (lg.get("events") or []))
                   if str(e.get("status")) == "STARTED" and e.get("id") is not None]
        out: List[PropLine] = []
        for eid in started:
            payload = get(_BASE + "/events/" + eid + "/categories") or {}
            out.extend(_parse_event(payload, eid, sport=sport.lower(),
                                    match=names.get(eid)))
        return out
    except Exception as exc:  # noqa: BLE001 -- never bubble a feed error
        logger.warning("prop_draftkings_live.fetch_props failed: %s", exc)
        return unavailable("draftkings_live: %s" % type(exc).__name__)


class DraftKingsLivePropProvider:
    """Provider shim: .fetch_props(sport) -> live two-way PropLines (drop-in for the trader)."""

    name = "draftkings_live"

    def __init__(self, http_get: Optional[Callable[[str], Dict[str, Any]]] = None):
        self._http_get = http_get

    def fetch_props(self, sport: str) -> Union[List[PropLine], Dict[str, str]]:
        return fetch_props(sport, http_get=self._http_get)


__all__ = ["fetch_props", "live_event_ids", "DraftKingsLivePropProvider"]
