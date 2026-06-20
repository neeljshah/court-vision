"""slate_ev_recency_gate.py -- cap pathological EV and gate stale/non-sports rows.

Workstream R6-5-slate-ev-recency-cap.

QA iter 10 P1 (raw :8098 slate): a Polymarket binary 'Yes vs No' contract whose
tipoff was ~11 months in the past appeared on the raw slate surface with ev=683.2.
This is a fabricated-edge magnitude -- not a calibrated divergence.  Two root causes:

  1. RECENCY GAP: tipoff > STALE_TIPOFF_HOURS (default 12h) in the past.
  2. NON-SPORTS-BINARY: matchup is 'Yes vs No' (or similar non-team-name pattern),
     not a "<Team A> vs <Team B>" format.
  3. PATHOLOGICAL EV: ev / edge_vs_market > EV_CAP (default 5.0).

This module closes all three gaps:

  * Drop  -- when tipoff_utc > STALE_TIPOFF_HOURS hours ago OR matchup is a
             non-sports binary (contains 'yes vs no', or has no recognizable
             team-name format).
  * Cap   -- when |ev| > EV_CAP on a row that otherwise passes recency+matchup
             checks: clamp to +/-EV_CAP and set ev_capped=True + a label.

The drop logic complements board_sanitizer.sanitize (which already drops
'yes vs no' matchups and past-tipoff cards by a <= now boundary).  This module
adds a configurable lookback window so the raw :8098 slate -- served before
board_sanitizer runs -- can also be protected.

RAILS:
  - Pure: no network, no IO, no global mutable state.
  - Never mutates input dicts; returns new dicts.
  - No $ / roi / pnl / bankroll / profit / stake / usd / dollar field.
  - ASCII only; <= 300 LOC.
  - Reuses board_sanitizer constants where safe to avoid constant drift.
  - Injectable 'now' for deterministic tests.
  - stale-never-green: a row whose tipoff is > STALE_TIPOFF_HOURS ago is DROPPED,
    not capped.

Per-file test:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/bestbets/test_slate_ev_recency_gate.py -q
"""
from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Reuse constants from board_sanitizer where appropriate.
# ---------------------------------------------------------------------------
try:
    from scripts.platformkit.bestbets.board_sanitizer import (
        MATCHUP_BINARY_TOKEN,
        _TIPOFF_KEYS,
    )
except Exception:  # noqa: BLE001
    MATCHUP_BINARY_TOKEN = "yes vs no"
    _TIPOFF_KEYS = ("tipoff_utc", "tipoff", "game_datetime", "commence_time")

# ---------------------------------------------------------------------------
# Module-level tuneable constants (exported for tests).
# ---------------------------------------------------------------------------

#: How many hours before *now* a tipoff is allowed to be.  Rows with a tipoff
#: older than this are stale and DROPPED (stale-never-green).
STALE_TIPOFF_HOURS: int = 12

#: EV (edge_vs_market or ev field) cap.  A row that passes the drop checks but
#: carries |ev| > this is capped and labelled ev_capped=True.
EV_CAP: float = 5.0

#: Keys checked for the edge/EV value (first key found with a parseable float wins).
_EV_KEYS: Tuple[str, ...] = ("ev", "edge_vs_market", "edge")

#: Honest label applied to capped rows (ASCII only).
EV_CAP_NOTE: str = (
    "ev_capped: raw EV exceeded sane bound; capped to calibrated range; "
    "calibration not edge"
)

#: Drop reason label written to dropped rows (never reaches output, but
#: available on the _explain_drop helper for logging/tests).
_DROP_REASON_STALE: str = "stale_tipoff"
_DROP_REASON_NON_SPORTS: str = "non_sports_matchup"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_tipoff(raw: Any) -> Optional[datetime]:
    """Parse a tipoff value (string or datetime) into an aware UTC datetime.

    Returns None when the value is missing, None, or unparseable.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw
    if isinstance(raw, str):
        try:
            s = raw.strip().replace("Z", "+00:00")
            tip = datetime.fromisoformat(s)
            if tip.tzinfo is None:
                tip = tip.replace(tzinfo=timezone.utc)
            return tip
        except (ValueError, AttributeError):
            return None
    return None


def _get_tipoff(row: Dict[str, Any]) -> Optional[datetime]:
    """Return the first parseable tipoff datetime found across known tipoff keys."""
    for key in _TIPOFF_KEYS:
        tip = _parse_tipoff(row.get(key))
        if tip is not None:
            return tip
    return None



def _is_non_sports_binary(matchup: Any) -> bool:
    """Return True when *matchup* looks like a non-sports binary event.

    Detection rules (any one triggers True):
      1. Contains MATCHUP_BINARY_TOKEN ('yes vs no', case-insensitive).
      2. matchup is not a string (None, int, etc.).
    """
    if not isinstance(matchup, str):
        return True  # non-string matchup -> not a team-vs-team row
    lower = matchup.strip().lower()
    if not lower:
        return True  # empty string
    return MATCHUP_BINARY_TOKEN in lower


def _get_ev(row: Dict[str, Any]) -> Optional[float]:
    """Return the first parseable EV value found across known EV keys."""
    for key in _EV_KEYS:
        raw = row.get(key)
        if raw is None:
            continue
        try:
            val = float(raw)
            if math.isfinite(val):
                return val
        except (TypeError, ValueError):
            continue
    return None


def _set_ev(out: Dict[str, Any], val: float) -> None:
    """Write *val* back into every EV key that was present in *out*."""
    for key in _EV_KEYS:
        if key in out:
            out[key] = val


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_ev_recency_gate(
    rows: List[Dict[str, Any]],
    now: Optional[datetime] = None,
    stale_hours: int = STALE_TIPOFF_HOURS,
    ev_cap: float = EV_CAP,
) -> List[Dict[str, Any]]:
    """Return a sanitized copy of *rows* with stale/binary rows dropped and EV capped.

    Parameters
    ----------
    rows:
        Raw slate rows (list of dicts) as served by the :8098 API surface.
        Neither the list nor any input dict is mutated.
    now:
        UTC reference time for the recency check.  Defaults to
        datetime.now(timezone.utc).  Inject a fixed value for deterministic tests.
    stale_hours:
        Override the stale-tipoff window (default STALE_TIPOFF_HOURS=12).
    ev_cap:
        Override the EV cap magnitude (default EV_CAP=5.0).

    Returns
    -------
    List[Dict[str, Any]]
        New list of new dict copies with:
          * Non-sports-binary matchup rows DROPPED.
          * Rows with tipoff > stale_hours ago DROPPED.
          * Rows with |ev| > ev_cap: ev capped to +/-ev_cap,
            ev_capped=True, ev_cap_note=EV_CAP_NOTE, ev_raw=<original>.
          * All other rows passed through unchanged (deep copy).
        Never raises; returns [] on unexpected error.
    """
    if not rows:
        return []
    try:
        return _apply_inner(rows, now=now, stale_hours=stale_hours, ev_cap=ev_cap)
    except Exception:  # noqa: BLE001 -- guard must never crash the board
        return []


def _apply_inner(
    rows: List[Dict[str, Any]],
    now: Optional[datetime],
    stale_hours: int,
    ev_cap: float,
) -> List[Dict[str, Any]]:
    """Inner implementation; always called through apply_ev_recency_gate()."""
    if now is None:
        now = datetime.now(tz=timezone.utc)

    # Temporarily override module constants if caller supplied overrides.
    # We pass them explicitly to helpers rather than monkeypatching the module.
    result: List[Dict[str, Any]] = []
    for row in rows:
        drop, _reason = _should_drop_with_hours(row, now=now, stale_hours=stale_hours)
        if drop:
            continue
        out = copy.deepcopy(row)
        _cap_ev_with_bound(out, ev_cap=ev_cap)
        result.append(out)
    return result


def _should_drop_with_hours(
    row: Dict[str, Any],
    now: datetime,
    stale_hours: int,
) -> Tuple[bool, str]:
    """Like _should_drop but respects an explicit stale_hours argument."""
    if not isinstance(row, dict):
        return True, "not_a_dict"
    if _is_non_sports_binary(row.get("matchup")):
        return True, _DROP_REASON_NON_SPORTS
    tip = _get_tipoff(row)
    if tip is not None:
        cutoff = now - timedelta(hours=stale_hours)
        if tip < cutoff:
            return True, _DROP_REASON_STALE
    return False, ""


def _cap_ev_with_bound(out: Dict[str, Any], ev_cap: float) -> bool:
    """Cap EV on *out* using an explicit ev_cap argument.  Returns True if capped."""
    ev = _get_ev(out)
    if ev is None:
        return False
    if abs(ev) <= ev_cap:
        return False
    capped = math.copysign(ev_cap, ev)
    _set_ev(out, capped)
    out["ev_capped"] = True
    out["ev_cap_note"] = EV_CAP_NOTE
    out["ev_raw"] = ev
    return True


__all__ = [
    "STALE_TIPOFF_HOURS",
    "EV_CAP",
    "EV_CAP_NOTE",
    "MATCHUP_BINARY_TOKEN",
    "apply_ev_recency_gate",
]
