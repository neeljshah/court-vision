"""tests/test_pregame_calibration.py — pregame calibration serving layer."""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import pytest  # noqa: E402
from src.prediction import pregame_calibration as pc  # noqa: E402

_HAS_MODELS = (pc._DIR / "meta.json").exists() and bool(pc.enabled_stats())


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("CV_PREGAME_CAL", raising=False)
    assert pc.is_enabled() is False
    monkeypatch.setenv("CV_PREGAME_CAL", "1")
    assert pc.is_enabled() is True


def test_noop_when_flag_off(monkeypatch):
    monkeypatch.delenv("CV_PREGAME_CAL", raising=False)
    assert pc.apply("pts", 25.0, {"l10_min": 30}) == 25.0


def test_disabled_stat_passes_through():
    # ast is intentionally NOT enabled (calibration kills its edge)
    assert "ast" not in pc.enabled_stats()
    assert pc.blend_weight("ast") == 0.0
    assert pc.apply("ast", 7.0, {"l10_min": 30}, force=True) == 7.0


@pytest.mark.skipif(not _HAS_MODELS, reason="calibrators not trained")
def test_blend_weights_are_per_stat():
    # PTS full, REB/FG3M half, AST raw — the validated principled policy.
    assert pc.blend_weight("pts") == 1.0
    assert pc.blend_weight("reb") == 0.5
    assert pc.blend_weight("fg3m") == 0.5
    assert pc.blend_weight("ast") == 0.0


@pytest.mark.skipif(not _HAS_MODELS, reason="calibrators not trained")
def test_calibrator_actually_moves_prediction():
    # regression guard: the DMatrix-feature-name bug silently no-op'd calibration.
    cov = {"l10_min": 34, "rest_days": 2, "is_home": 1, "opp_pace": 101,
           "opp_def": 110, "month": 1, "days_into_season": 80}
    out = pc.apply("pts", 25.0, cov, force=True)
    assert out != 25.0  # full calibration must change a clearly-biased input


@pytest.mark.skipif(not _HAS_MODELS, reason="calibrators not trained")
def test_blend_and_guard_bounds():
    cov = {"l10_min": 34, "rest_days": 2, "is_home": 1, "opp_pace": 101,
           "opp_def": 110, "month": 1, "days_into_season": 80}
    base = 9.0
    out = pc.apply("reb", base, cov, force=True)  # a=0.5 blend
    # half blend nudges; net move stays inside the +-35% guard band
    assert 0.65 * base <= out <= 1.35 * base


def test_unknown_stat_passes_through():
    assert pc.apply("zzz", 5.0, force=True) == 5.0


@pytest.mark.skipif(not _HAS_MODELS, reason="calibrators not trained")
def test_pts_calibration_changes_and_is_bounded():
    base = 25.0
    out = pc.apply("pts", base, {"l10_min": 32, "rest_days": 2, "is_home": 1,
                                 "opp_pace": 101.0, "opp_def": 110.0,
                                 "month": 1, "days_into_season": 80}, force=True)
    # it should move the prediction but stay within the +-35% guard band
    assert 0.65 * base <= out <= 1.35 * base


@pytest.mark.skipif(not _HAS_MODELS, reason="calibrators not trained")
def test_pts_enabled_by_default_set():
    assert "pts" in pc.enabled_stats()


def test_missing_covariates_uses_defaults_no_raise():
    # no covariates dict at all -> must not raise; returns a number
    out = pc.apply("pts", 20.0, None, force=True)
    assert isinstance(out, (int, float))
