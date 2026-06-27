"""scripts.platformkit.ingame.ingame_prop_repricer -- in-game P(over) re-pricer.

Re-prices a player prop as the game elapses by shrinking the pregame expected
count toward the realized state. Sport-blind: takes the engine's pregame
distribution (lam, model family, dispersion) plus live (frac_elapsed,
realized_so_far) and returns the updated P(over line).

MATHEMATICAL MODEL (additive count stats: hits, RBIs, shots, etc.)
------------------------------------------------------------------
Decompose the final stat into [realized_so_far, remaining]:

    final = realized_so_far + remaining
    remaining ~ same family (Poisson / Negative-Binomial) with shrunken lam:
        lam_remaining = lam_full * (1 - frac_elapsed)

Then:

    P(final > line) = P(remaining > line - realized_so_far)

Edge cases (no fabrication):
  * realized_so_far already > line -> already cleared -> p_over = 1.0.
  * line - realized_so_far <= -1 (strictly negative integer-line residual) -> 1.0.
  * frac_elapsed = 0 -> identity (returns the pregame p_over evaluated at line).
  * frac_elapsed >= 1.0 (FINAL) -> None (no in-game bet; settler handles).
  * lam_full is None / non-finite / negative -> None (skip).
  * The engine flagged status != "ok" -> None.

HONEST RAILS (binding)
----------------------
  * The ONLY validated lever is FRESHNESS (exposure shrinks linearly with
    frac_elapsed). This is a CALIBRATION step on realized information, NOT a
    $ edge. edge_claimed stays False; UNITS only.
  * The re-pricer NEVER fabricates -- a missing field / FINAL game / unknown
    distribution -> None (clean skip, never a guessed probability).
  * The in-play day-trader STILL gates every placement (calibration_justified
    + liquid + fresh + tier floor). This module only supplies the number.
  * No flag flip, no data/registry write, no edges claimed in any output.

NON-GOALS for v1
----------------
  * Realized stat ingest (per-player box-score read) -- caller supplies the
    realized_so_far map. Defaults to 0 (pure freshness re-price) when absent.
  * Non-additive stats (e.g. "Anytime Goal" is already binary; "Outs" is per-
    start scalar). For non-additive stats the re-pricer falls back to the
    pregame p_over evaluated at the same line (no decay applied) -- callers can
    pass freshness=None to opt out of decay entirely.

RAILS: build only under scripts/platformkit/; never edit src/ or kernel/;
ASCII; <=300 LOC; pure (no network); public fns NEVER raise.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ingame/test_ingame_prop_repricer.py -q
"""
from __future__ import annotations

import logging
import math
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Additive count stats whose final value = realized + remaining (Poisson-ish).
# Anything outside this set falls back to a no-decay reprice (pregame number).
_ADDITIVE_STATS = frozenset({
    # Soccer
    "Shots", "Shots On Target", "Saves", "Tackles", "Assists",
    "Passes Attempted", "Passes Completed", "Fouls", "Fouls Drawn",
    "Cards", "Goals", "Goal+Assist", "Offsides",
    # MLB batter
    "Hits", "Total Bases", "RBIs", "Runs", "Home Runs", "Walks",
    "Batter Strikeouts", "Stolen Bases",
    # MLB composite batter (sum of counts -> additive in the mean)
    "Hits+Runs+RBIs",
    # MLB pitcher
    "Strikeouts", "Pitcher Strikeouts", "Walks Allowed", "Hits Allowed", "Earned Runs",
})


def _is_additive(stat_canonical: Optional[str]) -> bool:
    """True when the final stat decomposes cleanly as realized + remaining."""
    return str(stat_canonical or "") in _ADDITIVE_STATS


def _shrink_lam(lam_full: float, frac_elapsed: float) -> Optional[float]:
    """Exposure-fraction shrink: lam_remaining = lam_full * (1 - frac).
    None on invalid frac / lam."""
    try:
        lam_f = float(lam_full)
        frac_f = float(frac_elapsed)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lam_f) or lam_f < 0.0:
        return None
    if not (0.0 <= frac_f < 1.0):
        return None
    remaining_frac = max(0.0, 1.0 - frac_f)
    return lam_f * remaining_frac


def _build_p_over(lam_remaining: float, model: str,
                  dispersion: Optional[float]) -> Optional[Callable[[float], float]]:
    """Rebuild the engine's tail-probability callable at the SHRUNKEN lam.

    Reuses domains.soccer.prop_engine._make_p_over (sport-blind Poisson / NB
    tail; the MLB engine already shares this helper). None on import error so
    the re-pricer degrades cleanly instead of fabricating a number.
    """
    try:
        from domains.soccer.prop_engine import _make_p_over  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_prop_repricer: _make_p_over import failed: %s", exc)
        return None
    r: Optional[float] = None
    mdl = "poisson"
    if dispersion is not None:
        try:
            r = float(dispersion)
        except (TypeError, ValueError):
            r = None
        if r is not None and r > 0.0:
            mdl = "negbin"
        else:
            r = None
    if str(model) == "negbin" and r is not None:
        mdl = "negbin"
    try:
        return _make_p_over(float(lam_remaining), mdl, r)
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_prop_repricer: _make_p_over build failed: %s", exc)
        return None


def reprice_prop(
    *,
    lam_full: Optional[float],
    line: float,
    frac_elapsed: float,
    realized_so_far: float = 0.0,
    model: str = "poisson",
    dispersion: Optional[float] = None,
    p_over_full: Optional[Callable[[float], float]] = None,
    stat_canonical: Optional[str] = None,
) -> Optional[float]:
    """In-game P(stat > line) for a player prop. None when un-priceable.

    Re-prices via exposure-fraction shrink on additive count stats; falls back
    to the pregame p_over evaluated at *line* for non-additive stats (no decay
    applied) so a non-additive prop still re-quotes consistently.

    Args:
        lam_full: pregame expected count (from engine.prop_distribution["lam"]).
        line: the over/under line.
        frac_elapsed: in [0, 1). 0 = pregame; >=1 means FINAL -> None.
        realized_so_far: player's current tally for this stat (default 0).
        model: "poisson" | "negbin" (engine.prop_distribution["model"]).
        dispersion: NB size parameter (engine.prop_distribution -- forward as-is).
        p_over_full: pregame p_over callable (engine.prop_distribution["p_over"]),
            used for the non-additive / freshness-disabled fallback. Optional.
        stat_canonical: canonical stat name (Shots / Hits / RBIs / etc.).
            Determines additive vs non-additive routing. None -> assumed additive
            (conservative: re-price with freshness).

    Returns:
        Updated P(over line) in [0, 1], or None on un-priceable input. NEVER
        raises (a model miss is a clean skip).
    """
    try:
        line_f = float(line)
    except (TypeError, ValueError):
        return None

    try:
        realized_f = float(realized_so_far)
    except (TypeError, ValueError):
        realized_f = 0.0
    if not math.isfinite(realized_f) or realized_f < 0.0:
        realized_f = 0.0

    # Additive stat fast paths -----------------------------------------------
    if _is_additive(stat_canonical) or stat_canonical is None:
        # Already cleared the line -- no remaining count needed.
        if realized_f > line_f:
            return 1.0
        # Residual line (what remaining count must exceed).
        line_remaining = line_f - realized_f
        # If residual is strictly < 0 (e.g. line 0.5, realized 1 -> residual -0.5),
        # P(remaining > -0.5) for any non-negative count = 1.0.
        if line_remaining < 0.0:
            return 1.0
        lam_remaining = _shrink_lam(lam_full, frac_elapsed) \
            if lam_full is not None else None
        if lam_remaining is None:
            # Lam unusable -- fall through to the non-additive fallback below.
            pass
        else:
            p_over_fn = _build_p_over(lam_remaining, model, dispersion)
            if p_over_fn is None:
                return None
            try:
                p = float(p_over_fn(line_remaining))
            except Exception as exc:  # noqa: BLE001
                logger.debug("ingame_prop_repricer: p_over eval failed: %s", exc)
                return None
            if math.isnan(p) or not math.isfinite(p):
                return None
            return max(0.0, min(1.0, p))

    # Non-additive / freshness-unavailable fallback ---------------------------
    # Re-evaluate the pregame p_over at the original line (no decay). Caller
    # ends up with the pregame number again -- honest: nothing was re-priced.
    if p_over_full is None:
        return None
    try:
        p = float(p_over_full(line_f))
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_prop_repricer: pregame p_over fallback failed: %s", exc)
        return None
    if math.isnan(p) or not math.isfinite(p):
        return None
    return max(0.0, min(1.0, p))


def reprice_from_dist(
    dist: Dict[str, Any],
    *,
    line: float,
    frac_elapsed: float,
    realized_so_far: float = 0.0,
    stat_canonical: Optional[str] = None,
) -> Optional[float]:
    """Convenience: re-price using the FULL distribution dict from prop_distribution.

    *dist* is whatever `engine.prop_distribution(...)` returned:
      {"lam", "model", "p_over"(callable), "status", "rate", "exposure", "n", ...}.
    Returns None when dist is missing / status != "ok" / lam unusable. Never raises.
    """
    if not isinstance(dist, dict):
        return None
    if str(dist.get("status") or "") != "ok":
        return None
    return reprice_prop(
        lam_full=dist.get("lam"),
        line=line,
        frac_elapsed=frac_elapsed,
        realized_so_far=realized_so_far,
        model=str(dist.get("model") or "poisson"),
        dispersion=None,  # the dist's p_over already bakes dispersion; we rebuild
        p_over_full=dist.get("p_over"),
        stat_canonical=stat_canonical,
    )


__all__ = ["reprice_prop", "reprice_from_dist"]
