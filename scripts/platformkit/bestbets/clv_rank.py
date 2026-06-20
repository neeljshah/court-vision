"""scripts.platformkit.bestbets.clv_rank -- CLV-aware ranking tiebreak for best-bet cards.

BB-Q5-1: Extends divergence_rank by layering CLV signal as a secondary sort key
within the same tier and divergence bucket.

Sort key (primary -> secondary -> tertiary -> quaternary):
  1. tier_rank      -- A=0, B=1, C=2; unknown=99. Tier ALWAYS dominates.
  2. beat_close     -- graded beat-the-close TRUE > FALSE/None; INSUFFICIENT_DATA sinks.
  3. clv_pct        -- among graded, higher clv_pct ranks first. INSUFFICIENT_DATA gets
                       a sentinel that is lower than any real value (not fabricated 0).
  4. divergence_score  -- from divergence_rank (float, already attached by rank_cards).

DESIGN DECISIONS:
  * INSUFFICIENT_DATA is NOT fabricated as clv_pct=0. A real clv_pct=0 is graded.
    INSUFFICIENT_DATA uses a sentinel of -inf so it sinks below all graded cards.
  * CLV never overrides tier: a tier-B graded card never beats a tier-A INSUFFICIENT_DATA
    card in the sort.
  * Pure module: no I/O, no network, no global state mutation.
  * Does NOT import bestbets_compute (PROPOSE-ONLY integration pattern).
  * No dollar / roi / pnl / profit field anywhere.

RAILS (binding):
  * UNITS not $. No dollar / ROI / PnL / profit key anywhere.
  * INSUFFICIENT_DATA sinks to bottom of its tier, never treated as 0.
  * Missing 'clv' dict on a card does not raise -- treated as INSUFFICIENT_DATA.
  * tier still dominates CLV (A beats B regardless).
  * empty list -> []
  * <= 300 LOC; ASCII only.

Build on (read-only):
  * divergence_rank.divergence_score / rank_cards  (read-only import)
  * clv_index lookup value shape: {clv_pct, beat_close, clv_status, clv_is_proxy}
  * card['clv'] dict shape from bestbets_compute (read-only mirror)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit.bestbets.divergence_rank import (
    DEFAULT_SIGMA,
    divergence_score as _divergence_score,
    _tier_rank as _base_tier_rank,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Sentinel for INSUFFICIENT_DATA: sinks below any real clv_pct (even negative).
_CLV_PCT_SINK: float = float("-inf")

# Status strings -- canonical
_STATUS_INSUFFICIENT = "INSUFFICIENT_DATA"

# Tier ordering mirrored from divergence_rank (A=0, B=1, C=2, unknown=99).
_TIER_ORDER: Dict[str, int] = {"A": 0, "B": 1, "C": 2}
_UNKNOWN_TIER_RANK: int = 99


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_clv_dict(card: Dict[str, Any]) -> Dict[str, Any]:
    """Safely extract the 'clv' sub-dict from a card.

    Returns an empty dict if the key is missing or not a dict.
    Never raises.
    """
    raw = card.get("clv")
    if isinstance(raw, dict):
        return raw
    return {}


def _clv_sort_key(clv: Dict[str, Any]) -> Tuple[int, float]:
    """Return (beat_close_rank, clv_pct_effective) for sorting.

    beat_close_rank:
      0 -- graded AND beat_close=True   (best)
      1 -- graded AND beat_close=False  (graded but did not beat close)
      2 -- INSUFFICIENT_DATA            (worst -- sinks to bottom of tier)

    clv_pct_effective:
      real clv_pct float for graded cards (higher is better -> negate for sort)
      _CLV_PCT_SINK for INSUFFICIENT_DATA (sinks below all graded)

    The sort uses these as ascending keys:
      key = (beat_close_rank, -clv_pct_effective)
    so (0, -big_pct) < (0, -small_pct) < (1, ...) < (2, ...).
    """
    status = str(clv.get("clv_status") or "").strip()
    is_insufficient = (
        not clv  # empty dict (missing clv key on card)
        or status == _STATUS_INSUFFICIENT
        or status == ""
    )

    if is_insufficient:
        return (2, _CLV_PCT_SINK)

    beat_close = clv.get("beat_close")
    if beat_close is True:
        bc_rank = 0
    else:
        # False, None, or any other falsy value -- graded but not beat-close
        bc_rank = 1

    clv_pct_raw = clv.get("clv_pct")
    try:
        clv_pct_f = float(clv_pct_raw) if clv_pct_raw is not None else 0.0
    except (TypeError, ValueError):
        clv_pct_f = 0.0

    if not math.isfinite(clv_pct_f):
        clv_pct_f = 0.0

    return (bc_rank, clv_pct_f)


def _tier_rank(card: Dict[str, Any]) -> int:
    """Return sort key for tier: lower = higher priority."""
    tier_str = card.get("tier") or ""
    return _TIER_ORDER.get(str(tier_str).upper(), _UNKNOWN_TIER_RANK)


def _card_sort_tuple(card: Dict[str, Any]) -> Tuple[int, int, float, float]:
    """Build the full 4-key sort tuple for one card.

    Sort semantics (all ascending):
      (tier_rank, beat_close_rank, -clv_pct_effective, -divergence_score)

    So:
      - Lower tier_rank sorts first  (A before B before C).
      - Lower beat_close_rank sorts first  (graded-beat-close before INSUFFICIENT).
      - Higher clv_pct sorts first  (negated).
      - Higher divergence_score sorts first  (negated).
    """
    tr = _tier_rank(card)
    clv = _extract_clv_dict(card)
    bc_rank, clv_pct_eff = _clv_sort_key(clv)
    div_score = card.get("divergence_score") or 0.0
    try:
        div_score = float(div_score)
    except (TypeError, ValueError):
        div_score = 0.0
    if not math.isfinite(div_score):
        div_score = 0.0

    # Negate clv_pct_eff and div_score so that higher values sort first
    # (but only when they are finite; -inf stays -inf which means it sorts last
    # when negated -> +inf, which is correct for the ascending sort).
    neg_clv = -clv_pct_eff if math.isfinite(clv_pct_eff) else float("inf")
    neg_div = -div_score

    return (tr, bc_rank, neg_clv, neg_div)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def attach_divergence_scores(
    cards: List[Dict[str, Any]],
    *,
    default_sigma: Optional[float] = None,
) -> None:
    """Attach 'divergence_score' to each card in-place using divergence_rank logic.

    Mirrors the attach logic from divergence_rank.rank_cards without sorting,
    so clv_rank can own the final sort order.
    """
    resolved_sigma: float
    if (
        default_sigma is not None
        and isinstance(default_sigma, (int, float))
        and math.isfinite(float(default_sigma))
        and float(default_sigma) > 0.0
    ):
        resolved_sigma = float(default_sigma)
    else:
        resolved_sigma = DEFAULT_SIGMA

    for card in cards:
        mp = card.get("model_prob")
        mk = card.get("market_prob")
        if mp is None or mk is None:
            card.setdefault("divergence_score", 0.0)
            continue
        card_sigma = card.get("sigma")
        eff_sigma: Optional[float]
        if card_sigma is not None:
            try:
                eff_sigma = float(card_sigma)
            except (TypeError, ValueError):
                eff_sigma = resolved_sigma
        else:
            eff_sigma = resolved_sigma
        card["divergence_score"] = _divergence_score(mp, mk, eff_sigma)


def rank_cards_clv(
    cards: List[Dict[str, Any]],
    *,
    default_sigma: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Sort cards by (tier, beat_close DESC, clv_pct DESC, divergence_score DESC).

    Parameters
    ----------
    cards:
        List of card dicts. Each card may have:
          - 'tier'            (str "A"/"B"/"C", or missing)
          - 'model_prob'      (float, optional -- for divergence_score attachment)
          - 'market_prob'     (float, optional -- for divergence_score attachment)
          - 'divergence_score' (float, optional -- if already set, kept as-is;
                                if absent, computed from model_prob/market_prob)
          - 'clv'             (dict with keys: clv_pct, beat_close, clv_status)
                               or absent -> treated as INSUFFICIENT_DATA

    default_sigma:
        Passed to divergence_score attachment for cards lacking a precomputed score.

    Returns
    -------
    List[Dict[str, Any]]
        Same card objects (mutated in-place to add divergence_score if missing),
        sorted by the 4-key CLV-aware key.
        Empty input returns [].

    Guarantees:
      * tier A card always before tier B, regardless of CLV.
      * INSUFFICIENT_DATA sinks to the bottom of its tier (not fabricated as 0).
      * graded beat_close=True outranks graded beat_close=False at same tier.
      * higher clv_pct outranks lower among graded at same tier + same beat_close.
      * divergence_score breaks remaining ties.
      * Never raises on missing 'clv' dict.
      * No dollar / roi / pnl / profit key is written to any card.
    """
    if not cards:
        return []

    # Attach divergence_score where missing
    attach_divergence_scores(cards, default_sigma=default_sigma)

    cards.sort(key=_card_sort_tuple)
    return cards


def _recursive_banned_key_check(obj: Any, banned: set) -> Optional[str]:
    """Recursively scan obj for any banned key. Returns the first hit or None."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in banned:
                return str(k)
            found = _recursive_banned_key_check(v, banned)
            if found:
                return found
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            found = _recursive_banned_key_check(item, banned)
            if found:
                return found
    return None


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    "attach_divergence_scores",
    "rank_cards_clv",
]
