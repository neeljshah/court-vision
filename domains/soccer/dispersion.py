"""Per-stat Negative-Binomial dispersion calibration for soccer player props.

WHY THIS EXISTS (load-bearing honesty):
  Poisson assumes variance == mean. Real soccer counting stats (Shots, Fouls...)
  are mildly OVER-dispersed: variance > mean. Modelling them as pure Poisson makes
  the count distribution too TIGHT, which FABRICATES fake edges at the tails
  (a +131% "EV" on thin early-tournament data is an artifact, not a real edge).
  This module estimates, leak-free, a per-stat dispersion index phi = var/mean and
  exposes it so the edge board can widen the tails (NB with variance = lam*phi).

DESIGN (phi, not r -- the cleaner path):
  We calibrate and return a per-stat dispersion INDEX phi = var/mean (a scale-free
  number), NOT a fixed NB size r. The NB size depends on the per-row mean lam, so a
  single global r would be wrong for players with different lam. Instead the caller
  converts phi to a ROW-SPECIFIC size: r_row = lam / (phi - 1) when phi > 1, else
  Poisson. That makes NB variance = lam + lam^2/r_row = lam + lam*(phi-1) = lam*phi,
  i.e. the realized over-dispersion is applied at each row's own scale. We DO also
  return a representative ``r`` (phi evaluated at a per-stat representative mean) for
  callers that want a single size, but the row-specific path is preferred.

PRIORS (thin data -> trust a prior, not a noisy fit):
  With only ~24 matches the per-stat fit is noisy. When the pooled player-match
  sample for a stat is small (< _MIN_N) or has no mean, we fall back to a SENSIBLE
  PER-STAT PRIOR phi (typical soccer count over-dispersion) and status "prior".
  Representative means (_REP_MEAN) are documented per stat and used only to turn a
  prior phi into the optional representative r.

LEAK-FREE (load-bearing): the fit pools ONLY player-match rows whose ``date`` is
STRICTLY BEFORE ``as_of_date``. A match on/after as_of never enters the fit.

Public functions NEVER raise -- they degrade to a status, never fabricate width.

Per-file test (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_dispersion.py -q
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from domains.soccer.player_rates import CANON_TO_COLS, _prior_rows

_EPS = 1e-9
# Minimum pooled player-match rows before we trust a fit over the prior.
_MIN_N = 40
# NB size clamp: r below 1 is wildly over-dispersed (suspect); above 50 ~ Poisson.
_R_MIN = 1.0
_R_MAX = 50.0

# Per-stat PRIOR dispersion index phi (variance/mean) -- typical soccer
# count over-dispersion. Used when the fit is too thin to trust. Cards/Goals/
# Assists are rare/Bernoulli-ish so Poisson (phi~1) is already wide enough.
_PRIOR_PHI: Dict[str, float] = {
    "Shots": 1.35,
    "Shots On Target": 1.25,
    "Fouls": 1.20,
    "Fouls Drawn": 1.20,
    "Cards": 1.00,
    "Assists": 1.00,
    "Goal+Assist": 1.05,
    "Goals": 1.00,
    "Offsides": 1.10,
    "Saves": 1.20,
}
# Representative per-match mean for each stat (typical starter), used ONLY to turn
# a prior/clamped phi into the optional single representative r = m/(phi-1).
_REP_MEAN: Dict[str, float] = {
    "Shots": 1.6,
    "Shots On Target": 0.6,
    "Fouls": 1.2,
    "Fouls Drawn": 1.2,
    "Cards": 0.2,
    "Assists": 0.15,
    "Goal+Assist": 0.35,
    "Goals": 0.2,
    "Offsides": 0.4,
    "Saves": 0.9,
}
_DEFAULT_PRIOR_PHI = 1.20
_DEFAULT_REP_MEAN = 1.0


def _r_from_phi(phi: float, mean: float) -> Optional[float]:
    """Convert a dispersion index phi at a given mean to an NB size r, clamped.

    r = mean / (phi - 1). phi <= 1 (at/under Poisson) -> None (Poisson is fine).
    """
    if phi is None or mean is None:
        return None
    if phi <= 1.0 or mean <= 0.0:
        return None
    r = mean / (phi - 1.0)
    if r < _R_MIN:
        r = _R_MIN
    elif r > _R_MAX:
        r = _R_MAX
    return float(r)


def _match_counts(df: pd.DataFrame, stat_canonical: str, as_of_date):
    """Per-(player,match) total stat counts for rows before as_of with minutes>0.

    Returns a pandas Series of counts (one per qualifying player-match row), or
    None when the stat / data are unusable. Leak-free via _prior_rows.
    """
    cols = CANON_TO_COLS.get(stat_canonical)
    if cols is None:
        return None
    prior = _prior_rows(df, as_of_date)
    if prior is None or len(prior) == 0:
        return None
    if "minutes" in prior.columns:
        mins = pd.to_numeric(prior["minutes"], errors="coerce").fillna(0.0)
        prior = prior.loc[mins > 0.0]
    if len(prior) == 0:
        return None
    counts = pd.Series(0.0, index=prior.index)
    have_any = False
    for col in cols:
        if col in prior.columns:
            counts = counts + pd.to_numeric(prior[col], errors="coerce").fillna(0.0)
            have_any = True
    if not have_any:
        return None
    return counts


def stat_dispersion(df: pd.DataFrame, stat_canonical: str, as_of_date) -> Dict[str, object]:
    """Leak-free NB dispersion for one canonical stat.

    Returns {"r", "phi", "n", "status"}:
      * phi = var/mean (dispersion index). >1 over-dispersed, <=1 Poisson-ok.
      * r   = representative NB size (phi at the stat's representative mean), or
              None when phi<=1 (Poisson is already wide enough).
      * n   = pooled player-match rows used.
      * status: "ok" (trusted fit), "prior" (thin -> per-stat prior phi used),
                "unknown" (stat not modelled / no data at all).
    Never raises.
    """
    if stat_canonical not in CANON_TO_COLS:
        return {"r": None, "phi": _DEFAULT_PRIOR_PHI, "n": 0, "status": "unknown"}

    prior_phi = _PRIOR_PHI.get(stat_canonical, _DEFAULT_PRIOR_PHI)
    rep_mean = _REP_MEAN.get(stat_canonical, _DEFAULT_REP_MEAN)

    counts = _match_counts(df, stat_canonical, as_of_date)
    if counts is None or len(counts) == 0:
        # No usable data at all -> lean fully on the prior.
        return {"r": _r_from_phi(prior_phi, rep_mean), "phi": float(prior_phi),
                "n": 0, "status": "prior"}

    n = int(len(counts))
    m = float(counts.mean())

    if n < _MIN_N or m <= 0.0:
        # Too thin (or degenerate mean) to trust the empirical fit.
        return {"r": _r_from_phi(prior_phi, rep_mean), "phi": float(prior_phi),
                "n": n, "status": "prior"}

    # Population variance (ddof=0): the MLE dispersion index for the pooled sample.
    v = float(counts.var(ddof=0))
    phi = v / m if m > 0.0 else 1.0

    if phi <= 1.0:
        # At/under Poisson -> Poisson is already wide enough; no NB widening.
        return {"r": None, "phi": float(phi), "n": n, "status": "ok"}

    return {"r": _r_from_phi(phi, rep_mean), "phi": float(phi), "n": n, "status": "ok"}


def all_dispersions(df: pd.DataFrame, as_of_date) -> Dict[str, Dict[str, object]]:
    """Compute stat_dispersion for every canonical stat once (for the board)."""
    out: Dict[str, Dict[str, object]] = {}
    for stat in CANON_TO_COLS:
        out[stat] = stat_dispersion(df, stat, as_of_date)
    return out


def r_for_lam(phi: Optional[float], lam: Optional[float]) -> Optional[float]:
    """Row-specific NB size for a given dispersion index phi and row mean lam.

    r_row = lam / (phi - 1) when phi > 1 (NB variance = lam*phi); else None
    (Poisson). Public helper used by the edge board. Never raises.
    """
    try:
        if phi is None or lam is None:
            return None
        return _r_from_phi(float(phi), float(lam))
    except (TypeError, ValueError):
        return None


__all__ = ["stat_dispersion", "all_dispersions", "r_for_lam"]
