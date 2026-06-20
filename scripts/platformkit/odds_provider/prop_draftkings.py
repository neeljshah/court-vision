"""scripts.platformkit.odds_provider.prop_draftkings -- keyless DraftKings props.

DraftKings exposes player-prop markets via a public (no-key) sportsbook API.
The navigation is a two-step: a league-events call returns the event list for a
sport, and a per-event offer-categories call returns the prop markets posted for
that event. Both endpoints are keyless and return JSON.

REAL API shape:
  League events:
    GET /sites/US-IL-SB/api/2/categories/{league_id}/{cat_id}/subcategories
    -> eventGroup.events[]: {eventId, name "Team A at Team B", startDate}

  Event offers (per eventId):
    GET /sites/US-IL-SB/api/2/events/{event_id}/categories/{cat_id}/subcategories
    -> eventGroup.offerCategories[].offerSubcategory.offers[][]:
        offer: {outcomes[]: {label "Over"|"Under", oddsAmerican "+120",
                             oddsDecimal "2.20", participant "<Player>",
                             line "<value>"}}

Pricing: DraftKings posts TWO-WAY American odds (oddsAmerican) AND decimal odds
(oddsDecimal) per outcome. We prefer oddsDecimal (already in the right format) and
fall back to converting oddsAmerican via american_to_decimal. payout_type is
"sportsbook" for every row -- DraftKings is a licensed sportsbook, not a DFS
pick'em product.

HONEST OFFSEASON HANDLING: when the feed returns no events (NBA off-season, soccer
between tournaments) or no prop rows after parsing, fetch_props returns the
UNAVAILABLE sentinel with a clear reason. Never fabricate rows.

SPORTS WIRED (degraded gracefully during off-season):
  nba         -- NBA: league_id 42648, cat_id 1000  (Player Points / Rebounds / Assists)
  mlb         -- MLB: league_id 84240, cat_id 1000  (Hits / Strikeouts / etc.)
  soccer_intl -- Soccer / World Cup: league_id derived per tournament

No network at import. http_get is injectable; the default does keyless urllib GETs
with a browser UA + 12s timeout and returns {} on any error. fetch_props NEVER
raises -> returns UNAVAILABLE instead.

LOC discipline: <=300 LOC/file. ASCII only.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from .base import american_to_decimal, is_unavailable, unavailable
from .prop_base import PropLine, canon_stat

logger = logging.getLogger(__name__)

# DraftKings public sportsbook API (no auth required).
_DK_HOST = "https://sportsbook-us-il.draftkings.com"
_EVENTS_URL = (
    _DK_HOST + "/sites/US-IL-SB/api/2/categories/{league_id}/{cat_id}/subcategories"
    "?includeEventProps=false&format=json"
)
_OFFERS_URL = (
    _DK_HOST + "/sites/US-IL-SB/api/2/events/{event_id}/categories/{cat_id}"
    "/subcategories?format=json"
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# sport -> (league_id, player_prop_category_id)
# NBA off-season wired (returns empty -> UNAVAILABLE, not an error).
# Soccer / World Cup uses the FIFA international league id.
_SPORT_IDS: Dict[str, tuple] = {
    "nba": ("42648", "1000"),
    "mlb": ("84240", "1000"),
    "soccer_intl": ("3", "1000"),
}

# Maximum events to fetch per sport (keeps tests and live calls bounded).
_MAX_EVENTS = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_http_get(url: str) -> Dict[str, Any]:
    """One keyless GET; returns parsed JSON dict or {} on any error."""
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001 -- never bubble a network error
        logger.warning("draftkings GET failed %s: %s", url, exc)
        return {}


def _to_float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _dec_price(outcome: Dict[str, Any]) -> Optional[float]:
    """Decimal odds (> 1.0) from an outcome dict; falls back to American -> decimal.

    DraftKings exposes both oddsDecimal (string, e.g. "2.20") and oddsAmerican
    (string, e.g. "+120" or "-110"). We prefer oddsDecimal and convert only when
    that field is absent/invalid; neither path fabricates a price.
    """
    d = _to_float(outcome.get("oddsDecimal"))
    if d is not None and d > 1.0:
        return d
    am = outcome.get("oddsAmerican")
    if am is not None:
        return american_to_decimal(am)
    return None


def _match_title(event: Dict[str, Any]) -> Optional[str]:
    return event.get("name") or None


def _event_id_str(event: Dict[str, Any]) -> str:
    return str(event.get("eventId") or event.get("id") or "")


def parse_event_offers(
    offers_body: Dict[str, Any],
    sport: str,
    event: Dict[str, Any],
    as_of: str,
) -> List[PropLine]:
    """Parse one event's offers payload into PropLine rows (pure, no network).

    DraftKings event-offers payload shape:
      eventGroup.offerCategories[].offerSubcategory.offers[][]:
        each sub-list is one prop-market row (typically [over_outcome, under_outcome])
        outcome keys: label ("Over"/"Under"), oddsAmerican, oddsDecimal,
                      participant (player name), line (the numeric line).

    Returns [] when no prop rows can be parsed.
    """
    if not isinstance(offers_body, dict):
        return []
    eg = offers_body.get("eventGroup") or {}
    cats = eg.get("offerCategories") or []
    match = _match_title(event)
    eid = _event_id_str(event)

    out: List[PropLine] = []
    for cat in cats:
        if not isinstance(cat, dict):
            continue
        sub = cat.get("offerSubcategory") or {}
        sub_name = sub.get("name") or cat.get("name") or ""
        offers_list = sub.get("offers") or []
        for offer_row in offers_list:
            # Each offer_row is a list (one slot = one market/line).
            if not isinstance(offer_row, list):
                continue
            for offer in offer_row:
                if not isinstance(offer, dict):
                    continue
                outcomes = offer.get("outcomes") or []
                if not isinstance(outcomes, list) or len(outcomes) < 2:
                    continue  # need at least two sides (Over + Under)
                over_price = under_price = None
                player = None
                line_val = None
                for oc in outcomes:
                    if not isinstance(oc, dict):
                        continue
                    label = (oc.get("label") or "").strip().lower()
                    p = _dec_price(oc)
                    lv = _to_float(oc.get("line"))
                    if lv is not None:
                        line_val = lv
                    pname = (oc.get("participant") or "").strip()
                    if pname and not player:
                        player = pname
                    if label == "over":
                        over_price = p
                    elif label == "under":
                        under_price = p
                if line_val is None or player is None:
                    continue
                if over_price is None and under_price is None:
                    continue  # no usable price on either side
                # stat label: use the sub-category name (e.g. "Points O/U" ->
                # strip " O/U" / " Alternate" suffixes, then canon_stat.
                raw_stat = (sub_name
                            .replace(" O/U", "").replace(" Alternate", "")
                            .replace(" Alt", "").strip())
                if not raw_stat:
                    raw_stat = offer.get("label") or offer.get("betOfferTypeName") or ""
                stat = canon_stat(raw_stat) if raw_stat else "Unknown"
                out.append(PropLine(
                    sport=sport,
                    event_id=eid,
                    match=match,
                    player=player,
                    team=None,
                    stat=stat,
                    line=line_val,
                    over_price=over_price,
                    under_price=under_price,
                    payout_type="sportsbook",
                    source="draftkings",
                    as_of=as_of,
                ))
    return out


def parse_events(events_body: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract event dicts from a league-categories payload.

    Returns a list of raw event dicts (each carries at minimum eventId + name).
    An empty list means no events are posted (off-season / feed gap).
    """
    if not isinstance(events_body, dict):
        return []
    eg = events_body.get("eventGroup") or {}
    events = eg.get("events") or []
    return [e for e in events if isinstance(e, dict)]


class DraftKingsProvider:
    """Keyless DraftKings sportsbook prop provider.

    fetch_props(sport) -> list[PropLine] with payout_type="sportsbook"
                          or UNAVAILABLE sentinel when no lines are posted.

    NEVER raises. http_get is injectable so tests can run with zero network.
    """

    name = "draftkings"

    def __init__(
        self,
        *,
        http_get: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._http_get = http_get or _default_http_get

    def fetch_props(
        self, sport: str
    ) -> Union[List[PropLine], Dict[str, str]]:
        sport = (sport or "").lower()
        ids = _SPORT_IDS.get(sport)
        if ids is None:
            return unavailable("draftkings: unsupported sport '%s'" % sport)
        league_id, cat_id = ids
        as_of = _now_iso()
        try:
            events_body = self._http_get(
                _EVENTS_URL.format(league_id=league_id, cat_id=cat_id))
        except Exception as exc:  # noqa: BLE001 -- degrade, never raise
            logger.warning("draftkings events fetch failed: %s", exc)
            return unavailable(
                "draftkings: events call failed (%s)" % type(exc).__name__)
        if is_unavailable(events_body):
            return events_body
        if not isinstance(events_body, dict) or not events_body:
            return unavailable("draftkings: empty/invalid events response")
        events = parse_events(events_body)
        if not events:
            return unavailable(
                "draftkings: no events for sport '%s' (offseason?)" % sport)
        rows: List[PropLine] = []
        for ev in events[:_MAX_EVENTS]:
            eid = _event_id_str(ev)
            if not eid:
                continue
            try:
                offers_body = self._http_get(
                    _OFFERS_URL.format(event_id=eid, cat_id=cat_id))
            except Exception as exc:  # noqa: BLE001 -- skip one event, keep going
                logger.warning("draftkings offers fetch failed eid=%s: %s",
                               eid, exc)
                continue
            if is_unavailable(offers_body) or not isinstance(offers_body, dict):
                continue
            rows.extend(parse_event_offers(offers_body, sport, ev, as_of))
        if not rows:
            return unavailable(
                "draftkings: no prop rows for sport '%s'" % sport)
        return rows


__all__ = [
    "DraftKingsProvider",
    "parse_event_offers",
    "parse_events",
]
