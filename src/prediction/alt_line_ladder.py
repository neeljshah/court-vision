"""
alt_line_ladder.py — Phase 15.5: Production EV ladder for alt prop lines.

Converts a player's (point_estimate, conformal_interval, pinnacle_signal) into a
ranked ladder of 22 candidate bets (11 alt-line offsets × over + under), each with
EV and quarter-Kelly sizing.

Stacked uncertainty fallback:
  1. conformal_interval passed by caller (preferred — empirically calibrated)
  2. ConformalPredictor.load_residuals(stat) — loaded from data/models/
  3. Gaussian IQR fit from conformal_interval bounds (always available)

Public API
----------
    build_alt_line_ladder(player, stat, point_estimate, conformal_interval,
                          pinnacle_signal) -> list[dict]
    ladder_to_bets(ladder, bankroll, edge_min, kelly_cap) -> list[dict]
    _compute_ev(model_prob, book_prob) -> float
    _kelly_fraction(model_prob, book_prob) -> float
"""
from __future__ import annotations

import math
import os
from typing import Tuple

# ── Constants ──────────────────────────────────────────────────────────────────

_ALT_OFFSETS: list[float] = [
    -2.5, -2.0, -1.5, -1.0, -0.5,
     0.0,
     0.5,  1.0,  1.5,  2.0,  2.5,
]  # 11 offsets → 22 rows per call

_KELLY_CAP_PER_BET: float = 0.02   # max 2% of bankroll per position
_SIGMA_FLOOR: float = 0.3           # minimum sigma from IQR fit


# ── Math helpers ───────────────────────────────────────────────────────────────

def _normal_cdf(z: float) -> float:
    """Standard normal CDF via math.erf."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _prob_over(mu: float, sigma: float, line: float) -> float:
    """P(X > line) for X ~ N(mu, sigma)."""
    z = (line - mu) / max(sigma, _SIGMA_FLOOR)
    return round(1.0 - _normal_cdf(z), 6)


def _fit_uncertainty_distribution(
    point_est: float,
    lo: float,
    hi: float,
) -> Tuple[float, float]:
    """Derive (mu, sigma) from conformal interval.

    CV_ALTLINE_SIGMA_FIX (default OFF — byte-identical when OFF):
      OFF: original IQR divisor 1.349 (was incorrect for 80% CI — inflates sigma ~1.90x).
      ON:  correct divisor 2.5631 for an 80% CI (Q10–Q90): hi-lo = 2*1.2816*sigma.
           Tightens sigma to the correct value; P(X>line) moves away from 0.50,
           EV increases (was systematically understated by the inflated sigma).
    Note: the 12%/8%-per-point book-decay constants in _book_prob_at_alt_line are a
    SEPARATE unvalidated assumption (data-gated on Pinnacle alt prices) — not fixed here.
    See docs/_audits/BETTING_MATH_CORRECTNESS_AUDIT.md Bug 2.
    """
    import os as _os
    if _os.environ.get("CV_ALTLINE_SIGMA_FIX", "0").strip() in ("1", "true", "yes", "on"):
        # 80% CI (Q10–Q90) for Normal: hi - lo = 2 * z_{0.90} * sigma = 2.5631 * sigma
        divisor = 2.5631
    else:
        # Original IQR divisor (Q25–Q75): hi - lo = 1.349 * sigma — preserved for byte-identity
        divisor = 1.349
    sigma = max((hi - lo) / divisor, _SIGMA_FLOOR)
    return float(point_est), float(sigma)


def _american_to_prob(american_odds: int) -> float:
    """Implied probability from American odds (includes vig)."""
    if american_odds > 0:
        return 100.0 / (american_odds + 100.0)
    return abs(american_odds) / (abs(american_odds) + 100.0)


def _remove_vig(over_prob: float, under_prob: float) -> Tuple[float, float]:
    """Normalise over/under implied probs to sum to 1.0 (remove vig)."""
    total = over_prob + under_prob
    if total <= 0:
        return 0.5, 0.5
    return round(over_prob / total, 6), round(under_prob / total, 6)


def _book_prob_at_alt_line(vf_over: float, line_distance: float) -> float:
    """
    Decay vig-free book over-probability for alt lines.

    Pinnacle offers worse prices farther from the main line:
      - line_distance >= 0 (over is harder): 12% decay per point
      - line_distance < 0  (over is easier): 8% decay per point
    """
    if line_distance >= 0:
        # over is HARDER (higher alt line): book over-prob decays DOWN.
        return max(vf_over * (1.0 - 0.12 * abs(line_distance)), 0.01)
    # line_distance < 0: a LOWER alt line -> the OVER is EASIER -> book over-prob
    # should RISE toward 1. CV_ALTLINE_DECAY_DIR_FIX corrects the legacy form below,
    # which multiplied by (1 - 0.08*|d|) < 1 and wrongly LOWERED the over-prob ->
    # EV inflated on easier-over rungs (fake edge; /api/alt-ladder display only, the
    # slate/parlay path collapses alt-lines to mainline). Default OFF = byte-identical.
    if (os.environ.get("CV_ALTLINE_DECAY_DIR_FIX", "").strip().lower()
            not in ("", "0", "false", "no", "off")):
        return min(vf_over * (1.0 + 0.08 * abs(line_distance)), 0.99)
    return min(vf_over * (1.0 - 0.08 * abs(line_distance)), 0.99)


def _compute_ev(model_prob: float, book_prob: float) -> float:
    """EV = model_prob / book_prob - 1.0. Returns 0.0 if book_prob <= 0."""
    if book_prob <= 0:
        return 0.0
    return round(model_prob / book_prob - 1.0, 4)


def _kelly_fraction(model_prob: float, book_prob: float) -> float:
    """Quarter-Kelly (0.25 * full Kelly), capped at _KELLY_CAP_PER_BET. Returns 0.0 if book_prob <= 0."""
    if book_prob <= 0 or book_prob >= 1.0:
        return 0.0
    dec_odds = 1.0 / book_prob
    if dec_odds <= 1.0:
        return 0.0
    full_kelly = (model_prob * dec_odds - 1.0) / (dec_odds - 1.0)
    quarter_kelly = 0.25 * full_kelly
    return round(min(max(quarter_kelly, 0.0), _KELLY_CAP_PER_BET), 6)


# ── Public API ─────────────────────────────────────────────────────────────────

def build_alt_line_ladder(
    player: str,
    stat: str,
    point_estimate: float,
    conformal_interval: Tuple[float, float],
    pinnacle_signal: dict,
) -> list[dict]:
    """
    Build a 22-row EV ladder (11 offsets × over + under), sorted by EV descending.

    Args:
        player:             Player name (used for logging / ConformalPredictor lookup).
        stat:               Stat key (e.g. "pts", "reb").
        point_estimate:     Model point prediction.
        conformal_interval: (lo_80, hi_80) — 80% conformal interval from caller.
        pinnacle_signal:    {"line": float, "over_odds": int, "under_odds": int}

    Returns:
        List of dicts with keys: alt_line, direction, model_prob, book_prob, ev, kelly_raw.
    """
    lo, hi = conformal_interval
    mu, sigma = _fit_uncertainty_distribution(point_estimate, lo, hi)

    main_line: float = float(pinnacle_signal.get("line", point_estimate))
    over_odds: int = int(pinnacle_signal.get("over_odds", -110))
    under_odds: int = int(pinnacle_signal.get("under_odds", -110))

    over_imp = _american_to_prob(over_odds)
    under_imp = _american_to_prob(under_odds)
    vf_over, vf_under = _remove_vig(over_imp, under_imp)

    results: list[dict] = []
    for offset in _ALT_OFFSETS:
        alt_line = round(main_line + offset, 1)
        line_distance = alt_line - main_line  # == offset

        # Over
        model_prob_over = _prob_over(mu, sigma, alt_line)
        book_prob_over = _book_prob_at_alt_line(vf_over, line_distance)
        ev_over = _compute_ev(model_prob_over, book_prob_over)
        kelly_over = _kelly_fraction(model_prob_over, book_prob_over)

        results.append({
            "alt_line":   alt_line,
            "direction":  "over",
            "model_prob": model_prob_over,
            "book_prob":  round(book_prob_over, 4),
            "ev":         ev_over,
            "kelly_raw":  kelly_over,
        })

        # Under (complement)
        model_prob_under = round(1.0 - model_prob_over, 6)
        book_prob_under = round(1.0 - book_prob_over, 4)
        ev_under = _compute_ev(model_prob_under, book_prob_under)
        kelly_under = _kelly_fraction(model_prob_under, book_prob_under)

        results.append({
            "alt_line":   alt_line,
            "direction":  "under",
            "model_prob": model_prob_under,
            "book_prob":  book_prob_under,
            "ev":         ev_under,
            "kelly_raw":  kelly_under,
        })

    results.sort(key=lambda r: r["ev"], reverse=True)
    return results


def ladder_to_bets(
    ladder: list[dict],
    bankroll: float,
    edge_min: float = 0.04,
    kelly_cap: float = 0.02,
) -> list[dict]:
    """Filter ladder by EV threshold and convert kelly_raw to dollar stakes."""
    bets = []
    for row in ladder:
        if row.get("ev", 0.0) < edge_min:
            continue
        kelly = min(row.get("kelly_raw", 0.0), kelly_cap)
        stake = round(bankroll * kelly, 2)
        if stake <= 0:
            continue
        bets.append({**row, "stake": stake})
    return bets
