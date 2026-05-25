"""
Tests for L18 Bankroll Manager.

Uses tmp_path fixture so the real ledger is never touched.
Monkeypatches CONFIG["ledger_path"] before each test.
"""
from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_module():
    """Re-import the module so module-level globals are fresh."""
    mod_name = "scripts.execute_loop.L18_bankroll_manager"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    # Also remove parent packages if needed
    import importlib
    return importlib.import_module(mod_name)


@pytest.fixture()
def bm(tmp_path, monkeypatch):
    """Return L18 module with ledger_path redirected to tmp_path."""
    mod_name = "scripts.execute_loop.L18_bankroll_manager"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    # Ensure the nba-ai-system root is on sys.path
    root = Path(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    import importlib
    mod = importlib.import_module(mod_name)
    monkeypatch.setitem(mod.CONFIG, "ledger_path", str(tmp_path / "bankroll_state.json"))
    # Reset to defaults each test
    if (tmp_path / "bankroll_state.json").exists():
        (tmp_path / "bankroll_state.json").unlink()
    return mod


# ---------------------------------------------------------------------------
# Test 1: kelly_fraction basic positive edge
# ---------------------------------------------------------------------------

def test_kelly_fraction_basic(bm):
    """kelly_fraction(0.6, -110) ≈ 0.0400 (quarter of full Kelly ~0.1600).

    b = 100/110 ≈ 0.9091
    f* = (b*p - q) / b = (0.9091*0.6 - 0.4) / 0.9091 ≈ 0.1600
    quarter-Kelly = 0.1600 * 0.25 = 0.0400
    """
    frac = bm.kelly_fraction(0.6, -110)
    assert abs(frac - 0.0400) < 0.001, f"Expected ~0.0400, got {frac:.6f}"


# ---------------------------------------------------------------------------
# Test 2: kelly_fraction at breakeven returns 0
# ---------------------------------------------------------------------------

def test_kelly_fraction_breakeven(bm):
    """prob=0.524 at -110 is within breakeven_margin → 0."""
    # Implied prob for -110 is 110/210 ≈ 0.5238
    # 0.524 < 0.5238 + 0.005, so should return 0
    frac = bm.kelly_fraction(0.524, -110)
    assert frac == 0.0, f"Expected 0.0, got {frac}"


# ---------------------------------------------------------------------------
# Test 3: kelly_fraction negative edge returns 0
# ---------------------------------------------------------------------------

def test_kelly_fraction_negative_edge(bm):
    """prob=0.4 at -110: well below implied prob → 0."""
    frac = bm.kelly_fraction(0.4, -110)
    assert frac == 0.0, f"Expected 0.0, got {frac}"


# ---------------------------------------------------------------------------
# Test 4: kelly_fraction positive-odds positive edge
# ---------------------------------------------------------------------------

def test_kelly_fraction_plus_odds(bm):
    """kelly_fraction(0.7, +150) should be positive."""
    frac = bm.kelly_fraction(0.7, 150)
    assert frac > 0.0, f"Expected positive fraction, got {frac}"


# ---------------------------------------------------------------------------
# Test 5: update_bankroll persists and reloads correctly
# ---------------------------------------------------------------------------

def test_update_and_reload(bm):
    """update + reload → state matches."""
    state = bm.get_bankroll_state()
    initial_br = state.current_bankroll

    bm.update_bankroll(500.0, notes="test win")
    reloaded = bm.get_bankroll_state()

    assert abs(reloaded.current_bankroll - (initial_br + 500.0)) < 0.01
    assert abs(reloaded.daily_pnl - 500.0) < 0.01
    assert abs(reloaded.weekly_pnl - 500.0) < 0.01


# ---------------------------------------------------------------------------
# Test 6: check_risk_limits rejects stake > 2% of bankroll
# ---------------------------------------------------------------------------

def test_check_risk_limits_single_bet_too_large(bm):
    """Stake above max_single_bet_pct (2%) should be rejected."""
    state = bm.get_bankroll_state()
    oversized = state.current_bankroll * 0.025  # 2.5% > 2% limit
    ok, msg = bm.check_risk_limits(oversized)
    assert not ok
    assert "max_single_bet" in msg


# ---------------------------------------------------------------------------
# Test 7: kill switch blocks check_risk_limits, allows update_bankroll
# ---------------------------------------------------------------------------

def test_kill_switch_blocks_and_allows_update(bm):
    """Kill switch: check_risk_limits returns False; update_bankroll still writes."""
    bm.trip_kill_switch("manual test")

    ok, msg = bm.check_risk_limits(100.0)
    assert not ok
    assert "kill_switch" in msg

    # update_bankroll should still work
    state = bm.update_bankroll(-50.0, notes="recovery tracking")
    assert state.daily_pnl == pytest.approx(-50.0, abs=0.01)
    assert state.kill_switch_active is True


# ---------------------------------------------------------------------------
# Test 8: reset_daily zeros daily_pnl and advances date
# ---------------------------------------------------------------------------

def test_reset_daily(bm):
    """reset_daily → daily_pnl=0, daily_start_iso advances."""
    bm.update_bankroll(200.0)
    state_before = bm.get_bankroll_state()
    assert state_before.daily_pnl > 0

    bm.reset_daily()
    state_after = bm.get_bankroll_state()

    assert state_after.daily_pnl == pytest.approx(0.0)
    # daily_start_iso should have advanced (not equal to previous)
    assert state_after.daily_start_iso >= state_before.daily_start_iso


# ---------------------------------------------------------------------------
# Test 9: Non-PSD correlation matrix falls back to identity, logs warning
# ---------------------------------------------------------------------------

def test_non_psd_corr_fallback(bm, caplog):
    """Non-PSD corr_matrix → identity fallback with warning."""
    bets = [
        bm.BetCandidate("m1", 0.6, -110, "game1"),
        bm.BetCandidate("m2", 0.6, -110, "game1"),
    ]
    # Construct a non-PSD 2x2 matrix: off-diagonal > 1 violates PSD
    bad_corr = np.array([[1.0, 2.0], [2.0, 1.0]])  # eigenvalues: 3, -1

    with caplog.at_level(logging.WARNING, logger="scripts.execute_loop.L18_bankroll_manager"):
        fracs = bm.kelly_with_correlation(bets, bad_corr)

    assert len(fracs) == 2
    assert all(f >= 0 for f in fracs)
    assert any("PSD" in r.message or "identity" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Test 10: clear_kill_switch rejects bad token, accepts correct token
# ---------------------------------------------------------------------------

def test_clear_kill_switch(bm):
    """clear_kill_switch: wrong token raises ValueError; correct token clears."""
    bm.trip_kill_switch("test reason")

    with pytest.raises(ValueError, match="Invalid user_token"):
        bm.clear_kill_switch("WRONG_TOKEN")

    # Kill switch should still be active
    state = bm.get_bankroll_state()
    assert state.kill_switch_active is True

    # Correct token clears it
    bm.clear_kill_switch("CONFIRM_RESUME")
    state = bm.get_bankroll_state()
    assert state.kill_switch_active is False
    assert state.kill_switch_reason == ""


# ---------------------------------------------------------------------------
# Test 11: Auto-trip kill switch when daily loss exceeds threshold
# ---------------------------------------------------------------------------

def test_auto_trip_kill_switch_daily(bm):
    """check_risk_limits auto-trips kill switch when daily loss limit would be breached.

    Strategy:
      - starting_bankroll = 100_000
      - daily_loss_limit = 10% * 100_000 = 10_000
      - Lose 9.5% (9_500) so current = 90_500, daily_pnl = -9_500
      - Propose 1_800 stake:
          * single-bet cap = 2% * 90_500 = 1_810  → 1_800 passes
          * daily check: -9_500 - 1_800 = -11_300 < -10_000 → REJECT + trip
    """
    state = bm.get_bankroll_state()
    sbr = state.starting_bankroll  # 100_000

    bm.update_bankroll(-sbr * 0.095)  # lose 9.5% → current = 90_500, daily_pnl = -9_500

    # 1_800 < 2% * 90_500 (=1_810) so single-bet check passes; daily check fails
    proposed = 1_800.0
    ok, msg = bm.check_risk_limits(proposed)

    assert not ok
    assert "daily_loss_limit" in msg

    # Kill switch should have been auto-tripped
    state = bm.get_bankroll_state()
    assert state.kill_switch_active is True
    assert "daily_loss_limit" in state.kill_switch_reason
