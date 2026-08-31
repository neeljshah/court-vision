"""Synthetic checks for win-probability calibration diagnostics."""
from scripts.platformkit.wp_diagnostics import diagnose, max_loser_wp, reliability


def _tick(game, prob, outcome, phase="Q1"):
    return {"game": game, "model_prob": prob, "outcome": outcome, "phase": phase}


def test_max_loser_wp_separates_overconfident_and_calibrated_paths():
    overconfident = [_tick("loss-%d" % i, 0.95, 0.0) for i in range(8)]
    calibrated = [_tick("loss-%d" % i, 0.35, 0.0) for i in range(8)]
    over = max_loser_wp(overconfident)
    calm = max_loser_wp(calibrated)
    assert over["quantiles"]["50"] > calm["quantiles"]["50"]
    assert over["above_0_8"] == 8
    assert calm["above_0_8"] == 0


def test_biased_fixture_reliability_flag_fires_and_isotonic_improves():
    ticks = [_tick("win-%03d" % i, 0.9, 0.0, "Q2") for i in range(60)]
    ticks += [_tick("loss-%03d" % i, 0.1, 1.0, "Q2") for i in range(60)]
    rows = reliability(ticks)
    assert rows[1]["flag"] is True
    assert rows[9]["flag"] is True
    assert all(row["status"] == "INSUFFICIENT" for row in rows if row["n"] < 50)
    report = diagnose(ticks)
    assert report["isotonic_check"]["delta"] is not None
    assert report["isotonic_check"]["delta"] > 0
