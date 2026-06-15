"""domains.basketball_nba.repricer — in-game / live re-pricing for NBA.

NBA is high-scoring and continuous, so a discrete scoreline matrix (soccer/MLB) is the
wrong shape. Instead this uses the validated in-game KEYSTONE — the realized score is an
ever-tightening ANCHOR (pooled team-score RMSE shrinks Q1≈12.5 → Q4≈4.2) — via a Gaussian
remaining-points model:

  final_margin ~ Normal( (home-away) + (mu_home-mu_away)*rem_frac, margin_sigma^2 * rem_frac )
  final_total  ~ Normal( (home+away) + (mu_home+mu_away)*rem_frac, total_sigma^2 * rem_frac )

Variance scales with the REMAINING fraction (Brownian), so as the clock runs out the
distribution collapses onto the realized score — exactly the score-anchor effect. Emits
win-prob, spread-cover, and totals over/under. Pure math (erf-based normal CDF), no scipy.

Reads state by duck-typing (elapsed_minutes / home_score / away_score / pregame_params),
so it works with live_repricer.GameState without importing it.

HONEST: re-pricing MACHINERY only. Whether any live probability beats the book is a gate
question, not answered here. No edge is claimed; markets are efficient.
INVARIANTS: never edit src/ or kernel/; pure math; <=300 LOC.
"""
from __future__ import annotations

import math
from typing import Any, Dict

_NBA_FULL_MINUTES = 48.0
_DEF_MU = 113.0          # default expected full-game points per team
_DEF_MARGIN_SIGMA = 13.5  # full-game final-margin SD (points)
_DEF_TOTAL_SIGMA = 18.0   # full-game final-total SD (points)
_SPREAD_OFFSETS = (-6.5, -3.5, -1.5, 1.5, 3.5, 6.5)  # home line = projected +/- offset
_TOTAL_OFFSETS = (-10.5, -5.5, 0.5, 5.5, 10.5)


def _norm_cdf(z: float) -> float:
    """Standard-normal CDF via erf (no scipy)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


class NBARepricer:
    """In-game re-pricing for NBA using a Gaussian score-anchor remaining-points model."""

    def reprice(self, state: Any) -> Dict[str, Any]:
        pp = getattr(state, "pregame_params", {}) or {}
        mu_home = float(pp.get("mu_home", _DEF_MU))
        mu_away = float(pp.get("mu_away", _DEF_MU))
        margin_sigma = float(pp.get("margin_sigma", _DEF_MARGIN_SIGMA))
        total_sigma = float(pp.get("total_sigma", _DEF_TOTAL_SIGMA))

        elapsed = float(getattr(state, "elapsed_minutes", 0.0))
        rem_frac = max(0.0, (_NBA_FULL_MINUTES - elapsed) / _NBA_FULL_MINUTES)
        h0, a0 = int(state.home_score), int(state.away_score)

        if rem_frac <= 0.0:
            return self._final_state_surface(h0, a0, state)

        margin_mean = (h0 - a0) + (mu_home - mu_away) * rem_frac
        total_mean = (h0 + a0) + (mu_home + mu_away) * rem_frac
        margin_sd = max(1e-6, margin_sigma * math.sqrt(rem_frac))
        total_sd = max(1e-6, total_sigma * math.sqrt(rem_frac))

        win_home = _norm_cdf(margin_mean / margin_sd)
        out: Dict[str, Any] = {
            "win_home": win_home,
            "win_away": 1.0 - win_home,
            "proj_margin_home": margin_mean,
            "proj_total": total_mean,
        }
        # Spread-cover surface (home covers line L when final margin > L).
        for off in _SPREAD_OFFSETS:
            line = round(margin_mean + off, 1)
            p = 1.0 - _norm_cdf((line - margin_mean) / margin_sd)
            out[f"home_cover_{line:+g}"] = p
        # Totals over/under surface.
        for off in _TOTAL_OFFSETS:
            line = round(total_mean + off, 1)
            po = 1.0 - _norm_cdf((line - total_mean) / total_sd)
            out[f"over_{line:g}"] = po
            out[f"under_{line:g}"] = 1.0 - po
        out.update(self._metadata(state, rem_frac, margin_mean, total_mean,
                                  margin_sd, total_sd))
        return out

    @staticmethod
    def _final_state_surface(h0: int, a0: int, state: Any) -> Dict[str, Any]:
        """Deterministic surface at the final buzzer (ties -> overtime, marked 0.5)."""
        win_home = 1.0 if h0 > a0 else (0.5 if h0 == a0 else 0.0)
        out: Dict[str, Any] = {
            "win_home": win_home,
            "win_away": 1.0 - win_home,
            "proj_margin_home": float(h0 - a0),
            "proj_total": float(h0 + a0),
        }
        out.update(NBARepricer._metadata(state, 0.0, float(h0 - a0),
                                         float(h0 + a0), 0.0, 0.0))
        return out

    @staticmethod
    def _metadata(state: Any, rem_frac: float, margin_mean: float, total_mean: float,
                  margin_sd: float, total_sd: float) -> Dict[str, Any]:
        return {
            "_sport": "nba",
            "_elapsed_minutes": getattr(state, "elapsed_minutes", 0.0),
            "_remaining_fraction": rem_frac,
            "_current_score": (state.home_score, state.away_score),
            "_margin_sd": margin_sd,
            "_total_sd": total_sd,
            "_honest_note": (
                "Re-pricing machinery only (Gaussian score-anchor; variance collapses as "
                "the clock runs). Whether live probs beat closing lines is a gate question. "
                "No edge claimed."
            ),
        }
