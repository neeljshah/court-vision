"""Tests for the max-loser-WP calibrated null diagnostic."""
import numpy as np

from scripts.platformkit.wp_diag_null import (
    _martingale_path,
    compare,
    path_parameters,
    simulate_null,
)


def test_calibrated_synthetic_observed_stats_are_inside_null_band() -> None:
    rng = np.random.default_rng(71)
    params = {"pregame_probs": np.linspace(0.2, 0.8, 21), "ticks": 16, "step_vol": 0.055}
    ticks = []
    for game in range(80):
        path, outcome = _martingale_path(float(params["pregame_probs"][game % 21]), 16,
                                         0.055, rng)
        for index, probability in enumerate(path[:-1]):
            ticks.append({"game": str(game), "timestamp": "%03d" % index,
                          "model_prob": float(probability), "outcome": float(outcome)})
    fitted = path_parameters(ticks)
    loser_peaks = {}
    for tick in ticks:
        if tick["outcome"] == 0.0:
            loser_peaks[tick["game"]] = max(loser_peaks.get(tick["game"], 0.0), tick["model_prob"])
    peaks = sorted(loser_peaks.values())
    report = {"max_loser_wp": {"per_game": [
        {"game": game, "max_loser_wp": peak} for game, peak in loser_peaks.items()]}}
    from scripts.platformkit.wp_diag_null import observed_statistics
    rows = compare(observed_statistics(report), simulate_null(fitted, len(peaks), 2000))
    assert all(row["verdict"] == "INSIDE" for row in rows)
