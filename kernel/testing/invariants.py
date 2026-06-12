"""
kernel/testing/invariants.py
-----------------------------
Reusable, sport-blind invariant checkers for adapter conformance tests.

No domain imports; no heavy dependencies.  Callers pass plain accessor
callables so the checkers stay data-structure-agnostic.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, Callable, Dict, List, Sequence, Tuple


# ---------------------------------------------------------------------------
# fold_scores
# ---------------------------------------------------------------------------

def fold_scores(
    events: Sequence[Any],
    get_points: Callable[[Any], int],
    get_side: Callable[[Any], str],
) -> Dict[str, int]:
    """Fold a sequence of canonical events into per-side point totals.

    Args:
        events:     Any iterable of event objects (dicts, dataclasses, …).
        get_points: Accessor returning the integer points for an event.
        get_side:   Accessor returning a string key identifying the scoring
                    side (e.g. ``"home"`` / ``"away"``).

    Returns:
        ``{side: total_points, …}`` for every side that appears.
    """
    totals: Dict[str, int] = {}
    for ev in events:
        side = get_side(ev)
        totals[side] = totals.get(side, 0) + get_points(ev)
    return totals


# ---------------------------------------------------------------------------
# check_truncation_invariance
# ---------------------------------------------------------------------------

def check_truncation_invariance(
    events: Sequence[Any],
    get_points: Callable[[Any], int],
    get_side: Callable[[Any], str],
    expected_totals: Dict[str, int],
) -> Tuple[bool, Dict[str, Any]]:
    """Assert that folding ALL events reproduces *expected_totals* exactly.

    This generalises the DOMAIN_ADAPTER_SPEC §2(c) invariant: if you fold
    the complete event log the side totals must match the declared final
    score.

    Returns:
        ``(passed, detail)`` where *detail* always contains ``"actual"`` and
        ``"expected"``; on failure it also contains ``"mismatches"``.
    """
    actual = fold_scores(events, get_points, get_side)
    mismatches = {
        side: {"expected": expected_totals[side], "actual": actual.get(side)}
        for side in expected_totals
        if actual.get(side) != expected_totals[side]
    }
    # Also flag sides present in actual but absent from expected
    for side in actual:
        if side not in expected_totals:
            mismatches[side] = {"expected": None, "actual": actual[side]}

    detail: Dict[str, Any] = {"actual": actual, "expected": expected_totals}
    if mismatches:
        detail["mismatches"] = mismatches
        return False, detail
    return True, detail


# ---------------------------------------------------------------------------
# check_prefix_running_scores
# ---------------------------------------------------------------------------

def check_prefix_running_scores(
    events: Sequence[Any],
    get_points: Callable[[Any], int],
    get_side: Callable[[Any], str],
    get_running: Callable[[Any, str], int],
    cuts: Sequence[int],
) -> List[Tuple[int, str, int, int, bool]]:
    """At each cut index verify folded score == event's running-score accessor.

    For each ``(cut, side)`` pair the folded total of ``events[:cut]`` must
    equal ``get_running(events[cut - 1], side)``.

    Args:
        events:      Full event sequence.
        get_points:  Points accessor.
        get_side:    Side-key accessor.
        get_running: ``(event, side) -> int`` — returns the cumulative score
                     for *side* as recorded **on** that event.
        cuts:        1-based cut indices to check (must be ≥ 1).

    Returns:
        List of ``(cut, side, folded, recorded, passed)`` tuples — one entry
        per ``(cut, side)`` combination observed up to that cut.
    """
    results: List[Tuple[int, str, int, int, bool]] = []
    for cut in cuts:
        if cut < 1 or cut > len(events):
            continue
        prefix = events[:cut]
        folded = fold_scores(prefix, get_points, get_side)
        anchor_event = events[cut - 1]
        for side, total in folded.items():
            recorded = get_running(anchor_event, side)
            results.append((cut, side, total, recorded, total == recorded))
    return results


# ---------------------------------------------------------------------------
# check_registry_order
# ---------------------------------------------------------------------------

def check_registry_order(
    target_names: Sequence[str],
    expected_order: Sequence[str],
) -> bool:
    """Return True iff *target_names* equals *expected_order* element-by-element.

    Useful for asserting that a stat-name registry tuple was not accidentally
    reordered between schema versions.
    """
    return list(target_names) == list(expected_order)


# ---------------------------------------------------------------------------
# check_frozen
# ---------------------------------------------------------------------------

def check_frozen(instance: Any) -> bool:
    """Return True iff *instance* raises FrozenInstanceError on attribute set.

    Works with ``@dataclass(frozen=True)``; also returns True for any object
    whose ``__setattr__`` raises ``FrozenInstanceError`` or a subclass.
    """
    # Pick an attribute name unlikely to be a real slot so we don't mutate
    # anything meaningful even on mutable instances.
    probe = "_invariant_probe_attr_"
    try:
        object.__setattr__(instance, probe)  # type: ignore[call-arg]
    except TypeError:
        pass  # object.__setattr__ with 2 args → expected, ignore
    try:
        setattr(instance, probe, object())
        # If we got here the instance accepted the write — clean up if we can
        try:
            delattr(instance, probe)
        except AttributeError:
            pass
        return False
    except FrozenInstanceError:
        return True
    except (AttributeError, TypeError):
        # __slots__ with no matching slot also raises AttributeError — treat
        # as "not writable" which is logically frozen for our purposes, but
        # callers care specifically about FrozenInstanceError, so return False.
        return False


# ---------------------------------------------------------------------------
# check_monotonic_nonincreasing
# ---------------------------------------------------------------------------

def check_monotonic_nonincreasing(values: Sequence[float]) -> bool:
    """Return True iff *values* is monotonically non-increasing.

    Suitable for remaining-fraction style sequences (e.g. time-remaining
    expressed as a 0-1 fraction decreasing from 1 to 0).

    An empty or single-element sequence is considered non-increasing.
    """
    return all(values[i] >= values[i + 1] for i in range(len(values) - 1))
