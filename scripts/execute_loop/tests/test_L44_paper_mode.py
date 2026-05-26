"""test_L44_paper_mode.py — Tests for L44_paper_mode single-source-of-truth module.

All env-var state is fully isolated per test via monkeypatch.  The module is
reloaded between tests so cached os.environ reads cannot leak.
"""
from __future__ import annotations

import importlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODULE_KEY = "scripts.execute_loop.L44_paper_mode"


def _reload_module():
    """Force a fresh import of L44_paper_mode, bypassing the module cache."""
    sys.modules.pop(_MODULE_KEY, None)
    import scripts.execute_loop.L44_paper_mode as mod
    return mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# All live-mode env vars; unset before each test so tests start clean.
_ALL_LIVE_VARS = [
    "SUBMISSION_MODE",
    "KALSHI_LIVE_ENABLED",
    "POLYMARKET_LIVE_ENABLED",
    "SPORTTRADE_LIVE_ENABLED",
    "PROPHET_LIVE_ENABLED",
    "WITHDRAWAL_LIVE_ENABLED",
    "DK_LIVE_SUBMISSION_ENABLED",
    "FD_LIVE_SUBMISSION_ENABLED",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Guarantee that all live-mode env vars are absent at the start of each test."""
    for var in _ALL_LIVE_VARS:
        monkeypatch.delenv(var, raising=False)
    yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIsPaperMode:
    def test_default_is_paper_mode(self):
        """No env vars set → is_paper_mode() returns True (safe default)."""
        mod = _reload_module()
        assert mod.is_paper_mode() is True

    def test_submission_mode_live_overrides(self, monkeypatch):
        """SUBMISSION_MODE=live → is_paper_mode() returns False."""
        monkeypatch.setenv("SUBMISSION_MODE", "live")
        mod = _reload_module()
        assert mod.is_paper_mode() is False

    def test_per_layer_kalshi_live(self, monkeypatch):
        """KALSHI_LIVE_ENABLED=1 → is_live_for_layer('kalshi') True; is_paper_mode() False."""
        monkeypatch.setenv("KALSHI_LIVE_ENABLED", "1")
        mod = _reload_module()
        assert mod.is_live_for_layer("kalshi") is True
        assert mod.is_paper_mode() is False

    def test_per_layer_polymarket_live(self, monkeypatch):
        """POLYMARKET_LIVE_ENABLED=1 → is_live_for_layer('polymarket') True; is_paper_mode() False."""
        monkeypatch.setenv("POLYMARKET_LIVE_ENABLED", "1")
        mod = _reload_module()
        assert mod.is_live_for_layer("polymarket") is True
        assert mod.is_paper_mode() is False

    def test_multiple_layer_flags_trigger_live(self, monkeypatch):
        """Any single per-layer flag set to '1' is sufficient to enter live mode."""
        for var in _ALL_LIVE_VARS[1:]:  # skip SUBMISSION_MODE
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("DK_LIVE_SUBMISSION_ENABLED", "1")
        mod = _reload_module()
        assert mod.is_paper_mode() is False

    def test_case_insensitive_env_values(self, monkeypatch):
        """SUBMISSION_MODE=LIVE and SUBMISSION_MODE=Live are both recognised as live."""
        for value in ("LIVE", "Live", "liVe"):
            monkeypatch.setenv("SUBMISSION_MODE", value)
            mod = _reload_module()
            assert mod.is_paper_mode() is False, (
                f"Expected live mode for SUBMISSION_MODE={value!r}"
            )


class TestIsLiveForLayer:
    def test_unknown_layer_name_returns_false(self):
        """is_live_for_layer() with an unknown name returns False (paper = safe default)."""
        mod = _reload_module()
        assert mod.is_live_for_layer("nonexistent") is False
        assert mod.is_live_for_layer("") is False
        assert mod.is_live_for_layer("L09_kalshi_client") is False

    def test_known_layers_default_to_paper(self):
        """All known layer names return False when no flags are set."""
        mod = _reload_module()
        known_layers = [
            "kalshi",
            "polymarket",
            "sporttrade",
            "prophet",
            "withdrawal",
            "dk_submission",
            "fd_submission",
        ]
        for layer in known_layers:
            assert mod.is_live_for_layer(layer) is False, (
                f"Expected paper for layer={layer!r}"
            )

    def test_per_layer_sporttrade_live(self, monkeypatch):
        """SPORTTRADE_LIVE_ENABLED=1 → is_live_for_layer('sporttrade') True."""
        monkeypatch.setenv("SPORTTRADE_LIVE_ENABLED", "1")
        mod = _reload_module()
        assert mod.is_live_for_layer("sporttrade") is True

    def test_per_layer_prophet_live(self, monkeypatch):
        """PROPHET_LIVE_ENABLED=1 → is_live_for_layer('prophet') True."""
        monkeypatch.setenv("PROPHET_LIVE_ENABLED", "1")
        mod = _reload_module()
        assert mod.is_live_for_layer("prophet") is True

    def test_per_layer_withdrawal_live(self, monkeypatch):
        """WITHDRAWAL_LIVE_ENABLED=1 → is_live_for_layer('withdrawal') True."""
        monkeypatch.setenv("WITHDRAWAL_LIVE_ENABLED", "1")
        mod = _reload_module()
        assert mod.is_live_for_layer("withdrawal") is True

    def test_per_layer_dk_submission_live(self, monkeypatch):
        """DK_LIVE_SUBMISSION_ENABLED=1 → is_live_for_layer('dk_submission') True."""
        monkeypatch.setenv("DK_LIVE_SUBMISSION_ENABLED", "1")
        mod = _reload_module()
        assert mod.is_live_for_layer("dk_submission") is True

    def test_per_layer_fd_submission_live(self, monkeypatch):
        """FD_LIVE_SUBMISSION_ENABLED=1 → is_live_for_layer('fd_submission') True."""
        monkeypatch.setenv("FD_LIVE_SUBMISSION_ENABLED", "1")
        mod = _reload_module()
        assert mod.is_live_for_layer("fd_submission") is True

    def test_global_live_does_not_affect_is_live_for_layer(self, monkeypatch):
        """SUBMISSION_MODE=live does NOT make is_live_for_layer() return True.

        Per-layer flags must be set explicitly — the global flag is intentionally
        not inherited so that each exchange is opt-in independently.
        """
        monkeypatch.setenv("SUBMISSION_MODE", "live")
        mod = _reload_module()
        for layer in ("kalshi", "polymarket", "sporttrade", "prophet",
                      "withdrawal", "dk_submission", "fd_submission"):
            assert mod.is_live_for_layer(layer) is False, (
                f"is_live_for_layer('{layer}') should be False when only SUBMISSION_MODE=live"
            )


class TestAssertPaperMode:
    def test_assert_paper_mode_passes_by_default(self):
        """assert_paper_mode() does not raise when no live flags are set."""
        mod = _reload_module()
        mod.assert_paper_mode("unit_test_operation")  # must not raise

    def test_assert_paper_mode_raises_in_live(self, monkeypatch):
        """assert_paper_mode() raises PaperModeRequired when a live flag is active."""
        monkeypatch.setenv("SUBMISSION_MODE", "live")
        mod = _reload_module()
        with pytest.raises(mod.PaperModeRequired) as exc_info:
            mod.assert_paper_mode("nightly_retrain_dry_run")
        assert "nightly_retrain_dry_run" in str(exc_info.value)

    def test_assert_paper_mode_default_operation_name(self, monkeypatch):
        """assert_paper_mode() uses 'operation' as the default operation label."""
        monkeypatch.setenv("KALSHI_LIVE_ENABLED", "1")
        mod = _reload_module()
        with pytest.raises(mod.PaperModeRequired) as exc_info:
            mod.assert_paper_mode()
        assert "operation" in str(exc_info.value)

    def test_paper_mode_required_is_runtime_error(self, monkeypatch):
        """PaperModeRequired is a subclass of RuntimeError."""
        monkeypatch.setenv("WITHDRAWAL_LIVE_ENABLED", "1")
        mod = _reload_module()
        with pytest.raises(RuntimeError):
            mod.assert_paper_mode("guard_test")

    def test_paper_mode_required_stores_operation(self, monkeypatch):
        """PaperModeRequired.operation attribute matches what was passed in."""
        monkeypatch.setenv("POLYMARKET_LIVE_ENABLED", "1")
        mod = _reload_module()
        exc = mod.PaperModeRequired("my_op")
        assert exc.operation == "my_op"
