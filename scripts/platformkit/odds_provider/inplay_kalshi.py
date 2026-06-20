"""scripts.platformkit.odds_provider.inplay_kalshi -- LIQUID Kalshi in-play feed.

The frontier-unblock connector: the ONLY keyless venue with REAL in-play depth in
season (Kalshi KX*GAME game-winner markets). It exposes the SAME two-function
contract every other in-play source uses so it plugs into the daemon + the CLV
replay with zero new plumbing:

  fetch_inplay(sport)               -> live in-play ticks for currently-open KX*GAME
                                       markets (one YES-prob tick per LIQUID side).
  fetch_price_history(market_ref,*) -> the historical in-play series for one market.

Canonical tick (UNCHANGED schema the CLV replay consumes), with phase tagged:
  {"sport","game_id","venue":"kalshi","market_type":"moneyline","side","ticker",
   "prob" (YES in [0,1]), "ts" (ISO-8601 UTC 'Z'), "phase":"in_play"}

REUSE, never duplicate:
  * KalshiProvider supplies the keyless markets fetch (http getter + cache + the
    KX<league> open-market filter). We read the SAME /markets body it fetches so we
    can apply the liquidity gate on the raw *_dollars / *_fp fields, then reuse
    kalshi._yes_ask_prob + kalshi.group_markets for the price + grouping.
  * inplay_history.fetch_price_history supplies the candlestick back-fetch (it
    already reads the live *_dollars candle fields). We do NOT add a 2nd fetcher.

THE LIQUIDITY GATE (the honest fix for "listed but untraded"): a market counts as
tradeable in-play ONLY if, on the LIVE *_dollars / *_fp fields (NOT the deprecated
integer fields which read None):
  * it is open + not settled (KalshiProvider already filters status=open), AND
  * its YES spread (yes_ask_dollars - yes_bid_dollars) is <= MAX_SPREAD, AND
  * its traded volume (volume_fp) is above MIN_VOLUME, AND
  * both side sizes (yes_bid_size_fp, yes_ask_size_fp) are above MIN_SIZE.
An untraded pregame contract (all *_fp None / zero, wide/no spread) therefore emits
NOTHING -- it can never masquerade as a live in-play price. A missing / illiquid
market -> VOID (skipped), NEVER 0-filled into a fake observation.

HONESTY (binding): commence_time stays None (Kalshi's only timestamp is a
SETTLEMENT bound, never a tip-off) so a near-final price can NEVER be mislabeled
is_true_close. phase is always "in_play". No $ / ROI / edge -- probability only.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; stdlib +
repo-internal only. Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_inplay_kalshi.py -q
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

from .http_cache import http_get_json
from .inplay_history import fetch_price_history as _candle_history
from .kalshi import _BASE, _yes_ask_prob, group_markets

logger = logging.getLogger(__name__)

VENUE = "kalshi"
PHASE = "in_play"

# Sport -> Kalshi per-GAME series ticker. Kalshi's two-team game-winner contracts
# live in the KX<LEAGUE>GAME series (one EVENT per game holding two team markets).
# We query the /markets list endpoint with series_ticker=<this> so those per-game
# markets page in DIRECTLY. The old code used the broad KX<LEAGUE> prefix (kalshi.
# _SERIES_HINT) over an UNFILTERED limit=200 page -- the per-game series never
# appeared in the first page, so fetch_inplay silently found nothing. A sport with
# no per-game series here is unsupported in-play (-> []), never guessed.
_GAME_SERIES: Dict[str, str] = {
    "mlb": "KXMLBGAME",
    "soccer": "KXEPLGAME",
    "soccer_intl": "KXWCGAME",
    "nba": "KXNBAGAME",
}

# Liquidity-gate thresholds (probability-space dollars + fractional-point sizes).
# A market must clear ALL of these on its LIVE fields to count as tradeable in-play.
# Defaults are deliberately conservative: the research probe showed liquid in-season
# game markets sit at a 1-2c spread with 5-6 figure volume / sizes, while untraded
# pregame contracts read None on every *_fp field and have no real spread.
MAX_SPREAD = 0.02   # <= 2c YES bid/ask spread
MIN_VOLUME = 50.0   # traded contracts (volume_fp) floor
MIN_SIZE = 1.0      # both bid_size_fp and ask_size_fp must be above this floor

Tick = Dict[str, Any]
HttpGet = Callable[[str], Any]


def _fp(market: Dict[str, Any], key: str) -> Optional[float]:
    """A fractional-point (*_fp) or *_dollars field coerced to float, else None.

    Reads ONLY the LIVE fields. The deprecated bare-integer fields (yes_bid,
    yes_ask, volume, open_interest) read None on the live API, so a market priced
    only by those returns None here and is gated out -- never zero-filled.
    """
    v = market.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _spread(market: Dict[str, Any]) -> Optional[float]:
    """YES bid/ask spread in dollars (ask - bid) from the live *_dollars fields.

    None if either side is unquoted (cannot prove a tight market) or the spread is
    nonsensical (negative). A None spread fails the gate (we never assume tight).
    """
    bid = _fp(market, "yes_bid_dollars")
    ask = _fp(market, "yes_ask_dollars")
    if bid is None or ask is None:
        return None
    s = ask - bid
    return s if s >= 0.0 else None


def is_liquid(market: Dict[str, Any],
              *, max_spread: float = MAX_SPREAD,
              min_volume: float = MIN_VOLUME,
              min_size: float = MIN_SIZE) -> bool:
    """True iff *market* clears the in-play liquidity gate on its LIVE fields.

    Requires a tight quoted spread AND real traded volume AND real depth on BOTH
    sides -- so an untraded pregame contract (None/zero *_fp) is excluded. Pure +
    total; never raises (a malformed market -> False, i.e. VOID, never faked live).
    """
    try:
        spread = _spread(market)
        if spread is None or spread > max_spread:
            return False
        vol = _fp(market, "volume_fp")
        if vol is None or vol <= min_volume:
            return False
        bid_sz = _fp(market, "yes_bid_size_fp")
        ask_sz = _fp(market, "yes_ask_size_fp")
        if bid_sz is None or ask_sz is None:
            return False
        return bid_sz > min_size and ask_sz > min_size
    except Exception as exc:  # noqa: BLE001 -- classification must never sink a row
        logger.debug("is_liquid check failed: %s", exc)
        return False


def _side_label(market: Dict[str, Any]) -> str:
    """Best-effort YES-team label for a market (yes_sub_title or title tail)."""
    return (market.get("yes_sub_title") or market.get("title") or "").strip()


def _tick_from_market(sport: str, market: Dict[str, Any], ts: str) -> Optional[Tick]:
    """One canonical in-play tick from ONE liquid Kalshi market, or None.

    The YES prob comes from kalshi._yes_ask_prob (the same *_dollars reader the
    provider uses); the ticker is the market ticker; the game_id is the event
    ticker (the two-team game). commence_time is intentionally ABSENT (None-by-
    omission is enforced by the daemon path; we never stamp a settlement bound as a
    start). Returns None if the market has no usable YES price (VOID, never faked).
    """
    prob = _yes_ask_prob(market)
    if prob is None:
        return None
    ticker = str(market.get("ticker") or "").strip()
    if not ticker:
        return None
    game_id = str(market.get("event_ticker") or ticker).strip()
    return {
        "sport": sport,
        "game_id": game_id,
        "venue": VENUE,
        "market_type": "moneyline",
        "side": _side_label(market) or "yes",
        "ticker": ticker,
        "prob": prob,
        "ts": ts,
        "phase": PHASE,
    }


def fetch_inplay(sport: str, *, http: HttpGet = http_get_json,
                 now_iso: Optional[str] = None,
                 max_spread: float = MAX_SPREAD,
                 min_volume: float = MIN_VOLUME,
                 min_size: float = MIN_SIZE) -> List[Tick]:
    """Live in-play ticks for currently-open KX<league>GAME markets of *sport*.

    Queries the keyless /markets list endpoint with series_ticker=KX<league>GAME
    (KXMLBGAME for mlb, KXWCGAME for World Cup soccer) so the per-GAME team-winner
    markets page in DIRECTLY -- the old broad KX<league> prefix over an unfiltered
    limit=200 page missed them. Applies the LIQUIDITY GATE to each raw market on its
    live *_dollars / *_fp fields and emits ONE canonical tick per market that clears
    it. An illiquid / untraded market is SKIPPED (VOID) -- never 0-filled, never
    faked into a live price. *http* is injected for offline tests. Never raises: an
    unsupported sport or a feed failure yields [].
    """
    series = _GAME_SERIES.get(str(sport).lower())
    if not series:
        return []
    params = {"series_ticker": series, "limit": 200, "status": "open"}
    url = "%s/markets?%s" % (_BASE, urllib.parse.urlencode(params))
    try:
        body = http(url)
    except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
        logger.warning("kalshi in-play markets failed for %s: %s", sport, exc)
        return []
    markets = body.get("markets") if isinstance(body, dict) else None
    if not isinstance(markets, list):
        return []
    ts = now_iso or _now_iso()
    out: List[Tick] = []
    # The series_ticker filter is server-side; the startswith is a cheap defensive
    # guard so a stray cross-series market (a mixed page) can never leak through.
    relevant = [m for m in markets if isinstance(m, dict)
                and str(m.get("event_ticker", "")).startswith(series)]
    for m in relevant:
        if not is_liquid(m, max_spread=max_spread, min_volume=min_volume,
                         min_size=min_size):
            continue  # illiquid / untraded -> VOID, never a fake in-play price
        tick = _tick_from_market(sport, m, ts)
        if tick is not None:
            out.append(tick)
    return out


def fetch_price_history(market_ref: str, window: Optional[int] = None,
                        *, sport: str = "", side: str = "",
                        period_interval: int = 1,
                        http: HttpGet = http_get_json,
                        now_epoch: Optional[int] = None) -> List[Tick]:
    """Historical in-play series for ONE Kalshi market, canonical schema + phase.

    REUSES inplay_history.fetch_price_history (Kalshi candlesticks; reads the live
    *_dollars candle fields) -- no duplicate fetcher. *market_ref* is a market
    ticker (its series prefix is derived). *window* is a lookback in SECONDS
    (default 6h, enough for one game's in-play path). Each returned candle tick is
    re-tagged phase="in_play" and stripped to the canonical schema. Never raises:
    a feed/parse failure yields [].
    """
    now = int(now_epoch if now_epoch is not None else time.time())
    span = int(window) if window else 6 * 3600
    raw = _candle_history(
        "", str(market_ref), now - span, now, period_interval,
        sport=sport, side=side, market_type="moneyline", http=http)
    out: List[Tick] = []
    for r in raw:
        out.append({
            "sport": r.get("sport", sport),
            "game_id": r.get("game_id", str(market_ref)),
            "venue": VENUE,
            "market_type": r.get("market_type", "moneyline"),
            "side": r.get("side", side),
            "ticker": r.get("ticker", str(market_ref)),
            "prob": r.get("prob"),
            "ts": r.get("ts"),
            "phase": PHASE,
        })
    return out


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "fetch_inplay",
    "fetch_price_history",
    "is_liquid",
    "MAX_SPREAD",
    "MIN_VOLUME",
    "MIN_SIZE",
    "VENUE",
    "PHASE",
]
