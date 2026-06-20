"""domains.mlb.discrimination_diag -- Degenerate-distribution diagnostic for MLB moneyline.

QA-MLB-DISCRIM (iter 2 P1): MLB cards collapsing to ~4 unique model_prob values is a
fabricated-edge violation.  This PURE READ-ONLY module surfaces an honest verdict.

Verdicts: NOT_DISCRIMINATING | OK | INSUFFICIENT_DATA | UNAVAILABLE
Output keys: status, n_games, n_unique_probs, discrimination_ratio, dominant_prob,
             n_dominant, std_dev, reason, note.  No $ / roi / pnl field.  Never raises.
Reads: moneyline_recal.RecalResult.recal_probs, markets.full_market_surface moneyline rows.
Does NOT edit the human-gated predictor.  Pure; no file I/O; ASCII only; <=300 LOC.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, List, Optional, Sequence

# -- Constants (module-level so tests can inspect them) ---------------------

MIN_GAMES: int = 5                       # min games to make a discrimination judgement
MIN_DISCRIMINATION_RATIO: float = 0.5   # n_unique/n_games threshold
PROB_ROUND_DIGITS: int = 6              # decimal places before de-dup

STATUS_NOT_DISCRIMINATING: str = "NOT_DISCRIMINATING"
STATUS_OK: str = "OK"
STATUS_INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"
STATUS_UNAVAILABLE: str = "UNAVAILABLE"

_CALIBRATION_NOTE: str = (
    "calibration diagnostic only; no $ / edge / ROI claimed; vs_close=UNPROVEN"
)


# -- Internal helpers -------------------------------------------------------

def _coerce_prob(val: Any) -> Optional[float]:
    """Return a rounded float in (0, 1), or None when invalid."""
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    if f < 0.0 or f > 1.0:
        return None
    return round(f, PROB_ROUND_DIGITS)


def _dominant_entry(counter: "Counter[float]") -> tuple:
    """Return (dominant_prob, n_dominant) from a Counter, or (None, 0)."""
    if not counter:
        return (None, 0)
    prob, count = counter.most_common(1)[0]
    return (float(prob), int(count))


def _std_dev(probs: List[float]) -> Optional[float]:
    """Population std-dev of a prob list; None when fewer than 2 values."""
    n = len(probs)
    if n < 2:
        return None
    mean = sum(probs) / n
    variance = sum((p - mean) ** 2 for p in probs) / n
    return round(math.sqrt(variance), 8)


# -- Public API -------------------------------------------------------------

def scan_moneyline_probs(
    probs: Optional[Sequence[Any]],
    *,
    min_games: int = MIN_GAMES,
    min_ratio: float = MIN_DISCRIMINATION_RATIO,
) -> dict:
    """Assess whether an MLB moneyline prob sequence shows adequate discrimination.

    Designed to consume:
      * ``RecalResult.recal_probs`` (numpy array) from moneyline_recal.py
      * ``[surface['moneyline']['home'] for surface in ...]`` from markets.py
      * Any sequence of float-like model_prob values

    Parameters
    ----------
    probs:
        Sequence of moneyline home-win probabilities (float-like).
        None / empty list -> UNAVAILABLE.
    min_games:
        Minimum number of valid games required to make a discrimination judgement.
    min_ratio:
        n_unique_probs / n_games threshold below which NOT_DISCRIMINATING is flagged.

    Returns
    -------
    dict
        See module docstring for full output shape.  Never raises.
    """
    try:
        return _scan_inner(probs, min_games=min_games, min_ratio=min_ratio)
    except Exception:  # noqa: BLE001
        return _unavailable(
            "Unexpected error during discrimination scan; cannot assess.",
            n_games=0,
        )


def _unavailable(reason: str, *, n_games: int = 0) -> dict:
    return {
        "status": STATUS_UNAVAILABLE,
        "n_games": n_games,
        "n_unique_probs": 0,
        "discrimination_ratio": None,
        "dominant_prob": None,
        "n_dominant": 0,
        "std_dev": None,
        "reason": reason,
        "note": _CALIBRATION_NOTE,
    }


def _scan_inner(
    probs: Optional[Sequence[Any]],
    *,
    min_games: int,
    min_ratio: float,
) -> dict:
    # --- Reject None / empty -----------------------------------------------
    if probs is None:
        return _unavailable("probs is None; no MLB moneyline data available.")

    # Coerce to list if numpy array or other sequence
    try:
        prob_list = list(probs)
    except TypeError:
        return _unavailable("probs is not iterable; cannot assess.")

    if len(prob_list) == 0:
        return _unavailable("Empty prob sequence; no MLB moneyline data to evaluate.")

    # --- Filter to valid probabilities -------------------------------------
    valid: List[float] = [v for v in (_coerce_prob(p) for p in prob_list) if v is not None]

    if len(valid) == 0:
        return _unavailable(
            f"None of {len(prob_list)} input value(s) are valid probabilities.",
            n_games=0,
        )

    n_games = len(valid)

    # --- Insufficient data -------------------------------------------------
    if n_games < min_games:
        dom_prob, n_dom = _dominant_entry(Counter(valid))
        return {
            "status": STATUS_INSUFFICIENT_DATA,
            "n_games": n_games,
            "n_unique_probs": len(set(valid)),
            "discrimination_ratio": None,
            "dominant_prob": dom_prob,
            "n_dominant": n_dom,
            "std_dev": _std_dev(valid),
            "reason": (
                f"Only {n_games} valid game(s) (need >= {min_games} to assess "
                "discrimination); verdict withheld."
            ),
            "note": _CALIBRATION_NOTE,
        }

    # --- Core discrimination assessment ------------------------------------
    counter: Counter = Counter(valid)
    n_unique = len(counter)
    ratio = n_unique / n_games
    dom_prob, n_dom = _dominant_entry(counter)
    std = _std_dev(valid)

    if ratio < min_ratio:
        return {
            "status": STATUS_NOT_DISCRIMINATING,
            "n_games": n_games,
            "n_unique_probs": n_unique,
            "discrimination_ratio": round(ratio, 6),
            "dominant_prob": dom_prob,
            "n_dominant": n_dom,
            "std_dev": std,
            "reason": (
                f"Only {n_unique} unique model_prob value(s) across {n_games} games "
                f"(ratio {ratio:.3f} < threshold {min_ratio:.3f}). "
                f"Dominant prob {dom_prob} covers {n_dom}/{n_games} games. "
                "Distribution is degenerate (likely fallback/cached defaults). "
                "Serving these probs as per-game edge is a fabricated-edge violation; "
                "status=NOT_DISCRIMINATING."
            ),
            "note": _CALIBRATION_NOTE,
        }

    return {
        "status": STATUS_OK,
        "n_games": n_games,
        "n_unique_probs": n_unique,
        "discrimination_ratio": round(ratio, 6),
        "dominant_prob": dom_prob,
        "n_dominant": n_dom,
        "std_dev": std,
        "reason": (
            f"{n_unique} unique prob value(s) across {n_games} games "
            f"(ratio {ratio:.3f} >= threshold {min_ratio:.3f}); "
            f"std_dev={std:.5f}. Distribution is adequately spread."
        ),
        "note": _CALIBRATION_NOTE,
    }


# -- Convenience wrapper: RecalResult ---------------------------------------

def from_recal_result(recal_result: Any, **kwargs) -> dict:
    """Run discrimination scan on a RecalResult from moneyline_recal.py.

    Reads ``recal_result.recal_probs`` (the walk-forward calibrated probs).
    Pure read; never mutates recal_result.

    Parameters
    ----------
    recal_result:
        A ``RecalResult`` dataclass instance (moneyline_recal.py).
    **kwargs:
        Forwarded to scan_moneyline_probs (min_games, min_ratio).
    """
    if recal_result is None:
        return _unavailable("recal_result is None; no data to scan.")
    probs = getattr(recal_result, "recal_probs", None)
    if probs is None:
        return _unavailable("RecalResult.recal_probs is missing.")
    return scan_moneyline_probs(probs, **kwargs)


# -- Convenience wrapper: markets.full_market_surface rows -----------------

def from_market_surfaces(surfaces: Optional[List[Any]], **kwargs) -> dict:
    """Run discrimination scan on a list of full_market_surface() dicts.

    Reads ``surface['moneyline']['home']`` for each game surface.
    Pure read; never mutates inputs.

    Parameters
    ----------
    surfaces:
        List of dicts returned by markets.full_market_surface().
    **kwargs:
        Forwarded to scan_moneyline_probs (min_games, min_ratio).
    """
    if surfaces is None:
        return _unavailable("None market surface list; no MLB moneyline data.")
    try:
        surface_list = list(surfaces)
    except TypeError:
        return _unavailable("market surfaces is not iterable; cannot assess.")
    if not surface_list:
        return _unavailable("Empty market surface list; no MLB moneyline data.")
    probs = []
    for s in surface_list:
        try:
            p = s.get("moneyline", {}).get("home")
            probs.append(p)
        except (AttributeError, TypeError):
            probs.append(None)
    return scan_moneyline_probs(probs, **kwargs)


__all__ = [
    "MIN_GAMES",
    "MIN_DISCRIMINATION_RATIO",
    "PROB_ROUND_DIGITS",
    "STATUS_NOT_DISCRIMINATING",
    "STATUS_OK",
    "STATUS_INSUFFICIENT_DATA",
    "STATUS_UNAVAILABLE",
    "scan_moneyline_probs",
    "from_recal_result",
    "from_market_surfaces",
]
