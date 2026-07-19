"""scripts.platformkit.odds_provider.inplay_kalshi -- LIQUID Kalshi in-play feed.

The frontier-unblock connector: the ONLY keyless venue with REAL in-play depth in
season (Kalshi KX*GAME/TOTAL/SPREAD/TEAMTOTAL/MATCH markets).

  fetch_inplay(sport)               -> live in-play ticks across ALL wired series
                                       (kalshi_series_spec.SERIES_SPEC).
  fetch_price_history(market_ref,*) -> the historical in-play series for one market.

Canonical tick (moneyline rows BYTE-COMPATIBLE with the pre-widening schema):
  {"sport","game_id","venue":"kalshi","market_type","side","ticker","prob" (YES
   in [0,1]), "line" (None for moneyline; the strike otherwise), "ts", "phase"}
  Additive (fetch_inplay only): "best_bid"/"best_ask"/"spread_bp" -- the SAME
  live *_dollars fields the liquidity gate already required; None if unquoted,
  never fabricated. Consumed by ingame_exec_gate.build_exec_depth for the
  placement-time microstructure stamp (see kalshi_tick_depth.py).

REUSE, never duplicate: kalshi._yes_ask_prob (price) + kalshi_series_spec (the
per-sport series list + future-game guard) + inplay_history.fetch_price_history.

THE LIQUIDITY GATE (the honest fix for "listed but untraded"): a market counts as
tradeable in-play ONLY if, on the LIVE *_dollars / *_fp fields (NOT the deprecated
integer fields which read None): open+not settled, YES spread <= MAX_SPREAD,
volume_fp above MIN_VOLUME, and both yes_bid_size_fp/yes_ask_size_fp above
MIN_SIZE. An untraded pregame contract emits NOTHING -- a missing/illiquid market
-> VOID, NEVER 0-filled.

HONESTY (binding): commence_time stays None (a SETTLEMENT bound, never a tip-off)
so a near-final price is NEVER mislabeled is_true_close. No $/ROI/edge --
probability only; market_type is NEVER assumed a WIN prob outside "moneyline".

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; stdlib +
repo-internal only. Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_inplay_kalshi.py -q

PACING + 429 OBSERVABILITY (see kalshi_pacing.py for root-cause + fix): additive,
off-by-default no-ops if unused -- REQUEST_STAGGER_SEC drips series calls; *stats*
is mutated with n_requests/n_429, never changing fetch_inplay's return type.

CROSS-PROCESS RATE GOVERNOR (see kalshi_rate_governor.py): opt-in via
governor_caller (None default = no governor, byte-identical); both production
daemons opt in explicitly (env KALSHI_GOVERNOR_OFF=1 disables). Fail-open.
"""
from __future__ import annotations

import logging
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .http_cache import http_get_json
from .inplay_history import fetch_price_history as _candle_history
from .kalshi import _BASE, _yes_ask_prob
from .kalshi_liquidity import MAX_SPREAD, MIN_SIZE, MIN_VOLUME, is_liquid
from .kalshi_pacing import MAX_429_COOLDOWN_SEC, REQUEST_STAGGER_SEC
from .kalshi_pacing import cooldown_after_429, is_429, record_429, record_request, stagger_sleep
from .kalshi_rate_governor import before_request as _governor_before
from .kalshi_rate_governor import report_429 as _governor_report_429, resolve_governor as _resolve_governor
from .kalshi_series_spec import (  # noqa: F401 -- _GAME_SERIES is a back-compat re-export
    _GAME_SERIES,
    is_future_game,
    series_for,
)
from .kalshi_tick_depth import best_bid_ask, spread_bp
from .transport import resilient_get_json

logger = logging.getLogger(__name__)

VENUE = "kalshi"
PHASE = "in_play"

# RATE POLITENESS: Kalshi's public rate limit is ~30 rps (documented, keyless
# tier); see kalshi_pacing.py for why a bursty 429 wall still forms and how
# REQUEST_STAGGER_SEC/MAX_429_COOLDOWN_SEC (imported above) fix it.

# Liquidity-gate thresholds + is_liquid() live in kalshi_liquidity (imported above).

Tick = Dict[str, Any]
HttpGet = Callable[[str], Any]
SleepFn = Callable[[float], None]

# The future-game ticker-date guard (shared by ALL series: game/total/spread/team_total/
# match tickers embed the same '-DDMONYY' fragment, including tennis KXATPMATCH/KXWTAMATCH)
# now lives in kalshi_series_spec -- see is_future_game there for the full rationale.


def _parse_iso_now(s: Any) -> datetime:
    """Best-effort parse of an ISO 'now' stamp -> aware UTC; falls back to now() on miss."""
    try:
        v = str(s).strip()
        if v.endswith("Z"):
            v = v[:-1] + "+00:00"
        dt = datetime.fromisoformat(v)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _side_label(market: Dict[str, Any]) -> str:
    """Best-effort YES-team label for a market (yes_sub_title or title tail)."""
    return (market.get("yes_sub_title") or market.get("title") or "").strip()


def _line_from_market(market: Dict[str, Any]) -> Optional[float]:
    """The LINE for a total/spread/team_total market (None for moneyline).

    Reads `floor_strike` (verified live 2026-07-03 on KXMLBTOTAL/KXMLBSPREAD/
    KXMLBTEAMTOTAL/KXWCSPREAD/KXWCTEAMTOTAL, e.g. floor_strike=8.5 for "Over 8.5
    runs scored"); `cap_strike` as a fallback. A moneyline market (strike_type=
    "structured") has neither -- correctly reads None (no line). This is the REAL
    body field, not a ticker-suffix parse. Never raises.
    """
    for key in ("floor_strike", "cap_strike"):
        v = market.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _tick_from_market(sport: str, market: Dict[str, Any], ts: str,
                      market_type: str) -> Optional[Tick]:
    """One canonical in-play tick from ONE liquid Kalshi market, or None.

    The YES prob comes from kalshi._yes_ask_prob (the same *_dollars reader the
    provider uses); the ticker is the market ticker; the game_id is the event
    ticker (the two-team game). commence_time is intentionally ABSENT (None-by-
    omission is enforced by the daemon path; we never stamp a settlement bound as a
    start). *market_type* is the caller's (series_ticker, market_type) pair tag --
    "line" is None for moneyline, else the real strike (see _line_from_market).
    best_bid/best_ask/spread_bp (kalshi_tick_depth) are additive from the SAME
    live fields; None if unquoted, never fabricated. Returns None if the market
    has no usable YES price (VOID, never faked).
    """
    prob = _yes_ask_prob(market)
    if prob is None:
        return None
    ticker = str(market.get("ticker") or "").strip()
    if not ticker:
        return None
    game_id = str(market.get("event_ticker") or ticker).strip()
    bid, ask = best_bid_ask(market)
    return {
        "sport": sport,
        "game_id": game_id,
        "venue": VENUE,
        "market_type": market_type,
        "side": _side_label(market) or "yes",
        "ticker": ticker,
        "prob": prob,
        "line": _line_from_market(market) if market_type != "moneyline" else None,
        "ts": ts,
        "phase": PHASE,
        "best_bid": bid,
        "best_ask": ask,
        "spread_bp": spread_bp(bid, ask),
    }


def _fetch_one_series(sport: str, series: str, market_type: str, *, http: HttpGet,
                      ts: Optional[str], now_dt: datetime, max_spread: float,
                      min_volume: float, min_size: float,
                      stats: Optional[Dict[str, Any]] = None,
                      sleep_fn: SleepFn = time.sleep,
                      governor: Optional[Any] = None,
                      n_active_sports: int = 1) -> List[Tick]:
    """Ticks for ONE (series_ticker, market_type) pair. [] on any failure -- a single
    series failing (network, bad body) must never sink the sport's other series.

    *ts*: caller-supplied stamp (tests pass *now_iso* -> deterministic, identical on
    every series). None (production default) -> HONEST PER-SERIES timestamp taken
    right after THIS series' own HTTP response lands, not the batch start -- avoids
    a later-staggered series inheriting an earlier, stale pre-fetch ts (latency fix;
    ts is a measurement field only, never a decision input).

    *stats*, if given, is MUTATED in place (kalshi_pacing.record_request/record_429).
    On a 429 (kalshi_pacing.is_429) this also takes a short, capped cool-down
    (kalshi_pacing.cooldown_after_429) before returning []. *governor*, if given,
    additionally gates the request (kalshi_rate_governor, fail-open) and is told
    of any 429. Never raises regardless of *stats*/*sleep_fn*/*governor*.
    """
    _governor_before(governor, sport, n_active_sports=n_active_sports)
    record_request(stats)
    params = {"series_ticker": series, "limit": 200, "status": "open"}
    url = "%s/markets?%s" % (_BASE, urllib.parse.urlencode(params))
    try:
        body = http(url)
    except Exception as exc:  # noqa: BLE001 -- isolate, never bubble past this series
        logger.warning("kalshi in-play markets failed for %s/%s: %s", sport, series, exc)
        if is_429(exc):
            record_429(stats)
            cooldown_after_429(exc, sleep_fn)
            _governor_report_429(governor)
        return []
    fetch_ts = ts if ts is not None else _now_iso()  # per-series stamp at actual response time
    markets = body.get("markets") if isinstance(body, dict) else None
    if not isinstance(markets, list):
        return []
    out: List[Tick] = []
    # The series_ticker filter is server-side; the startswith is a cheap defensive
    # guard so a stray cross-series market (a mixed page) can never leak through.
    relevant = [m for m in markets if isinstance(m, dict)
                and str(m.get("event_ticker", "")).startswith(series)]
    for m in relevant:
        # FUTURE-GAME guard: a liquid contract for a game days out (the next days' slate,
        # actively traded pre-tournament) is NOT in-play -- emitting it would let a pregame
        # price masquerade as live. Drop only the clearly-future games (today/tomorrow kept;
        # their true liveness is the downstream score-state bridge's call).
        if is_future_game(m.get("event_ticker") or m.get("ticker"), now_dt):
            continue
        if not is_liquid(m, max_spread=max_spread, min_volume=min_volume,
                         min_size=min_size):
            continue  # illiquid / untraded -> VOID, never a fake in-play price
        tick = _tick_from_market(sport, m, fetch_ts, market_type)
        if tick is not None:
            out.append(tick)
    return out


def fetch_inplay(sport: str, *, http: HttpGet = resilient_get_json,
                 now_iso: Optional[str] = None,
                 max_spread: float = MAX_SPREAD,
                 min_volume: float = MIN_VOLUME,
                 min_size: float = MIN_SIZE,
                 stats: Optional[Dict[str, Any]] = None,
                 sleep_fn: SleepFn = time.sleep,
                 stagger_sec: float = 0.0,
                 governor_caller: Optional[str] = None,
                 n_active_sports: int = 1) -> List[Tick]:
    """Live in-play ticks across ALL of *sport*'s wired Kalshi series.

    Iterates kalshi_series_spec.series_for(sport) -- one /markets?series_ticker=...
    call per (series_ticker, market_type) pair (e.g. mlb queries KXMLBGAME,
    KXMLBTOTAL, KXMLBSPREAD, KXMLBTEAMTOTAL) -- and tags every tick it parses with
    that pair's market_type. Applies the LIQUIDITY GATE to each raw market on its
    live *_dollars / *_fp fields and emits ONE canonical tick per market that
    clears it. An illiquid / untraded market is SKIPPED (VOID) -- never 0-filled,
    never faked into a live price. A series with zero open markets contributes
    nothing (honest empty); one series failing does not sink the others (isolated
    per-series in _fetch_one_series). *http* is injected for offline tests (default
    is the escalating transport.resilient_get_json, same seam as http_get_json).
    Never raises: an unsupported sport or a feed failure yields [].

    PACING (LANE 1): *stagger_sec* defaults to 0.0 (byte-identical to pre-LANE-1
    behavior). The production capture loop opts IN with stagger_sec=
    REQUEST_STAGGER_SEC (see inplay_capture_loop._default_inplay_fetch). *stats*,
    if given, is MUTATED with n_requests/n_429 regardless -- return type unchanged.

    RATE GOVERNOR (kalshi_rate_governor.py): *governor_caller* defaults to None
    (byte-identical, no governor -- every pre-existing caller/test UNCHANGED, same
    opt-in discipline as *stagger_sec*). The two production daemons opt IN
    explicitly ("capture", "snapshot"); env KALSHI_GOVERNOR_OFF=1 disables either.
    """
    pairs = series_for(sport)
    if not pairs:
        return []
    # ts: None in production (default) -> each series stamps its OWN tick at its actual
    # HTTP response time in _fetch_one_series (honest, avoids inflating measured latency
    # for later-staggered series). An explicit now_iso (tests) still wins everywhere, for
    # deterministic byte-identical output. now_dt (future-game guard) is independent of
    # this and always resolves to a real instant either way.
    ts = now_iso
    now_dt = _parse_iso_now(ts) if ts is not None else datetime.now(timezone.utc)
    governor = _resolve_governor(governor_caller)
    out: List[Tick] = []
    for i, (series, market_type) in enumerate(pairs):
        stagger_sleep(sleep_fn, stagger_sec, is_first=(i == 0))
        out.extend(_fetch_one_series(
            sport, series, market_type, http=http, ts=ts, now_dt=now_dt,
            max_spread=max_spread, min_volume=min_volume, min_size=min_size,
            stats=stats, sleep_fn=sleep_fn, governor=governor,
            n_active_sports=max(1, n_active_sports)))
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
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "fetch_inplay", "fetch_price_history", "is_liquid", "MAX_SPREAD",
    "MIN_VOLUME", "MIN_SIZE", "VENUE", "PHASE",
    "REQUEST_STAGGER_SEC", "MAX_429_COOLDOWN_SEC",
]
