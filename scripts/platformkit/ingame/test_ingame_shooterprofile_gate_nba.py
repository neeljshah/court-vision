"""Tests for scripts.platformkit.ingame.ingame_shooterprofile_gate_nba (+_io).

Covers: (1) the bridge join + tricode normalization, (2) the walk-forward
driver on synthetic states -- a strong INJECTED conditional signal ships,
its shuffled planted-null does not survive, (3) NOT_TESTABLE when the gated-
state floor is unmet, (4) the real driver runs end-to-end on the on-disk
corpora for both --layer values and returns a well-formed verdict.

Per-file pytest ONLY: python -m pytest scripts/platformkit/ingame/test_ingame_shooterprofile_gate_nba.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.ingame import ingame_shooterprofile_gate_nba as G
from scripts.platformkit.ingame import ingame_shooterprofile_gate_nba_io as IO


# --------------------------------------------------------------------- bridge
def test_norm_abbr_maps_divergent_tricodes():
    assert IO._norm_abbr("GS") == "GSW"
    assert IO._norm_abbr("NO") == "NOP"
    assert IO._norm_abbr("NY") == "NYK"
    assert IO._norm_abbr("SA") == "SAS"
    assert IO._norm_abbr("UTAH") == "UTA"
    assert IO._norm_abbr("WSH") == "WAS"
    assert IO._norm_abbr("BOS") == "BOS"  # unchanged tricode passes through


def test_bridge_games_joins_on_normalized_tricode_and_date():
    lines = pd.DataFrame({
        "event_id": [1, 2], "home_abbr": ["GS", "BOS"], "away_abbr": ["NY", "MIA"],
        "date": pd.to_datetime(["2025-11-01", "2025-11-02"]),
        "home_q1": [25, 20], "home_q2": [25, 20], "home_q3": [25, 20], "home_q4": [25, 20],
        "away_q1": [20, 25], "away_q2": [20, 25], "away_q3": [20, 25], "away_q4": [20, 25],
    })
    box = pd.DataFrame({
        "game_id": ["g1", "g1", "g2", "g2"],
        "date": pd.to_datetime(["2025-11-01"] * 2 + ["2025-11-02"] * 2),
        "team": ["GSW", "NYK", "BOS", "MIA"],
        "is_home": [True, False, True, False],
    })
    bridged = IO.bridge_games(lines, box)
    assert len(bridged) == 2
    assert set(bridged["game_id"]) == {"g1", "g2"}
    assert set(bridged["home_nba"]) == {"GSW", "BOS"}


def test_bridge_games_no_match_returns_empty():
    lines = pd.DataFrame({
        "event_id": [1], "home_abbr": ["GS"], "away_abbr": ["NY"],
        "date": pd.to_datetime(["2025-11-01"]),
        "home_q1": [25], "home_q2": [25], "home_q3": [25], "home_q4": [25],
        "away_q1": [20], "away_q2": [20], "away_q3": [20], "away_q4": [20],
    })
    box = pd.DataFrame({
        "game_id": ["gX", "gX"], "date": pd.to_datetime(["2025-12-25"] * 2),
        "team": ["LAL", "BOS"], "is_home": [True, False],
    })
    bridged = IO.bridge_games(lines, box)
    assert len(bridged) == 0


# ------------------------------------------------------------- synthetic gate
def _make_conditional_states(n_games=140, seed=1, signal_strength=6.0, noise=0.35):
    """Synthetic states where cond_prior/cond_val strongly informs the outcome
    ONLY on gated (hot/tercile) states, and score_diff is a noisy correlate of
    the SAME conditional signal (so BASE alone is weak but the conditional
    prior recovers real information -- a genuine, not-degenerate injected win).
    cond_delta is a continuous per-game draw (not binary) so the 60th-pct TRAIN
    threshold has real games strictly above it, matching how apply_hot_night_gate
    computes np.percentile(train_deltas, 60) and gates on delta > thresh."""
    rng = np.random.RandomState(seed)
    states = []
    for g in range(n_games):
        gid = 1000 + g
        cond_delta = float(rng.uniform(0.0, 0.5))   # continuous eFG-delta draw
        hot = cond_delta > 0.30                      # top ~40% of the draw range
        true_p = 0.5 + (0.35 if hot else 0.0) * (1 if g % 2 == 0 else -1)
        true_p = min(0.95, max(0.05, true_p))
        y = int(rng.rand() < true_p)
        cond_prior = true_p if hot else 0.5   # perfect info ONLY when gated
        for q in (1, 2, 3):
            frac = 1.0 - IO.QSEC[q] / IO._REG_SEC
            score_diff = float(rng.randn() * noise * signal_strength)  # weak/noisy BASE
            states.append({
                "game_id": gid, "period": q, "seconds_remaining": IO.QSEC[q],
                "score_diff": score_diff,
                "p_live": IO.p_live_from_margin(score_diff, frac),
                "outcome": y, "cond_delta": cond_delta, "cond_prior": cond_prior,
                "team": f"T{g}",
            })
    return states


def test_run_gate_ships_a_genuine_conditional_signal():
    states = _make_conditional_states()
    verdict, metrics, per_fold = G.run_gate(states, IO.apply_hot_night_gate)
    assert verdict == "SHIP_CONDITIONAL_PRIOR"
    assert metrics["brier_prior"] < metrics["brier_base"]
    assert metrics["dm_p"] < 0.05
    assert metrics["meets_min_gated_floor"] is True


def test_planted_null_shuffle_kills_the_signal():
    states = _make_conditional_states()
    shuffled = IO.shuffle_hot_night(states, seed=0)
    verdict, metrics, _ = G.run_gate(shuffled, IO.apply_hot_night_gate)
    # shuffling cond_prior across states must not preserve the genuine lift:
    # either it fails to ship, or if it ships the CI must not favor the prior.
    ci = tuple(metrics.get("dm_ci95", (0.0, 0.0)))
    assert verdict != "SHIP_CONDITIONAL_PRIOR" or not G._planted_null_dies(ci) is False


def test_planted_null_dies_sign_convention():
    # CI entirely positive (prior significantly beats base) -> did NOT die (survived).
    assert G._planted_null_dies((0.01, 0.05)) is False
    # CI entirely negative (base significantly beats prior) -> died (no false "survival").
    assert G._planted_null_dies((-0.05, -0.01)) is True
    # CI spans zero -> died (no significant beat either way).
    assert G._planted_null_dies((-0.02, 0.02)) is True


def test_not_testable_when_gated_floor_unmet():
    """A corpus with too few gated states must report NOT_TESTABLE, not a false SHIP."""
    states = _make_conditional_states(n_games=60, seed=2)
    # force almost every game to be non-hot -> gated-state floor (100) unmet.
    for s in states:
        s["cond_delta"] = 0.0
    verdict, metrics, _ = G.run_gate(states, IO.apply_hot_night_gate)
    assert verdict == "NOT_TESTABLE"
    assert metrics["meets_min_gated_floor"] is False


def test_no_usable_folds_is_not_testable():
    verdict, metrics, per_fold = G.run_gate([], IO.apply_hot_night_gate)
    assert verdict == "NOT_TESTABLE"
    assert per_fold == []


# --------------------------------------------------------------- end-to-end
@pytest.mark.parametrize("layer", ["hot_night", "scheme_fit"])
def test_real_driver_runs_end_to_end(layer):
    """Runs the real on-disk corpora; asserts a well-formed, honestly-labeled
    verdict without asserting a specific SHIP/REJECT direction (calibration
    facts on real data, not a fixed expectation)."""
    v = G.run(layer)
    assert v.layer == layer
    assert v.verdict in ("SHIP_CONDITIONAL_PRIOR", "REJECT", "NOT_TESTABLE")
    d = v.to_dict()
    assert d["vs_close"].startswith("UNPROVEN")
    assert "metrics" in d and "planted_null" in d and "caveats" in d
    assert any("CALIBRATION" in c for c in d["caveats"])


def test_run_rejects_unknown_layer():
    with pytest.raises(ValueError):
        G.run("not_a_real_layer")
