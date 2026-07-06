"""scripts.platformkit.odds_provider.kalshi -- keyless Kalshi public market data.

Kalshi's public market-data REST endpoints need NO auth (only trading does).
Base: https://api.elections.kalshi.com/trade-api/v2 (also reachable as
external-api.kalshi.com). Prices are quoted in DOLLARS in [0, 1] -- i.e. the
implied probability of the YES side -- in the *_dollars fields (yes_ask_dollars,
yes_bid_dollars, no_ask_dollars, ...). An optional bearer token is read from ENV
(KALSHI_API_TOKEN) ONLY; absent is fine for public reads.

Sports mapping: a Kalshi sports game is an EVENT (event_ticker) holding two
team-winner MARKETS (one per team), each a YES/NO contract "<team> wins". We group
markets by event_ticker, treat the higher-volume / alphabetically-first team as
home only when an explicit home hint is absent (caller-supplied team match in
aggregate.py disambiguates). We expose BOTH teams' YES asks as the two sides; the
venue label is "kalshi". Implied prob (yes_ask_dollars) -> decimal = 1/prob.

3-WAY (regulation-time soccer, e.g. KXWCGAME): some series group THREE markets
per event_ticker -- team-A, "Tie", team-B (each its own YES/NO contract). These
are recognized and emitted as {"home": dec, "away": dec, "draw": dec}, the SAME
flat moneyline shape base.OddsEvent documents (see parse_events._split_three_way
for the tie-leg detection rule). Downstream consumers already devig this 3-way
(markets._moneyline_quotes' Shin N-outcome solver) -- unchanged for this fix.

A market we cannot confidently map to a two-team (or team/tie/team) game is
skipped (never guessed).

CROSS-PROCESS RATE GOVERNOR (see kalshi_rate_governor.py): opt-in via
governor_caller (None default = no governor, byte-identical -- every
pre-existing caller/test stays unchanged), same discipline as
inplay_kalshi.fetch_inplay's own governor_caller. m18 (pm_close_capture, via
close_capture._kalshi_close) opts in explicitly with governor_caller=
"close_capture" since it instantiates KalshiProvider directly (bypasses
aggregate()'s other providers), hammering this endpoint ungoverned. Env
KALSHI_GOVERNOR_OFF=1 disables. Fail-open.
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from .base import OddsEvent, prob_to_decimal, unavailable
from .http_cache import disk_cache_get_meta, http_get_json
from .kalshi_pacing import is_429 as _is_429
from .kalshi_rate_governor import before_request as _governor_before
from .kalshi_rate_governor import report_429 as _governor_report_429, resolve_governor as _resolve_governor

logger = logging.getLogger(__name__)

_BASE = "https://api.elections.kalshi.com/trade-api/v2"

# Sport -> Kalshi series-ticker prefixes for team game-winner markets. Used as a
# client-side event_ticker startswith GUARD (defensive, mirrors inplay_kalshi's
# relevant-filter) and as the fallback sport-scope when no exact GAME series is
# registered for a sport (tennis: MATCH-shaped, not GAME -- correctly absent from
# _GAME_SERIES below).
# "npb" added 2026-07-03 (paper enablement sweep, LANE 5); "kbo" added
# 2026-07-04 (LANE 4 close-capture widening) -- both live-verified in
# kalshi_series_spec.py.
_SERIES_HINT: Dict[str, str] = {
    "nba": "KXNBA",
    "wnba": "KXWNBA",
    "mlb": "KXMLB",
    "soccer": "KXEPL",
    "soccer_intl": "KXWC",
    "tennis": "KXATP",
    "npb": "KXNPB",
    "kbo": "KXKBO",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _game_series_ticker(sport: str) -> Optional[str]:
    """Exact Kalshi GAME series_ticker for *sport*, or None (no exact series /
    lookup unavailable -- caller falls back to the unfiltered+startswith path).

    Sourced from kalshi_series_spec._GAME_SERIES (the same server-verified
    registry inplay_kalshi already queries by), guarded so a missing/broken
    import degrades to None rather than raising. Never raises.
    """
    try:
        from .kalshi_series_spec import _GAME_SERIES
        return _GAME_SERIES.get(str(sport).lower())
    except Exception:  # noqa: BLE001 -- degrade, never bubble
        return None


def _token() -> Optional[str]:
    """Optional bearer token from ENV ONLY (public reads work without it)."""
    t = os.environ.get("KALSHI_API_TOKEN")
    return t.strip() if t and t.strip() else None


def _yes_ask_prob(market: Dict[str, Any]) -> Optional[float]:
    """YES ask as an implied probability in (0,1) from the *_dollars field.

    Falls back to last_price_dollars when no ask is quoted. None if unusable.
    """
    for key in ("yes_ask_dollars", "last_price_dollars", "yes_bid_dollars"):
        v = market.get(key)
        try:
            p = float(v)
        except (TypeError, ValueError):
            continue
        if 0.0 < p < 1.0:
            return p
    return None


def group_markets(markets: List[Dict[str, Any]],
                  ) -> Dict[str, List[Dict[str, Any]]]:
    """Group market dicts by event_ticker (a Kalshi game holds 2 team markets)."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for m in markets or []:
        ev = m.get("event_ticker")
        if ev:
            out.setdefault(ev, []).append(m)
    return out


def _team_label(market: Dict[str, Any]) -> str:
    """Best-effort team label for a YES contract (yes_sub_title or title tail)."""
    return (market.get("yes_sub_title") or market.get("title") or "").strip()


# Tokens identifying the TIE/DRAW leg of a 3-way (soccer regulation) Kalshi game
# group (e.g. KXWCGAME-26JUN22USAMEX has THREE markets: "United States", "Tie",
# "Mexico"). Matched case-insensitively against the full label -- mirrors
# inplay_capture_loop._draw_leg / pm_game_placer._TIE_TOKENS (the SAME convention
# already proven live on the in-play side of this exact series).
_TIE_TOKENS = frozenset({"tie", "draw", "x"})


def _is_tie_label(label: str) -> bool:
    lab = str(label or "").strip().lower()
    return lab in _TIE_TOKENS or "draw" in lab or "tie" in lab


def _split_three_way(legs: List[Dict[str, Any]],
                     ) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
    """Split a 3-leg Kalshi group into (team_a, tie, team_b), or None.

    Exactly one leg must carry a tie/draw label (by _is_tie_label); the other two
    are the two team legs, returned in their original relative order. None if the
    group is NOT shaped like a regulation 3-way (zero or >1 tie-labeled legs) --
    never guessed.
    """
    tie_idx = [i for i, l in enumerate(legs) if _is_tie_label(_team_label(l))]
    if len(tie_idx) != 1:
        return None
    i = tie_idx[0]
    teams = [l for j, l in enumerate(legs) if j != i]
    if len(teams) != 2:
        return None
    return teams[0], legs[i], teams[1]


def parse_events(markets: List[Dict[str, Any]], sport: str,
                 as_of: Optional[str] = None,
                 ) -> List[OddsEvent]:
    """Turn a flat Kalshi market list into normalized OddsEvents (2-way or 3-way).

    Pure: unit-tested on canned markets. Home/away here is the market order
    (caller matches by team name to fix orientation).

    2-LEG groups (the pre-existing path, BYTE-IDENTICAL): both legs must carry a
    usable YES ask -> {"home": dec, "away": dec, "draw": None}.

    3-LEG groups (NEW, additive): a regulation-time soccer market (e.g. Kalshi
    KXWCGAME groups team-A/tie/team-B as three separate YES/NO markets under one
    event_ticker). Recognized ONLY when exactly one leg's label is a tie/draw
    token (_is_tie_label) and the other two are team legs, ALL THREE carrying a
    usable YES ask -> {"home": dec, "away": dec, "draw": dec}, the SAME flat
    moneyline shape base.OddsEvent already documents and every downstream
    consumer (markets._moneyline_quotes 3-way Shin devig, book_table._ML_SIDES,
    aggregate._merge_into) already reads for soccer 1X2 (Pinnacle/ESPN). Devigged
    AS a 3-way (markets.py's Shin N-outcome solver), never forced 2-way.

    A group that is neither a clean 2-leg NOR a clean 3-way (any leg missing a
    price, or a >=3-leg group with zero/multiple tie-labeled legs) is skipped
    (never guessed into a line).

    *as_of* is the TRUE fetched-at time of the source body (the original fetch
    time on a cache hit, never now()) so a cached/dead feed cannot read fresh.
    Defaults to now() only when the caller has no fetched-at (pure-test path).
    """
    as_of = as_of or _now_iso()
    out: List[OddsEvent] = []
    for ev_ticker, legs in group_markets(markets).items():
        if len(legs) == 2:
            priced = [(l, _yes_ask_prob(l)) for l in legs]
            if any(p is None for _l, p in priced):
                continue
            (m_a, p_a), (m_b, p_b) = priced
            dec_a, dec_b = prob_to_decimal(p_a), prob_to_decimal(p_b)
            if dec_a is None or dec_b is None:
                continue
            home, away = _team_label(m_a), _team_label(m_b)
            draw_dec: Optional[float] = None
        elif len(legs) == 3:
            split = _split_three_way(legs)
            if split is None:
                continue
            m_a, m_tie, m_b = split
            p_a, p_tie, p_b = (_yes_ask_prob(m_a), _yes_ask_prob(m_tie),
                              _yes_ask_prob(m_b))
            if p_a is None or p_tie is None or p_b is None:
                continue
            dec_a, draw_dec, dec_b = (prob_to_decimal(p_a), prob_to_decimal(p_tie),
                                      prob_to_decimal(p_b))
            if dec_a is None or dec_b is None or draw_dec is None:
                continue
            home, away = _team_label(m_a), _team_label(m_b)
        else:
            continue
        # Kalshi's close_time is a SETTLEMENT/expiry bound (at or after game end),
        # NOT the tip-off time. Putting it in commence_time would let a near-final
        # in-play price be labeled is_true_close=True by line_store._within_lock,
        # inflating CLV. Leave commence_time=None so a Kalshi-only game can never
        # satisfy the lock window and is always honestly marked clv_is_proxy=True.
        out.append(OddsEvent(
            event_id=ev_ticker, sport=sport, home=home, away=away,
            commence_time=None,
            prices={"kalshi": {"home": dec_a, "away": dec_b, "draw": draw_dec}},
            source="kalshi", as_of=as_of))
    return out


class KalshiProvider:
    """Keyless Kalshi public-market-data provider. fetch -> list[OddsEvent]|UNAVAILABLE."""

    name = "kalshi"

    def __init__(self,
                 http_get: Callable[[str], Any] = http_get_json,
                 *, use_cache: bool = True, page_limit: int = 200,
                 governor_caller: Optional[str] = None) -> None:
        self._http_get = http_get
        self._use_cache = use_cache
        self._page_limit = page_limit
        # None (default) = no governor, byte-identical for every pre-existing
        # caller; resolve once here (mirrors fetch_inplay's governor_caller).
        self._governor = _resolve_governor(governor_caller)

    def _get(self, url: str) -> Tuple[Any, str]:
        """Return (body, fetched_at_iso) -- the TRUE network fetch time of the body
        (original fetch time on a cache hit, never now()) so a cached/dead Kalshi
        body cannot re-stamp itself fresh within the freshness TTL."""
        if self._use_cache:
            body, fetched_at, _hit = disk_cache_get_meta(url, http_get=self._http_get)
            return body, fetched_at
        return self._http_get(url), _now_iso()

    def fetch(self, sport: str) -> Union[List[OddsEvent], Dict[str, str]]:
        sport = sport.lower()
        prefix = _SERIES_HINT.get(sport)
        if not prefix:
            return unavailable(f"kalshi: unsupported sport '{sport}'")
        params: Dict[str, Any] = {"limit": self._page_limit, "status": "open"}
        # BUGFIX (2026-07-04, LANE 4): an UNFILTERED /markets call paginates across
        # ALL ~2300 Kalshi series; a single 200-row page can miss a sport's markets
        # entirely regardless of volume (verified live: nba/mlb/soccer/tennis/wnba/
        # npb ALL returned 0 rows via the old unfiltered call, masked for
        # nba/mlb/soccer/tennis only because aggregate() also merges ESPN/fanduel/
        # polymarket/pinnacle for those sports -- wnba/npb/kbo have NO other odds
        # source, so this was a silent total outage for them). Passing the exact
        # per-sport GAME series_ticker (kalshi_series_spec._GAME_SERIES, the
        # server-verified moneyline series -- same registry inplay_kalshi already
        # uses) makes the call SERVER-SIDE scoped, matching the in-play fetcher's
        # already-correct pattern. A sport with no GAME series (tennis: MATCH-
        # shaped, not GAME) falls back to the prior unfiltered+startswith behavior
        # unchanged. The client-side startswith stays as a defensive guard either
        # way (mirrors inplay_kalshi._fetch_one_series).
        series_ticker = _game_series_ticker(sport)
        if series_ticker:
            params["series_ticker"] = series_ticker
        url = f"{_BASE}/markets?" + urllib.parse.urlencode(params)
        _governor_before(self._governor, sport)
        try:
            body, fetched_at = self._get(url)
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("kalshi markets failed for %s: %s", sport, exc)
            if _is_429(exc):
                _governor_report_429(self._governor)
            return unavailable(f"kalshi call failed ({type(exc).__name__})")
        markets = body.get("markets") if isinstance(body, dict) else None
        if not isinstance(markets, list):
            return unavailable("kalshi: unexpected markets shape")
        relevant = [m for m in markets
                    if str(m.get("event_ticker", "")).startswith(prefix)]
        return parse_events(relevant, sport, fetched_at)


__all__ = ["KalshiProvider", "parse_events", "group_markets"]
