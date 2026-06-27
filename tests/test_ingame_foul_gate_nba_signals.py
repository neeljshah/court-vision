"""Per-file test for ingame_foul_gate_nba_signals (no network, synthetic states)."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame import ingame_foul_gate_nba_signals as S


def _state(margin, frac, fd):
    return {"score_diff": margin, "frac_elapsed": frac, "foul_diff": fd,
            "p0": 0.5, "p_live": 0.5, "outcome": 1, "game_id": 0,
            "seconds_remaining": 2880 * (1 - frac)}


def test_bonus_late_zeroes_blowout_and_early():
    states = [
        _state(2.0, 0.9, 5.0),    # close & late -> keep
        _state(20.0, 0.9, 5.0),   # late but blowout -> zero
        _state(2.0, 0.2, 5.0),    # close but early -> zero
    ]
    v = S.sig_bonus_late(states)
    assert v[0] == 5.0 and v[1] == 0.0 and v[2] == 0.0


def test_foul_x_lead_sign_interaction():
    states = [_state(10.0, 0.5, 3.0),    # home leading -> +
              _state(-10.0, 0.5, 3.0),   # home trailing -> -
              _state(0.0, 0.5, 3.0)]     # tied -> 0
    v = S.sig_foul_x_lead(states)
    assert v[0] == 3.0 and v[1] == -3.0 and v[2] == 0.0


def _synth(n_games=150, ticks=18, predictive=False, seed=0):
    """Outcome driven (when predictive) by foul_diff*sign(early margin) -- the EXACT
    quantity sig_foul_x_lead computes -- so a correct gate must recover it."""
    rng = np.random.default_rng(seed)
    out = []
    for g in range(n_games):
        true_p = rng.uniform(0.25, 0.75)
        fd_g = rng.normal(0, 3)
        lead_sign = 1.0 if true_p >= 0.5 else -1.0
        win = None
        for t in range(ticks):
            frac = (t + 0.5) / ticks
            margin = rng.normal((true_p - 0.5) * 18, 6)
            fd = fd_g + rng.normal(0, 2)
            if win is None:
                lin = (true_p - 0.5) * 3
                if predictive:
                    lin += 0.3 * fd_g * lead_sign  # == foul_x_lead expectation
                win = int(rng.uniform() < 1.0 / (1.0 + np.exp(-lin)))
            out.append({"game_id": g, "seconds_remaining": 2880 * (1 - frac),
                        "score_diff": margin, "frac_elapsed": frac, "foul_diff": fd,
                        "p0": float(np.clip(0.5 + (true_p - 0.5) * 0.4, 0.05, 0.95)),
                        "p_live": float(1 / (1 + np.exp(-0.08 * margin))),
                        "outcome": win})
    return out


def test_null_signal_rejects():
    a = _synth(predictive=False, seed=1)
    b = _synth(predictive=False, seed=2)
    r = S.gate_signal(a, b, S.sig_foul_x_lead)
    assert r["verdict"] in ("REJECT", "PARTIAL")


def test_predictive_signal_improves_brier():
    # foul_x_lead aligns with the injected fd-driven outcome via sign(margin)
    a = _synth(predictive=True, seed=3, n_games=250)
    b = _synth(predictive=True, seed=4, n_games=250)
    r = S.gate_signal(a, b, S.sig_foul_x_lead)
    assert (r["a_to_b"]["brier_delta"] > 0) or (r["b_to_a"]["brier_delta"] > 0)
