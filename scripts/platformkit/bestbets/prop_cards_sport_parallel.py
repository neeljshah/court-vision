"""scripts.platformkit.bestbets.prop_cards_sport_parallel -- cross-sport fan-out.

LANE m13-sport-parallel: the scoring pass ran 356-800s vs the 660s SLA because
per-sport boards (independent) were scored SEQUENTIALLY. This module runs each
sport's board build concurrently so cycle wall-clock ~= slowest sport (~371s
MLB) instead of the SUM of all sports.

WHY THREADS NOT PROCESSES: the hot loop (_board_edges -> build_prop_board ->
prop_edge._gather) is I/O-bound (HTTP fetch to PrizePicks/Underdog/sportsbook
providers) with a modest pandas/dict-merge tail, not CPU-bound number crunching.
_gather() ALREADY runs its own per-PROVIDER ThreadPoolExecutor (prop_edge.py) --
nesting one more thread-pool level for per-SPORT fan-out is the same pattern,
stays in-process (no Windows spawn/pickling of provider objects, PropLine
dataclasses, or closures across a process boundary), and shares the GIL-safe
dict/module state the rest of this package already assumes. A ProcessPoolExecutor
would require every provider + PropLine + config object to be pickle-safe across
the spawn boundary (Windows has no fork) for a workload that is not CPU-bound --
not worth the complexity.

CROSS-SPORT SHARED STATE AUDIT (binding invariant: no races):
  * prop_cards_cache.line_cache_read/write -- keyed by a per-sport FILE
    (data/frontend/prop_line_cache/<sport>.json); two sports never touch the
    same path. Safe.
  * prop_cards_circuit_io._LAST_CIRCUIT_SKIPS -- a module-level dict WRITTEN
    per-sport (apply_circuit_breaker sets _LAST_CIRCUIT_SKIPS[sport] = ...).
    Different sports write different KEYS; CPython dict item-assignment is
    atomic under the GIL, so concurrent per-sport writes cannot corrupt the
    dict itself. Safe (no additional lock needed).
  * prop_circuit_breaker's on-disk state file (data/cache/odds_circuit_breaker/
    prop_circuit_breaker.json) is a SHARED file across ALL sports/providers:
    is_open()/record_result() do read -> mutate -> atomic-write (the write
    itself is atomic tmp+os.replace, but the READ-MODIFY-WRITE as a whole is
    not). Two sports now calling this concurrently on DIFFERENT provider keys
    could theoretically interleave: both read state v1, both mutate their own
    provider key, whichever saves LAST wins and silently drops the other
    thread's update for that cycle (a lost-update, not a corrupt file -- the
    write itself never tears). FLAGGED, NOT FIXED HERE: prop_circuit_breaker.py
    lives under scripts/platformkit/odds_provider/ and is owned by a different
    lane (m13-circuit; not in this lane's OWNS list), so this module does not
    edit it. Practical exposure is low (a lost update just means one sport's
    success/failure ping for one provider is dropped for one cycle -- the NEXT
    cycle's record_result recovers it; failure_threshold=3 means one dropped
    ping cannot itself mis-open or mis-close a circuit) but a future lane
    should add a per-state-file threading.Lock there (same registry pattern as
    clv_ledger_guarded_append.py) to close it properly.
  * Everything else read via _board_edges (prop_edge_config.get_config,
    parquet reads) is per-sport-keyed / read-only. Safe.

DETERMINISTIC OUTPUT: run_sports_parallel() returns results keyed by sport and
the caller (prop_cards.build_prop_cards) assembles the final list by iterating
_sports in its OWN fixed order -- never dict/future-completion order -- so the
served card list is byte-identical to the sequential build for the same inputs.

FAILURE ISOLATION: one sport's board build raising is caught HERE per-sport
(never lets one exception cancel sibling futures) and recorded honestly as
SCORE_ERROR in the returned per-sport error map; the sport contributes zero
cards for that cycle rather than a fabricated row.

OVERALL DEADLINE (2026-07-05 m13-freeze fix): per-provider fetches were already
bounded (_PROP_FETCH_DEADLINE_S in prop_edge.py), but nothing bounded the SUM of
a sport's sequential steps (feed fetch + up to two synth-fallback passes, each
re-reading the gamelog parquet) -- under live-slate load one sport's total could
run long enough to blow the 240s props_pred_tick score_with_timeout budget even
though every individual fetch finished inside its own 30s cap. deadline_sec adds
a WALL-CLOCK ceiling on the whole fan-out using the same recipe already proven in
frontend/bestbets_routes.py (_LIVE_DEADLINE_SEC): an explicit (non-`with`) pool +
as_completed(timeout=...) + shutdown(wait=False, cancel_futures=True) so a slow
sport's still-running future is ABANDONED (never awaited) rather than blocking the
caller past the deadline -- the `with` form's __exit__ calls shutdown(wait=True)
unconditionally, which would defeat this. Py3.10: catches
concurrent.futures.TimeoutError, NOT the builtin TimeoutError.

Stdlib + repo-internal only. ASCII-only. <=300 LOC.
Per-file test: scripts/platformkit/bestbets/test_prop_cards_sport_parallel.py
"""
from __future__ import annotations

import concurrent.futures
import logging
import time
from concurrent.futures import TimeoutError as _FuturesTimeout
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Cap concurrent sport workers. Small (sport count is O(2-4) today); a fixed
# ceiling avoids an unbounded pool if _sports ever grows a lot.
MAX_SPORT_WORKERS = 8

# Overall wall-clock ceiling on the whole fan-out (all sports together), well
# below the 240s props_pred_tick score_with_timeout budget so this deadline
# fires FIRST and the caller gets an honest partial board instead of the outer
# timeout discarding everything. Tune via PROP_SPORT_FANOUT_DEADLINE_S.
def _env_float(name: str, default: float) -> float:
    import os
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


DEFAULT_FANOUT_DEADLINE_SEC = _env_float("PROP_SPORT_FANOUT_DEADLINE_S", 180.0)

# Last-cycle per-sport error/timing metadata, for honest cycle-metadata
# reporting (prop_cards.last_sport_errors/last_sport_seconds delegate here).
# Never fabricated; empty until a sport actually errors / a cycle actually
# runs. Module-level (single-threaded per-tick caller writes via
# record_last_cycle(); readers get a snapshot copy).
_LAST_SPORT_ERRORS: Dict[str, str] = {}
_LAST_SPORT_SECONDS: Dict[str, float] = {}


def record_last_cycle(errors: Dict[str, str], per_sport_seconds: Dict[str, float]) -> None:
    """Record this cycle's per-sport errors/timing (called once per
    build_prop_cards() cycle). Never raises."""
    try:
        _LAST_SPORT_ERRORS.clear()
        _LAST_SPORT_ERRORS.update(errors or {})
        _LAST_SPORT_SECONDS.clear()
        _LAST_SPORT_SECONDS.update(per_sport_seconds or {})
    except Exception:  # noqa: BLE001
        pass


def last_sport_errors() -> Dict[str, str]:
    """{sport: "SCORE_ERROR: ..."} for the most recent cycle. Never raises."""
    return dict(_LAST_SPORT_ERRORS)


def last_sport_seconds() -> Dict[str, float]:
    """{sport: wall-clock seconds} for the most recent cycle. Never raises."""
    return dict(_LAST_SPORT_SECONDS)


def run_sports_parallel(
    sports: Tuple[str, ...],
    build_one: Callable[[str], List[Dict[str, Any]]],
    deadline_sec: Optional[float] = DEFAULT_FANOUT_DEADLINE_SEC,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, float]]:
    """Run build_one(sport) for every sport in *sports* CONCURRENTLY (threads),
    bounded by an OVERALL *deadline_sec* wall clock (None/<=0 = no deadline, the
    old unbounded behavior; tests rely on this).

    Returns (cards, errors, per_sport_seconds):
      * cards -- all sports' cards concatenated in the FIXED order of *sports*
        (never dict/completion order) so output is deterministic regardless of
        which sport's fetch finishes first.
      * errors -- {sport: "SCORE_ERROR: <repr>"} for any sport whose build_one
        raised; that sport contributes [] cards (never fabricated rows). A sport
        still running when the deadline fires is recorded as
        "SCORE_ERROR: fanout deadline exceeded" (honest partial, not fabricated).
        Empty dict when every sport finished in time and succeeded.
      * per_sport_seconds -- {sport: wall-clock seconds} for the proof artifact
        (only for sports that finished; a deadline-abandoned sport has none).

    One sport raising or timing out NEVER cancels or corrupts siblings (each
    future's exception is caught independently; abandoned futures are left to
    finish/die on their own -- Python threads cannot be force-killed safely, the
    SAME daemon-thread contract as props_score_timeout.score_with_timeout).
    Never raises out."""
    _sports = tuple(sports or ())
    if not _sports:
        return [], {}, {}
    if len(_sports) == 1:
        # No fan-out benefit for a single sport; skip the pool entirely (no
        # deadline applied -- there is no sibling to protect from a hang, and
        # the caller's own outer timeout already bounds this case).
        sport = _sports[0]
        t0 = time.time()
        try:
            cards = list(build_one(sport) or [])
            return cards, {}, {sport: time.time() - t0}
        except Exception as exc:  # noqa: BLE001 -- isolate; never raise out
            logger.debug("prop_cards_sport_parallel: %s failed: %s", sport, exc)
            return [], {sport: "SCORE_ERROR: %r" % (exc,)}, {sport: time.time() - t0}

    workers = min(MAX_SPORT_WORKERS, len(_sports))
    per_sport_cards: Dict[str, List[Dict[str, Any]]] = {}
    errors: Dict[str, str] = {}
    per_sport_seconds: Dict[str, float] = {}

    def _timed(sport: str) -> List[Dict[str, Any]]:
        t0 = time.time()
        try:
            return list(build_one(sport) or [])
        finally:
            per_sport_seconds[sport] = time.time() - t0

    # NB: NOT `with ThreadPoolExecutor(...)` -- its __exit__ calls
    # shutdown(wait=True) unconditionally, which BLOCKS until every sport's
    # future finishes even after our as_completed deadline fires, defeating the
    # deadline (same footgun documented in frontend/bestbets_routes.py). Manage
    # the pool explicitly + shutdown non-blocking so this returns AT the deadline.
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    try:
        futs = {ex.submit(_timed, sport): sport for sport in _sports}
        try:
            wait_kw = {} if not deadline_sec or deadline_sec <= 0 else {"timeout": deadline_sec}
            for fut in concurrent.futures.as_completed(futs, **wait_kw):
                sport = futs[fut]
                try:
                    per_sport_cards[sport] = fut.result()
                except Exception as exc:  # noqa: BLE001 -- isolate per sport
                    logger.debug("prop_cards_sport_parallel: %s failed: %s",
                                sport, exc)
                    per_sport_cards[sport] = []
                    errors[sport] = "SCORE_ERROR: %r" % (exc,)
        except _FuturesTimeout:
            logger.warning("prop_cards_sport_parallel: fanout hit %.0fs deadline "
                           "(%d/%d sports done)", deadline_sec, len(per_sport_cards),
                           len(_sports))
            for sport in _sports:
                if sport not in per_sport_cards:
                    errors[sport] = "SCORE_ERROR: fanout deadline exceeded"
                    per_sport_cards[sport] = []
    except Exception as exc:  # noqa: BLE001 -- pool machinery itself must never raise
        logger.debug("prop_cards_sport_parallel: pool failed: %s", exc)
        for sport in _sports:
            if sport not in per_sport_cards:
                errors.setdefault(sport, "SCORE_ERROR: %r" % (exc,))
                per_sport_cards.setdefault(sport, [])
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    # DETERMINISTIC ORDER: assemble by the caller's fixed sport order, never by
    # dict/future-completion order.
    cards: List[Dict[str, Any]] = []
    for sport in _sports:
        cards.extend(per_sport_cards.get(sport, []))
    return cards, errors, per_sport_seconds


def bucket_model_only_by_sport(
        sports: Tuple[str, ...],
        build_one: Callable[[str], List[Dict[str, Any]]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Run *build_one(sport)* per sport through run_sports_parallel (default
    deadline) and bucket the resulting cards by their own "sport" key. Used by
    prop_cards_bounded's per-sport model-only builders (feed + synth-fallback)
    so that per-sport work is BOUNDED here too -- not just the feed fetch inside
    build_prop_cards. Errors/timing are discarded (the per-sport SCORE_ERROR
    case degrades to an honest empty list for that sport, never fabricated)."""
    cards, _errors, _secs = run_sports_parallel(sports, build_one)
    by_sport: Dict[str, List[Dict[str, Any]]] = {s: [] for s in sports}
    for c in cards:
        by_sport.setdefault(c.get("sport"), []).append(c)
    return by_sport


__all__ = ["run_sports_parallel", "bucket_model_only_by_sport", "MAX_SPORT_WORKERS",
           "record_last_cycle", "last_sport_errors", "last_sport_seconds"]
