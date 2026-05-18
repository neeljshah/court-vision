"""Risk Framework guards: position limits and circuit breakers.

Matches the README's "Risk Framework" section. Each guard is a pure function
returning `(ok, reason)`; `evaluate_all` runs every guard against a proposed
slate and returns the list of violations. Designed to be called by the bet
selector before sizing; no live-capital code is wired to these limits yet
(paper-trading gate first).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple


# ── Position limits (fraction of bankroll) ───────────────────────────────────
MAX_PORTFOLIO_PCT     = 0.20   # total exposure across an entire slate
MAX_GAME_PCT          = 0.05   # exposure on a single game
MAX_PLAYER_PCT        = 0.08   # exposure on a single player across props
MAX_CORRELATED_PCT    = 0.15   # exposure within one correlated cluster
MAX_BET_PCT           = 0.04   # single-bet cap (already in betting_portfolio)

# ── Circuit breakers (drawdown + streak) ─────────────────────────────────────
DAILY_LOSS_HALT_PCT   = 0.05   # halt all new bets if today's PnL <= -5%
KILL_SWITCH_PCT       = 0.10   # liquidate / freeze if drawdown >= 10%

# Streak throttle: after N consecutive losses, scale Kelly to fraction
STREAK_LOSSES_THROTTLE = 3     # 3 losses -> 0.50x stake
STREAK_LOSSES_PAPER    = 5     # 5 losses -> paper-only mode
STREAK_THROTTLE_FACTOR = 0.50

# Model agreement: if ensemble spread on edge_pct exceeds this many units,
# skip the bet (disagreement halt). Edge units, not percentage points.
MAX_ENSEMBLE_SPREAD   = 3.0

# Data quality degradation: reduce Kelly when fallback vendor is in use
FALLBACK_KELLY_FACTOR = 0.50


@dataclass(frozen=True)
class Exposure:
    """Per-bet exposure record for a proposed slate."""
    bet_id:           str
    stake:            float
    game_id:          str
    player_id:        str
    correlated_group: str   # e.g. "PnR_handler_AST_cluster"


@dataclass(frozen=True)
class Violation:
    name:     str
    actual:   float
    limit:    float
    detail:   str


def _exposure_sum(records: Iterable[Exposure], key: str) -> Mapping[str, float]:
    out: dict[str, float] = {}
    for r in records:
        k = getattr(r, key)
        out[k] = out.get(k, 0.0) + r.stake
    return out


def check_portfolio_limit(
    proposed_stakes: Sequence[Exposure], bankroll: float
) -> Tuple[bool, Optional[Violation]]:
    total = sum(r.stake for r in proposed_stakes)
    limit = MAX_PORTFOLIO_PCT * bankroll
    if total > limit:
        return False, Violation("portfolio", total, limit,
                                f"total slate exposure ${total:.2f} > ${limit:.2f}")
    return True, None


def check_game_limit(
    proposed_stakes: Sequence[Exposure], bankroll: float
) -> Tuple[bool, Optional[Violation]]:
    limit = MAX_GAME_PCT * bankroll
    by_game = _exposure_sum(proposed_stakes, "game_id")
    for g, amt in by_game.items():
        if amt > limit:
            return False, Violation("game", amt, limit,
                                    f"game {g} exposure ${amt:.2f} > ${limit:.2f}")
    return True, None


def check_player_limit(
    proposed_stakes: Sequence[Exposure], bankroll: float
) -> Tuple[bool, Optional[Violation]]:
    limit = MAX_PLAYER_PCT * bankroll
    by_player = _exposure_sum(proposed_stakes, "player_id")
    for p, amt in by_player.items():
        if amt > limit:
            return False, Violation("player", amt, limit,
                                    f"player {p} exposure ${amt:.2f} > ${limit:.2f}")
    return True, None


def check_correlated_limit(
    proposed_stakes: Sequence[Exposure], bankroll: float
) -> Tuple[bool, Optional[Violation]]:
    limit = MAX_CORRELATED_PCT * bankroll
    by_cluster = _exposure_sum(proposed_stakes, "correlated_group")
    for c, amt in by_cluster.items():
        if amt > limit:
            return False, Violation("correlated", amt, limit,
                                    f"cluster {c} exposure ${amt:.2f} > ${limit:.2f}")
    return True, None


def check_daily_loss_halt(daily_pnl_pct: float) -> Tuple[bool, Optional[Violation]]:
    if daily_pnl_pct <= -DAILY_LOSS_HALT_PCT:
        return False, Violation("daily_loss_halt", daily_pnl_pct,
                                -DAILY_LOSS_HALT_PCT,
                                f"daily PnL {daily_pnl_pct:+.1%} <= halt threshold")
    return True, None


def check_kill_switch(drawdown_pct: float) -> Tuple[bool, Optional[Violation]]:
    if drawdown_pct >= KILL_SWITCH_PCT:
        return False, Violation("kill_switch", drawdown_pct, KILL_SWITCH_PCT,
                                f"drawdown {drawdown_pct:.1%} >= {KILL_SWITCH_PCT:.0%}")
    return True, None


def streak_kelly_factor(consecutive_losses: int) -> float:
    """Return Kelly multiplier: 1.0 normal, 0.5 throttle, 0.0 paper-only."""
    if consecutive_losses >= STREAK_LOSSES_PAPER:
        return 0.0
    if consecutive_losses >= STREAK_LOSSES_THROTTLE:
        return STREAK_THROTTLE_FACTOR
    return 1.0


def check_model_disagreement(
    ensemble_edges: Sequence[float],
) -> Tuple[bool, Optional[Violation]]:
    if not ensemble_edges or len(ensemble_edges) < 2:
        return True, None
    spread = max(ensemble_edges) - min(ensemble_edges)
    if spread > MAX_ENSEMBLE_SPREAD:
        return False, Violation("model_disagreement", spread, MAX_ENSEMBLE_SPREAD,
                                f"ensemble edge spread {spread:.2f}u "
                                f"> {MAX_ENSEMBLE_SPREAD}u")
    return True, None


def evaluate_all(
    proposed_stakes: Sequence[Exposure],
    bankroll: float,
    daily_pnl_pct: float = 0.0,
    drawdown_pct: float = 0.0,
    consecutive_losses: int = 0,
    ensemble_edges: Sequence[float] = (),
) -> List[Violation]:
    """Run every guard. Empty list means the slate passes."""
    violations: List[Violation] = []
    for fn in (
        lambda: check_portfolio_limit(proposed_stakes, bankroll),
        lambda: check_game_limit(proposed_stakes, bankroll),
        lambda: check_player_limit(proposed_stakes, bankroll),
        lambda: check_correlated_limit(proposed_stakes, bankroll),
        lambda: check_daily_loss_halt(daily_pnl_pct),
        lambda: check_kill_switch(drawdown_pct),
        lambda: check_model_disagreement(ensemble_edges),
    ):
        ok, v = fn()
        if not ok and v is not None:
            violations.append(v)
    return violations


__all__ = [
    "Exposure", "Violation",
    "MAX_PORTFOLIO_PCT", "MAX_GAME_PCT", "MAX_PLAYER_PCT",
    "MAX_CORRELATED_PCT", "MAX_BET_PCT",
    "DAILY_LOSS_HALT_PCT", "KILL_SWITCH_PCT",
    "STREAK_LOSSES_THROTTLE", "STREAK_LOSSES_PAPER", "STREAK_THROTTLE_FACTOR",
    "MAX_ENSEMBLE_SPREAD", "FALLBACK_KELLY_FACTOR",
    "check_portfolio_limit", "check_game_limit", "check_player_limit",
    "check_correlated_limit", "check_daily_loss_halt", "check_kill_switch",
    "check_model_disagreement", "streak_kelly_factor",
    "evaluate_all",
]
