"""scripts.platformkit.improve.segmented_ledger_tick -- live PRODUCER tick for
the segmented recalibration ledger (SIX-01).

per_market_ledger.record_per_market (the reducer) is NEVER called in the live
loop, so improve_ledger_segmented.jsonl stays empty and improvement_trend /
coverage_map read nothing. This module is the additive, supervised, read-mostly
PRODUCER that closes that gap.

On each tick it:
  1. Guards the PIPELINE_ENABLED sentinel (read-only). If absent -> NO_CANDIDATE.
  2. Pulls newly-settled rows for the cycle from the injected source.
  3. Deduplicates via seen_ids (PRIMARY guard -- same pattern as the daemon).
  4. If zero unseen settled rows -> NO_CANDIDATE (no file write).
  5. Calls per_market_ledger.record_per_market on the fresh batch.
     Markets below MIN_MARKET_N automatically emit INSUFFICIENT_DATA (that
     contract is enforced inside per_market_ledger; we do not re-implement it).
  6. Advances the cursor so re-runs with the same seen_ids are idempotent.
  7. Returns a TickResult (decision, n_new, ledger_rows).

INVARIANTS:
  - Never edits selfimprove_daemon.py or selfimprove_runner.py.
  - Never creates the PIPELINE_ENABLED sentinel (read-only check).
  - Append-only writes; never overwrites an existing ledger row.
  - No key matching /$|roi|pnl|profit/i in any produced row (enforced by
    per_market_ledger._assert_no_banned_keys which raises, caught here).
  - Never raises -- all exceptions are caught; error decision returned.
  - ASCII-only; stdlib + repo-internal only; <= 300 LOC.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.improve.pipeline_flag import pipeline_enabled
from scripts.platformkit.improve.per_market_ledger import (
    record_per_market,
    MIN_MARKET_N,
)
from scripts.platformkit.improve.cursor_util import (
    advance as _advance,
    game_id as _game_id,
    key as _key,
)

logger = logging.getLogger("segmented_ledger_tick")

# Decisions
NO_CANDIDATE = "NO_CANDIDATE"
SHIP = "SHIP"
ERROR = "ERROR"

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# TickResult
# ---------------------------------------------------------------------------


@dataclass
class TickResult:
    """Result of one segmented-ledger producer tick."""

    decision: str
    """NO_CANDIDATE | SHIP | ERROR"""

    n_new: int = 0
    """Unseen settled rows consumed this tick."""

    ledger_rows: List[Dict[str, Any]] = field(default_factory=list)
    """Ledger rows written (one per market segment; empty when NO_CANDIDATE)."""

    reasons: List[str] = field(default_factory=list)
    """Human-readable explanations (sentinel absent, zero rows, etc.)."""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "n_new": self.n_new,
            "n_ledger_rows": len(self.ledger_rows),
            "reasons": self.reasons,
        }


# ---------------------------------------------------------------------------
# Cursor helpers
# ---------------------------------------------------------------------------


def _load_cursor(cursor: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a mutable copy of cursor (or a fresh empty cursor)."""
    if cursor is None:
        return {"seen_ids": [], "high_water": ""}
    return dict(cursor)


# ---------------------------------------------------------------------------
# Core tick
# ---------------------------------------------------------------------------


def tick(
    *,
    settled_rows_fn: Optional[Callable[..., Sequence[Dict[str, Any]]]] = None,
    ledger_path: Optional[Path] = None,
    cursor: Optional[Dict[str, Any]] = None,
    _sentinel: Optional[Path] = None,
) -> TickResult:
    """Run one segmented-ledger producer tick.  Never raises.

    Args:
        settled_rows_fn: callable(seen_ids) -> Sequence[dict].  Each dict is a
            settled row with at least {p_raw, y, market} (same shape as
            per_market_ledger rows).  Injected for testing; production callers
            supply their own settled-row provider.
        ledger_path: override the default improve_ledger_segmented.jsonl path.
        cursor:     mutable dict {seen_ids: list[str], high_water: str}.  If
            supplied, the tick advances it in-place (idempotent re-run guard).
            Pass the same dict object across ticks to get dedup across ticks.
        _sentinel:  test-only override for the PIPELINE_ENABLED path.

    Returns:
        TickResult with decision NO_CANDIDATE | SHIP | ERROR.

    Contract:
        - sentinel absent  -> NO_CANDIDATE, no file write.
        - zero new settled -> NO_CANDIDATE, no file write.
        - n_new > 0        -> record_per_market writes ledger; decision = SHIP.
        - under-N market   -> INSUFFICIENT_DATA row (from per_market_ledger).
        - idempotent: same seen_ids -> zero new -> NO_CANDIDATE on re-run.
        - no banned key in any ledger row (per_market_ledger enforces this).
        - never raises.
    """
    # ------------------------------------------------------------------
    # 1. Sentinel guard (read-only)
    # ------------------------------------------------------------------
    try:
        enabled = pipeline_enabled(_sentinel=_sentinel)
    except Exception as exc:  # noqa: BLE001
        logger.debug("pipeline_enabled() raised: %s", exc)
        enabled = False

    if not enabled:
        return TickResult(
            decision=NO_CANDIDATE,
            reasons=["PIPELINE_ENABLED sentinel absent -- no-op"],
        )

    # ------------------------------------------------------------------
    # 2. Pull settled rows (via injected fn or empty default)
    # ------------------------------------------------------------------
    cur = _load_cursor(cursor)
    seen_ids: set = set(str(s) for s in (cur.get("seen_ids") or []))

    if settled_rows_fn is None:
        raw: Sequence[Dict[str, Any]] = []
    else:
        try:
            raw = list(settled_rows_fn(seen_ids=sorted(seen_ids)))
        except Exception as exc:  # noqa: BLE001
            logger.debug("settled_rows_fn raised: %s", exc)
            return TickResult(
                decision=ERROR,
                reasons=["settled_rows_fn raised: %s" % str(exc)[:200]],
            )

    # ------------------------------------------------------------------
    # 3. Dedup by game_id / row id (PRIMARY guard)
    # ------------------------------------------------------------------
    fresh = [r for r in raw if _game_id(r) not in seen_ids]
    n_new = len(fresh)

    if n_new == 0:
        return TickResult(
            decision=NO_CANDIDATE,
            n_new=0,
            reasons=["zero unseen settled rows -- no-op"],
        )

    # ------------------------------------------------------------------
    # 4. Write to the ledger (per_market_ledger handles INSUFFICIENT_DATA)
    # ------------------------------------------------------------------
    try:
        ledger_rows = record_per_market(fresh, ledger_path=ledger_path)
    except Exception as exc:  # noqa: BLE001
        logger.debug("record_per_market raised: %s", exc)
        return TickResult(
            decision=ERROR,
            n_new=n_new,
            reasons=["record_per_market raised: %s" % str(exc)[:200]],
        )

    # ------------------------------------------------------------------
    # 5. Sanity-check no banned key leaked through (defense in depth)
    # ------------------------------------------------------------------
    for row in ledger_rows:
        for k in _iter_keys(row):
            if _BANNED_KEY_RE.search(k):
                logger.warning("banned key '%s' found -- row dropped from result", k)
                ledger_rows = [
                    r for r in ledger_rows if not any(
                        _BANNED_KEY_RE.search(kk) for kk in _iter_keys(r)
                    )
                ]
                break

    # ------------------------------------------------------------------
    # 6. Advance cursor (idempotent dedup on re-run)
    # ------------------------------------------------------------------
    folded_ids = [_game_id(r) for r in fresh]
    batch_keys = [_key(r) for r in raw]
    new_hw = max([str(cur.get("high_water") or "")] + batch_keys) if batch_keys else str(cur.get("high_water") or "")
    _advance(cur, new_hw, folded_ids)
    # Write back into the caller's mutable cursor dict (if supplied)
    if cursor is not None:
        cursor["seen_ids"] = cur["seen_ids"]
        cursor["high_water"] = cur["high_water"]

    n_graded = len(ledger_rows)
    return TickResult(
        decision=SHIP,
        n_new=n_new,
        ledger_rows=ledger_rows,
        reasons=[
            "%d new settled rows -> %d market segment(s) graded" % (n_new, n_graded),
        ],
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iter_keys(obj: Any):
    """Recursively yield all dict keys."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _iter_keys(item)


__all__ = [
    "TickResult",
    "tick",
    "NO_CANDIDATE",
    "SHIP",
    "ERROR",
]
