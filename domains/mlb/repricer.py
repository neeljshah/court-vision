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


class MLBRepricer:
    """In-game re-pricing for MLB using the over-dispersed NegBinom run engine."""

    def reprice(self, state: Any) -> Dict[str, Any]:
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
        remaining = max(0.0, _MLB_FULL_INNINGS - innings_played)
        frac = remaining / _MLB_FULL_INNINGS
        h0, a0 = int(state.home_score), int(state.away_score)

        if frac <= 0.0:
            return self._final_state_surface(h0, a0, state)

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
        """Deterministic surface once regulation is complete (ties -> extra innings TBD)."""
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
                "Re-pricing machinery only. In-game freshness is a real lane; whether "
                "live probs beat closing lines is a gate question. No edge claimed."
            ),
        }
