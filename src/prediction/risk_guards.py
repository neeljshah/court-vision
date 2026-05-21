"""Risk Framework guards: position limits and circuit breakers.

Matches the README's "Risk Framework" section. Each guard is a pure function
returning `(ok, reason)`; `evaluate_all` runs every guard against a proposed
slate and returns the list of violations. Designed to be called by the bet
selector before sizing; no live-capital code is wired to these limits yet
(paper-trading gate first).

Persistent state (CircuitBreakerState) is stored at data/output/circuit_state.json
and written atomically (temp-file + rename) so a mid-write crash never corrupts it.
Missing or corrupt state files default to the most conservative posture and log a
warning — callers are never raised an exception.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

# ── Default state-file location ──────────────────────────────────────────────
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_STATE_PATH = os.path.join(_PROJECT_DIR, "data", "output", "circuit_state.json")


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


# ── Persistent circuit breaker state ─────────────────────────────────────────

def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_since(iso_ts: Optional[str]) -> float:
    """Return elapsed hours since an ISO-8601 UTC timestamp, or ∞ if None."""
    if not iso_ts:
        return float("inf")
    try:
        dt = datetime.fromisoformat(iso_ts)
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 3600.0
    except (ValueError, TypeError):
        return float("inf")


# Conservative defaults: pretend nothing is tripped on a fresh/corrupt state.
_DEFAULT_STATE: Dict[str, Any] = {
    # Breaker 1: daily loss halt
    "daily_loss_halt_tripped_at": None,      # ISO UTC or None
    # Breaker 2: drawdown kill-switch
    "drawdown_kill_switch_tripped_at": None, # ISO UTC or None
    "drawdown_high_water_mark": 0.0,         # abs dollar HWM
    # Breaker 3: corr-cluster cap — purely stateless (checked per-call)
    # Breaker 4: model-disagreement halt — purely stateless (checked per-call)
    # Breaker 5: losing-streak throttle
    "consecutive_losses": 0,
    "streak_paper_tripped_at": None,         # ISO UTC or None (set when >=5 losses)
}

_COOLDOWN_HOURS = 24.0  # both daily-loss halt and drawdown kill-switch


class CircuitBreakerState:
    """Load, mutate, and atomically persist circuit-breaker state.

    Usage::

        cbs = CircuitBreakerState()          # loads from default path
        cbs = CircuitBreakerState(path)      # custom path (for tests)
        cbs.daily_loss_halt_tripped_at       # read a field
        cbs.trip_daily_loss_halt()           # mutate + save
        cbs.save()                           # explicit save (usually not needed)
    """

    def __init__(self, path: str = DEFAULT_STATE_PATH) -> None:
        self._path = path
        self._data: Dict[str, Any] = {}
        self._load()

    # ── internal I/O ────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load state from disk; fall back to conservative defaults on any error."""
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                if not isinstance(raw, dict):
                    raise ValueError("state file is not a JSON object")
                # Merge with defaults so new keys survive old files
                self._data = {**_DEFAULT_STATE, **raw}
                return
        except Exception as exc:  # corrupt JSON, permission error, etc.
            log.warning("circuit_state: failed to load %s (%s) — using defaults", self._path, exc)
        self._data = dict(_DEFAULT_STATE)

    def save(self) -> None:
        """Atomically write state to disk (temp-file + rename)."""
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            dir_ = os.path.dirname(self._path)
            fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, indent=2)
                os.replace(tmp, self._path)  # atomic on POSIX; best-effort on Windows
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception as exc:
            log.error("circuit_state: failed to save %s (%s)", self._path, exc)

    # ── property accessors ──────────────────────────────────────────────────

    @property
    def daily_loss_halt_tripped_at(self) -> Optional[str]:
        return self._data.get("daily_loss_halt_tripped_at")

    @property
    def drawdown_kill_switch_tripped_at(self) -> Optional[str]:
        return self._data.get("drawdown_kill_switch_tripped_at")

    @property
    def drawdown_high_water_mark(self) -> float:
        return float(self._data.get("drawdown_high_water_mark", 0.0))

    @property
    def consecutive_losses(self) -> int:
        try:
            return int(self._data.get("consecutive_losses", 0))
        except (ValueError, TypeError):
            return 0

    @property
    def streak_paper_tripped_at(self) -> Optional[str]:
        return self._data.get("streak_paper_tripped_at")

    # ── mutation helpers ────────────────────────────────────────────────────

    def trip_daily_loss_halt(self) -> None:
        self._data["daily_loss_halt_tripped_at"] = _now_utc_iso()
        self.save()

    def clear_daily_loss_halt(self) -> None:
        self._data["daily_loss_halt_tripped_at"] = None
        self.save()

    def trip_drawdown_kill_switch(self) -> None:
        self._data["drawdown_kill_switch_tripped_at"] = _now_utc_iso()
        self.save()

    def clear_drawdown_kill_switch(self) -> None:
        self._data["drawdown_kill_switch_tripped_at"] = None
        self.save()

    def update_high_water_mark(self, bankroll: float) -> None:
        if bankroll > self.drawdown_high_water_mark:
            self._data["drawdown_high_water_mark"] = bankroll
            self.save()

    def record_loss(self) -> None:
        self._data["consecutive_losses"] = self.consecutive_losses + 1
        if self._data["consecutive_losses"] >= STREAK_LOSSES_PAPER:
            if not self._data.get("streak_paper_tripped_at"):
                self._data["streak_paper_tripped_at"] = _now_utc_iso()
        self.save()

    def record_win(self) -> None:
        self._data["consecutive_losses"] = 0
        self._data["streak_paper_tripped_at"] = None
        self.save()

    def reset_streak(self) -> None:
        """Alias for record_win — clears the streak entirely."""
        self.record_win()


# ── Stateful circuit-breaker functions ───────────────────────────────────────
# Each returns (action: str, violation: Optional[Violation]).
# action is one of: "allow" | "halt" | "paper_only" | "throttle" | "block" | "skip"


def cb_daily_loss_cap(
    daily_pnl_pct: float,
    *,
    state: Optional[CircuitBreakerState] = None,
    state_path: str = DEFAULT_STATE_PATH,
) -> Tuple[str, Optional[Violation]]:
    """Breaker 1: halt all new bets if daily P&L ≤ −5% of bankroll (24h halt).

    Returns ("halt", Violation) while tripped; ("allow", None) when clear.
    Reads and writes ``circuit_state.json``.
    """
    s = state if state is not None else CircuitBreakerState(state_path)

    # Check if currently tripped and within cooldown window
    if s.daily_loss_halt_tripped_at is not None:
        if _hours_since(s.daily_loss_halt_tripped_at) < _COOLDOWN_HOURS:
            return "halt", Violation(
                "daily_loss_halt",
                daily_pnl_pct,
                -DAILY_LOSS_HALT_PCT,
                f"daily-loss halt active (tripped {s.daily_loss_halt_tripped_at}); "
                f"24h cooldown not yet elapsed",
            )
        else:
            s.clear_daily_loss_halt()

    # Check trigger condition
    if daily_pnl_pct <= -DAILY_LOSS_HALT_PCT:
        s.trip_daily_loss_halt()
        return "halt", Violation(
            "daily_loss_halt",
            daily_pnl_pct,
            -DAILY_LOSS_HALT_PCT,
            f"daily PnL {daily_pnl_pct:+.1%} ≤ halt threshold; 24h halt engaged",
        )
    return "allow", None


def cb_drawdown_kill_switch(
    bankroll: float,
    *,
    state: Optional[CircuitBreakerState] = None,
    state_path: str = DEFAULT_STATE_PATH,
) -> Tuple[str, Optional[Violation]]:
    """Breaker 2: paper-only mode if drawdown > 10% of high-water mark (24h cooldown).

    Call this on every session start with the current bankroll so the HWM is kept
    up-to-date.  Returns ("paper_only", Violation) while tripped.
    """
    s = state if state is not None else CircuitBreakerState(state_path)

    # Update HWM before checking drawdown
    s.update_high_water_mark(bankroll)
    hwm = s.drawdown_high_water_mark

    # Check if currently tripped
    if s.drawdown_kill_switch_tripped_at is not None:
        if _hours_since(s.drawdown_kill_switch_tripped_at) < _COOLDOWN_HOURS:
            drawdown_pct = (hwm - bankroll) / hwm if hwm > 0 else 0.0
            return "paper_only", Violation(
                "drawdown_kill_switch",
                drawdown_pct,
                KILL_SWITCH_PCT,
                f"drawdown kill-switch active (tripped {s.drawdown_kill_switch_tripped_at}); "
                f"24h cooldown not yet elapsed",
            )
        else:
            s.clear_drawdown_kill_switch()

    # Check trigger condition
    if hwm > 0:
        drawdown_pct = (hwm - bankroll) / hwm
        if drawdown_pct > KILL_SWITCH_PCT:
            s.trip_drawdown_kill_switch()
            return "paper_only", Violation(
                "drawdown_kill_switch",
                drawdown_pct,
                KILL_SWITCH_PCT,
                f"drawdown {drawdown_pct:.1%} > {KILL_SWITCH_PCT:.0%} of HWM; paper-only mode engaged",
            )
    return "allow", None


def cb_corr_cluster_cap(
    proposed_stakes: Sequence[Exposure],
    bankroll: float,
    *,
    state: Optional[CircuitBreakerState] = None,  # unused — stateless check
    state_path: str = DEFAULT_STATE_PATH,          # unused — stateless check
) -> Tuple[str, Optional[Violation]]:
    """Breaker 3: block bets in a cluster exceeding 15% of bankroll exposure.

    This breaker is stateless (no cooldown) — it evaluates the proposed slate
    and returns ("block", Violation) for the first over-limit cluster found.
    """
    limit = MAX_CORRELATED_PCT * bankroll
    by_cluster = _exposure_sum(proposed_stakes, "correlated_group")
    for cluster, amt in by_cluster.items():
        if amt > limit:
            return "block", Violation(
                "corr_cluster_cap",
                amt,
                limit,
                f"cluster '{cluster}' exposure ${amt:.2f} > ${limit:.2f} (15% cap)",
            )
    return "allow", None


def cb_model_disagreement_halt(
    ensemble_edges: Sequence[float],
    *,
    state: Optional[CircuitBreakerState] = None,  # unused — stateless check
    state_path: str = DEFAULT_STATE_PATH,          # unused — stateless check
) -> Tuple[str, Optional[Violation]]:
    """Breaker 4: skip a market if ensemble spread > 3 units.

    Stateless — no cooldown needed; the spread is recalculated per market.
    Returns ("skip", Violation) when the spread is too wide.
    """
    if not ensemble_edges or len(ensemble_edges) < 2:
        return "allow", None
    spread = max(ensemble_edges) - min(ensemble_edges)
    if spread > MAX_ENSEMBLE_SPREAD:
        return "skip", Violation(
            "model_disagreement_halt",
            spread,
            MAX_ENSEMBLE_SPREAD,
            f"ensemble spread {spread:.2f}u > {MAX_ENSEMBLE_SPREAD}u; market skipped",
        )
    return "allow", None


def cb_losing_streak_throttle(
    *,
    state: Optional[CircuitBreakerState] = None,
    state_path: str = DEFAULT_STATE_PATH,
) -> Tuple[str, Optional[Violation]]:
    """Breaker 5: 3 consecutive losses → 50% stakes; 5 → paper-only.

    Does NOT record a new loss — call ``state.record_loss()`` / ``state.record_win()``
    separately when a bet result is known.  This function only reads the current streak
    and returns the appropriate action.

    Returns:
        ("allow",      None)        — fewer than 3 losses
        ("throttle",   Violation)   — 3–4 losses (50% Kelly factor)
        ("paper_only", Violation)   — 5+ losses
    """
    s = state if state is not None else CircuitBreakerState(state_path)
    n = s.consecutive_losses

    if n >= STREAK_LOSSES_PAPER:
        return "paper_only", Violation(
            "losing_streak_throttle",
            float(n),
            float(STREAK_LOSSES_PAPER),
            f"{n} consecutive losses ≥ {STREAK_LOSSES_PAPER}; paper-only mode",
        )
    if n >= STREAK_LOSSES_THROTTLE:
        return "throttle", Violation(
            "losing_streak_throttle",
            float(n),
            float(STREAK_LOSSES_THROTTLE),
            f"{n} consecutive losses ≥ {STREAK_LOSSES_THROTTLE}; stakes reduced to 50%",
        )
    return "allow", None


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
    # Persistent circuit breakers
    "DEFAULT_STATE_PATH",
    "CircuitBreakerState",
    "cb_daily_loss_cap",
    "cb_drawdown_kill_switch",
    "cb_corr_cluster_cap",
    "cb_model_disagreement_halt",
    "cb_losing_streak_throttle",
]
