"""domains.tennis.repricer — in-game / live re-pricing for tennis.

Tennis state is naturally SET-level, so this conditions on the current set score and
computes the analytic "race-to-N-sets" conditional match-win probability rather than
re-simulating (which avoids the MAE-vs-RMSE median-shift artifact flagged for in-game
work — a probability is graded on Brier, not MAE).

  need_1 = sets_to_win - sets_won_1 ;  need_2 = sets_to_win - sets_won_2
  P(player1 wins match | state) = sum_{k=0}^{need_2-1} C(need_1-1+k, k) * p^need_1 * (1-p)^k

where p = probability player 1 wins a single remaining set (pregame_params['p_set']).
Optionally nudged by the in-progress set via extra['games_1']/['games_2'] (a small,
bounded lean — the dominant conditioning is the completed-set score).

Reads state by duck-typing (pregame_params / extra), so it works with
live_repricer.GameState without importing it.

HONEST: re-pricing MACHINERY only. Whether any live probability beats the book is a gate
question, not answered here. No edge is claimed; markets are efficient.
INVARIANTS: never edit src/ or kernel/; pure math; <=300 LOC.
"""
from __future__ import annotations

import math
from typing import Any, Dict

_DEF_BEST_OF = 3
_GAMES_LEAN = 0.04   # max per-set-prob nudge from a lopsided in-progress set


def _race_win_prob(p: float, need_1: int, need_2: int) -> float:
    """P(player1 reaches need_1 set-wins before player2 reaches need_2), Bernoulli(p) sets."""
    if need_1 <= 0:
        return 1.0
    if need_2 <= 0:
        return 0.0
    p = min(max(p, 1e-6), 1 - 1e-6)
    total = 0.0
    for k in range(need_2):  # player2 wins k sets (k < need_2) before player1's need_1-th
        total += math.comb(need_1 - 1 + k, k) * (p ** need_1) * ((1 - p) ** k)
    return float(min(max(total, 0.0), 1.0))


class TennisRepricer:
    """Set-level in-game re-pricing for tennis via the race-to-N-sets conditional."""

    def reprice(self, state: Any) -> Dict[str, Any]:
        pp = getattr(state, "pregame_params", {}) or {}
        extra = getattr(state, "extra", {}) or {}
        best_of = int(pp.get("best_of", _DEF_BEST_OF))
        sets_to_win = best_of // 2 + 1
        p_set = float(pp.get("p_set", 0.5))

        s1 = int(extra.get("sets_1", 0))
        s2 = int(extra.get("sets_2", 0))
        need_1 = sets_to_win - s1
        need_2 = sets_to_win - s2

        # Match already decided.
        if need_1 <= 0 or need_2 <= 0:
            win1 = 1.0 if need_1 <= 0 else 0.0
            return self._surface(win1, p_set, best_of, s1, s2, state, decided=True)

        # Small bounded lean from an in-progress set's game score (does not flip the model).
        g1 = int(extra.get("games_1", 0))
        g2 = int(extra.get("games_2", 0))
        p_eff = p_set
        if (g1 + g2) > 0:
            lean = _GAMES_LEAN * (g1 - g2) / max(6, g1 + g2)
            p_eff = min(max(p_set + lean, 1e-6), 1 - 1e-6)

        win1 = _race_win_prob(p_eff, need_1, need_2)
        return self._surface(win1, p_eff, best_of, s1, s2, state, decided=False)

    @staticmethod
    def _surface(win1: float, p_eff: float, best_of: int, s1: int, s2: int,
                 state: Any, decided: bool) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "match_win_p1": win1,
            "match_win_p2": 1.0 - win1,
            "_sport": "tennis",
            "_best_of": best_of,
            "_current_sets": (s1, s2),
            "_p_set_effective": p_eff,
            "_decided": decided,
            "_honest_note": (
                "Set-level race-to-N conditional (Brier-graded, not MAE). Re-pricing "
                "machinery only; whether live probs beat the book is a gate question. "
                "No edge claimed."
            ),
        }
        return out
