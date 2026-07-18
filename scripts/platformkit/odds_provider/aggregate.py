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
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .base import OddsEvent, is_unavailable
from .espn import EspnProvider
from .fanduel import FanDuelProvider
from .kalshi import KalshiProvider
from .oddsapi_provider import OddsApiProvider
from .pinnacle import PinnacleProvider
from .polymarket import PolymarketProvider
from .team_resolver import canonical

logger = logging.getLogger(__name__)

_TEAM_STOP = {"the", "fc", "afc", "cf", "sc"}

# The keyed OddsAPI feed (DraftKings/FanDuel/BetMGM/Caesars/... in one call) is
# folded into the live stack ONLY when its scarce monthly quota is healthy -- i.e.
# above this reserve floor. This keeps paper trading pulling EVERY book it can when
# units are plentiful, while never draining the reserve we keep for grading closes.
# Below the floor (or with no key) it stays dormant; it re-activates automatically
# when the monthly budget resets. Tune via ODDSAPI_RESERVE_FLOOR.
_ODDSAPI_RESERVE_FLOOR = int(os.environ.get("ODDSAPI_RESERVE_FLOOR", "1500") or 1500)


def _oddsapi_affordable() -> bool:
    """True only when ODDS_API_KEY is set AND enough monthly units remain above the
    reserve floor. Never raises (a budget-read failure -> keep OddsAPI dormant)."""
    if not os.environ.get("ODDS_API_KEY", "").strip():
        return False
    try:
        from src.data.odds_api_client import get_budget  # type: ignore
        b = get_budget()
        rem = b.get("remaining_from_header")
        if not isinstance(rem, int):
            rem = int(b.get("max_units", 0) or 0) - int(b.get("used_units", 0) or 0)
        return int(rem) > _ODDSAPI_RESERVE_FLOOR
    except Exception:  # noqa: BLE001 -- budget read must never sink the slate
        return False


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


# Two books quoting the SAME teams within this many seconds are the same game; a
# wider gap is a different fixture (next-day series / doubleheader) and must NOT
# merge -- else a future game's line overwrites today's and manufactures a fake CLV
# edge. Time is only used to DISAMBIGUATE: if either side lacks a parseable
# commence_time we fall back to team-only matching (no merge is dropped).
_SAME_GAME_WINDOW_SEC = 6 * 3600


def _commence_epoch(value: Any) -> Optional[float]:
    """ISO commence_time -> epoch seconds, tolerant of 'Z' / missing seconds. None
    on absent/unparseable (caller then falls back to team-only matching)."""
    if not value:
        return None
    s = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return None


def _times_compatible(e1: OddsEvent, e2: OddsEvent) -> bool:
    """True if the two events' commence times are close, OR either is unknown."""
    t1, t2 = _commence_epoch(e1.commence_time), _commence_epoch(e2.commence_time)
    if t1 is None or t2 is None:
        return True  # unknown time -> do not block a team match (legacy behaviour)
    return abs(t1 - t2) <= _SAME_GAME_WINDOW_SEC


def _event_match(e1: OddsEvent, e2: OddsEvent) -> bool:
    """Same game iff both teams plausibly match (either orientation) AND the
    commence times are compatible (so a next-day/series game with the same teams
    never merges into today's slate)."""
    sp = e1.sport or e2.sport  # both share a sport in practice
    straight = (teams_match(e1.home, e2.home, sp)
                and teams_match(e1.away, e2.away, sp))
    flipped = (teams_match(e1.home, e2.away, sp)
               and teams_match(e1.away, e2.home, sp))
    if not (straight or flipped):
        return False
    return _times_compatible(e1, e2)


def _flip_spread(spread: Any) -> Any:
    """Swap home/away legs of an extended spread node when orientation flips.

    A spread node is {'home': {'line','odds'}, 'away': {'line','odds'}}; flipping
    the game orientation swaps which side is home/away. The handicap LINE already
    lives with its leg (home line is the negative of away), so swapping the leg
    dicts preserves correctness -- no number is recomputed or fabricated.
    """
    if not isinstance(spread, dict):
        return spread
    return {"home": spread.get("away"), "away": spread.get("home")}


def _merge_into(target: OddsEvent, other: OddsEvent) -> None:
    """Fold *other*'s venues into *target*, flipping sides if orientation differs.

    Carries ALL markets a venue quotes: the flat moneyline keys (home/away/draw)
    AND the extended spread/total nodes. On a flip the moneyline home/away swap and
    the spread node's legs swap; the total node (over/under) is orientation-agnostic
    and is carried unchanged. A None / empty leg is dropped (never fabricated).
    """
    sp = target.sport or other.sport
    flip = not (teams_match(target.home, other.home, sp)
                and teams_match(target.away, other.away, sp))
    for venue, sides in other.prices.items():
        if flip:
            sides = {"home": sides.get("away"), "away": sides.get("home"),
                     "draw": sides.get("draw"),
                     "spread": _flip_spread(sides.get("spread")),
                     "total": sides.get("total")}
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
    """The standard provider stack: ESPN + FanDuel (soft) + Kalshi + Polymarket +
    Pinnacle (sharp), plus the keyed OddsAPI multi-book feed when its quota is
    healthy (see _oddsapi_affordable). FanDuel adds the soft-book dispersion that
    makes line-shopping +CLV possible -- ESPN (DraftKings) + Pinnacle are both sharp
    + tightly aligned; OddsAPI widens venue coverage (Caesars/BetMGM/...) for free
    line-shopping when units allow."""
    kw = {} if http_get is None else {"http_get": http_get}
    provs: List[Any] = [
        EspnProvider(use_cache=use_cache, **kw),
        FanDuelProvider(use_cache=use_cache, **kw),
        # governor_caller="aggregate": every default_providers() daemon (line
        # daemon, pm paper tick, best-bets, frontend) previously hit Kalshi
        # UNGOVERNED and collectively starved the governed live daemons
        # (429 storm 2026-07-14, n_429_total=2606).
        # Espn/FanDuel/Polymarket/Pinnacle/OddsApi are NOT wired to
        # kalshi_rate_governor (finding 21, 2026-07-18): that module is
        # calibrated + keyed specifically for Kalshi (BASE_RPS ~ Kalshi's
        # documented rps ceiling, 429 detection via kalshi_pacing.is_429,
        # one shared state file). Reusing it for these unrelated hosts would
        # wrongly couple their backoff to Kalshi's. Correct fix = a separate
        # generic per-host governor (new module) -- out of scope here, flagged
        # as follow-up.
        KalshiProvider(use_cache=use_cache, governor_caller="aggregate", **kw),
        PolymarketProvider(use_cache=use_cache, **kw),
        PinnacleProvider(use_cache=use_cache, **kw),
    ]
    if _oddsapi_affordable():
        provs.append(OddsApiProvider(use_cache=use_cache, **kw))
    return provs


# A SLOW source must not serialize behind (or stall) the whole slate. Providers are
# fetched CONCURRENTLY and gathered in PROVIDER ORDER (so the merge's "first provider
# owns orientation" contract is byte-identical to a sequential fetch), under a shared
# wall-clock deadline: a provider that has not returned by the deadline is recorded as
# an error and abandoned (its thread is left to finish + die), exactly like the
# bestbets-route deadline -- the slate returns AT the deadline, never hangs on one
# pathological source. Each HTTP fetch already has its own timeout+retry (http_cache);
# this deadline is the outer backstop. Tune via ODDS_AGG_FETCH_DEADLINE_S.
_AGG_FETCH_DEADLINE_S = float(os.environ.get("ODDS_AGG_FETCH_DEADLINE_S", "25") or 25)


def _classify(name: str, res: Any, sources: Dict[str, str],
              lists: List[List[OddsEvent]]) -> None:
    """Fold one provider result into (sources, lists) -- the shared ok/down/odd rule."""
    if is_unavailable(res):
        sources[name] = res.get("reason", "unavailable")
    elif isinstance(res, list):
        sources[name] = "ok"
        lists.append(res)
    else:
        sources[name] = "unexpected result"


def _fetch_all(provs: Sequence[Any], sport: str,
               ) -> Tuple[Dict[str, str], List[List[OddsEvent]]]:
    """Fetch every provider concurrently under a shared deadline; gather in order.

    Returns (sources, lists) identical in shape to the old sequential loop. A
    provider that raises -> 'error (<Type>)'; one that overruns the shared deadline
    -> 'error (Timeout)'. Order is preserved (lists appended provider-by-provider)
    so merge_events' orientation-ownership is unchanged. Never raises.
    """
    import time as _time
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FTimeout
    sources: Dict[str, str] = {}
    lists: List[List[OddsEvent]] = []
    pool = ThreadPoolExecutor(max_workers=min(8, max(1, len(provs))))
    try:
        futs = [(getattr(p, "name", "?"), pool.submit(p.fetch, sport)) for p in provs]
        deadline = _time.monotonic() + _AGG_FETCH_DEADLINE_S
        for name, fut in futs:  # gather IN PROVIDER ORDER (deterministic merge)
            remaining = max(0.0, deadline - _time.monotonic())
            try:
                res = fut.result(timeout=remaining)
            except _FTimeout:
                sources[name] = "error (Timeout)"
                fut.cancel()
                continue
            except Exception as exc:  # noqa: BLE001 -- a provider must never sink the slate
                sources[name] = "error (%s)" % type(exc).__name__
                continue
            _classify(name, res, sources, lists)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)  # return AT the deadline
    return sources, lists


def aggregate(sport: str, providers: Optional[Sequence[Any]] = None,
              ) -> Dict[str, Any]:
    """Fetch + merge all providers for *sport* into one honest slate payload.

    Returns {"sport", "status", "as_of", "sources": {name: "ok"|reason},
    "events": [OddsEvent.to_dict(), ...]}. status="ok" if at least one provider
    is up, else "unavailable". Providers are fetched CONCURRENTLY under a shared
    deadline (one slow source can neither serialize nor stall the slate) and merged
    in provider order. Never raises; never fabricates a price.
    """
    provs = list(providers) if providers is not None else default_providers()
    wall_now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sources, lists = _fetch_all(provs, sport)
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
    its {venue: {home: dec, away: dec[, "Draw": dec]}} dict (keyed by the
    caller's team-name strings, plus the literal "Draw" selection for a genuine
    3-way soccer market) -- exactly what slate -> odds_shop.summarise_twoway and
    bet_board._moneyline_prices consume. No match / no odds -> None.

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
                    # Draw is orientation-agnostic (a flip only swaps home/away
                    # legs -- _flip_spread's sibling logic in _merge_into already
                    # keeps 'draw' unflipped) and is NEVER attached for a 2-way
                    # sport: sides only carries a non-None 'draw' when the source
                    # is a genuine 3-way market (soccer), so this is a no-op for
                    # nba/mlb/wnba/npb/kbo/tennis (regression-safe by construction).
                    d = sides.get("draw")
                    # Key by the CALLER's team-name strings: slate.build_slate calls
                    # odds_shop.summarise_twoway(book_prices, home, away) with the
                    # team names, so the inner dict must use those exact labels.
                    # "Draw" is the literal selection string bet_board_flat.flatten_soccer
                    # emits for the 1X2 draw leg (bet_board._moneyline_prices looks it
                    # up by that exact key) -- carry it through under that same key.
                    clean: Dict[str, float] = {}
                    if h is not None:
                        clean[home] = float(h)
                    if a is not None:
                        clean[away] = float(a)
                    if d is not None:
                        clean["Draw"] = float(d)
                    if clean:
                        out[venue] = clean
                return out or None
        return None

    return _lookup


__all__ = [
    "aggregate", "merge_events", "to_odds_lookup", "default_providers",
    "normalize_team", "teams_match",
]
