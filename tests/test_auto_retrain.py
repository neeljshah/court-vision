"""
tests/test_auto_retrain.py -- Tests for scripts/auto_retrain.py 14-day staleness gate.

Verifies:
  - models fresher than 14 days → no-op (training functions never called)
  - models older than 14 days  → train_all_meta + train_calibration both called
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make project root importable
PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))


# ── helpers to patch _stale_pkls ─────────────────────────────────────────────

def _make_fake_pkls(tmp_path: Path, age_seconds: float) -> list[Path]:
    """Create a fake .pkl file whose mtime is *age_seconds* old."""
    fake = tmp_path / "fake_model.pkl"
    fake.write_bytes(b"")
    mtime = time.time() - age_seconds
    os.utime(fake, (mtime, mtime))
    return [fake]


# ── tests ─────────────────────────────────────────────────────────────────────

class TestStalenessGate:
    """14-day gate: fresh → skip; stale → retrain."""

    def test_fresh_models_no_retrain(self, tmp_path: Path) -> None:
        """Models < 14 days old must NOT trigger training."""
        mock_meta = MagicMock(return_value={})
        mock_calib = MagicMock(return_value={})

        import importlib
        import scripts.auto_retrain as ar_mod
        importlib.reload(ar_mod)

        with (
            patch.object(ar_mod, "_stale_pkls", return_value=[]),
            patch.object(ar_mod, "_log_outcome") as mock_log,
            patch.dict("sys.modules", {
                "src.prediction.prop_model_stack": MagicMock(
                    train_all_meta=mock_meta,
                    train_calibration=mock_calib,
                ),
            }),
        ):
            result = ar_mod.run_retrain_if_stale()

        assert result["retrained"] is False
        assert result["stale"] == []
        mock_meta.assert_not_called()
        mock_calib.assert_not_called()
        mock_log.assert_called_once()
        log_line: str = mock_log.call_args[0][0]
        assert "skipped" in log_line

    def test_stale_models_trigger_retrain(self, tmp_path: Path) -> None:
        """Models > 14 days old must call train_all_meta AND train_calibration."""
        stale_pkls: list[Path] = _make_fake_pkls(tmp_path, age_seconds=86400 * 20)  # 20 days

        mock_meta = MagicMock(return_value={"pts": {"coef": 0.9, "r2": 0.8}})
        mock_calib = MagicMock(return_value={"pts": {"n": 100, "over_rate": 0.5, "fitted": True}})

        prop_module = MagicMock()
        prop_module.train_all_meta = mock_meta
        prop_module.train_calibration = mock_calib

        import importlib
        import scripts.auto_retrain as ar_mod
        importlib.reload(ar_mod)

        with (
            patch.object(ar_mod, "_stale_pkls", return_value=stale_pkls),
            patch.object(ar_mod, "_log_outcome") as mock_log,
            patch.dict("sys.modules", {"src.prediction.prop_model_stack": prop_module}),
        ):
            result = ar_mod.run_retrain_if_stale()

        assert result["retrained"] is True
        assert len(result["stale"]) == 1
        assert result["stale"][0].endswith(".pkl")
        mock_meta.assert_called_once_with()
        mock_calib.assert_called_once_with()
        mock_log.assert_called_once()
        log_line: str = mock_log.call_args[0][0]
        assert "retrained" in log_line

    def test_boundary_exactly_14_days_is_fresh(self, tmp_path: Path) -> None:
        """A model at exactly 14 days minus 1 second is still considered fresh."""
        # Patch _stale_pkls with empty list (boundary: just under 14 days)
        with (
            patch("scripts.auto_retrain._stale_pkls", return_value=[]),
            patch("scripts.auto_retrain._log_outcome"),
        ):
            from scripts import auto_retrain as ar_mod
            result = ar_mod.run_retrain_if_stale()

        assert result["retrained"] is False

    def test_multiple_stale_models_all_reported(self, tmp_path: Path) -> None:
        """All stale model names should appear in the result."""
        stale_files: list[Path] = []
        for name in ["model_a.pkl", "model_b.pkl", "model_c.pkl"]:
            p = tmp_path / name
            p.write_bytes(b"")
            mtime = time.time() - 86400 * 30  # 30 days old
            os.utime(p, (mtime, mtime))
            stale_files.append(p)

        mock_meta = MagicMock(return_value={})
        mock_calib = MagicMock(return_value={})
        prop_module = MagicMock()
        prop_module.train_all_meta = mock_meta
        prop_module.train_calibration = mock_calib

        import importlib
        import scripts.auto_retrain as ar_mod
        importlib.reload(ar_mod)

        with (
            patch.object(ar_mod, "_stale_pkls", return_value=stale_files),
            patch.object(ar_mod, "_log_outcome"),
            patch.dict("sys.modules", {"src.prediction.prop_model_stack": prop_module}),
        ):
            result = ar_mod.run_retrain_if_stale()

        assert len(result["stale"]) == 3
        assert result["retrained"] is True
        mock_meta.assert_called_once_with()
        mock_calib.assert_called_once_with()
