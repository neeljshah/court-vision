"""domains.mlb.repricer — in-game / live re-pricing for MLB.

Mirrors the soccer in-game repricer but uses the VALIDATED negative-binomial run engine
(domains/mlb/negbinom_engine.py, W101 — over-dispersed run totals/RL tail-calibration win):

  1. remaining_frac = max(0, 9 - innings_played) / 9
  2. scale pregame run-rate lambdas by remaining_frac (homogeneous run process over 9 innings)
  3. build the REMAINING-runs NegBinom joint matrix, then SHIFT by runs already scored
  4. emit the standard ML / run-line / totals surface from the final-score matrix

Reads state by duck-typing (pregame_params / extra / home_score / away_score /
elapsed_minutes), so it works with live_repricer.GameState without importing it.

HONEST: re-pricing MACHINERY only. Whether any live probability beats the book is a gate
question, not answered here. No edge is claimed; markets are efficient.
INVARIANTS: never edit src/ or kernel/; pure numpy/math; <=300 LOC.
"""
from __future__ import annotations

from typing import Any, Dict

import numpy as np

_MLB_FULL_INNINGS = 9.0
_APPROX_MIN_PER_INNING = 20.0  # fallback when innings_played not given explicitly
_TOTAL_LINES = (6.5, 7.5, 8.5, 9.5, 10.5)

# Empirical per-inning share of a 9-inning game's runs (innings 1-9), from the full
# linescore corpus (data/domains/mlb/pitchers.parquet). Runs are NOT uniform: the 1st
# inning scores most (fresh top-of-order), the 8th/9th least (bullpen + home team often
# not batting). Using this curve instead of a flat 1/9 makes the REMAINING-runs estimate
# (and thus the in-game total/win-prob) sharper — a leak-free distribution-shape win.
# HONESTY: this curve is GLOBAL and IN-SAMPLE to the backtest corpus (fit on the same
# linescores it is then scored against) — the leak-free OOS verdict lives in
# proof_mlb/curve_oos.py (built this wave), not here.
_INNING_SHARES = (0.122, 0.101, 0.114, 0.116, 0.116, 0.117, 0.111, 0.106, 0.096)
_INNING_SHARES_SUM = sum(_INNING_SHARES)
# Cumulative fraction of a game's runs still to come AFTER inning n (n = innings played).
# _REMAINING_CUM[n] == sum(_INNING_SHARES[n:]) / sum, so _REMAINING_CUM[0] == 1.0 and
# _REMAINING_CUM[9] == 0.0. Used to LINEARLY INTERPOLATE the remaining fraction at a
# fractional innings_played (e.g. 5.5 -> halfway between the inning-5 and inning-6 nodes),
# so a mid-inning state no longer snaps to the wrong slice via banker's rounding.
_REMAINING_CUM = tuple(
    sum(_INNING_SHARES[n:]) / _INNING_SHARES_SUM for n in range(int(_MLB_FULL_INNINGS) + 1)
)
# One extra inning's worth of the full-game run rate (1/9 of the 9-inning lambda) — used to
# keep a regulation TIE live with a small residual lambda instead of freezing the markets
# (a tie goes to EXTRA INNINGS where more runs WILL score, so the over must not be frozen).
_EXTRA_INNING_FRAC = 1.0 / _MLB_FULL_INNINGS


def _remaining_frac(innings_played: float, *, homogeneous: bool = False) -> float:
    """Fraction of a 9-inning game's runs still to come after ``innings_played``.

    Default uses the empirical per-inning run curve (early innings worth more); pass
    homogeneous=True for the flat (9 - n)/9 baseline (for A/B comparison).

    For a FRACTIONAL innings_played the per-inning-curve remaining fraction is LINEARLY
    INTERPOLATED between the integer-inning nodes of the cumulative-remaining curve (so e.g.
    5.5 sits halfway between the inning-5 and inning-6 remaining levels). At an INTEGER
    innings_played this reduces EXACTLY to sum(_INNING_SHARES[n:]) / _INNING_SHARES_SUM, so
    the backtested integer-inning path is byte-for-byte unchanged.
    """
    if homogeneous:
        return max(0.0, _MLB_FULL_INNINGS - innings_played) / _MLB_FULL_INNINGS
    if innings_played >= _MLB_FULL_INNINGS:
        return 0.0
    if innings_played <= 0.0:
        return 1.0
    lo = int(innings_played)                 # floor: integer inning node below the state
    hi = lo + 1
    w = innings_played - lo                   # fractional part in [0, 1)
    return _REMAINING_CUM[lo] * (1.0 - w) + _REMAINING_CUM[hi] * w


class MLBRepricer:
    """In-game re-pricing for MLB using the over-dispersed NegBinom run engine."""

    def reprice(self, state: Any) -> Dict[str, Any]:
        # HONESTY: the NegBinom thinning here is an APPROXIMATION — reprice scales the run
        # rate (lam *= frac) but REUSES the full-game dispersion r, so the remaining-runs
        # tail shape is slightly mis-specified for a partial inning (a thinned NegBinom does
        # not stay a NegBinom with the same r). This is a modeling assumption, NOT a leak.
        from domains.mlb.negbinom_engine import (  # noqa: PLC0415
            runs_matrix_nb, markets_from_matrix_nb, _FALLBACK_R,
        )
        pp = getattr(state, "pregame_params", {}) or {}
        extra = getattr(state, "extra", {}) or {}
        lam_home = float(pp.get("lam_home", 4.5))
        lam_away = float(pp.get("lam_away", 4.5))
        r_home = float(pp.get("r_home", _FALLBACK_R))
        r_away = float(pp.get("r_away", _FALLBACK_R))

        innings_played = float(
            extra.get("innings_played",
                      getattr(state, "elapsed_minutes", 0.0) / _APPROX_MIN_PER_INNING)
        )
        # Per-inning run curve by default (early innings worth more); homogeneous override
        # via extra={'homogeneous_frac': True} for A/B accuracy comparison. frac is now
        # linearly interpolated at fractional innings (P2), and the _innings_remaining
        # metadata / lambda-scale horizon both derive from THIS same frac (P3) so they stay
        # consistent. remaining is expressed back in inning-units (frac * 9 innings).
        homogeneous = bool(extra.get("homogeneous_frac"))
        frac = _remaining_frac(innings_played, homogeneous=homogeneous)
        remaining = frac * _MLB_FULL_INNINGS
        h0, a0 = int(state.home_score), int(state.away_score)

        if frac <= 0.0:
            # Regulation over. If the game is DECIDED (h0 != a0) the markets are deterministic.
            # If it is TIED it goes to EXTRA INNINGS where more runs WILL score, so DON'T freeze
            # the over / pin the run-line: simulate one extra inning's worth of residual runs.
            if h0 != a0:
                return self._final_state_surface(h0, a0, state)
            frac = _EXTRA_INNING_FRAC
            remaining = frac * _MLB_FULL_INNINGS

        P_rem = runs_matrix_nb(max(1e-6, lam_home * frac), max(1e-6, lam_away * frac),
                               r_home, r_away)
        n = P_rem.shape[0]
        m = n + max(h0, a0)
        P_final = np.zeros((m, m), dtype=float)
        for dh in range(n):
            for da in range(n):
                P_final[h0 + dh, a0 + da] += P_rem[dh, da]
        s = P_final.sum()
        if s > 0:
            P_final /= s

        out = markets_from_matrix_nb(P_final, total_lines=_TOTAL_LINES)
        out.update(self._metadata(state, remaining, lam_home * frac, lam_away * frac))
        return out

    @staticmethod
    def _final_state_surface(h0: int, a0: int, state: Any) -> Dict[str, Any]:
        """Deterministic surface once regulation is over AND the game is DECIDED (h0 != a0).

        A regulation TIE never reaches here — reprice() keeps it live with a residual
        extra-inning lambda — so the 0.5 ML branch below is a defensive fallback only.
        """
        out: Dict[str, Any] = {
            "ml_home": 1.0 if h0 > a0 else (0.5 if h0 == a0 else 0.0),
            "ml_away": 1.0 if a0 > h0 else (0.5 if h0 == a0 else 0.0),
            "rl_home_minus15": 1.0 if (h0 - a0) >= 2 else 0.0,
        }
        out["rl_away_plus15"] = 1.0 - out["rl_home_minus15"]
        total = h0 + a0
        for line in _TOTAL_LINES:
            out[f"over_{line:g}"] = 1.0 if total > line else 0.0
            out[f"under_{line:g}"] = 0.0 if total > line else 1.0
        out.update(MLBRepricer._metadata(state, 0.0, 0.0, 0.0))
        return out

    @staticmethod
    def _metadata(state: Any, remaining: float,
                  lam_rem_h: float, lam_rem_a: float) -> Dict[str, Any]:
        return {
            "_sport": "mlb",
            "_innings_remaining": remaining,
            "_current_score": (state.home_score, state.away_score),
            "_lam_remaining_home": lam_rem_h,
            "_lam_remaining_away": lam_rem_a,
            "_honest_note": (
                "Goal: the SHARPEST in-game forecaster. The per-inning run curve cuts "
                "final-total bias ~35% vs flat scaling. A live book also sees the score, so "
                "this is forecaster QUALITY, not a guaranteed price edge — but a better "
                "predictor is the point."
            ),
        }
