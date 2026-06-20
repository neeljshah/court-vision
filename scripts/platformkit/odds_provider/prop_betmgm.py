"""scripts.platformkit.odds_provider.prop_betmgm -- keyless BetMGM props.

BetMGM exposes player-prop markets via its public CDS API (no auth required).
One competition-level fixtures call returns all scheduled events with their
optionMarkets (prop markets) embedded.

REAL API shape (probed via Playwright R18 intercept 2026-06-18):
  GET /cds-api/bettingoffer/fixtures?...&competitionIds={cid}
    -> fixtures[]: {id, name:{value:"Team A @ Team B"}, startDate,
         optionMarkets[]: {id, name:{value:"Player Name Points"},
           options[]: {name:{value:"Over"|"Under"}, attr:"<line>",
                       price:{americanOdds:<int>}}}}

Pricing: TWO-WAY American integer odds per option (price.americanOdds),
converted via american_to_decimal -> payout_type "sportsbook".

HONEST WAF HANDLING: BetMGM's CDS API returns 403 from non-browser TLS
(datacenter IPs). fetch_props degrades to UNAVAILABLE on empty/error.
Empty fixture list -> UNAVAILABLE (offseason/WAF honest). Never fabricates.

No network at import. http_get is injectable; the default does keyless urllib GETs
with a browser UA + 12s timeout and returns {} on any error. fetch_props NEVER
raises -> returns the UNAVAILABLE sentinel instead.

LOC discipline: <=300 LOC. ASCII only. No $ field.
Per-file test:
  python -m pytest scripts/platformkit/odds_provider/test_prop_betmgm.py -q
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from .base import american_to_decimal, is_unavailable, unavailable
from .prop_base import PropLine, canon_stat

logger = logging.getLogger(__name__)

# BetMGM CDS-API: NJ subdomain + accessId (publicly embedded in every page load;
# not a secret -- rotates slowly, keyless in the same sense as FanDuel's _ak).
_MGM_HOST = "https://sports.nj.betmgm.com"
_ACCESS_ID = "NDgwODYwLTk2NTktMTI4ODEz"  # publicly visible app key, not a secret
_FIXTURES_URL = (
    _MGM_HOST + "/cds-api/bettingoffer/fixtures"
    "?x-bwin-accessId=" + _ACCESS_ID
    + "&lang=en-us&country=US&userCountry=US&offerMapping=Filtered"
    + "&scoreboardMode=Full&fixtureTypes=Standard"
    + "&state=Live%2CLatest%2CUpcoming&competitionIds={cid}"
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# sport key -> BetMGM competition id.
# NBA = 6004, MLB = 6003, Soccer World Cup = approximated; extend as needed.
_SPORT_CID: Dict[str, str] = {
    "nba": "6004",
    "mlb": "6003",
    "soccer_intl": "5",
}

# Maximum number of fixtures to process per call (keeps tests + live bounded).
_MAX_FIXTURES = 15

# Stat fragments for player-prop market name recognition.
# BetMGM market names: "Jayson Tatum - Player Points", "LeBron Rebounds", etc.
_STAT_FRAGMENTS = (
    ("points", "Points"),
    ("rebounds", "Rebounds"),
    ("assists", "Assists"),
    ("threes", "3-Pointers Made"),
    ("three pointers", "3-Pointers Made"),
    ("3-pointers", "3-Pointers Made"),
    ("steals", "Steals"),
    ("blocks", "Blocks"),
    ("turnovers", "Turnovers"),
    # Soccer props
    ("shots on target", "Shots On Target"),
    ("shots", "Shots"),
    ("saves", "Saves"),
    ("goals", "Goals"),
)

# Strip trailing stat phrase to isolate the player name.
_STAT_TAIL_RE = re.compile(
    r"\s*[-\u2013]\s*(player\s+)?(points|rebounds|assists|threes|three pointers"
    r"|3-pointers|steals|blocks|turnovers|shots on target|shots|saves|goals).*$",
    re.IGNORECASE,
)

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_http_get(url: str) -> Dict[str, Any]:
    """One keyless GET; returns parsed JSON dict or {} on any error."""
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("betmgm GET failed %s: %s", url, exc)
        return {}


def _to_float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _str_val(obj: Any) -> str:
    """String from a BetMGM localised-name object ({value:...}) or plain str."""
    if isinstance(obj, dict):
        return str(obj.get("value") or obj.get("en") or obj.get("short") or "")
    return str(obj or "")


def _label_to_canonical(m_name: str) -> Optional[str]:
    """Map a BetMGM market name to a canonical stat.

    Market names take forms like 'Jayson Tatum - Player Points' or
    'Player Rebounds - LeBron James'. We scan for a known stat fragment
    and return the canonical name; None for non-player-prop markets.
    """
    low = m_name.lower()
    for frag, canonical in _STAT_FRAGMENTS:
        if frag in low:
            return canon_stat(canonical)
    return None


def _player_from_market_name(m_name: str) -> Optional[str]:
    """Strip the stat phrase to isolate the player name.

    'Jayson Tatum - Player Points' -> 'Jayson Tatum'
    'Player Rebounds - LeBron James' -> 'LeBron James'
    Returns None when no clear player token remains.
    """
    stripped = _STAT_TAIL_RE.sub("", m_name).strip()
    # Remove leading "Player " prefix when the name-first variant is used.
    if stripped.lower().startswith("player "):
        stripped = stripped[7:].strip()
    return stripped if stripped else None


def parse_fixtures(body: Dict[str, Any], sport: str) -> List[PropLine]:
    """Parse a BetMGM fixtures response into player-prop PropLine rows (pure).

    BetMGM fixtures shape:
      body["fixtures"] -> list of event dicts
      event: {id, name: {value: "Team A @ Team B"}, startDate,
               optionMarkets: [{id, name: {value: "...Points"}, options: [...]}]}
      option: {name: {value: "Over"|"Under"}, attr: "<line>", price: {americanOdds: N}}

    Returns [] when no player-prop rows can be parsed.
    """
    if not isinstance(body, dict):
        return []
    fixtures = body.get("fixtures") or body.get("games") or []
    if isinstance(body, list):  # some feeds return the array at top level
        fixtures = body
    if not isinstance(fixtures, list):
        return []

    as_of = _now_iso()
    out: List[PropLine] = []

    for ev in fixtures[:_MAX_FIXTURES]:
        if not isinstance(ev, dict):
            continue
        ev_id = str(ev.get("id") or ev.get("fixtureId") or "")
        ev_name = _str_val(ev.get("name") or "")
        # Only include matchup events (contain "@" or "vs")
        if "@" not in ev_name and " vs " not in ev_name.lower():
            continue

        markets = ev.get("optionMarkets") or ev.get("markets") or []
        if not isinstance(markets, list):
            continue

        for mkt in markets:
            if not isinstance(mkt, dict):
                continue
            m_name = _str_val(mkt.get("name") or "")
            stat = _label_to_canonical(m_name)
            if stat is None:
                continue
            player = _player_from_market_name(m_name)
            if not player:
                continue

            options = mkt.get("options") or mkt.get("selections") or []
            if not isinstance(options, list):
                continue

            # Group by line value; each line may have Over + Under sides.
            by_line: Dict[float, Dict[str, Optional[float]]] = {}
            for opt in options:
                if not isinstance(opt, dict):
                    continue
                label = _str_val(opt.get("name") or "").strip().lower()
                line_val = _to_float(
                    opt.get("attr") or opt.get("handicap") or opt.get("line"))
                # price: {americanOdds: int} or americanOdds at top level
                price_obj = opt.get("price") or {}
                am = (price_obj.get("americanOdds") if isinstance(price_obj, dict)
                      else opt.get("americanOdds"))
                dec = american_to_decimal(am) if am is not None else None
                if line_val is None or dec is None:
                    continue
                sides = by_line.setdefault(line_val, {"over": None, "under": None})
                if label.startswith("o") or label == "yes":
                    if dec > 1.0:
                        sides["over"] = dec
                elif label.startswith("u") or label == "no":
                    if dec > 1.0:
                        sides["under"] = dec

            for line_val, sides in by_line.items():
                if sides["over"] is None and sides["under"] is None:
                    continue
                out.append(PropLine(
                    sport=sport,
                    event_id=ev_id,
                    match=ev_name or None,
                    player=player,
                    team=None,
                    stat=stat,
                    line=line_val,
                    over_price=sides["over"],
                    under_price=sides["under"],
                    payout_type="sportsbook",
                    source="betmgm",
                    as_of=as_of,
                ))
    return out


class BetMGMProvider:
    """Keyless BetMGM sportsbook prop provider.

    fetch_props(sport) -> list[PropLine] with payout_type="sportsbook"
                          or UNAVAILABLE sentinel when the WAF blocks / no
                          lines are posted (offseason).

    NEVER raises. http_get is injectable so tests run with zero network.
    """

    name = "betmgm"

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
        cid = _SPORT_CID.get(sport)
        if cid is None:
            return unavailable("betmgm: unsupported sport '%s'" % sport)
        url = _FIXTURES_URL.format(cid=cid)
        try:
            body = self._http_get(url)
        except Exception as exc:  # noqa: BLE001 -- degrade, never raise
            logger.warning("betmgm fixtures fetch failed: %s", exc)
            return unavailable(
                "betmgm: fixtures call failed (%s)" % type(exc).__name__)
        if is_unavailable(body):
            return body
        if not isinstance(body, dict) or not body:
            return unavailable("betmgm: empty/invalid fixtures response")
        fixtures = body.get("fixtures") or body.get("games") or []
        if not fixtures:
            return unavailable(
                "betmgm: no fixtures for sport '%s' (offseason or WAF block)"
                % sport)
        rows = parse_fixtures(body, sport)
        if not rows:
            return unavailable(
                "betmgm: no player-prop markets posted for sport '%s'" % sport)
        return rows


__all__ = [
    "BetMGMProvider",
    "parse_fixtures",
]
