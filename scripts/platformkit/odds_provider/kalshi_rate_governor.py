"""scripts.platformkit.odds_provider.kalshi_rate_governor -- cross-process pacing.

ADDITIVE to (never replaces) kalshi_pacing.py: kalshi_pacing's stagger+cooldown
is LOCAL to one fetch_inplay call; this module is the GLOBAL, cross-PROCESS
budget that was missing. See docs/research/organization-sprint/
PROPOSED_kalshi_rate_governor_2026-07-05.md for the diagnosis (1678 unpaced
m2_inplay 429s/day vs 197 for the paced m2_inplay_capture; both daemons hit the
same venue with no shared budget; capture cycle_duration 34.7s vs a 20s target).

DESIGN: each daemon PROCESS gets its own token bucket sized to a configured
fair share of BASE_RPS (DEFAULT_RATE_SHARES) -- within one process, a
deficit-based per-sport fair queue keeps one sport's series burst from
starving another sport's tick. On any 429, on_429() writes a fail-open
pressure record to a SHARED JSON state file (atomic tmp+replace, mirrors
inplay_capture_loop._write_heartbeat); every acquire() (this process, or the
other daemon's process on its next read) sees the pressure and halves its
effective refill rate for a decay window -- the cross-process "shared wall"
coordination kalshi_pacing.py's own docstring diagnoses but cannot close
alone (its cooldown is local-only). KALSHI_GOVERNOR_OFF=1 makes acquire() an
immediate no-op (decision paths BYTE-UNCHANGED; only spaces out HTTP calls).
Fail-open throughout: a missing/corrupt state file or a broken clock/sleep_fn
never raises, never blocks (same discipline as kalshi_pacing.stagger_sleep).

INTEGRATION: wired at the single HTTP choke point, inplay_kalshi._fetch_one_series.
fetch_inplay's governor_caller defaults to None (byte-identical, no governor) --
same opt-in discipline REQUEST_STAGGER_SEC/stagger_sec already use in this file
tree, so every pre-existing caller/test stays UNCHANGED. Both production daemons
opt IN explicitly: inplay_capture_loop._default_inplay_fetch passes
governor_caller="capture"; inplay_snapshot_daemon._governed_default_fetch (a
thin wrapper, since inplay_feed.default_fetch has 4 OTHER callers that must stay
ungoverned) passes governor_caller="snapshot".

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII only; stdlib
only. Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_rate_governor.py -q
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

SleepFn = Callable[[float], None]
ClockFn = Callable[[], float]

# Conservative shared ceiling: Kalshi's documented keyless-tier limit is noted
# in-repo as ~30 rps (inplay_kalshi.py:70-72); this stays well under that so
# there is headroom for the OTHER Kalshi callers in this repo not wired to the
# governor yet (pregame kalshi.py, depth_capture.py, inplay_history.py candles).
BASE_RPS = 15.0

# Per-process fair shares of BASE_RPS (PROPOSED doc + prompt default, since the
# doc did not specify a cross-process split): capture is the slower/steadier
# LIVE_INTERVAL_SEC=20s loop; snapshot is the faster FAST_INTERVAL_SEC=5s loop
# with 8 sports (vs capture's 6) -- it gets the larger share. feed_health added
# 2026-07-07: a 10-minute-interval health probe (7 sports, 1 call each), not a
# hot loop -- a small fixed share is enough to stop it 429ing itself while it
# still yields to the two live-trading daemons. close_capture added 2026-07-07:
# a 900s-interval settled-row sweep, not a hot loop -- without a registered
# share it fell to the unknown-caller default (0.5), which on a full live slate
# pushed the aggregate demand past the shared ceiling (429 storm -> slow sweeps
# -> m18 heartbeat flap). backfill added 2026-07-09: 8 parallel settled-market
# backfill processes each paced their OWN 1 req/s locally but never consulted
# this governor, stacking unpaced on top of the live fleet's ~15rps budget and
# tripping a 1,254-count 429 penalty (all feed probes RED ~50min). A small fixed
# share (same unknown-caller trap as close_capture) plus run_all_backfills'
# max-2-concurrent cap keeps a backfill fleet inside the shared budget.
# aggregate added 2026-07-14: the default_providers() stack (line daemon, pm
# paper tick, best-bets compute, frontend serve) hit Kalshi with NO governor at
# all -- several unpaced processes stacked on the live daemons' budget and
# 429-stormed the venue (n_429_total=2606). One call per sport per tick, so a
# small per-process share is ample; the shared pressure file coordinates the rest.
# depth_capture / inplay_history added 2026-07-18 (go-live hardening audit,
# findings 19/20): both were listed above as UNWIRED Kalshi callers. Both are
# bounded, non-hot-loop passes (a CLI snapshot / a historical candle backfill),
# so a small fixed share is enough.
DEFAULT_RATE_SHARES: Dict[str, float] = {"capture": 0.35, "snapshot": 0.65,
                                         "feed_health": 0.15, "close_capture": 0.15,
                                         "backfill": 0.10, "aggregate": 0.15,
                                         "depth_capture": 0.10, "inplay_history": 0.10}

# Bucket capacity: a small burst allowance (2s worth of tokens at the full
# per-process rate) so a fresh process start doesn't have to wait from empty,
# but cannot burst indefinitely.
BURST_SECONDS = 2.0

# 429 backoff: on any reported 429, halve the effective rate for this many
# seconds (linear decay back to 1.0x over the window), shared cross-process via
# the state file.
BACKOFF_DECAY_SEC = 30.0
BACKOFF_MULTIPLIER = 0.5

DEFAULT_STATE_PATH = Path("data/cache/kalshi_governor_state.json")

ENV_KILL_SWITCH = "KALSHI_GOVERNOR_OFF"


def _now() -> float:
    return time.time()


def _kill_switch_on() -> bool:
    """True iff the env kill switch is set -- fail-open OFF path, checked fresh
    every call (no caching) so a mid-run env flip takes effect immediately."""
    return os.environ.get(ENV_KILL_SWITCH, "").strip() not in ("", "0", "false", "False")


def _read_state(path: Path) -> Dict[str, Any]:
    """Best-effort read of the shared pressure file. Missing/corrupt -> {} (no
    pressure), never raises -- fail-open is the binding invariant here."""
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeDecodeError):
        return {}


def _write_state(path: Path, data: Dict[str, Any]) -> None:
    """Atomic tmp+replace write (mirrors inplay_capture_loop._write_heartbeat).
    Best-effort: a write failure is logged, never raised -- the governor must
    never sink the caller's real request over an observability write."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except OSError as exc:
        logger.debug("kalshi_rate_governor state write failed: %s", exc)


def _pressure_multiplier(state: Dict[str, Any], now: float) -> float:
    """Effective rate multiplier from the shared 429-pressure record: 1.0 (no
    pressure) unless a 429 landed within BACKOFF_DECAY_SEC, in which case a
    linear ramp from BACKOFF_MULTIPLIER back up to 1.0 over the window."""
    last_429 = state.get("last_429_ts")
    if not isinstance(last_429, (int, float)):
        return 1.0
    age = now - float(last_429)
    if age < 0 or age >= BACKOFF_DECAY_SEC:
        return 1.0
    frac = age / BACKOFF_DECAY_SEC  # 0 (just hit) .. 1 (fully decayed)
    return BACKOFF_MULTIPLIER + (1.0 - BACKOFF_MULTIPLIER) * frac


class KalshiRateGovernor:
    """Per-process token bucket + per-sport fairness + shared 429 backoff.

    One instance is meant to be a module-level singleton PER PROCESS (each
    daemon has its own bucket in memory); the two daemons coordinate only
    through the shared state FILE (429 pressure), never in-memory, since they
    are separate OS processes. Fail-open throughout: any internal error yields
    "acquire granted immediately", never a hang or a crash.
    """

    def __init__(self, *, caller: str = "snapshot",
                rate_share: Optional[float] = None,
                base_rps: float = BASE_RPS,
                state_path: Path = DEFAULT_STATE_PATH,
                clock: ClockFn = _now,
                sleep_fn: SleepFn = time.sleep) -> None:
        self._caller = caller
        # Unknown caller (a typo'd/unregistered caller string) gets a SMALL
        # default share, not half the fleet budget -- a typo must not silently
        # grant itself the same headroom as a registered, reviewed daemon.
        share = rate_share if rate_share is not None else DEFAULT_RATE_SHARES.get(caller, 0.05)
        self._base_rate = max(0.1, base_rps * share)
        self._capacity = self._base_rate * BURST_SECONDS
        self._tokens = self._capacity
        self._state_path = state_path
        self._clock = clock
        self._sleep_fn = sleep_fn
        # A broken clock at construction time must never crash the caller (same
        # fail-open promise acquire()/on_429() make) -- fall back to time.time().
        start = self._safe_clock()
        self._last_refill = start
        # Per-sport deficit fairness: tokens already spent this decay window,
        # keyed by sport. Reset lazily when the window rolls over.
        self._sport_spent: Dict[str, float] = {}
        self._window_start = start

    def _safe_clock(self) -> float:
        try:
            return self._clock()
        except Exception:  # noqa: BLE001 -- fail-open, never raises from a broken clock
            return time.time()

    def _refill(self, now: float, multiplier: float) -> None:
        elapsed = max(0.0, now - self._last_refill)
        self._tokens = min(self._capacity, self._tokens + elapsed * self._base_rate * multiplier)
        self._last_refill = now

    def _reset_fairness_window_if_stale(self, now: float) -> None:
        # A fresh per-sport fairness window every BACKOFF_DECAY_SEC keeps one
        # sport's earlier burst from permanently depressing its future share.
        if now - self._window_start >= BACKOFF_DECAY_SEC:
            self._sport_spent = {}
            self._window_start = now

    def acquire(self, sport: str, *, n_active_sports: int = 1,
               max_wait_sec: float = 5.0) -> bool:
        """Block (bounded) until one token is available for *sport*, honoring
        per-sport fairness and any shared 429 pressure. Returns True once
        granted, or True immediately if the kill switch is on or on any
        internal error (fail-open -- a governor bug must never block a real
        request indefinitely). *max_wait_sec* bounds the wait so a starved
        sport still eventually fires rather than hanging the caller forever.
        """
        if _kill_switch_on():
            return True
        try:
            return self._acquire_inner(sport, n_active_sports=n_active_sports,
                                       max_wait_sec=max_wait_sec)
        except Exception as exc:  # noqa: BLE001 -- fail-open, never blocks the fetch
            logger.debug("kalshi_rate_governor acquire failed open: %s", exc)
            return True

    def _acquire_inner(self, sport: str, *, n_active_sports: int,
                       max_wait_sec: float) -> bool:
        deadline = self._clock() + max(0.0, max_wait_sec)
        n_active = max(1, int(n_active_sports))
        while True:
            now = self._clock()
            self._reset_fairness_window_if_stale(now)
            state = _read_state(self._state_path)
            multiplier = _pressure_multiplier(state, now)
            self._refill(now, multiplier)
            fair_share = self._capacity / n_active
            spent = self._sport_spent.get(sport, 0.0)
            if self._tokens >= 1.0 and spent < fair_share:
                self._tokens -= 1.0
                self._sport_spent[sport] = spent + 1.0
                return True
            if now >= deadline:
                # Bounded wait exhausted: grant anyway (VOID-never-hang) rather
                # than stall the caller past max_wait_sec.
                return True
            self._sleep_fn(min(0.25, max(0.01, deadline - now)))

    def on_429(self) -> None:
        """Record a 429 in the SHARED state file so every governor instance
        (this process and the other daemon's process, on its next read) backs
        off together. Best-effort: never raises."""
        try:
            state = _read_state(self._state_path)
            state["last_429_ts"] = self._clock()
            state["last_429_caller"] = self._caller
            state["n_429_total"] = int(state.get("n_429_total", 0)) + 1
            _write_state(self._state_path, state)
        except Exception as exc:  # noqa: BLE001 -- observability write, never fatal
            logger.debug("kalshi_rate_governor on_429 record failed: %s", exc)


_SINGLETONS: Dict[str, KalshiRateGovernor] = {}


def get_governor(caller: str = "snapshot") -> KalshiRateGovernor:
    """Module-level per-caller singleton (one bucket per process identity).
    Cheap to call repeatedly -- returns the same instance for the same
    *caller* string within this process."""
    inst = _SINGLETONS.get(caller)
    if inst is None:
        inst = KalshiRateGovernor(caller=caller)
        _SINGLETONS[caller] = inst
    return inst


# The three helpers below exist so OTHER modules (inplay_kalshi.py) need only a
# single line at each call site, no local try/except -- every failure mode here
# is fail-open (None/no-op), never raises past this module.


def resolve_governor(caller: Optional[str]) -> Optional[KalshiRateGovernor]:
    """None if *caller* is None (fully skip); else get_governor(caller), or
    None if that itself errors (unpaced, not fatal)."""
    if caller is None:
        return None
    try:
        return get_governor(caller)
    except Exception as exc:  # noqa: BLE001 -- governor unavailable -> unpaced, not fatal
        logger.debug("kalshi rate governor unavailable for %s: %s", caller, exc)
        return None


def before_request(governor: Optional[KalshiRateGovernor], sport: str, *,
                   n_active_sports: int = 1) -> None:
    """Acquire a token if *governor* is given; no-op otherwise or on error."""
    if governor is None:
        return
    try:
        governor.acquire(sport, n_active_sports=n_active_sports)
    except Exception as exc:  # noqa: BLE001 -- fail-open, never blocks a real fetch
        logger.debug("kalshi rate governor acquire failed open for %s: %s", sport, exc)


def report_429(governor: Optional[KalshiRateGovernor]) -> None:
    """Report a 429 if *governor* is given; no-op otherwise or on error."""
    if governor is None:
        return
    try:
        governor.on_429()
    except Exception as exc:  # noqa: BLE001 -- observability, never fatal
        logger.debug("kalshi rate governor on_429 report failed: %s", exc)


__all__ = [
    "BASE_RPS",
    "DEFAULT_RATE_SHARES",
    "BURST_SECONDS",
    "BACKOFF_DECAY_SEC",
    "BACKOFF_MULTIPLIER",
    "DEFAULT_STATE_PATH",
    "ENV_KILL_SWITCH",
    "KalshiRateGovernor",
    "get_governor",
    "resolve_governor",
    "before_request",
    "report_429",
]
