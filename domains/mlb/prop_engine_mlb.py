"""MLB player-prop DISTRIBUTION engine: per-player history -> P(over line).

Pipeline (mirrors domains/soccer/prop_engine.py):
  rate (player_rates_mlb, leak-free + shrunk)  x  exposure (exposure_mlb)  -> lam
    batter:  lam = per_pa   * E[PA]
    pitcher: lam = per_bf   * E[BF]
    Outs:    lam = per_start  (exposure-natural, modelled directly per start)
  lam  -->  count distribution (Poisson default, Negative-Binomial optional)
  dist -->  p_over(line)  -->  alt-line ladder.

Outputs are keyed by CANONICAL MLB stat names (player_rates_mlb.MLB_CANON) so they
join downstream to the scraped prop line's stat.

The Poisson/NB pmf + p_over math is REUSED from domains/soccer/prop_engine (pure
stdlib, sport-blind) so the two engines can never drift.

CALIBRATION / DISPERSION NOTE (load-bearing): Poisson assumes variance == mean.
MLB counting stats (esp. pitcher strikeouts) are mildly OVER-dispersed; modelling
them as pure Poisson makes the tails too TIGHT and FABRICATES fake edges. Supply
``dispersion`` (NB size r > 0; smaller r => more over-dispersion) to widen. The
width here is a PRIOR and MUST be calibrated later on realized outcomes before any
probability is trusted. No $-edge claims; calibration is the yardstick.

Public functions NEVER raise -- they degrade to {"status": "unknown"}.

Run the per-file test (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_prop_engine_mlb.py -q
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import pandas as pd

# Reuse the proven, sport-blind pmf + p_over math from the soccer engine.
from domains.soccer.prop_engine import _make_p_over
from domains.mlb.exposure_mlb import expected_bf, expected_pa
from domains.mlb.player_rates_mlb import (
    MLB_CANON,
    PER_START_STATS,
    batter_rate,
    is_pitcher_stat,
    pitcher_rate,
)

_EPS = 1e-9


def _resolve_rate_and_exposure(
    df, player_id, stat_canonical, as_of, exposure, batting_order
):
    """Return (lam, meta) or (None, meta) when unknown. meta carries rate/exposure.

    lam = rate * exposure, except per-start stats where lam = per_start directly.
    """
    meta: Dict[str, object] = {"rate": None, "exposure": None, "n": 0}
    if is_pitcher_stat(stat_canonical):
        rate = pitcher_rate(df, player_id, stat_canonical, as_of)
        if rate.get("status") != "ok":
            return None, meta
        if stat_canonical in PER_START_STATS:
            per_start = rate.get("per_start")
            meta.update(rate=per_start, exposure=1.0, n=rate.get("n_start", 0))
            if per_start is None:
                return None, meta
            return float(per_start), meta
        per_bf = rate.get("per_bf")
        meta["rate"] = per_bf
        meta["n"] = rate.get("n_bf", 0)
        if per_bf is None:
            return None, meta
        exp = exposure
        if exp is None:
            eb = expected_bf(df, player_id, as_of)
            exp = eb.get("e_bf")
        try:
            exp = float(exp)
        except (TypeError, ValueError):
            return None, meta
        meta["exposure"] = exp
        return float(per_bf) * max(exp, 0.0), meta

    # batter path
    rate = batter_rate(df, player_id, stat_canonical, as_of)
    if rate.get("status") != "ok":
        return None, meta
    per_pa = rate.get("per_pa")
    meta["rate"] = per_pa
    meta["n"] = rate.get("n_pa", 0)
    if per_pa is None:
        return None, meta
    exp = exposure
    if exp is None:
        ep = expected_pa(df, player_id, as_of, batting_order=batting_order)
        exp = ep.get("e_pa")
    try:
        exp = float(exp)
    except (TypeError, ValueError):
        return None, meta
    meta["exposure"] = exp
    return float(per_pa) * max(exp, 0.0), meta


def prop_distribution(
    df: pd.DataFrame,
    player_id,
    stat_canonical: str,
    as_of,
    *,
    exposure: Optional[float] = None,
    dispersion: Optional[float] = None,
    batting_order=None,
) -> Dict[str, object]:
    """Build the count distribution for one player + canonical MLB stat.

    Returns {"lam", "model", "p_over"(callable), "status", "rate", "exposure",
    "n"}. lam = rate x exposure (batter per_pa*E[PA]; pitcher per_bf*E[BF]; Outs
    per_start directly). model is "negbin" when ``dispersion`` (NB size r) > 0 else
    "poisson". p_over(line) = P(X > line). Degrades to status "unknown" (no
    fabricated probability) when the rate or exposure is unknown. Never raises.
    """
    unknown = {
        "lam": None, "model": None, "p_over": None, "status": "unknown",
        "rate": None, "exposure": None, "n": 0,
    }
    if stat_canonical not in MLB_CANON:
        return dict(unknown)

    try:
        lam, meta = _resolve_rate_and_exposure(
            df, player_id, stat_canonical, as_of, exposure, batting_order
        )
    except Exception:
        return dict(unknown)

    if lam is None or lam < 0.0 or not math.isfinite(lam):
        out = dict(unknown)
        out.update(rate=meta.get("rate"), exposure=meta.get("exposure"),
                   n=meta.get("n", 0))
        return out

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
        "rate": meta.get("rate"),
        "exposure": meta.get("exposure"),
        "n": meta.get("n", 0),
    }


def prop_ladder(
    df: pd.DataFrame,
    player_id,
    stat_canonical: str,
    as_of,
    lines: List[float],
    **kw,
) -> List[Dict[str, object]]:
    """Alt-line ladder: [{"line", "p_over", "p_under"}] for each line.

    Returns an entry per line with p_over=None/p_under=None when the distribution
    is unknown (never a fabricated probability). Never raises.
    """
    dist = prop_distribution(df, player_id, stat_canonical, as_of, **kw)
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
