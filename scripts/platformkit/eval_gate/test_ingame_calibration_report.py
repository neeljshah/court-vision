"""Per-file test for the S43 in-game calibration report (descriptive, no bar)."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.calib_decomp import bin_edges
from scripts.platformkit.eval_gate.ingame_calibration_report import build_ingame_report


def _stream(n_games: int = 20, n_ticks: int = 30):
    """20 games x 30 ticks; the loser's path peaks at a value we know per game."""
    ticks, probs, outcomes, games = [], [], [], []
    for g in range(n_games):
        won = g % 2 == 0
        peak = 0.50 + 0.02 * g          # only the LOSER games' peaks may be reported
        for t in range(n_ticks):
            ticks.append({"i": len(ticks)})
            # winners ride high; losers rise to `peak` exactly once, at the last tick
            probs.append(0.95 if won else (peak if t == n_ticks - 1 else 0.10))
            outcomes.append(1.0 if won else 0.0)
            games.append("G%02d" % g)
    return ticks, probs, outcomes, games


def test_max_loser_wp_uses_only_loser_paths():
    ticks, probs, outcomes, games = _stream()
    report = build_ingame_report(ticks, {"s": probs}, outcomes, games)
    loser = report["series"]["s"]["max_loser_wp"]
    assert loser["n_loser_games"] == 10            # only the 10 losing games
    peaks = {row["game"]: row["max_loser_wp"] for row in loser["per_game"]}
    assert set(peaks) == {"G%02d" % g for g in range(1, 20, 2)}
    for g in range(1, 20, 2):                      # the loser's own peak, not 0.95
        assert abs(peaks["G%02d" % g] - (0.50 + 0.02 * g)) < 1e-12
    assert loser["max"] == max(peaks.values())
    assert loser["above_0_8"] == sum(v > 0.8 for v in peaks.values())
    assert abs(loser["share_above_0_8"] - loser["above_0_8"] / 10) < 1e-12


def test_perfectly_calibrated_series_has_near_zero_reliability():
    rng = np.random.default_rng(20260903)
    ticks, probs, outcomes, games = [], [], [], []
    for g in range(20):
        p = 0.05 + 0.9 * rng.random()
        for t in range(400):
            ticks.append({"i": len(ticks)})
            probs.append(p)
            outcomes.append(float(rng.random() < p))
            games.append("G%02d" % g)
    block = build_ingame_report(ticks, {"cal": probs}, outcomes, games)["series"]["cal"]
    assert block["murphy"]["reliability"] < 5e-3
    assert block["ece"] < 5e-2
    assert block["reproduction_max_abs_diff"] < 1e-9


def test_bin_edges_match_calib_decomp():
    ticks, probs, outcomes, games = _stream()
    report = build_ingame_report(ticks, {"s": probs}, outcomes, games, bins=10)
    edges = bin_edges(10)
    assert report["bin_edges"] == [float(e) for e in edges]
    rows = report["series"]["s"]["reliability_bins"]
    assert len(rows) == len(edges) - 1
    assert [row["bin"] for row in rows] == [
        "%0.1f-%0.1f" % (edges[k], edges[k + 1]) for k in range(len(edges) - 1)]
    assert sum(row["n"] for row in rows) == len(probs)


def test_misaligned_series_is_refused():
    ticks, probs, outcomes, games = _stream()
    try:
        build_ingame_report(ticks, {"s": probs[:-1]}, outcomes, games)
    except ValueError:
        return
    raise AssertionError("misaligned series accepted")
