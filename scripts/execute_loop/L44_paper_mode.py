"""L44_paper_mode.py — Single Source of Truth for Paper vs Live Mode.

Purpose:
    Centralises all paper/live mode policy for the execute_loop.  Prior to L44
    each layer (L05, L09, L10, L11, L12, L16, L28, …) maintained its own
    inline env-var checks, module-level constants, or ad-hoc helper functions.
    This made the policy diffuse and hard to audit.  L44 is the canonical
    library that all layers will adopt.  Existing layers are unchanged in this
    PR; they will migrate in future rounds.

Environment Variables:
    SUBMISSION_MODE
        Set to "live" (case-insensitive) to enable live mode globally.
        Any other value (or absent) leaves the process in paper mode.

    KALSHI_LIVE_ENABLED
        Set to "1" to enable live mode for the Kalshi exchange layer (L09).

    POLYMARKET_LIVE_ENABLED
        Set to "1" to enable live mode for the Polymarket layer (L10).

    SPORTTRADE_LIVE_ENABLED
        Set to "1" to enable live mode for the SportTrade layer (L11).

    PROPHET_LIVE_ENABLED
        Set to "1" to enable live mode for the Prophet layer (L12).

    WITHDRAWAL_LIVE_ENABLED
        Set to "1" to enable live mode for the Withdrawal Automation layer (L28).

    DK_LIVE_SUBMISSION_ENABLED
        Set to "1" to enable live mode for the DraftKings submission path (L05).

    FD_LIVE_SUBMISSION_ENABLED
        Set to "1" to enable live mode for the FanDuel submission path (L05).

Paper vs Live Mode Policy (MODE GATING):
    L44 IS the canonical mode-gating library; it does not itself need a
    PAPER_MODE constant since its public functions are the source of truth.
    - Paper is the DEFAULT.  No environment variables need to be set.
    - Live mode is opt-in and requires an EXPLICIT signal.
    - is_paper_mode() returns False (i.e. live is active) if ANY of the
      following conditions hold:
        1. SUBMISSION_MODE == "live"  (case-insensitive)
        2. KALSHI_LIVE_ENABLED == "1"
        3. POLYMARKET_LIVE_ENABLED == "1"
        4. SPORTTRADE_LIVE_ENABLED == "1"
        5. PROPHET_LIVE_ENABLED == "1"
        6. WITHDRAWAL_LIVE_ENABLED == "1"
        7. DK_LIVE_SUBMISSION_ENABLED == "1"
        8. FD_LIVE_SUBMISSION_ENABLED == "1"
    - is_live_for_layer() checks ONLY the per-layer flag for the named layer.
      It does NOT inherit from SUBMISSION_MODE.  Each layer must be opted in
      independently.
    - assert_paper_mode() provides a hard guard for code paths that must never
      execute in live mode (e.g. test harnesses, dry-run simulations).

Usage example:
    from scripts.execute_loop.L44_paper_mode import (
        is_paper_mode,
        is_live_for_layer,
        assert_paper_mode,
        PaperModeRequired,
    )

    if is_paper_mode():
        log_paper_order(order)
    else:
        exchange_client.submit(order)

    # Per-layer check inside L09
    if is_live_for_layer("kalshi"):
        ...

    # Guard in test harness
    assert_paper_mode("nightly_retrain_dry_run")
"""
from __future__ import annotations

import os
from typing import Optional

__all__ = [
    "is_paper_mode",
    "is_live_for_layer",
    "assert_paper_mode",
    "PaperModeRequired",
]

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

# Global override env var — "live" (any case) activates live mode system-wide.
_GLOBAL_LIVE_VAR = "SUBMISSION_MODE"
_GLOBAL_LIVE_VALUE = "live"

# Mapping of logical layer names to their per-layer env vars.
_LAYER_FLAGS: dict[str, str] = {
    "kalshi": "KALSHI_LIVE_ENABLED",
    "polymarket": "POLYMARKET_LIVE_ENABLED",
    "sporttrade": "SPORTTRADE_LIVE_ENABLED",
    "prophet": "PROPHET_LIVE_ENABLED",
    "withdrawal": "WITHDRAWAL_LIVE_ENABLED",
    "dk_submission": "DK_LIVE_SUBMISSION_ENABLED",
    "fd_submission": "FD_LIVE_SUBMISSION_ENABLED",
}


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------


class PaperModeRequired(RuntimeError):
    """Raised by assert_paper_mode() when the process is in live mode.

    Attributes:
        operation: Human-readable name of the blocked operation.
    """

    def __init__(self, operation: str = "operation") -> None:
        self.operation = operation
        super().__init__(
            f"'{operation}' may only run in paper mode, but the process is "
            "currently in LIVE mode.  Unset all live-mode environment variables "
            "before invoking this operation."
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _global_live_active() -> bool:
    """Return True if SUBMISSION_MODE is set to 'live' (case-insensitive)."""
    val = os.environ.get(_GLOBAL_LIVE_VAR, "").strip().lower()
    return val == _GLOBAL_LIVE_VALUE


def _any_per_layer_live_active() -> bool:
    """Return True if any per-layer live flag is set to '1'."""
    for env_var in _LAYER_FLAGS.values():
        if os.environ.get(env_var, "").strip() == "1":
            return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_paper_mode() -> bool:
    """Return True if the current process is in paper mode.

    Paper is the default.  Live is enabled ONLY if any of these env vars are
    set:
      - SUBMISSION_MODE=live   (general, case-insensitive)
      - KALSHI_LIVE_ENABLED=1  (per-exchange)
      - POLYMARKET_LIVE_ENABLED=1
      - SPORTTRADE_LIVE_ENABLED=1
      - PROPHET_LIVE_ENABLED=1
      - WITHDRAWAL_LIVE_ENABLED=1
      - DK_LIVE_SUBMISSION_ENABLED=1
      - FD_LIVE_SUBMISSION_ENABLED=1

    The function returns False (live mode) as soon as ANY of the above
    conditions is satisfied.

    Returns:
        bool: True → paper mode (safe default).
              False → live mode (real money / real orders).
    """
    if _global_live_active():
        return False
    if _any_per_layer_live_active():
        return False
    return True


def is_live_for_layer(layer_name: str) -> bool:
    """Return True if a specific layer is in live mode.

    Only the per-layer environment variable is checked; SUBMISSION_MODE is
    intentionally ignored so that each exchange/layer must be opted in
    explicitly.

    Args:
        layer_name: One of 'kalshi', 'polymarket', 'sporttrade', 'prophet',
                    'withdrawal', 'dk_submission', 'fd_submission'.
                    Unknown names return False (paper = safe default).

    Returns:
        bool: True → live mode for this layer.
              False → paper mode (default if flag absent or layer unknown).
    """
    env_var: Optional[str] = _LAYER_FLAGS.get(layer_name)
    if env_var is None:
        return False
    return os.environ.get(env_var, "").strip() == "1"


def assert_paper_mode(operation: str = "operation") -> None:
    """Raise PaperModeRequired if the current process is NOT in paper mode.

    Use this guard in modules that must never execute in live mode, such as
    test harnesses, dry-run simulations, or analytics-only pipelines.

    Args:
        operation: Human-readable description of the blocked operation.
                   Included in the exception message to aid debugging.

    Raises:
        PaperModeRequired: If is_paper_mode() returns False.
    """
    if not is_paper_mode():
        raise PaperModeRequired(operation)
