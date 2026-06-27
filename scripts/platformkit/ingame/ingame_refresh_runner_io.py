"""scripts.platformkit.ingame.ingame_refresh_runner_io -- IO + loop plumbing split
out of ingame_refresh_runner.py to keep each file <=300 LOC (mirrors the wave's
ingame_layer_gate_nba_io.py pattern).

NON-MATH glue only:
  * _append_jsonl       : append-only jsonl writer (proposals / status rows).
  * _call_feed          : call the settled-finals feed, threading seen game_ids when
                          the provider accepts them (out-of-order late finals).
  * run_refresh_forever : the always-on, per-sport isolated forever loop that drives
                          refresh_cycle (injected here to avoid a circular import).

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; stdlib only.
Calibration (held-out Brier), NEVER a market edge. No $ anywhere.
"""
from __future__ import annotations

import inspect
import pathlib
import time
from typing import Any, Callable, Dict, List, Optional, Sequence


def append_jsonl(path: pathlib.Path, rec: Dict[str, Any]) -> None:
    # Crash-safe append (read-modify-write + os.replace): a crash mid-write can
    # never leave a partial trailing line for the forever loop to choke on.
    from scripts.platformkit.io_atomic import append_jsonl_atomic
    append_jsonl_atomic(path, rec, encoding="ascii", sort_keys=True, default=str)


def call_feed(fn: Callable[..., Sequence[Dict[str, Any]]], sport: str,
              high_water: str, seen: set) -> Sequence[Dict[str, Any]]:
    """Call the settled-finals feed, passing seen game_ids when it accepts them.

    A seen_ids-aware provider (settled_finals.settled_since) then surfaces an
    out-of-order late final (key < high-water) instead of dropping it. Older/injected
    feeds that take only `since` still work; the runner re-dedups against disk anyway.
    """
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    if "seen_ids" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(sport, since=high_water, seen_ids=sorted(seen))
    return fn(sport, since=high_water)


def run_refresh_forever(refresh_cycle: Callable[..., Any], result_factory: Callable[..., Any],
                        error_decision: str, *, sports: Sequence[str],
                        settled_games_fn: Callable[..., Sequence[Dict[str, Any]]],
                        ingest_fn: Callable[..., Sequence[Dict[str, Any]]],
                        gate_fn: Callable[[str], Any],
                        fit_fn: Callable[[str], Dict[str, Any]],
                        clock: Optional[Callable[[], float]] = None,
                        sleep: Optional[Callable[[float], None]] = None,
                        cadence_sec: float = 3600.0,
                        max_cycles: Optional[int] = None,
                        should_stop: Optional[Callable[[], bool]] = None,
                        on_tick: Optional[Callable[[], None]] = None,
                        **cycle_kwargs: Any) -> List[Any]:
    """Always-on, per-sport isolated refresh loop. RESUMES from the checkpoint.

    refresh_cycle / result_factory / error_decision are injected by the runner module
    (avoids a circular import). One sport's failure (dead feed / raising gate) is ONE
    error CycleResult and the loop keeps going for the others. `cadence_sec` defaults to
    hourly (polite). bounded by `max_cycles` for tests; `should_stop()` brakes cleanly;
    `on_tick` beats a supervisor heartbeat each wake.
    """
    clock = clock or time.time
    sleep = sleep or time.sleep
    results: List[Any] = []
    tick = 0
    while True:
        if should_stop is not None and should_stop():
            break
        if max_cycles is not None and tick >= max_cycles:
            break
        if on_tick is not None:
            try:
                on_tick()
            except Exception:  # noqa: BLE001 -- heartbeat must never sink the loop
                pass
        for sport in sports:
            try:
                res = refresh_cycle(
                    sport, settled_games_fn=settled_games_fn, ingest_fn=ingest_fn,
                    gate_fn=gate_fn, fit_fn=fit_fn, now=clock(), **cycle_kwargs)
            except Exception as exc:  # noqa: BLE001 -- defense in depth
                res = result_factory(sport, error_decision,
                                     ["refresh_cycle raised: %s" % exc])
            results.append(res)
        tick += 1
        if max_cycles is not None and tick >= max_cycles:
            break
        if should_stop is not None and should_stop():
            break
        sleep(cadence_sec)
    return results


__all__ = ["append_jsonl", "call_feed", "run_refresh_forever"]
