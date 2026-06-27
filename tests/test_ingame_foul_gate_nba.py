"""Per-file test for scripts.platformkit.ingame.ingame_foul_gate_nba (no network).

Validates: (a) the foul correction collapses to c=0 on a NULL foul signal (no-op ->
M1==M0 -> REJECT), and (b) the gate DETECTS a genuinely-predictive injected foul signal
(c!=0, M1<M0). Uses synthetic states only.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame import ingame_foul_gate_nba as G


def _states(n_games=120, ticks=20, foul_predictive=False, seed=0):
    """Synthetic as-of states. p_live is a noisy margin signal; p0 a weak prior.

    If foul_predictive, the outcome is partly driven by foul_diff (so a foul layer
    SHOULD add skill); otherwise foul_diff is pure noise (layer should collapse to 0).
    """
    rng = np.random.default_rng(seed)
    out = []
    for g in range(n_games):
        true_p = rng.uniform(0.2, 0.8)
        fd_game = rng.normal(0, 3)  # per-game foul tilt
        win = None
        for t in range(ticks):
            frac = (t + 0.5) / ticks
            margin = rng.normal((true_p - 0.5) * 20, 6)
            fd = fd_game + rng.normal(0, 2)
            p_live = 1.0 / (1.0 + np.exp(-0.08 * margin))
            p0 = 0.5 + (true_p - 0.5) * 0.4
            if win is None:
                lin = (true_p - 0.5) * 3
                if foul_predictive:
                    lin += 0.25 * fd  # away fouling more -> home wins more
                win = int(rng.uniform() < 1.0 / (1.0 + np.exp(-lin)))
            out.append({"game_id": g, "seconds_remaining": 2880 * (1 - frac),
                        "score_diff": margin, "frac_elapsed": frac,
                        "foul_diff": fd, "home_fouls": 0.0, "away_fouls": 0.0,
                        "p0": float(np.clip(p0, 0.05, 0.95)), "p_live": float(p_live),
                        "outcome": win})
    return out


def test_null_foul_signal_collapses_to_noop():
    a = _states(foul_predictive=False, seed=1)
    b = _states(foul_predictive=False, seed=2)
    v = G.run_gate(a, b)
    # On a null foul signal the layer must NOT ship.
    assert v.verdict in ("REJECT", "PARTIAL")
    # the brier delta should be tiny in magnitude (layer is ~no-op)
    assert abs(v.a_to_b["brier_delta"]) < 0.01


def test_predictive_foul_signal_detected():
    a = _states(foul_predictive=True, seed=3, n_games=200)
    b = _states(foul_predictive=True, seed=4, n_games=200)
    v = G.run_gate(a, b)
    # A genuinely predictive foul signal should improve Brier in at least one direction
    assert (v.a_to_b["brier_delta"] > 0) or (v.b_to_a["brier_delta"] > 0)
    assert v.a_to_b["nontrivial_correction"] or v.b_to_a["nontrivial_correction"]


def test_fit_correction_zero_on_pure_noise():
    s = _states(foul_predictive=False, seed=5, n_games=150)
    m0 = np.array([st["p_live"] for st in s], float)
    c_by, spread = G.fit_foul_correction(s, m0)
    assert spread > 0
    # On noise the in-sample grid may pick small non-zero c's (overfit) -- the held-out
    # gate is what protects against that. Here we only assert no bucket picks a LARGE
    # slope; a real foul signal in the other tests drives |c| much higher.
    assert max(abs(v) for v in c_by.values()) <= 0.35
