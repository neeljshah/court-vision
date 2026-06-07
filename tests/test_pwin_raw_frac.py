"""Tests for the CV_PWIN_RAW_FRAC gated fix in edge_calibration.calibrate_p_win.

Bug (sweep-2 HIGH): the frac interpolation subtracts a RAW-edge `threshold` from the
isotonic-SHRUNK `cal_edge`, pinning p_win at baseline_hit (frac==0) for REB/AST whenever
the shrunk edge sits below threshold -> no edge-proportional Kelly sizing on the live slate.

Default OFF = byte-identical legacy. ON = frac driven off the raw edge (units match threshold).
"""
import os
import pytest
from src.prediction import edge_calibration as ec


@pytest.fixture(autouse=True)
def _force_fallback_and_clean_env(monkeypatch):
    # Force the linear-slope fallback so cal_edge is deterministic regardless of
    # whether an isotonic .joblib exists on disk.
    monkeypatch.setattr(ec, "load_isotonic_model", lambda stat: None)
    monkeypatch.delenv("CV_PWIN_RAW_FRAC", raising=False)
    ec.clear_model_cache()
    yield
    ec.clear_model_cache()


def test_legacy_off_pins_pwin_at_baseline_for_shrunk_edge(monkeypatch):
    """OFF (default): a raw edge well above threshold but shrunk below it pins p at baseline."""
    monkeypatch.delenv("CV_PWIN_RAW_FRAC", raising=False)
    # reb fallback slope 0.235 -> cal_edge = 4.0*0.235 = 0.94 < threshold 2.0
    p = ec.calibrate_p_win("reb", raw_edge=4.0, threshold=2.0, baseline_hit=0.55)
    assert p == pytest.approx(0.55, abs=1e-9), "legacy OFF must pin at baseline_hit"


def test_fix_on_scales_pwin_with_raw_edge(monkeypatch):
    """ON: the same case scales p above baseline (edge-proportional Kelly restored)."""
    monkeypatch.setenv("CV_PWIN_RAW_FRAC", "1")
    p = ec.calibrate_p_win("reb", raw_edge=4.0, threshold=2.0, baseline_hit=0.55)
    # frac = (4-2)/4 = 0.5 ; p_hi = min(0.85, 0.63) = 0.63 ; p = 0.55 + 0.5*0.08 = 0.59
    assert p == pytest.approx(0.59, abs=1e-9)
    assert p > 0.55


def test_off_is_byte_identical_to_hand_legacy(monkeypatch):
    """OFF reproduces the exact legacy formula on a non-pinned case."""
    monkeypatch.delenv("CV_PWIN_RAW_FRAC", raising=False)
    stat, raw, thr, base = "ast", 6.0, 1.0, 0.55
    cal = ec.calibrate_edge(stat, abs(raw))               # 6.0*0.366 = 2.196
    frac = min(1.0, max(0.0, (cal - thr) / max(thr * 2.0, 0.1)))
    p_hi = min(0.85, base + 0.08)
    expected = float(min(0.90, max(0.50, base + frac * (p_hi - base))))
    got = ec.calibrate_p_win(stat, raw, thr, base)
    assert got == pytest.approx(expected, abs=1e-12)


def test_on_and_off_agree_when_raw_and_cal_both_clear_threshold(monkeypatch):
    """When the raw edge is small enough that both forms saturate to frac=1, ON==OFF."""
    # huge raw edge -> both (raw-thr) and (cal-thr) exceed 2*thr -> frac clamps to 1.0
    off = ec.calibrate_p_win("pts", raw_edge=100.0, threshold=1.0, baseline_hit=0.55)
    monkeypatch.setenv("CV_PWIN_RAW_FRAC", "1")
    on = ec.calibrate_p_win("pts", raw_edge=100.0, threshold=1.0, baseline_hit=0.55)
    assert off == pytest.approx(on, abs=1e-12)
    assert on == pytest.approx(0.63, abs=1e-9)  # baseline+0.08 capped
