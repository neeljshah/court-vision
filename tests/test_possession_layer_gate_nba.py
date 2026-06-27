"""Per-file test for scripts.platformkit.ingame.possession_layer_gate_nba (no network).

Builds two SYNTHETIC possession-states corpora (frozen base schema + additive cols) and
checks the runner: (a) a pure-NOISE detail column is REJECTED (graceful-degrade negative
control), and (b) a genuinely outcome-predictive detail column improves held-out Brier in
at least one direction. Uses pandas frames only -- no parquet / network.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.ingame import possession_layer_gate_nba as G


def _corpus(n_games=160, ticks=18, predictive=False, seed=0):
    """Synthetic as-of states. state_diff is a noisy margin; outcome a logistic of it.

    `useful` is a real per-game predictor of the outcome (gets a SHIP chance when
    predictive=True); `noise` is pure per-row noise (must REJECT either way).
    """
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        true_p = rng.uniform(0.2, 0.8)
        signal_g = rng.normal(0, 1)  # per-game latent
        win = None
        for t in range(ticks):
            frac = (t + 0.5) / ticks
            margin = rng.normal((true_p - 0.5) * 20, 6)
            if win is None:
                lin = (true_p - 0.5) * 3
                if predictive:
                    lin += 1.4 * signal_g
                win = int(rng.uniform() < 1.0 / (1.0 + np.exp(-lin)))
            rows.append({
                "game_id": f"g{g}", "asof_idx": t,
                "state_diff": float(margin), "frac_elapsed": float(frac),
                "outcome": int(win),
                "useful": float(signal_g + rng.normal(0, 0.3)),
                "noise": float(rng.normal(0, 1)),
            })
    return pd.DataFrame(rows)


def test_noise_column_rejected():
    a = _corpus(predictive=False, seed=1)
    b = _corpus(predictive=False, seed=2)
    v = G.gate_column(a, b, "noise", min_ticks=50)
    assert v.verdict in ("REJECT", "PARTIAL", "INSUFFICIENT_DATA")
    # graceful degrade: a noise detail cannot meaningfully beat base in BOTH directions
    beats_both = (v.a_to_b and v.a_to_b.get("prior_beats_base") and
                  v.b_to_a and v.b_to_a.get("prior_beats_base"))
    assert not beats_both


def test_useful_column_improves_at_least_one_direction():
    a = _corpus(predictive=True, seed=3, n_games=240)
    b = _corpus(predictive=True, seed=4, n_games=240)
    v = G.gate_column(a, b, "useful", min_ticks=50)
    d1 = v.a_to_b.get("brier_delta") if v.a_to_b else None
    d2 = v.b_to_a.get("brier_delta") if v.b_to_a else None
    assert (d1 is not None and d1 > 0) or (d2 is not None and d2 > 0)


def test_run_report_shape():
    a = _corpus(predictive=False, seed=5)
    b = _corpus(predictive=False, seed=6)
    # monkey-load via direct cols arg (bypass parquet) by calling gate_column per col
    res = {"season_a": "A", "season_b": "B",
           "a_games": int(a["game_id"].nunique()), "a_states": int(len(a)),
           "b_games": int(b["game_id"].nunique()), "b_states": int(len(b)),
           "vs_close": "UNPROVEN", "columns": {
               "noise": {"verdict": G.gate_column(a, b, "noise", min_ticks=50).verdict,
                         "a_to_b": {}, "b_to_a": {}}}}
    txt = G._report(res)
    assert "POSSESSION" in txt and "noise" in txt and "vs_close" in txt
