"""scripts.platformkit.improve.recalibrate_with_corpus -- thin compose function that
bridges the orphaned CLV corpus into the self-improve candidate pipeline.

The problem: selfimprove_daemon passes corpora:[] to every recalibrate_fn call, so
every candidate is permanently REPLICATION_PENDING even when the sentinel is ON and a
genuine model-beats-close window exists. This module supplies the missing compose step.

recalibrate_with_corpus(name, settled, *, base_build, inject) -> Optional[dict]
  (a) Calls base_build(name, settled) -> the base candidate (or None = NO_CANDIDATE).
  (b) When pipeline_enabled() AND base_build returned a non-None candidate, passes it
      through inject(candidate, settled) to append the CLV close corpus IF the window
      genuinely beats the close on outcome-Brier.
  (c) Returns the (possibly unchanged) candidate.

INVARIANTS:
  INERT when sentinel absent: base candidate returned byte-identical, corpora==[] -> the
    daemon's downstream verdict stays NO_CANDIDATE / REPLICATION_PENDING unchanged.
  Shrink-toward-close / all-proxy -> no phantom corpus (inject returns unchanged).
  base_build returns None -> returns None (NO_CANDIDATE), never raises.
  inject raising -> candidate returned UNCHANGED (purity, never discards a valid candidate).
  No $/roi/pnl/edge key anywhere. vs_close stays UNPROVEN on every path.
  Never raises. stdlib + repo-internal; ASCII; <=300 LOC.

Daemon wire-in: PROPOSE-ONLY in docs/research/selfimprove_corpus_wire.py. This module
does NOT edit selfimprove_daemon.py; it is a plug-in recalibrate_fn factory only.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, Sequence

from scripts.platformkit.improve.pipeline_flag import pipeline_enabled

logger = logging.getLogger("recalibrate_with_corpus")

# vs_close invariant: this layer never stamps an upgrade.
_UNPROVEN = "UNPROVEN"


def recalibrate_with_corpus(
    name: str,
    settled: Sequence[Dict[str, Any]],
    *,
    base_build: Callable[..., Optional[Dict[str, Any]]],
    inject: Callable[..., Optional[Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """Compose base_build + inject into a single recalibrate_fn the daemon can call.

    Parameters
    ----------
    name:
        Market / sport name passed through to base_build.
    settled:
        Batch of newly-settled game dicts (the same list the daemon injects).
    base_build:
        Callable matching recalibrator.build_candidate(name, settled, ...) ->
        Optional[dict]. Must be the REAL build_candidate or a sentinel-respecting
        equivalent; this function does NOT re-impose MF1 (base_build already carries it).
    inject:
        Callable matching clv_corpus_inject.inject_corpus(candidate, settled, ...) ->
        Optional[dict]. Must already carry its own sentinel guard. This function calls
        inject ONLY when sentinel is ON to avoid a redundant filesystem check when inert.

    Returns
    -------
    Optional[dict]
        The candidate dict (possibly with a CLV corpus appended) or None.

    Guarantee: never raises; any exception at any step returns either None (when
    base_build failed/returned None) or the last-known-good candidate (when inject fails).
    """
    # Step (a): build the base candidate. base_build owns its own MF1 kill-switch.
    try:
        candidate = base_build(name, settled)
    except Exception as exc:  # noqa: BLE001 -- purity: treat raising base_build as None
        logger.debug("recalibrate_with_corpus(%s): base_build raised -> NO_CANDIDATE: %s",
                     name, exc)
        return None

    # NO_CANDIDATE path: return immediately, no corpus attempt.
    if candidate is None:
        return None

    # Step (b): when sentinel is ON attempt to append the CLV close corpus.
    # When sentinel is absent we return the base candidate unchanged (inert).
    # inject carries its own sentinel guard too; this outer check avoids a
    # filesystem stat when we are already inert (belt-and-suspenders, not required).
    if not pipeline_enabled():
        # Sentinel absent -> inert: return base candidate byte-identical, corpora==[].
        return candidate

    try:
        injected = inject(candidate, settled)
    except Exception as exc:  # noqa: BLE001 -- purity: inject failing must not lose candidate
        logger.debug("recalibrate_with_corpus(%s): inject raised -> candidate unchanged: %s",
                     name, exc)
        return candidate

    # If inject returned None (should not happen per its contract, but guard it):
    # fall back to the unmodified base candidate.
    if injected is None:
        logger.debug("recalibrate_with_corpus(%s): inject returned None -> base unchanged",
                     name)
        return candidate

    # Enforce vs_close invariant: this layer never stamps an upgrade.
    if injected.get("vs_close") != _UNPROVEN:
        out = dict(injected)
        out["vs_close"] = _UNPROVEN
        return out

    return injected


def make_recalibrate_fn(
    *,
    base_build: Callable[..., Optional[Dict[str, Any]]],
    inject: Callable[..., Optional[Dict[str, Any]]],
) -> Callable[[str, Sequence[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    """Return a recalibrate_fn(name, settled) closure suitable for daemon injection.

    Usage (PROPOSE-ONLY snippet; see docs/research/selfimprove_corpus_wire.py):
        from scripts.platformkit.improve.recalibrate_with_corpus import make_recalibrate_fn
        from scripts.platformkit.improve.recalibrator import build_candidate
        from scripts.platformkit.improve.clv_corpus_inject import inject_corpus
        recalibrate_fn = make_recalibrate_fn(
            base_build=build_candidate, inject=inject_corpus)
        # pass recalibrate_fn= to run_cycle(...)
    """
    def _fn(name: str, settled: Sequence[Dict[str, Any]],
            *_args: Any, **_kw: Any) -> Optional[Dict[str, Any]]:
        return recalibrate_with_corpus(
            name, settled, base_build=base_build, inject=inject)
    return _fn


__all__ = ["recalibrate_with_corpus", "make_recalibrate_fn"]
