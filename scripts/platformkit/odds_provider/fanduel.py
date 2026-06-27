"""scripts.platformkit.odds_provider.fanduel -- keyless FanDuel sportsbook moneyline.

FanDuel is a SOFT book: its price often diverges from the sharp (Pinnacle) line, so
adding it to the slate is what makes line-shopping +CLV possible (best_price /
clv.best_price_audit). The keyless sources we already had (ESPN republishes one book
= DraftKings; Pinnacle) are BOTH sharp -> no dispersion -> no edge.

Source: FanDuel's own web frontend public JSON (content-managed-page) with the
public ``_ak`` site key (visible in the site bundle -- not a secret, no auth). We
read the republished MONEY_LINE market; we do NOT place or scrape behind a login.

Endpoint -> attachments.{events, markets}; a MONEY_LINE market carries two runners
(the teams) with decimal odds; the event name is "Away (pitcher) @ Home (pitcher)"
so home is the side after " @ ". A side we cannot read is omitted, never guessed.

Robust by construction: browser UA + Referer (the API 403s without them), 12s
timeout, {} on any error -> fetch() returns UNAVAILABLE. No network at import.
http_get is injectable for offline tests. ASCII, <=300 LOC.

Per-file test: scripts/platformkit/odds_provider/test_fanduel.py
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Union

from scripts.platformkit.odds_provider.base import (
    OddsEvent, american_to_decimal, unavailable)

logger = logging.getLogger(__name__)

_AK = "FhMFpcPWXMeyZxOx"  # public site key from FanDuel's web bundle (not a secret)
_REGION = "nj"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# sport key -> FanDuel customPageId.
_PAGE: Dict[str, str] = {"mlb": "mlb", "nba": "nba", "nhl": "nhl", "nfl": "nfl"}


def _url(page_id: str) -> str:
    return ("https://sbapi.%s.sportsbook.fanduel.com/api/content-managed-page"
            "?page=CUSTOM&customPageId=%s&pbHorizontal=false&_ak=%s"
            "&timezone=America%%2FNew_York" % (_REGION, page_id, _AK))


def _default_http_get(url: str) -> Dict[str, Any]:
    """Keyless GET with the headers FanDuel requires; {} on any error."""
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA, "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://sportsbook.fanduel.com/"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8", "ignore"))
    except Exception as exc:  # noqa: BLE001 -- a dead source is UNAVAILABLE, not a crash
        logger.warning("fanduel GET failed %s: %s", url, type(exc).__name__)
        return {}


def _runner_decimal(runner: Dict[str, Any]) -> Optional[float]:
    """Decimal odds from a FanDuel runner (true decimal, else american)."""
    wro = runner.get("winRunnerOdds") or {}
    true = (((wro.get("trueOdds") or {}).get("decimalOdds") or {})
            .get("decimalOdds"))
    if isinstance(true, (int, float)) and true > 1.0:
        return float(true)
    amer = (wro.get("americanDisplayOdds") or {}).get("americanOddsInt")
    return american_to_decimal(amer)


def _split_event_name(name: str) -> Optional[tuple]:
    """'Away (P) @ Home (P)' -> (away_team, home_team), stripping pitcher parens."""
    if not name or " @ " not in name:
        return None
    away_raw, home_raw = name.split(" @ ", 1)

    def _clean(s: str) -> str:
        i = s.find(" (")
        return (s[:i] if i != -1 else s).strip()

    away, home = _clean(away_raw), _clean(home_raw)
    if not away or not home:
        return None
    return away, home


def parse_moneylines(payload: Dict[str, Any], sport: str) -> List[OddsEvent]:
    """MONEY_LINE markets in a content-managed-page payload -> OddsEvent list.

    A market we cannot fully read (missing team/odds) is skipped, never half-filled."""
    att = payload.get("attachments") or {}
    events = att.get("events") or {}
    markets = att.get("markets") or {}
    out: List[OddsEvent] = []
    for m in markets.values():
        if m.get("marketType") != "MONEY_LINE":
            continue
        eid = str(m.get("eventId"))
        ev = events.get(eid) or {}
        teams = _split_event_name(str(ev.get("name") or ""))
        if not teams:
            continue
        away, home = teams
        prices: Dict[str, Optional[float]] = {}
        for ru in m.get("runners") or []:
            rn = str(ru.get("runnerName") or "")
            dec = _runner_decimal(ru)
            if dec is None:
                continue
            if rn == home:
                prices["home"] = round(dec, 6)
            elif rn == away:
                prices["away"] = round(dec, 6)
        if "home" not in prices or "away" not in prices:
            continue  # never half-fill a two-way price
        out.append(OddsEvent(
            event_id="fd:%s" % eid, sport=sport, home=home, away=away,
            commence_time=ev.get("openDate"),
            prices={"fanduel": prices}, source="fanduel"))
    return out


class FanDuelProvider:
    """Keyless FanDuel moneyline provider. fetch(sport) -> list[OddsEvent] | UNAVAILABLE."""

    name = "fanduel"

    def __init__(self, *, http_get: Optional[Callable[[str], Dict[str, Any]]] = None,
                 use_cache: bool = True) -> None:
        self._http_get = http_get or _default_http_get
        self._use_cache = use_cache  # accepted for parity; GET already short + cached upstream

    def fetch(self, sport: str) -> Union[List[OddsEvent], Dict[str, str]]:
        sport = sport.lower()
        page = _PAGE.get(sport)
        if page is None:
            return unavailable("fanduel: unsupported sport '%s'" % sport)
        payload = self._http_get(_url(page))
        if not payload:
            return unavailable("fanduel: no payload (blocked/empty)")
        events = parse_moneylines(payload, sport)
        if not events:
            return unavailable("fanduel: no moneyline markets")
        return events


__all__ = ["FanDuelProvider", "parse_moneylines"]
