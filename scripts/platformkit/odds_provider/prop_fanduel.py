"""scripts.platformkit.odds_provider.prop_fanduel -- keyless FanDuel props.

FanDuel's NJ sportsbook API is reachable keyless via a STATIC public app key
(_ak). The navigation is: a content-managed page lists World Cup events, then an
event-page exposes that event's markets, including player-prop markets when posted.

REAL shapes (probed 2026-06-17):
  content-managed-page?page=CUSTOM&customPageId=fifa-world-cup&_ak=<key>
     -> attachments.events{ eventId -> {name "Team v Team", openDate, eventTypeId} }
  event-page?eventId=<id>&_ak=<key>
     -> layout.tabs{ tabId -> {title} }  (e.g. "Shots", "Saves", "Assists",
        "Cards + Fouls", "Shots on Target" -- these ARE the player-prop categories)
     -> attachments.markets{ marketId -> {marketName, bettingType, runners[]} }
        runner: {runnerName, handicap, winRunnerOdds.americanDisplayOdds.americanOdds}

Pricing: FanDuel posts TWO-WAY AMERICAN odds per runner. We convert each runner's
americanOdds via american_to_decimal and emit payout_type "sportsbook". An O/U
player-prop market has two runners ("Over"/"Under") sharing one handicap (the line);
a "to score / X+ shots" market is one-sided -> we record the side we see honestly.

HOW FAR WE GOT (honest): as of the probe the World Cup is ~2 weeks out and FanDuel
has NOT yet posted any player-prop markets for these events -- each event-page
returned only Moneyline + Penalty markets (the prop TABS exist but carry no markets
yet). So the player-prop PARSER below is written against the REAL market/runner
shape observed on the live moneyline markets, and the live path DEGRADES to
unavailable("no player-prop markets") when no prop market is present. We do NOT
fabricate prop rows. When FanDuel opens props the same parser consumes them.

No network at import. http_get is injectable; the default does keyless urllib GETs
with a browser UA + 12s timeout and returns {} on any error. fetch_props NEVER
raises -> returns the UNAVAILABLE sentinel instead.
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

_AK = "FhMFpcPWXMeyZxOx"  # static public app key (keyless; not a secret)
_HOST = "https://sbapi.nj.sportsbook.fanduel.com/api"
_PAGE_URL = (_HOST + "/content-managed-page?page=CUSTOM&customPageId={pid}"
             "&_ak=" + _AK + "&timezone=America%2FNew_York")
_EVENT_URL = _HOST + "/event-page?_ak=" + _AK + "&eventId={eid}"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# Our sport key -> FanDuel customPageId.
_PAGE_ID: Dict[str, str] = {"soccer_intl": "fifa-world-cup"}

# Market-name fragments that identify a PLAYER prop (vs team/match markets). The
# market title carries the stat; the runner carries Over/Under + the line.
_PLAYER_STATS = (
    "shots on target", "shots", "saves", "tackles", "assists", "passes",
    "fouls", "cards", "offsides", "clearances", "crosses",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_http_get(url: str) -> Dict[str, Any]:
    """One keyless GET with a browser UA; returns parsed JSON or {} on any error."""
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001 -- never bubble a network error
        logger.warning("fanduel GET failed: %s", exc)
        return {}


def _to_float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _runner_decimal(runner: Dict[str, Any]) -> Optional[float]:
    """Decimal odds from a runner's americanDisplayOdds.americanOdds (or None)."""
    am = ((runner.get("winRunnerOdds") or {}).get("americanDisplayOdds") or {}
          ).get("americanOdds")
    return american_to_decimal(am) if am is not None else None


def _split_stat(market_name: str) -> Optional[str]:
    """Return the canonical stat if *market_name* names a known player prop, else None.

    FanDuel prop titles look like 'Player Shots on Target' / 'Player - Total Shots'.
    We match on a known stat fragment so team/match markets are skipped.
    """
    low = market_name.lower()
    for frag in _PLAYER_STATS:
        if frag in low:
            return canon_stat(frag)
    return None


def parse_event_props(event_body: Dict[str, Any], sport: str,
                      ) -> List[PropLine]:
    """Parse one event-page payload into player-prop PropLine rows (pure).

    Recognizes Over/Under prop markets (two runners sharing a handicap line) and
    prices each side from its American odds. Returns [] when the event carries no
    player-prop markets (the current live state) -- the caller turns [] into an
    honest unavailable sentinel.
    """
    if not isinstance(event_body, dict):
        return []
    att = event_body.get("attachments") or {}
    markets = att.get("markets") or {}
    events = att.get("events") or {}
    ev = next(iter(events.values()), {}) if isinstance(events, dict) else {}
    match = ev.get("name")
    as_of = _now_iso()

    out: List[PropLine] = []
    if not isinstance(markets, dict):
        return out
    for mid, mk in markets.items():
        if not isinstance(mk, dict):
            continue
        stat = _split_stat(mk.get("marketName") or "")
        if stat is None:
            continue
        runners = mk.get("runners") or []
        # O/U prop: pair an "Over"/"Under" runner sharing the handicap line.
        over = under = None
        line_val = None
        player = None
        for r in runners:
            if not isinstance(r, dict):
                continue
            rname = (r.get("runnerName") or "").strip()
            hcap = _to_float(r.get("handicap"))
            if hcap is not None and hcap != 0.0:
                line_val = hcap
            low = rname.lower()
            if low.startswith("over") or low.endswith("over"):
                over = _runner_decimal(r)
            elif low.startswith("under") or low.endswith("under"):
                under = _runner_decimal(r)
            else:
                player = rname  # player-named runner (e.g. anytime / X+ markets)
        if line_val is None or (over is None and under is None):
            continue
        out.append(PropLine(
            sport=sport,
            event_id=str(mk.get("eventId") or mid or ""),
            match=match,
            player=player or (mk.get("marketName") or "").strip(),
            team=None,
            stat=stat,
            line=line_val,
            over_price=over,
            under_price=under,
            payout_type="sportsbook",
            source="fanduel",
            as_of=as_of,
        ))
    return out


def list_event_ids(page_body: Dict[str, Any]) -> List[str]:
    """Extract real match eventIds (name 'A v B') from a content-managed page."""
    if not isinstance(page_body, dict):
        return []
    events = (page_body.get("attachments") or {}).get("events") or {}
    if not isinstance(events, dict):
        return []
    out: List[str] = []
    for eid, ev in events.items():
        nm = (ev or {}).get("name") or ""
        if " v " in nm or " @ " in nm:
            out.append(str(eid))
    return out


class FanDuelProvider:
    """Keyless FanDuel prop provider. fetch_props -> list[PropLine]|UNAVAILABLE."""

    name = "fanduel"

    def __init__(self, *, http_get: Optional[Callable[[str], Any]] = None,
                 use_cache: bool = False) -> None:
        self._http_get = http_get or _default_http_get
        self._use_cache = use_cache  # reserved; live fetch is light + keyless

    def fetch_props(self, sport: str,
                    ) -> Union[List[PropLine], Dict[str, str]]:
        sport = (sport or "").lower()
        page_id = _PAGE_ID.get(sport)
        if not page_id:
            return unavailable("fanduel: unsupported sport '%s'" % sport)
        try:
            page = self._http_get(_PAGE_URL.format(pid=page_id))
            if is_unavailable(page):
                return page
            event_ids = list_event_ids(page)
            if not event_ids:
                return unavailable("fanduel: no World Cup events listed")
            rows: List[PropLine] = []
            for eid in event_ids:
                body = self._http_get(_EVENT_URL.format(eid=eid))
                if is_unavailable(body):
                    continue
                rows.extend(parse_event_props(body, sport))
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("fanduel fetch failed: %s", exc)
            return unavailable("fanduel call failed (%s)" % type(exc).__name__)
        if not rows:
            return unavailable("fanduel: no player-prop markets posted")
        return rows


__all__ = ["FanDuelProvider", "parse_event_props", "list_event_ids"]
