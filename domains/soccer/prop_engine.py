"""Soccer player-prop DISTRIBUTION engine: per-player history -> P(over line).

Pipeline:
  per90 (player_rates, leak-free + shrunk)  -->  lam = per90 * E[minutes]/90 * opp
  lam  -->  count distribution (Poisson default, Negative-Binomial optional)
  dist -->  p_over(line)  -->  alt-line ladder.

Outputs are keyed by CANONICAL stat names (player_rates.CANON_TO_COLS) so they
join downstream to the scraped prop line's stat.

CALIBRATION / DISPERSION NOTE (load-bearing):
  Poisson assumes variance == mean. Real counting stats like Shots are mildly
  OVER-dispersed (variance > mean); modelling them as pure Poisson makes the
  distribution too TIGHT, which FABRICATES fake edges at the tails. Supply
  ``dispersion`` (NB size parameter r > 0; smaller r => more over-dispersion) to
  widen the distribution. Conversely some stats are UNDER-dispersed. Either way
  the width (sigma) here is a PRIOR and MUST be calibrated later against realized
  outcomes (e.g. conformal / isotonic on out-of-sample residuals) before any
  probability is trusted for sizing. A too-tight distribution lies.

Public functions NEVER raise -- they degrade to {"status": "unknown"}.

Run the per-file test (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_prop_engine.py -q
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional

import pandas as pd

from domains.soccer.player_minutes import expected_minutes
from domains.soccer.player_rates import CANON_TO_COLS, player_rate

_FULL_MATCH_MIN = 90.0
_EPS = 1e-9
# Cap the pmf summation so a pathological lam can never spin forever.
_MAX_K = 2000


def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) for X ~ Poisson(lam). Pure stdlib (math.exp/lgamma)."""
    if lam < 0 or k < 0:
        return 0.0
    if lam == 0.0:
        return 1.0 if k == 0 else 0.0
    return math.exp(k * math.log(lam) - lam - math.lgamma(k + 1.0))


def _negbin_pmf(k: int, mean: float, r: float) -> float:
    """P(X = k) for a Negative Binomial parameterised by (mean, size r).

    Variance = mean + mean^2 / r, so variance > mean (over-dispersion); as
    r -> inf this collapses to Poisson(mean). p = r / (r + mean).
    """
    if mean < 0 or k < 0 or r <= 0:
        return 0.0
    if mean == 0.0:
        return 1.0 if k == 0 else 0.0
    p = r / (r + mean)
    # log C(k+r-1, k) + r*log(p) + k*log(1-p)
    log_coef = math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1.0)
    return math.exp(log_coef + r * math.log(p) + k * math.log(1.0 - p))


def _make_p_over(lam: float, model: str, r: Optional[float]) -> Callable[[float], float]:
    """Return p_over(line) = P(X > line). For half-integer lines this is
    1 - sum_{k<=floor(line)} pmf(k); for integer lines P(X > line) excludes the
    line itself (strictly greater)."""
    if model == "negbin":
        def pmf(k: int) -> float:
            return _negbin_pmf(k, lam, r)
    else:
        def pmf(k: int) -> float:
            return _poisson_pmf(k, lam)

    def p_over(line: float) -> float:
        try:
            line = float(line)
        except (TypeError, ValueError):
            return float("nan")
        if line < 0:
            return 1.0
        k_max = int(math.floor(line))
        cdf = 0.0
        for k in range(0, min(k_max, _MAX_K) + 1):
            cdf += pmf(k)
        p = 1.0 - cdf
        if p < 0.0:
            p = 0.0
        elif p > 1.0:
            p = 1.0
        return p

    return p_over


def prop_distribution(
    df: pd.DataFrame,
    player_id,
    stat_canonical: str,
    as_of_date,
    *,
    e_minutes: Optional[float] = None,
    position=None,
    opp_mult: float = 1.0,
    dispersion: Optional[float] = None,
    club_prior=None,
) -> Dict[str, object]:
    """Build the count distribution for one player + canonical stat.

    Returns {"lam", "model", "p_over" (callable), "status", "per90", "e_minutes",
    "n_eff"}. lam = per90 * (e_minutes or E[minutes]) / 90 * opp_mult.
    model is "negbin" when ``dispersion`` (NB size r) > 0 else "poisson".
    ``club_prior`` (optional {"per90","starts"}) is forwarded to player_rate as a
    strong club-season prior; None -> exact prior behaviour. n_eff surfaces the
    rate's effective sample so callers can recompute confidence. Degrades to status
    "unknown" (no fabricated probability) when the rate or minutes are unknown.
    Never raises.
    """
    unknown = {
        "lam": None,
        "model": None,
        "p_over": None,
        "status": "unknown",
        "per90": None,
        "e_minutes": None,
        "n_eff": 0.0,
    }

    if stat_canonical not in CANON_TO_COLS:
        return dict(unknown)

    rate = player_rate(
        df, player_id, stat_canonical, as_of_date,
        position=position, club_prior=club_prior,
    )
    if rate.get("status") != "ok" or rate.get("per90") is None:
        return dict(unknown)
    per90 = float(rate["per90"])
    n_eff = float(rate.get("n_eff", 0.0) or 0.0)

    mins = e_minutes
    if mins is None:
        em = expected_minutes(df, player_id, as_of_date)
        if em.get("status") != "ok" or em.get("e_minutes") is None:
            return dict(unknown)
        mins = float(em["e_minutes"])
    else:
        try:
            mins = float(mins)
        except (TypeError, ValueError):
            return dict(unknown)

    try:
        opp = float(opp_mult)
    except (TypeError, ValueError):
        opp = 1.0

    lam = per90 * max(mins, 0.0) / _FULL_MATCH_MIN * opp
    if lam < 0.0 or not math.isfinite(lam):
        return dict(unknown)

    r: Optional[float] = None
    model = "poisson"
    if dispersion is not None:
        try:
            r = float(dispersion)
        except (TypeError, ValueError):
            r = None
        if r is not None and r > 0.0:
            model = "negbin"
        else:
            r = None

    return {
        "lam": float(lam),
        "model": model,
        "p_over": _make_p_over(lam, model, r),
        "status": "ok",
        "per90": per90,
        "e_minutes": float(mins),
        "n_eff": n_eff,
    }


def prop_ladder(
    df: pd.DataFrame,
    player_id,
    stat_canonical: str,
    as_of_date,
    lines: List[float],
    **kw,
) -> List[Dict[str, object]]:
    """Alt-line ladder: [{"line", "p_over", "p_under"}] for each line.

    Returns an entry per line with p_over=None/p_under=None when the distribution
    is unknown (never a fabricated probability). Never raises.
    """
    dist = prop_distribution(df, player_id, stat_canonical, as_of_date, **kw)
    out: List[Dict[str, object]] = []
    p_over = dist.get("p_over")
    ok = dist.get("status") == "ok" and callable(p_over)
    for line in lines or []:
        if ok:
            p = p_over(line)  # type: ignore[misc]
            if isinstance(p, float) and math.isnan(p):
                out.append({"line": line, "p_over": None, "p_under": None})
            else:
                out.append({"line": line, "p_over": p, "p_under": 1.0 - p})
        else:
            out.append({"line": line, "p_over": None, "p_under": None})
    return out
