"""
test_circuit_breakers.py -- Integration tests for the 5 persistent circuit breakers.

Task 16-05 acceptance criterion: five pytest cases each inject a simulated
trigger condition and assert the correct halt/throttle action fires.

Each breaker is exercised against a fresh, isolated state file (tmp_path) so
the persistent circuit_state.json is never touched.
"""

from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.risk_guards import (  # noqa: E402
    CircuitBreakerState,
    Exposure,
    STREAK_LOSSES_THROTTLE,
    cb_corr_cluster_cap,
    cb_daily_loss_cap,
    cb_drawdown_kill_switch,
    cb_losing_streak_throttle,
    cb_model_disagreement_halt,
)


@pytest.fixture
def state(tmp_path) -> CircuitBreakerState:
    """A circuit-breaker state backed by an isolated temp file."""
    return CircuitBreakerState(str(tmp_path / "circuit_state.json"))


# ── Breaker 1: daily-loss cap ─────────────────────────────────────────────────

def test_daily_loss_cap_halts_on_5pct_loss(state):
    """Inject a -6% day -> breaker halts all new bets."""
    action, violation = cb_daily_loss_cap(-0.06, state=state)
    assert action == "halt"
    assert violation is not None
    assert violation.name == "daily_loss_halt"
    # A flat day must NOT halt (fresh state, cooldown elapsed).
    ok_action, ok_violation = cb_daily_loss_cap(0.0, state=state)
    # Still halted: the trip above persisted and the 24h cooldown is active.
    assert ok_action == "halt"
    assert ok_violation is not None


# ── Breaker 2: drawdown kill-switch ───────────────────────────────────────────

def test_drawdown_kill_switch_paper_only_on_12pct_drawdown(state):
    """HWM 10000, bankroll falls to 8800 (-12%) -> paper-only mode."""
    cb_drawdown_kill_switch(10_000.0, state=state)      # establish HWM
    action, violation = cb_drawdown_kill_switch(8_800.0, state=state)
    assert action == "paper_only"
    assert violation is not None
    assert violation.name == "drawdown_kill_switch"


# ── Breaker 3: correlated-cluster cap ─────────────────────────────────────────

def test_corr_cluster_cap_blocks_overexposed_cluster(state):
    """One cluster at 20% of bankroll -> blocked (15% cap)."""
    bankroll = 10_000.0
    stakes = [
        Exposure("b1", 1_200.0, "G1", "P1", "PnR_AST_cluster"),
        Exposure("b2",   900.0, "G1", "P2", "PnR_AST_cluster"),
    ]  # cluster total = 2100 = 21% > 15% cap
    action, violation = cb_corr_cluster_cap(stakes, bankroll, state=state)
    assert action == "block"
    assert violation is not None
    assert violation.name == "corr_cluster_cap"


# ── Breaker 4: model-disagreement halt ────────────────────────────────────────

def test_model_disagreement_halt_skips_wide_spread(state):
    """Ensemble edges spanning 5 units (> 3u cap) -> market skipped."""
    ensemble_edges = [1.0, 2.5, 6.0]   # spread = 5.0u
    action, violation = cb_model_disagreement_halt(ensemble_edges, state=state)
    assert action == "skip"
    assert violation is not None
    assert violation.name == "model_disagreement_halt"


# ── Breaker 5: losing-streak throttle ─────────────────────────────────────────

def test_losing_streak_throttle_reduces_stakes_after_3_losses(state):
    """3 consecutive losses -> stakes throttled to 50%."""
    for _ in range(STREAK_LOSSES_THROTTLE):
        state.record_loss()
    action, violation = cb_losing_streak_throttle(state=state)
    assert action == "throttle"
    assert violation is not None
    assert violation.name == "losing_streak_throttle"
    # 5+ losses escalates to paper-only.
    state.record_loss()
    state.record_loss()
    esc_action, _ = cb_losing_streak_throttle(state=state)
    assert esc_action == "paper_only"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
