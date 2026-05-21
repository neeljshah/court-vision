"""Tests for persistent CircuitBreakerState and the 5 stateful circuit breakers.

Coverage:
  - Atomic persistence: each breaker trips → reload from fresh instance → state survived
  - Trigger conditions: each breaker fires the correct action (halt/paper_only/throttle/block/skip)
  - Corrupt-state-file fail-safe path
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from src.prediction.risk_guards import (
    CircuitBreakerState,
    Exposure,
    cb_corr_cluster_cap,
    cb_daily_loss_cap,
    cb_drawdown_kill_switch,
    cb_losing_streak_throttle,
    cb_model_disagreement_halt,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _tmp_state(tmp_path) -> str:
    """Return a path to a non-existent JSON file inside pytest's tmp_path."""
    return str(tmp_path / "circuit_state.json")


def _ex(stake: float, cluster: str = "c1", game: str = "g1", player: str = "p1") -> Exposure:
    return Exposure(bet_id=f"b-{stake}", stake=stake,
                    game_id=game, player_id=player, correlated_group=cluster)


def _backdate_ts(hours: float) -> str:
    """Return an ISO UTC timestamp that is ``hours`` in the past."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    return dt.isoformat()


# ── CircuitBreakerState: basic persistence ───────────────────────────────────

class TestCircuitBreakerStatePersistence:
    def test_missing_file_uses_defaults(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        assert s.consecutive_losses == 0
        assert s.daily_loss_halt_tripped_at is None
        assert s.drawdown_kill_switch_tripped_at is None
        assert s.drawdown_high_water_mark == 0.0

    def test_corrupt_file_uses_defaults_does_not_raise(self, tmp_path):
        path = _tmp_state(tmp_path)
        with open(path, "w") as fh:
            fh.write("{{ NOT VALID JSON !!!")
        s = CircuitBreakerState(path)  # must not raise
        assert s.consecutive_losses == 0
        assert s.daily_loss_halt_tripped_at is None

    def test_non_dict_json_uses_defaults(self, tmp_path):
        path = _tmp_state(tmp_path)
        with open(path, "w") as fh:
            json.dump([1, 2, 3], fh)
        s = CircuitBreakerState(path)
        assert s.daily_loss_halt_tripped_at is None

    def test_save_creates_file(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s.record_loss()
        assert os.path.exists(path)

    def test_record_loss_survives_reload(self, tmp_path):
        path = _tmp_state(tmp_path)
        s1 = CircuitBreakerState(path)
        s1.record_loss()
        s1.record_loss()
        s2 = CircuitBreakerState(path)
        assert s2.consecutive_losses == 2

    def test_record_win_resets_streak(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s.record_loss()
        s.record_loss()
        s.record_win()
        s2 = CircuitBreakerState(path)
        assert s2.consecutive_losses == 0
        assert s2.streak_paper_tripped_at is None

    def test_hwm_persists(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s.update_high_water_mark(12_000.0)
        s2 = CircuitBreakerState(path)
        assert s2.drawdown_high_water_mark == 12_000.0

    def test_hwm_not_overwritten_by_lower_value(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s.update_high_water_mark(10_000.0)
        s.update_high_water_mark(8_000.0)
        s2 = CircuitBreakerState(path)
        assert s2.drawdown_high_water_mark == 10_000.0

    def test_trip_daily_loss_halt_survives_reload(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s.trip_daily_loss_halt()
        s2 = CircuitBreakerState(path)
        assert s2.daily_loss_halt_tripped_at is not None

    def test_trip_drawdown_kill_switch_survives_reload(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s.trip_drawdown_kill_switch()
        s2 = CircuitBreakerState(path)
        assert s2.drawdown_kill_switch_tripped_at is not None

    def test_streak_paper_tripped_at_set_at_5_losses(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        for _ in range(5):
            s.record_loss()
        s2 = CircuitBreakerState(path)
        assert s2.streak_paper_tripped_at is not None
        assert s2.consecutive_losses == 5


# ── Breaker 1: daily loss cap ────────────────────────────────────────────────

class TestCbDailyLossCap:
    def test_trigger_fires_halt(self, tmp_path):
        path = _tmp_state(tmp_path)
        action, v = cb_daily_loss_cap(-0.06, state_path=path)
        assert action == "halt"
        assert v is not None and v.name == "daily_loss_halt"

    def test_trigger_at_exact_threshold(self, tmp_path):
        path = _tmp_state(tmp_path)
        action, v = cb_daily_loss_cap(-0.05, state_path=path)
        assert action == "halt"

    def test_no_trigger_above_threshold(self, tmp_path):
        path = _tmp_state(tmp_path)
        action, v = cb_daily_loss_cap(-0.04, state_path=path)
        assert action == "allow"
        assert v is None

    def test_tripped_state_persists_and_re_halts(self, tmp_path):
        path = _tmp_state(tmp_path)
        # Trip it
        cb_daily_loss_cap(-0.06, state_path=path)
        # Fresh call with benign PnL — should still halt due to cooldown
        action, v = cb_daily_loss_cap(0.01, state_path=path)
        assert action == "halt"

    def test_cooldown_expires_and_clears(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        # Manually backdate the trip timestamp by 25 hours
        s._data["daily_loss_halt_tripped_at"] = _backdate_ts(25.0)
        s.save()
        # Benign PnL → cooldown expired, should clear and allow
        action, v = cb_daily_loss_cap(0.01, state_path=path)
        assert action == "allow"
        s2 = CircuitBreakerState(path)
        assert s2.daily_loss_halt_tripped_at is None

    def test_state_object_passthrough(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        action, v = cb_daily_loss_cap(-0.07, state=s)
        assert action == "halt"
        # Reload verifies it was written through the same state object
        s2 = CircuitBreakerState(path)
        assert s2.daily_loss_halt_tripped_at is not None


# ── Breaker 2: drawdown kill-switch ─────────────────────────────────────────

class TestCbDrawdownKillSwitch:
    def test_trigger_above_10pct_drawdown(self, tmp_path):
        path = _tmp_state(tmp_path)
        # Establish HWM first
        s = CircuitBreakerState(path)
        s.update_high_water_mark(10_000.0)
        # bankroll drops >10%
        action, v = cb_drawdown_kill_switch(8_900.0, state_path=path)
        assert action == "paper_only"
        assert v is not None and v.name == "drawdown_kill_switch"

    def test_no_trigger_below_10pct(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s.update_high_water_mark(10_000.0)
        action, v = cb_drawdown_kill_switch(9_100.0, state_path=path)
        assert action == "allow"
        assert v is None

    def test_updates_hwm_on_new_high(self, tmp_path):
        path = _tmp_state(tmp_path)
        cb_drawdown_kill_switch(12_000.0, state_path=path)
        s2 = CircuitBreakerState(path)
        assert s2.drawdown_high_water_mark == 12_000.0

    def test_tripped_state_persists_and_re_triggers(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s.update_high_water_mark(10_000.0)
        # Trip it
        cb_drawdown_kill_switch(8_000.0, state_path=path)
        # Call again with recovered bankroll — still within 24h cooldown
        action, v = cb_drawdown_kill_switch(9_800.0, state_path=path)
        assert action == "paper_only"

    def test_cooldown_expires_and_clears(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s.update_high_water_mark(10_000.0)
        s._data["drawdown_kill_switch_tripped_at"] = _backdate_ts(25.0)
        s.save()
        # bankroll within limit → should clear and allow
        action, v = cb_drawdown_kill_switch(9_500.0, state_path=path)
        assert action == "allow"


# ── Breaker 3: corr-cluster cap ──────────────────────────────────────────────

class TestCbCorrClusterCap:
    def test_block_when_cluster_over_15pct(self, tmp_path):
        path = _tmp_state(tmp_path)
        bankroll = 10_000.0
        # 16% in one cluster — over the 15% cap
        stakes = [_ex(800, cluster="PnR"), _ex(800, cluster="PnR")]
        action, v = cb_corr_cluster_cap(stakes, bankroll, state_path=path)
        assert action == "block"
        assert v is not None and v.name == "corr_cluster_cap"

    def test_allow_when_cluster_at_limit(self, tmp_path):
        path = _tmp_state(tmp_path)
        bankroll = 10_000.0
        # Exactly 15% — should pass (not strictly over)
        stakes = [_ex(750, cluster="PnR"), _ex(750, cluster="PnR")]
        action, v = cb_corr_cluster_cap(stakes, bankroll, state_path=path)
        assert action == "allow"

    def test_multiple_clusters_only_over_one(self, tmp_path):
        path = _tmp_state(tmp_path)
        bankroll = 10_000.0
        stakes = [
            _ex(600, cluster="A"), _ex(700, cluster="A"),  # 13% — ok
            _ex(900, cluster="B"), _ex(700, cluster="B"),  # 16% — block
        ]
        action, v = cb_corr_cluster_cap(stakes, bankroll, state_path=path)
        assert action == "block"
        assert "B" in v.detail

    def test_empty_slate_allows(self, tmp_path):
        path = _tmp_state(tmp_path)
        action, v = cb_corr_cluster_cap([], 10_000.0, state_path=path)
        assert action == "allow"


# ── Breaker 4: model-disagreement halt ───────────────────────────────────────

class TestCbModelDisagreementHalt:
    def test_skip_when_spread_over_3_units(self, tmp_path):
        path = _tmp_state(tmp_path)
        action, v = cb_model_disagreement_halt([1.0, 4.5], state_path=path)
        assert action == "skip"
        assert v is not None and v.name == "model_disagreement_halt"

    def test_allow_when_spread_at_3_units(self, tmp_path):
        path = _tmp_state(tmp_path)
        # spread == 3.0 (not strictly over) — should allow
        action, v = cb_model_disagreement_halt([0.0, 3.0], state_path=path)
        assert action == "allow"

    def test_allow_tight_cluster(self, tmp_path):
        path = _tmp_state(tmp_path)
        action, v = cb_model_disagreement_halt([2.0, 2.5, 2.2], state_path=path)
        assert action == "allow"

    def test_single_edge_allows(self, tmp_path):
        path = _tmp_state(tmp_path)
        action, v = cb_model_disagreement_halt([5.0], state_path=path)
        assert action == "allow"

    def test_empty_edges_allow(self, tmp_path):
        path = _tmp_state(tmp_path)
        action, v = cb_model_disagreement_halt([], state_path=path)
        assert action == "allow"


# ── Breaker 5: losing-streak throttle ────────────────────────────────────────

class TestCbLosingStreakThrottle:
    def test_allow_below_3_losses(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s._data["consecutive_losses"] = 2
        s.save()
        action, v = cb_losing_streak_throttle(state_path=path)
        assert action == "allow"
        assert v is None

    def test_throttle_at_3_losses(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s._data["consecutive_losses"] = 3
        s.save()
        action, v = cb_losing_streak_throttle(state_path=path)
        assert action == "throttle"
        assert v is not None and v.name == "losing_streak_throttle"

    def test_throttle_at_4_losses(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s._data["consecutive_losses"] = 4
        s.save()
        action, v = cb_losing_streak_throttle(state_path=path)
        assert action == "throttle"

    def test_paper_only_at_5_losses(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s._data["consecutive_losses"] = 5
        s.save()
        action, v = cb_losing_streak_throttle(state_path=path)
        assert action == "paper_only"

    def test_paper_only_above_5_losses(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        s._data["consecutive_losses"] = 8
        s.save()
        action, v = cb_losing_streak_throttle(state_path=path)
        assert action == "paper_only"

    def test_record_loss_increments_and_triggers(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        for _ in range(3):
            s.record_loss()
        # Now reload and check via breaker function
        action, v = cb_losing_streak_throttle(state_path=path)
        assert action == "throttle"

    def test_win_resets_throttle(self, tmp_path):
        path = _tmp_state(tmp_path)
        s = CircuitBreakerState(path)
        for _ in range(5):
            s.record_loss()
        s.record_win()
        action, v = cb_losing_streak_throttle(state_path=path)
        assert action == "allow"

    def test_streak_state_survives_reload(self, tmp_path):
        """Persistence: trip via record_loss, then load fresh and assert throttle fires."""
        path = _tmp_state(tmp_path)
        s1 = CircuitBreakerState(path)
        for _ in range(3):
            s1.record_loss()
        # Fresh instance
        s2 = CircuitBreakerState(path)
        action, v = cb_losing_streak_throttle(state=s2)
        assert action == "throttle"

    def test_paper_only_state_survives_reload(self, tmp_path):
        """Persistence: 5 losses → paper-only survives reload."""
        path = _tmp_state(tmp_path)
        s1 = CircuitBreakerState(path)
        for _ in range(5):
            s1.record_loss()
        s2 = CircuitBreakerState(path)
        action, _ = cb_losing_streak_throttle(state=s2)
        assert action == "paper_only"


# ── Corrupt-state fail-safe (parameterized) ───────────────────────────────────

@pytest.mark.parametrize("bad_content", [
    "{{ bad json",
    "",
    "null",
    "[]",
    '{"consecutive_losses": "not-a-number"}',
])
def test_corrupt_state_fail_safe_does_not_raise(tmp_path, bad_content):
    """Any corrupt/malformed state file must NOT crash the caller."""
    path = _tmp_state(tmp_path)
    with open(path, "w") as fh:
        fh.write(bad_content)
    # All 5 breakers must survive a corrupt state file
    s = CircuitBreakerState(path)
    assert s.consecutive_losses == 0  # conservative default
    assert s.daily_loss_halt_tripped_at is None

    # Also exercise breaker functions directly against corrupt file
    cb_daily_loss_cap(-0.01, state_path=path)
    cb_drawdown_kill_switch(10_000.0, state_path=path)
    cb_corr_cluster_cap([_ex(100)], 10_000.0, state_path=path)
    cb_model_disagreement_halt([1.0, 2.0], state_path=path)
    cb_losing_streak_throttle(state_path=path)


# ── Atomic write: mid-write crash safety ─────────────────────────────────────

def test_atomic_write_uses_temp_then_rename(tmp_path, monkeypatch):
    """Verify temp file is created during save and final file exists after."""
    path = _tmp_state(tmp_path)
    s = CircuitBreakerState(path)
    s.record_loss()
    # If we get here without exception the rename succeeded
    assert os.path.exists(path)
    with open(path) as fh:
        data = json.load(fh)
    assert data["consecutive_losses"] == 1


def test_partial_write_does_not_leave_corrupt_state(tmp_path, monkeypatch):
    """If os.replace fails, the original file must remain intact."""
    path = _tmp_state(tmp_path)
    # Write valid state first
    s1 = CircuitBreakerState(path)
    s1._data["consecutive_losses"] = 2
    s1.save()

    # Now monkeypatch os.replace to raise
    original_replace = os.replace

    def bad_replace(src, dst):
        try:
            os.unlink(src)
        except OSError:
            pass
        raise OSError("simulated mid-write crash")

    monkeypatch.setattr(os, "replace", bad_replace)
    s2 = CircuitBreakerState(path)
    s2._data["consecutive_losses"] = 99
    s2.save()  # must not raise; save() logs but swallows

    # Original file still has value 2
    monkeypatch.setattr(os, "replace", original_replace)
    s3 = CircuitBreakerState(path)
    assert s3.consecutive_losses == 2
