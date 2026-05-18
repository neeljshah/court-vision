"""Tests for the README's Risk Framework guards."""

from __future__ import annotations

import pytest

from src.prediction.risk_guards import (
    DAILY_LOSS_HALT_PCT,
    KILL_SWITCH_PCT,
    MAX_CORRELATED_PCT,
    MAX_GAME_PCT,
    MAX_PLAYER_PCT,
    MAX_PORTFOLIO_PCT,
    STREAK_LOSSES_PAPER,
    STREAK_LOSSES_THROTTLE,
    Exposure,
    check_correlated_limit,
    check_daily_loss_halt,
    check_game_limit,
    check_kill_switch,
    check_model_disagreement,
    check_player_limit,
    check_portfolio_limit,
    evaluate_all,
    streak_kelly_factor,
)


def _ex(stake: float, *, game="g1", player="p1", cluster="c1", bet_id=None) -> Exposure:
    return Exposure(bet_id=bet_id or f"b-{stake}", stake=stake,
                    game_id=game, player_id=player, correlated_group=cluster)


def test_portfolio_limit_exact_thresholds():
    bankroll = 10_000.0
    stakes = [_ex(stake=200) for _ in range(10)]  # 2000 total = 20% (limit)
    ok, _ = check_portfolio_limit(stakes, bankroll)
    assert ok
    # Push 1 cent over
    stakes2 = stakes + [_ex(stake=0.02)]
    ok2, v = check_portfolio_limit(stakes2, bankroll)
    assert not ok2
    assert v is not None and v.name == "portfolio"


def test_game_limit_blocks_concentration():
    # 8% on a single game with default bankroll exceeds 5% limit
    stakes = [_ex(stake=800, game="LAL_BOS_2026-05-17")]
    ok, v = check_game_limit(stakes, bankroll=10_000.0)
    assert not ok
    assert v.name == "game"


def test_player_limit_blocks_concentration():
    # Multiple bets on one player exceeding 8% bankroll
    stakes = [_ex(stake=500, player="LeBron"),
              _ex(stake=400, player="LeBron"),
              _ex(stake=200, player="LeBron")]
    ok, v = check_player_limit(stakes, bankroll=10_000.0)
    assert not ok
    assert v.name == "player" and v.actual == 1100.0


def test_correlated_cluster_limit():
    stakes = [_ex(stake=800, cluster="PnR_AST"),
              _ex(stake=800, cluster="PnR_AST")]
    ok, v = check_correlated_limit(stakes, bankroll=10_000.0)
    assert not ok
    assert v.name == "correlated"


def test_daily_loss_halt():
    ok_at_threshold, _ = check_daily_loss_halt(-DAILY_LOSS_HALT_PCT)
    assert not ok_at_threshold
    ok_above, _ = check_daily_loss_halt(-DAILY_LOSS_HALT_PCT + 0.001)
    assert ok_above


def test_kill_switch():
    ok_below, _ = check_kill_switch(0.099)
    assert ok_below
    ok_at, _ = check_kill_switch(KILL_SWITCH_PCT)
    assert not ok_at


def test_streak_kelly_factor():
    assert streak_kelly_factor(0) == 1.0
    assert streak_kelly_factor(2) == 1.0
    assert streak_kelly_factor(STREAK_LOSSES_THROTTLE) == 0.5
    assert streak_kelly_factor(4) == 0.5
    assert streak_kelly_factor(STREAK_LOSSES_PAPER) == 0.0


def test_model_disagreement_halt():
    # 3.5u spread (>3.0u limit) triggers
    ok, v = check_model_disagreement([1.0, 4.5, 2.5])
    assert not ok and v.name == "model_disagreement"
    # Tight cluster passes
    ok2, _ = check_model_disagreement([2.0, 2.5, 2.2])
    assert ok2


def test_evaluate_all_collects_multiple_violations():
    bankroll = 10_000.0
    # 8% on one game + 8% drawdown
    stakes = [_ex(stake=800, game="g1")]
    violations = evaluate_all(
        proposed_stakes=stakes,
        bankroll=bankroll,
        daily_pnl_pct=-0.08,    # below -5% halt
        drawdown_pct=0.11,       # above 10% kill-switch
        consecutive_losses=2,
        ensemble_edges=(1.0, 1.5),
    )
    names = {v.name for v in violations}
    assert "game" in names
    assert "daily_loss_halt" in names
    assert "kill_switch" in names


def test_evaluate_all_passes_clean_slate():
    stakes = [_ex(stake=100, game="g1"),
              _ex(stake=150, game="g2", player="p2", cluster="c2")]
    violations = evaluate_all(
        proposed_stakes=stakes,
        bankroll=10_000.0,
        daily_pnl_pct=0.02,
        drawdown_pct=0.01,
        consecutive_losses=0,
        ensemble_edges=(),
    )
    assert violations == []


def test_constants_match_readme_spec():
    # Pin the README's documented thresholds. If you change them, update
    # README.md §Risk Framework in the same commit.
    assert MAX_PORTFOLIO_PCT == 0.20
    assert MAX_GAME_PCT == 0.05
    assert MAX_PLAYER_PCT == 0.08
    assert MAX_CORRELATED_PCT == 0.15
    assert DAILY_LOSS_HALT_PCT == 0.05
    assert KILL_SWITCH_PCT == 0.10
    assert STREAK_LOSSES_THROTTLE == 3
    assert STREAK_LOSSES_PAPER == 5
