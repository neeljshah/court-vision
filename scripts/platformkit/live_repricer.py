"""scripts.platformkit.live_repricer — In-game / live re-pricing interface.

Given a partial game STATE, re-price the remaining markets by conditioning on what
has already happened + simulating the rest of the match using each sport's engine.

DESIGN: the soccer implementation is concrete and correct. For other sports a stub
returns a graceful not-wired dict rather than crashing — honest about coverage.

HONEST framing: in-game freshness is a real lane (regime shift, injury, live score
information). This module provides re-pricing MACHINERY only. Whether any live
probability beats the book is a gate question, not answered here. No edge is claimed.
See platform memory: 60/60 REJECT on signal catalogs; honest REJECTs are successes.

INVARIANTS: never edit src/ or kernel/; pure numpy/math; <=300 LOC; no heavy imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, Tuple, runtime_checkable

import numpy as np

from domains.soccer.scoreline_engine import markets_from_matrix, scoreline_matrix

# ---------------------------------------------------------------------------
# GameState — sport-agnostic container
# ---------------------------------------------------------------------------

@dataclass
class GameState:
    """Snapshot of live match state at the moment of re-pricing.

    Parameters
    ----------
    sport : str
        One of 'soccer', 'nba', 'tennis', 'mlb'. Determines which repricer is used.
    elapsed_minutes : float
        Minutes elapsed so far (0–90 for soccer, 0–48 for NBA, etc.).
    home_score : int
        Goals/points scored by the home team so far.
    away_score : int
        Goals/points scored by the away team so far.
    pregame_params : dict
        Sport-specific pregame model parameters. For soccer: keys
        'lam_home' and 'lam_away' (pregame expected goals per full match);
        'rho' (optional Dixon-Coles correlation, default 0.0).
    extra : dict
        Optional additional fields (e.g. fouls, red-cards, possession %).
        Not used by the core re-pricer; stored for downstream consumers.
    """
    sport: str
    elapsed_minutes: float
    home_score: int
    away_score: int
    pregame_params: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Repricer protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Repricer(Protocol):
    """Live re-pricing contract: given a GameState, return remaining-market probs."""

    def reprice(self, state: GameState) -> Dict[str, Any]:
        """Compute the full live market surface conditioned on *state*.

        Returns
        -------
        dict
            At minimum: keys from the sport's standard market surface, plus
            metadata keys '_sport', '_elapsed_minutes', '_current_score',
            '_remaining_minutes', '_honest_note'.
            Stubs return {'status': 'not_wired', ...} without raising.
        """
        ...


# ---------------------------------------------------------------------------
# SoccerRepricer — concrete, correct in-game re-pricing for soccer
# ---------------------------------------------------------------------------

_SOCCER_FULL_MINUTES = 90.0


class SoccerRepricer:
    """In-game re-pricing for soccer using the Dixon-Coles scoreline engine.

    Algorithm
    ---------
    1. Compute remaining_minutes = max(0, 90 - elapsed_minutes).
    2. Scale pregame Poisson lambdas proportionally to remaining time:
           lam_rem_home = lam_pregame_home * (remaining / 90)
           lam_rem_away = lam_pregame_away * (remaining / 90)
       This treats goals as a homogeneous Poisson process over the 90 minutes
       (standard in-play Poisson model; can be replaced with intensity curves later).
    3. Build the scoreline matrix for REMAINING goals via scoreline_matrix().
    4. Compute all standard markets from the remaining distribution, then
       SHIFT the indices by current_score to get final-score probabilities:
           P(final_home=h, final_away=a) = P(remaining_home=h - home_score,
                                              remaining_away=a - away_score)
       for h >= home_score, a >= away_score; 0 otherwise.
    5. Emit the standard market surface (live 1X2, O/U vs original pregame
       totals line, BTTS-still-possible, correct-score live, etc.).

    HONEST: re-pricing machinery; whether live probs beat the book is gated separately.
    """

    def reprice(self, state: GameState) -> Dict[str, Any]:  # noqa: D102
        lam_home = float(state.pregame_params.get("lam_home", 1.5))
        lam_away = float(state.pregame_params.get("lam_away", 1.1))
        rho = float(state.pregame_params.get("rho", 0.0))

        remaining = max(0.0, _SOCCER_FULL_MINUTES - state.elapsed_minutes)
        frac = remaining / _SOCCER_FULL_MINUTES  # 0.0 at FT, 1.0 at KO

        h0, a0 = int(state.home_score), int(state.away_score)

        # Degenerate: full time — result is already determined
        if frac <= 0.0 or remaining < 1e-6:
            return self._final_state_surface(h0, a0, state, remaining=0.0)

        # Scale lambdas to remaining time
        lam_rem_h = max(1e-6, lam_home * frac)
        lam_rem_a = max(1e-6, lam_away * frac)

        # Remaining-goals scoreline matrix (rows=home_extra, cols=away_extra)
        P_rem = scoreline_matrix(lam_rem_h, lam_rem_a, rho=rho)
        n = P_rem.shape[0]

        # Shift to final-score matrix: P_final[h_final, a_final]
        max_final = n + max(h0, a0)
        P_final = np.zeros((max_final, max_final), dtype=float)
        for dh in range(n):
            for da in range(n):
                hf = h0 + dh
                af = a0 + da
                if hf < max_final and af < max_final:
                    P_final[hf, af] += P_rem[dh, da]

        # Normalise (should already sum to 1 but guard truncation)
        total = P_final.sum()
        if total > 0:
            P_final /= total

        live_markets = markets_from_matrix(P_final, top_n=6)

        # Annotate with live context
        live_markets.update(
            self._metadata(state, remaining, lam_rem_h, lam_rem_a)
        )
        return live_markets

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _final_state_surface(
        h0: int, a0: int, state: GameState, remaining: float
    ) -> Dict[str, Any]:
        """Emit a deterministic surface when the match is over."""
        if h0 > a0:
            win_home, draw, win_away = 1.0, 0.0, 0.0
        elif a0 > h0:
            win_home, draw, win_away = 0.0, 0.0, 1.0
        else:
            win_home, draw, win_away = 0.0, 1.0, 0.0

        total = h0 + a0
        out: Dict[str, Any] = {
            "1X2_home": win_home,
            "1X2_draw": draw,
            "1X2_away": win_away,
            "btts_yes": 1.0 if (h0 >= 1 and a0 >= 1) else 0.0,
            "btts_no":  0.0 if (h0 >= 1 and a0 >= 1) else 1.0,
        }
        for line in (0.5, 1.5, 2.5, 3.5, 4.5):
            out[f"over_{line:g}"]  = 1.0 if total > line else 0.0
            out[f"under_{line:g}"] = 0.0 if total > line else 1.0
        out[f"cs_{h0}_{a0}"] = 1.0
        out.update(SoccerRepricer._metadata(state, remaining, 0.0, 0.0))
        return out

    @staticmethod
    def _metadata(
        state: GameState,
        remaining: float,
        lam_rem_h: float,
        lam_rem_a: float,
    ) -> Dict[str, Any]:
        return {
            "_sport": "soccer",
            "_elapsed_minutes": state.elapsed_minutes,
            "_remaining_minutes": remaining,
            "_current_score": (state.home_score, state.away_score),
            "_lam_remaining_home": lam_rem_h,
            "_lam_remaining_away": lam_rem_a,
            "_honest_note": (
                "Re-pricing machinery only. In-game freshness is a real lane; "
                "whether live probs beat closing lines is a gate question. "
                "No edge claimed."
            ),
        }


# ---------------------------------------------------------------------------
# Generic stub for unwired sports
# ---------------------------------------------------------------------------

class _SportStub:
    """Graceful stub for sports not yet wired this wave."""

    def __init__(self, sport: str) -> None:
        self._sport = sport

    def reprice(self, state: GameState) -> Dict[str, Any]:  # noqa: D102
        return {
            "status": "not_wired",
            "sport": self._sport,
            "note": (
                f"{self._sport} rest-of-game re-pricing is not wired this wave. "
                "Soccer is the concrete implementation. NBA/tennis/MLB stubs "
                "return this dict gracefully without crashing."
            ),
            "_honest_note": "No edge claimed; re-pricing machinery only.",
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_repricer(sport: str) -> Repricer:
    """Return the appropriate Repricer for *sport*.

    Currently wired
    ---------------
    soccer  : SoccerRepricer (full bivariate-Poisson in-game engine)
    mlb     : MLBRepricer (over-dispersed NegBinom run engine, W101)
    nba     : NBARepricer (Gaussian score-anchor remaining-points model)
    tennis  : TennisRepricer (set-level race-to-N-sets conditional)

    Stubs (return graceful not-wired dict)
    ---------------------------------------
    any other sport string.
    """
    if sport == "soccer":
        return SoccerRepricer()
    if sport == "mlb":
        from domains.mlb.repricer import MLBRepricer  # noqa: PLC0415
        return MLBRepricer()
    if sport == "nba":
        from domains.basketball_nba.repricer import NBARepricer  # noqa: PLC0415
        return NBARepricer()
    if sport == "tennis":
        from domains.tennis.repricer import TennisRepricer  # noqa: PLC0415
        return TennisRepricer()
    return _SportStub(sport)
