"""Tests for src/prediction/intel_selection.py — the gated intel-selection levers.

Coverage:
  * default-OFF is a strict no-op (multiplier 1.0 / score 0.0 / False) — the
    byte-identical gating contract, swept over many random inputs.
  * ON behavior is correct (multiplier > 1, score > 0) on the validated slices.
  * the playoff guard forces both back to the no-op even when fully gated ON.
  * gating thresholds are exact (edge 0.75, line 7.5, vac_ast 3, top-quartile,
    starter, under-only, PTS up-weight).
  * env-flag resolution (CV_INTEL_VAC_AST / CV_INTEL_BLOWOUT) matches the
    explicit ``enabled=`` argument.
"""
import importlib
import os

import pytest

import src.prediction.intel_selection as isel


# --------------------------------------------------------------------------- #
# default-OFF == strict no-op (byte-identical gating contract)
# --------------------------------------------------------------------------- #
def test_vac_ast_default_off_is_noop():
    # With the flag unset, every input -> 1.0, including fully-gated ones.
    os.environ.pop("CV_INTEL_VAC_AST", None)
    importlib.reload(isel)
    assert isel.vac_ast_size_multiplier("ast", 1.0, 5.5, 9.0, False) == 1.0
    assert isel.vac_ast_size_multiplier("ast", 0.8, 7.0, 4.0, False) == 1.0
    assert isel.vac_ast_size_multiplier("pts", 2.0, 5.5, 9.0, False) == 1.0


def test_blowout_default_off_is_noop():
    os.environ.pop("CV_INTEL_BLOWOUT", None)
    importlib.reload(isel)
    assert isel.blowout_under_flag("pts", "under", "starter", True, False) == 0.0
    assert isel.blowout_under_flag("pts", "under", "starter", True, False, as_score=False) is False
    assert isel.blowout_under_flag("pts", "under", 30.0, 0.95, False) == 0.0


def test_default_off_byte_identical_sweep():
    """Sweep many randomized inputs: OFF must always be the exact no-op."""
    import random

    os.environ.pop("CV_INTEL_VAC_AST", None)
    os.environ.pop("CV_INTEL_BLOWOUT", None)
    importlib.reload(isel)
    rng = random.Random(0)
    for _ in range(2000):
        stat = rng.choice(["ast", "pts", "reb", "fg3m"])
        edge = rng.uniform(-3, 3)
        line = rng.uniform(0.5, 35)
        vac = rng.uniform(0, 12)
        po = rng.random() < 0.5
        assert isel.vac_ast_size_multiplier(stat, edge, line, vac, po) == 1.0
        side = rng.choice(["over", "under"])
        role = rng.choice(["starter", "bench", 30.0, 10.0])
        risk = rng.random()
        assert isel.blowout_under_flag(stat, side, role, risk, po) == 0.0


# --------------------------------------------------------------------------- #
# vac_ast — ON behavior + thresholds
# --------------------------------------------------------------------------- #
def test_vac_ast_on_fires_on_gated_slice():
    # explicit enabled=True bypasses the env flag.
    assert isel.vac_ast_size_multiplier("ast", 1.0, 5.5, 4.0, False, enabled=True) == 1.25
    # very large vacancy -> top of the band.
    assert isel.vac_ast_size_multiplier("ast", 1.0, 5.5, 7.0, False, enabled=True) == 1.50


def test_vac_ast_multiplier_clamped():
    m = isel.vac_ast_size_multiplier("ast", 1.0, 5.5, 50.0, False, enabled=True)
    assert 1.0 <= m <= 1.5


def test_vac_ast_edge_threshold_exact():
    # edge below 0.75 -> no fire; at/above -> fire.
    assert isel.vac_ast_size_multiplier("ast", 0.74, 5.5, 4.0, False, enabled=True) == 1.0
    assert isel.vac_ast_size_multiplier("ast", 0.75, 5.5, 4.0, False, enabled=True) == 1.25
    # negative edge (UNDER) still inside the gate by |edge|.
    assert isel.vac_ast_size_multiplier("ast", -0.80, 5.5, 4.0, False, enabled=True) == 1.25


def test_vac_ast_line_cap_exact():
    assert isel.vac_ast_size_multiplier("ast", 1.0, 7.5, 4.0, False, enabled=True) == 1.25
    assert isel.vac_ast_size_multiplier("ast", 1.0, 7.6, 4.0, False, enabled=True) == 1.0


def test_vac_ast_min_threshold_exact():
    assert isel.vac_ast_size_multiplier("ast", 1.0, 5.5, 2.9, False, enabled=True) == 1.0
    assert isel.vac_ast_size_multiplier("ast", 1.0, 5.5, 3.0, False, enabled=True) == 1.25


def test_vac_ast_only_ast_stat():
    for s in ("pts", "reb", "fg3m", "blk"):
        assert isel.vac_ast_size_multiplier(s, 1.0, 5.5, 9.0, False, enabled=True) == 1.0


def test_vac_ast_playoff_guard():
    # fully gated ON but playoff -> forced no-op (AST breaks in playoffs).
    assert isel.vac_ast_size_multiplier("ast", 1.0, 5.5, 9.0, True, enabled=True) == 1.0


def test_vac_ast_nan_and_bad_inputs_noop():
    assert isel.vac_ast_size_multiplier("ast", float("nan"), 5.5, 9.0, False, enabled=True) == 1.0
    assert isel.vac_ast_size_multiplier("ast", 1.0, None, 9.0, False, enabled=True) == 1.0
    assert isel.vac_ast_size_multiplier("ast", 1.0, 5.5, None, False, enabled=True) == 1.0
    assert isel.vac_ast_size_multiplier(None, 1.0, 5.5, 9.0, False, enabled=True) == 1.0


# --------------------------------------------------------------------------- #
# blowout — ON behavior + thresholds
# --------------------------------------------------------------------------- #
def test_blowout_on_fires_on_starter_under_blowout():
    # PTS gets the larger up-weight.
    assert isel.blowout_under_flag("pts", "under", "starter", True, False, enabled=True) == 1.0
    # other stats get the smaller up-weight.
    assert isel.blowout_under_flag("reb", "under", "starter", True, False, enabled=True) == 0.5
    assert isel.blowout_under_flag("ast", "under", "starter", True, False, enabled=True) == 0.5


def test_blowout_bool_return_mode():
    assert isel.blowout_under_flag("pts", "under", "starter", True, False,
                                   enabled=True, as_score=False) is True
    assert isel.blowout_under_flag("pts", "over", "starter", True, False,
                                   enabled=True, as_score=False) is False


def test_blowout_under_only():
    assert isel.blowout_under_flag("pts", "over", "starter", True, False, enabled=True) == 0.0
    assert isel.blowout_under_flag("pts", "under", "starter", True, False, enabled=True) == 1.0


def test_blowout_starter_only():
    # bench role -> no fire.
    assert isel.blowout_under_flag("pts", "under", "bench", True, False, enabled=True) == 0.0
    # numeric role: as-of L10 minutes, 28 is the cut.
    assert isel.blowout_under_flag("pts", "under", 27.9, True, False, enabled=True) == 0.0
    assert isel.blowout_under_flag("pts", "under", 28.0, True, False, enabled=True) == 1.0


def test_blowout_top_quartile_percentile():
    # percentile rank in [0,1]; top quartile = >= 0.75.
    assert isel.blowout_under_flag("pts", "under", "starter", 0.74, False, enabled=True) == 0.0
    assert isel.blowout_under_flag("pts", "under", "starter", 0.75, False, enabled=True) == 1.0


def test_blowout_raw_magnitude_with_threshold():
    # raw |exp_margin| with a caller-supplied top-quartile cut.
    assert isel.blowout_under_flag("pts", "under", "starter", 8.0, False,
                                   enabled=True, threshold=9.69) == 0.0
    assert isel.blowout_under_flag("pts", "under", "starter", 10.0, False,
                                   enabled=True, threshold=9.69) == 1.0


def test_blowout_playoff_guard():
    # fully gated ON but playoff -> forced no-op (minutes mechanism inverts).
    assert isel.blowout_under_flag("pts", "under", "starter", True, True, enabled=True) == 0.0


def test_blowout_bad_risk_noop():
    # raw magnitude with NO threshold and outside [0,1] -> cannot classify -> no-op.
    assert isel.blowout_under_flag("pts", "under", "starter", 9.7, False, enabled=True) == 0.0
    assert isel.blowout_under_flag("pts", "under", "starter", None, False, enabled=True) == 0.0


# --------------------------------------------------------------------------- #
# env-flag resolution
# --------------------------------------------------------------------------- #
def test_env_flag_vac_ast_on(monkeypatch):
    monkeypatch.setenv("CV_INTEL_VAC_AST", "1")
    importlib.reload(isel)
    try:
        assert isel.vac_ast_enabled() is True
        # enabled=None resolves from env -> fires.
        assert isel.vac_ast_size_multiplier("ast", 1.0, 5.5, 4.0, False) == 1.25
    finally:
        monkeypatch.delenv("CV_INTEL_VAC_AST", raising=False)
        importlib.reload(isel)


def test_env_flag_blowout_on(monkeypatch):
    monkeypatch.setenv("CV_INTEL_BLOWOUT", "on")
    importlib.reload(isel)
    try:
        assert isel.blowout_enabled() is True
        assert isel.blowout_under_flag("pts", "under", "starter", True, False) == 1.0
    finally:
        monkeypatch.delenv("CV_INTEL_BLOWOUT", raising=False)
        importlib.reload(isel)


def test_env_flag_explicit_arg_overrides_env(monkeypatch):
    # explicit enabled=False beats an ON env flag.
    monkeypatch.setenv("CV_INTEL_VAC_AST", "1")
    importlib.reload(isel)
    try:
        assert isel.vac_ast_size_multiplier("ast", 1.0, 5.5, 4.0, False, enabled=False) == 1.0
    finally:
        monkeypatch.delenv("CV_INTEL_VAC_AST", raising=False)
        importlib.reload(isel)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
