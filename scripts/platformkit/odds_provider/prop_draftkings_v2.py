"""scripts.platformkit.odds_provider.prop_draftkings_v2 -- working DK prop adapter.

The legacy prop_draftkings module targets the dead
  sportsbook-us-il.draftkings.com/sites/US-IL-SB/api/2/categories/{league}/{cat}
URL pattern, which now returns Akamai 404/403 from every endpoint. This
adapter switches to the live DK SportContent API that the existing
scripts/draftkings_scraper.py proved works:

    https://sportsbook-nash.draftkings.com/api/sportscontent/dkusil/v1
        /leagues/{league_id}/categories/{cat_id}

returning a flat payload with `events[]`, `markets[]`, `selections[]`,
`subcategories[]`. Each market has an `eventId`, `name` shaped as
"{Player} {Stat}" (e.g. "Yordan Alvarez Home Runs"), and selections linked
by `marketId` with `label` ("Over 0.5") + `displayOdds.american` ("+150").

Requests use `curl_cffi.requests` with `impersonate="chrome120"` to pass
Akamai's TLS-fingerprint check; an injectable `http_get` makes tests fully
offline.

CONTRACT
--------
  * fetch_props(sport) -> list[PropLine] (payout_type="sportsbook") or the
    UNAVAILABLE sentinel. NEVER raises; NEVER fabricates a price.
  * Only sports with a known (league_id, [category_id...]) mapping are wired.
    Soccer / NBA can be added once their live league_ids land in _SPORT_IDS.

RAILS: scripts/platformkit only; ASCII; <=300 LOC; no $-edge claim; no flag
flip. Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/odds_provider/test_prop_draftkings_v2.py -q
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from .base import is_unavailable, unavailable
from .prop_base import PropLine, canon_stat

logger = logging.getLogger(__name__)

_BASE = "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusil/v1"
_URL = _BASE + "/leagues/{league_id}/categories/{cat_id}/subcategories/{sub_id}"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS: Dict[str, str] = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://sportsbook.draftkings.com/",
    "Origin": "https://sportsbook.draftkings.com",
    "User-Agent": _UA,
}

# sport -> (league_id, [(cat_id, sub_id, canon_stat) ...]).
# Each subcategory is its own fetch -> O/U markets only (not milestone "1+"
# markets, which are single-sided). Probed live 2026-06-23 on MLB league 84240:
# market name format is "{Player} {Stat} O/U"; selection label = "Over" /
# "Under" with `points` carrying the line and displayOdds.decimal the price.
_SPORT_IDS: Dict[str, tuple] = {
    "mlb": ("84240", (
        (743,   6719, "Hits"),               # Hits O/U (batter)
        (743,   6607, "Total Bases"),         # Total Bases O/U
        (743,   8025, "RBIs"),                # RBIs O/U
        (743,  17407, "Runs"),                # Runs O/U
        (743,  17408, "Stolen Bases"),        # Stolen Bases O/U
        (743,  17411, "Walks"),               # Walks (Batter) O/U
        (1031, 15221, "Strikeouts"),          # Strikeouts Thrown O/U (pitcher)
        (1031, 15219, "Walks Allowed"),       # Walks Allowed O/U
        (1031,  9886, "Hits Allowed"),        # Hits Allowed O/U
        (1031, 17412, "Earned Runs"),         # Earned Runs Allowed O/U
        (1031, 17413, "Pitching Outs"),       # Outs Recorded O/U
    )),
}

# Stat-suffix vocabulary for trimming the " O/U" trailing tag from market names
# ("Yordan Alvarez Hits O/U" -> player="Yordan Alvarez"). Longer suffixes first
# so a stat like "Total Bases" isn't shadowed by a shorter "Bases".
_OU_TAG = " O/U"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_http_get(url: str) -> Dict[str, Any]:
    """Live GET via curl_cffi (Chrome TLS fingerprint) -> parsed JSON dict.

    Falls back to urllib when curl_cffi is unavailable so unit tests that
    inject a fake http_get NEVER need the optional dep. Any network error
    returns {} -- the adapter then degrades to UNAVAILABLE.
    """
    try:
        from curl_cffi import requests as _cf  # noqa: PLC0415
        r = _cf.get(url, headers=_HEADERS, impersonate="chrome120", timeout=12)
        if r.status_code != 200:
            logger.warning("draftkings_v2 non-200 %s: %d", url, r.status_code)
            return {}
        try:
            return r.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("draftkings_v2 json parse failed %s: %s", url, exc)
            return {}
    except ImportError:
        pass  # fall through to urllib (will hit Akamai 403 in live; OK for tests)
    except Exception as exc:  # noqa: BLE001 -- never bubble network errors
        logger.warning("draftkings_v2 curl_cffi failed %s: %s", url, exc)
        return {}
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, Exception) as exc:  # noqa: BLE001
        logger.warning("draftkings_v2 urllib fallback failed %s: %s", url, exc)
        return {}


def _to_float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _american_to_decimal(american: Any) -> Optional[float]:
    """+150 -> 2.50; -110 -> 1.9091. None on bad input. DK uses U+2212 for minus."""
    if american is None:
        return None
    s = str(american).replace("−", "-").replace("+", "").strip()
    try:
        n = int(s)
    except (TypeError, ValueError):
        return None
    if n > 0:
        return round(1.0 + n / 100.0, 6)
    if n < 0:
        return round(1.0 + 100.0 / abs(n), 6)
    return None


def _strip_ou_tag(market_name: str, stat: str) -> Optional[str]:
    """Extract player from 'Yordan Alvarez Hits O/U' given canon stat 'Hits'.
    Returns the player substring, or None when the name does not end with
    ' {stat} O/U' / ' {stat}' (defensive -- never a guessed player)."""
    name = str(market_name or "").strip()
    if not name:
        return None
    # Trim a trailing ' O/U' tag if present.
    if name.endswith(_OU_TAG):
        name = name[: -len(_OU_TAG)].rstrip()
    # Then trim a trailing ' {stat}' so what remains is the player.
    suf = " " + stat
    if not name.endswith(suf):
        return None
    return name[: -len(suf)].strip() or None


def _label_side(label: Any) -> Optional[str]:
    """'Over' -> 'over'; 'Under' -> 'under'; else None."""
    s = str(label or "").strip().lower()
    return s if s in ("over", "under") else None


def _selection_decimal(sel: Dict[str, Any]) -> Optional[float]:
    """Decimal odds from a DK selection (oddsDecimal preferred, american fallback)."""
    if not isinstance(sel, dict):
        return None
    do = sel.get("displayOdds") or {}
    d = _to_float(do.get("decimal"))
    if d is None:
        d = _to_float(sel.get("oddsDecimal"))
    if d is not None and d > 1.0:
        return d
    am = (do.get("american") if isinstance(do, dict) else None) \
        or sel.get("oddsAmerican")
    return _american_to_decimal(am)


def parse_subcategory_payload(body: Dict[str, Any], sport: str, stat: str,
                              as_of: str) -> List[PropLine]:
    """Parse one /categories/{cat}/subcategories/{sub} payload into PropLines.

    Pure; no network. Walks markets[] (each = one player O/U on the SAME stat),
    pairs Over+Under selections by marketId + line (`points`), joins event name
    via events[]. Markets whose name does not strip into a player given the
    canonical *stat* are skipped (never a guessed player). A market with no
    usable price on either side is dropped (no fabricated decimal).
    """
    if not isinstance(body, dict):
        return []
    events = {str(e.get("id") or ""): e
              for e in (body.get("events") or []) if isinstance(e, dict)}
    sel_by_market: Dict[str, List[Dict[str, Any]]] = {}
    for s in body.get("selections") or []:
        if not isinstance(s, dict):
            continue
        mid = str(s.get("marketId") or "")
        if mid:
            sel_by_market.setdefault(mid, []).append(s)
    canon = canon_stat(stat) or stat
    out: List[PropLine] = []
    for m in body.get("markets") or []:
        if not isinstance(m, dict):
            continue
        player = _strip_ou_tag(m.get("name") or "", stat)
        if not player:
            continue
        eid = str(m.get("eventId") or "")
        event = events.get(eid, {})
        match = event.get("name")
        sels = sel_by_market.get(str(m.get("id") or ""), [])
        # Group selections per LINE (a single market can carry multiple O/U lines).
        per_line: Dict[float, Dict[str, float]] = {}
        for sel in sels:
            side = _label_side(sel.get("label"))
            if side is None:
                continue
            line_val = _to_float(sel.get("points"))
            if line_val is None:
                continue
            dec = _selection_decimal(sel)
            if dec is None:
                continue
            slot = per_line.setdefault(line_val, {})
            # Tie-break: keep the better decimal if a duplicate side appears.
            prev = slot.get(side)
            if prev is None or dec > prev:
                slot[side] = dec
        for line_val, sides in per_line.items():
            over_price = sides.get("over")
            under_price = sides.get("under")
            if over_price is None and under_price is None:
                continue
            out.append(PropLine(
                sport=sport, event_id=eid, match=match,
                player=player, team=None, stat=canon, line=line_val,
                over_price=over_price, under_price=under_price,
                payout_type="sportsbook", source="draftkings",
                as_of=as_of,
            ))
    return out


class DraftKingsV2Provider:
    """Working DraftKings prop provider on the sportscontent/dkusil/v1 endpoint.

    fetch_props(sport) -> list[PropLine] | UNAVAILABLE. Never raises. http_get
    is injectable so tests run with zero network.
    """

    name = "draftkings"

    def __init__(self, *, http_get: Optional[Callable[[str], Any]] = None) -> None:
        self._http_get = http_get or _default_http_get

    def fetch_props(self, sport: str) -> Union[List[PropLine], Dict[str, str]]:
        sp = (sport or "").lower()
        ids = _SPORT_IDS.get(sp)
        if ids is None:
            return unavailable("draftkings: unsupported sport '%s'" % sp)
        league_id, subcats = ids
        as_of = _now_iso()
        rows: List[PropLine] = []
        any_ok = False
        for cat_id, sub_id, stat in subcats:
            url = _URL.format(league_id=league_id, cat_id=cat_id, sub_id=sub_id)
            try:
                body = self._http_get(url)
            except Exception as exc:  # noqa: BLE001 -- never bubble
                logger.warning("draftkings_v2 cat/sub %s/%s fetch failed: %s",
                               cat_id, sub_id, exc)
                continue
            if is_unavailable(body):
                continue
            if not isinstance(body, dict) or not body:
                continue
            any_ok = True
            rows.extend(parse_subcategory_payload(body, sp, stat, as_of))
        if not any_ok:
            return unavailable(
                "draftkings: all subcategories failed for sport '%s'" % sp)
        return rows


__all__ = ["DraftKingsV2Provider", "parse_subcategory_payload"]
