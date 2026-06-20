"""scripts.platformkit.odds_provider.aggregate -- merge providers into one slate.

Runs each Provider, merges their OddsEvents per game (matched by normalized team
names, time-tolerant), and produces a per-event multi-venue price dict shaped
EXACTLY for odds_shop.summarise_twoway: {venue: {side: decimal}}. `to_odds_lookup`
returns a callable shaped like slate.build_slate's odds_lookup(sport, home, away)
seam so the aggregator drops straight into the existing front end.

A provider that returns UNAVAILABLE is recorded in `sources` and otherwise
ignored -- the merge proceeds with whatever venues ARE up. No fabricated prices.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .base import OddsEvent, is_unavailable
from .espn import EspnProvider
from .kalshi import KalshiProvider
from .pinnacle import PinnacleProvider
from .polymarket import PolymarketProvider
from .team_resolver import canonical

logger = logging.getLogger(__name__)

_TEAM_STOP = {"the", "fc", "afc", "cf", "sc"}


def _resolved_code_key(sport: Optional[str], name: str) -> Optional[str]:
    """canonical(sport,name) IFF it resolved a real code/nickname for a coded
    sport (nba/mlb); else None. A None means 'fall back to strict name match'.

    canonical's fallback returns "<sport>:<last-token>", which for a coded sport
    is only trustworthy when that token is a KNOWN nickname -- exactly what
    canonical returns from its code-map branches. We re-detect that here by
    checking the key's nickname is in the sport's known nickname set.
    """
    if not sport:
        return None
    sp = sport.lower()
    from .team_resolver import _CODE_TO_NICK  # local: static reference maps
    nicks = _CODE_TO_NICK.get(sp)
    if nicks is None:  # soccer/tennis/etc: no codes -> keep strict name match
        return None
    key = canonical(sp, name)
    return key if key.split(":", 1)[1] in set(nicks.values()) else None


def normalize_team(name: str) -> str:
    """Lowercase, strip punctuation/stopwords -> a loose team-match key.

    'San Antonio Spurs' -> 'san antonio spurs'; 'Man City' ~ 'manchester city'
    is NOT solved here (we match on shared significant tokens in match_key).
    """
    s = re.sub(r"[^a-z0-9 ]", " ", str(name).lower())
    toks = [t for t in s.split() if t and t not in _TEAM_STOP]
    return " ".join(toks)


def _tokens(name: str) -> set:
    return set(normalize_team(name).split())


def teams_match(a: str, b: str, sport: Optional[str] = None) -> bool:
    """True if two team names refer to the same team -- STRICT, to avoid attaching
    the WRONG game's odds. Biased to false negatives (no odds) over false positives
    (wrong price): a same-city different-team pair like 'New York Knicks' vs 'New
    York Yankees' must NOT match.

    Code<->name resolver (NBA/MLB): when *sport* is given and BOTH sides resolve
    to a known team code/nickname, compare their canonical keys -- so 'BOS' links
    to 'Boston Celtics' (nba) and 'CIN' to 'Cincinnati Reds' (mlb), while two
    different teams (CWS White Sox vs CHC Cubs; Knicks vs Nets) get distinct keys
    and still do NOT match. If either side does NOT confidently resolve (soccer/
    tennis, or an unknown team) we fall through to the strict name rule below.

    Name rule: exact normalized match, OR the distinctive NICKNAME (last token)
    agrees AND the token sets are subset-related or strongly overlap (Jaccard >=
    0.5). 'Spurs' vs 'San Antonio Spurs' -> match (subset); 'Boston Red Sox' vs
    'Chicago White Sox' -> NO match (Jaccard 0.2); 'Knicks' vs 'Yankees' -> NO
    match. Aliases like 'Man City'/'Manchester City' may miss (show no odds) --
    an honest degrade, never a wrong price.
    """
    ka, kb = _resolved_code_key(sport, a), _resolved_code_key(sport, b)
    if ka is not None and kb is not None:
        return ka == kb  # both confidently resolved -> trust canonical keys
    na, nb = normalize_team(a), normalize_team(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na.split()[-1] != nb.split()[-1]:  # nicknames must agree
        return False
    ta, tb = set(na.split()), set(nb.split())
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.5


def _event_match(e1: OddsEvent, e2: OddsEvent) -> bool:
    """Same game iff both home and away plausibly match (either orientation)."""
    sp = e1.sport or e2.sport  # both share a sport in practice
    straight = (teams_match(e1.home, e2.home, sp)
                and teams_match(e1.away, e2.away, sp))
    flipped = (teams_match(e1.home, e2.away, sp)
               and teams_match(e1.away, e2.home, sp))
    return straight or flipped


def _merge_into(target: OddsEvent, other: OddsEvent) -> None:
    """Fold *other*'s venues into *target*, flipping sides if orientation differs."""
    sp = target.sport or other.sport
    flip = not (teams_match(target.home, other.home, sp)
                and teams_match(target.away, other.away, sp))
    for venue, sides in other.prices.items():
        if flip:
            sides = {"home": sides.get("away"), "away": sides.get("home"),
                     "draw": sides.get("draw")}
        target.prices[venue] = {k: v for k, v in sides.items() if v is not None}


def merge_events(event_lists: Sequence[List[OddsEvent]]) -> List[OddsEvent]:
    """Merge several providers' event lists into one list, one entry per game.

    Pure: unit-tested. The first provider to mention a game owns its home/away
    orientation; later providers' venues are folded in (and flipped if needed).
    """
    merged: List[OddsEvent] = []
    for events in event_lists:
        for ev in events:
            hit = next((m for m in merged if _event_match(m, ev)), None)
            if hit is None:
                clone = OddsEvent(
                    event_id=ev.event_id, sport=ev.sport, home=ev.home,
                    away=ev.away, commence_time=ev.commence_time,
                    prices={}, source="aggregate", as_of=ev.as_of)
                _merge_into(clone, ev)
                merged.append(clone)
            else:
                _merge_into(hit, ev)
    return merged


def default_providers(http_get: Optional[Callable[[str], Any]] = None,
                       *, use_cache: bool = True) -> List[Any]:
    """The standard provider stack: ESPN (keyless) + Kalshi + Polymarket + Pinnacle."""
    kw = {} if http_get is None else {"http_get": http_get}
    return [
        EspnProvider(use_cache=use_cache, **kw),
        KalshiProvider(use_cache=use_cache, **kw),
        PolymarketProvider(use_cache=use_cache, **kw),
        PinnacleProvider(use_cache=use_cache, **kw),
    ]


def aggregate(sport: str, providers: Optional[Sequence[Any]] = None,
              ) -> Dict[str, Any]:
    """Fetch + merge all providers for *sport* into one honest slate payload.

    Returns {"sport", "status", "as_of", "sources": {name: "ok"|reason},
    "events": [OddsEvent.to_dict(), ...]}. status="ok" if at least one provider
    is up, else "unavailable". Never raises; never fabricates a price.
    """
    provs = list(providers) if providers is not None else default_providers()
    wall_now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sources: Dict[str, str] = {}
    lists: List[List[OddsEvent]] = []
    for p in provs:
        try:
            res = p.fetch(sport)
        except Exception as exc:  # noqa: BLE001 -- a provider must never sink the slate
            sources[getattr(p, "name", "?")] = f"error ({type(exc).__name__})"
            continue
        if is_unavailable(res):
            sources[getattr(p, "name", "?")] = res.get("reason", "unavailable")
        elif isinstance(res, list):
            sources[getattr(p, "name", "?")] = "ok"
            lists.append(res)
        else:
            sources[getattr(p, "name", "?")] = "unexpected result"
    events = merge_events(lists)
    status = "ok" if any(v == "ok" for v in sources.values()) else "unavailable"
    # STALE-NEVER-GREEN: the slate as_of is the OLDEST per-source fetched-at across
    # ALL providers (the true freshness floor), NOT now(). Read from the RAW provider
    # lists (pre-merge) so a venue folded into a merged event still counts -- a
    # cached/dead source cannot hide behind another venue's fresh now() stamp.
    as_of = _slate_as_of(lists, wall_now)
    return {"sport": sport.lower(), "status": status, "as_of": as_of,
            "sources": sources, "events": [e.to_dict() for e in events]}


def _slate_as_of(event_lists: Sequence[List[OddsEvent]], fallback: str) -> str:
    """The OLDEST event as_of across every provider list (freshness floor).

    Using the oldest stamp means a dashboard reading slate-level freshness sees the
    age of the STALEST source -- a cached/dead source cannot hide behind a now()
    stamp. Unparseable / missing stamps are ignored (never invented).
    """
    parsed = []
    for events in event_lists:
        for e in events:
            s = getattr(e, "as_of", None)
            if not s:
                continue
            try:
                parsed.append(
                    (datetime.fromisoformat(str(s).replace("Z", "+00:00")), s))
            except (TypeError, ValueError):
                continue
    if not parsed:
        return fallback
    return min(parsed, key=lambda t: t[0])[1]


def to_odds_lookup(sport: str, providers: Optional[Sequence[Any]] = None,
                   ) -> Callable[[str, str, str], Optional[Dict[str, Dict[str, float]]]]:
    """Build an odds_lookup(sport, home, away) callable for slate.build_slate.

    Aggregates ONCE up front (so the slate does not re-hit sources per row), then
    the returned closure matches each (home, away) to a merged event and returns
    its {venue: {"home": dec, "away": dec[, "draw": dec]}} dict -- exactly what
    slate -> odds_shop.summarise_twoway consumes. No match / no odds -> None.

    Wire it in with one line:
        build_slate("nba", odds_lookup=to_odds_lookup("nba"))
    """
    payload = aggregate(sport, providers)
    events = [OddsEvent(**{k: v for k, v in e.items()}) for e in payload["events"]]

    def _lookup(s: str, home: str, away: str
                ) -> Optional[Dict[str, Dict[str, float]]]:
        if s.lower() != sport.lower():
            return None
        probe = OddsEvent(event_id="", sport=s, home=home, away=away,
                          commence_time=None, prices={})
        for ev in events:
            if _event_match(ev, probe):
                flip = not (teams_match(ev.home, home, s)
                            and teams_match(ev.away, away, s))
                out: Dict[str, Dict[str, float]] = {}
                for venue, sides in ev.prices.items():
                    h = sides.get("away") if flip else sides.get("home")
                    a = sides.get("home") if flip else sides.get("away")
                    # Key by the CALLER's team-name strings: slate.build_slate calls
                    # odds_shop.summarise_twoway(book_prices, home, away) with the
                    # team names, so the inner dict must use those exact labels.
                    clean: Dict[str, float] = {}
                    if h is not None:
                        clean[home] = float(h)
                    if a is not None:
                        clean[away] = float(a)
                    if clean:
                        out[venue] = clean
                return out or None
        return None

    return _lookup


__all__ = [
    "aggregate", "merge_events", "to_odds_lookup", "default_providers",
    "normalize_team", "teams_match",
]
