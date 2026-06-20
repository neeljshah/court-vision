"""scripts.platformkit.bestbets.sport_clv_context -- per-sport CLV context label (BB-Q7).

Attaches a human-readable CLV context string to each card in a multi-sport
best-bets rollup, so the front-end can honestly communicate WHY the CLV signal
is limited or unavailable (offseason, proxy close, insufficient data, etc.)
rather than silently leaving a blank or fabricating a number.

Context strings are CALIBRATION labels, never edge / profit claims.

Design invariants (BB-Q7 acceptance criteria):
  1. NBA during offseason months -> context string contains "offseason".
  2. Unknown / unsupported sport -> a generic, non-null label (never empty string).
  3. PROXY provenance (clv_is_proxy=True OR Provenance.FILLED / UNKNOWN) is surfaced
     as "proxy close" in the context string, never as "edge" or "graded close".
  4. Pure module: no I/O, no network, no global state mutation.
  5. No dollar / roi / pnl / profit field anywhere.
  6. <= 300 LOC; ASCII only.

Context string hierarchy (first match wins):
  a. Sport is offseason this month          -> "<sport> offseason -- CLV unavailable"
  b. CLV provenance is PROXY or FILLED/UNKNOWN
                                            -> "proxy close -- CLV unreliable (not edge)"
  c. CLV status is INSUFFICIENT_DATA        -> "insufficient data -- CLV not graded"
  d. CLV is graded true-close               -> "graded close -- CLV available"
  e. No CLV info present                    -> "CLV context unavailable"
  f. Unknown sport (no season window)       -> "generic CLV label -- sport unrecognised"

Callers pass a card dict (or just a sport + optional CLV sub-dict) and receive a
context string. A batch helper operates on a list of cards in place.

Build on:
  * governance.policy.Provenance (UNAVAILABLE / PROXY / FILLED / UNKNOWN / REAL_MODEL)
    [read-only import -- never mutates]
  * scripts.platformkit.autonomy.schedule_policy.is_in_season + DEFAULT_SEASON_WINDOWS
    [read-only import -- season-window knowledge without duplication]
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Imports (read-only; this module never mutates external state)
# ---------------------------------------------------------------------------
from governance.policy import Provenance
from scripts.platformkit.autonomy.schedule_policy import (
    DEFAULT_SEASON_WINDOWS,
    is_in_season,
)

# ---------------------------------------------------------------------------
# Context string constants (ASCII, no $, no edge claim)
# ---------------------------------------------------------------------------
_OFFSEASON_TMPL = "{sport} offseason -- CLV unavailable"
_PROXY_CTX = "proxy close -- CLV unreliable (calibration only)"
_INSUFFICIENT_DATA_CTX = "insufficient data -- CLV not graded"
_GRADED_CTX = "graded close -- CLV available"
_NO_INFO_CTX = "CLV context unavailable"
_GENERIC_SPORT_CTX = "generic CLV label -- sport unrecognised"

# Provenance enum values that signal a PROXY / unreliable source.
_PROXY_PROVENANCES = frozenset({
    Provenance.FILLED,
    Provenance.UNAVAILABLE,
    Provenance.UNKNOWN,
})


# ---------------------------------------------------------------------------
# Core: compute context string for one sport + CLV sub-dict
# ---------------------------------------------------------------------------

def sport_clv_context(
    sport: Any,
    clv: Optional[Dict[str, Any]] = None,
    *,
    month: Optional[int] = None,
    season_windows: Optional[Dict[str, Any]] = None,
) -> str:
    """Return an honest CLV context label for one (sport, clv) pair.

    Parameters
    ----------
    sport:
        Sport slug, e.g. "nba", "mlb", "soccer", "tennis" (case-insensitive).
        An unknown / None sport returns the generic label.
    clv:
        Optional CLV sub-dict (from clv_index.lookup or a card's "clv" field).
        Shape:
          {
            "clv_pct":    float | None,
            "beat_close": bool | None,
            "clv_status": str,           -- "graded" | "proxy" | "INSUFFICIENT_DATA"
            "clv_is_proxy": bool,        -- True when close is estimated not real
          }
        May also carry a "provenance" key whose value is a Provenance enum or
        its string representation.
        If None or empty, the function falls back to _NO_INFO_CTX (if sport
        is in-season) or the offseason string.
    month:
        Calendar month (1-12). Defaults to the current UTC month. Injectable for
        tests to avoid real-clock dependency.
    season_windows:
        Override the DEFAULT_SEASON_WINDOWS table (injectable for tests).

    Returns
    -------
    str
        A non-empty ASCII context string. Never contains a $ symbol.
        Never claims edge or profit.

    Guarantees
    ----------
    * Always returns a non-empty str; never raises.
    * Does not mutate the clv dict or any module-level state.
    * ASCII only.
    """
    # Normalise sport slug
    sport_str = str(sport or "").strip().lower()

    # Resolve month (injectable for tests)
    m = int(month) if month is not None else _dt.datetime.utcnow().month

    windows = season_windows or DEFAULT_SEASON_WINDOWS

    # ---- a. Unknown sport (no season window defined) --------------------------
    if sport_str not in windows:
        return _GENERIC_SPORT_CTX

    # ---- b. Offseason check ---------------------------------------------------
    if not is_in_season(sport_str, m, windows):
        return _OFFSEASON_TMPL.format(sport=sport_str)

    # ---- In-season: inspect CLV provenance -----------------------------------
    if not clv or not isinstance(clv, dict):
        return _NO_INFO_CTX

    # ---- c. Provenance flag (FILLED / UNAVAILABLE / UNKNOWN -> proxy) --------
    raw_prov = clv.get("provenance")
    if raw_prov is not None:
        try:
            prov = Provenance(raw_prov)
        except (ValueError, KeyError):
            prov = None
        if prov is not None and prov in _PROXY_PROVENANCES:
            return _PROXY_CTX

    # ---- d. clv_is_proxy flag ------------------------------------------------
    if clv.get("clv_is_proxy") is True:
        return _PROXY_CTX

    # ---- e. clv_status check -------------------------------------------------
    status = str(clv.get("clv_status") or "").strip().upper()
    if status == "PROXY":
        return _PROXY_CTX
    if status == "INSUFFICIENT_DATA":
        return _INSUFFICIENT_DATA_CTX

    # ---- f. Graded true close ------------------------------------------------
    if status == "GRADED":
        return _GRADED_CTX

    # ---- g. Fallback: CLV key present but status not recognised --------------
    # If clv_pct is available it's probably graded; otherwise treat as no info.
    if clv.get("clv_pct") is not None:
        return _GRADED_CTX
    return _NO_INFO_CTX


# ---------------------------------------------------------------------------
# Card-level helper: compute context from a full card dict
# ---------------------------------------------------------------------------

def card_clv_context(
    card: Dict[str, Any],
    *,
    month: Optional[int] = None,
    season_windows: Optional[Dict[str, Any]] = None,
) -> str:
    """Extract sport + clv from a card dict and return the context string.

    Reads card["sport"] and card.get("clv") (optional dict). Everything else
    is handled by sport_clv_context. Never raises.
    """
    if not isinstance(card, dict):
        return _NO_INFO_CTX
    sport = card.get("sport")
    clv = card.get("clv") if isinstance(card.get("clv"), dict) else None
    return sport_clv_context(sport, clv, month=month, season_windows=season_windows)


# ---------------------------------------------------------------------------
# Batch helper: attach context string to a list of card dicts in-place
# ---------------------------------------------------------------------------

def attach_sport_clv_contexts(
    cards: List[Dict[str, Any]],
    *,
    output_key: str = "clv_context",
    month: Optional[int] = None,
    season_windows: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Attach a 'clv_context' string to each card in the list (in-place).

    Parameters
    ----------
    cards:
        List of card dicts (mutated in-place).
    output_key:
        Key to write the context string onto each card (default 'clv_context').
    month:
        Calendar month override for tests (omit for live clock).
    season_windows:
        Season-window override (omit for defaults).

    Returns
    -------
    The same list (in-place) for chaining.

    Guarantees
    ----------
    * Never raises on any input shape.
    * No dollar / roi / pnl / profit field is written.
    * Non-dict items in the list are skipped.
    """
    for card in cards:
        if not isinstance(card, dict):
            continue
        card[output_key] = card_clv_context(
            card, month=month, season_windows=season_windows
        )
    return cards


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "sport_clv_context",
    "card_clv_context",
    "attach_sport_clv_contexts",
    # Context string constants (re-exported for test assertions)
    "_OFFSEASON_TMPL",
    "_PROXY_CTX",
    "_INSUFFICIENT_DATA_CTX",
    "_GRADED_CTX",
    "_NO_INFO_CTX",
    "_GENERIC_SPORT_CTX",
]
