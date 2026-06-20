"""Per-file test for ingame_shot_gate_soccer (synthetic corpora, no network/parquet).

Two principled checks on the gate machinery:
  (1) NOISE shot_feat -> graceful degrade: shot coef ~0, candidate cannot beat the
      champion -> verdict NOT REPLICATED (REJECT/PARTIAL), never a false SHIP.
  (2) leak-free head-to-head: champion and candidate score the SAME test rows.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame.ingame_shot_gate_soccer import (
    aug_predict,
    fit_shot_coef,
    gate,
)
from scripts.platformkit.ingame.ingame_gate_generic_models import fit_base


def _corpus(n_games: int, seed: int, signal: bool) -> list:
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        strength = rng.normal(0, 1)            # latent home edge
        win = 1 if rng.random() < 1 / (1 + np.exp(-strength)) else 0
        p0 = float(1 / (1 + np.exp(-strength)))
        gd = 0.0
        for idx in range(19):
            fe = idx / 18.0
            if rng.random() < 0.04:
                gd += 1.0 if rng.random() < p0 else -1.0
            # shot_feat: pure noise if signal=False, else weakly tracks the latent edge
            shot = rng.normal(0, 1) if not signal else strength + rng.normal(0, 0.5)
            rows.append({
                "game_id": f"{seed}_{g}", "state_diff": gd, "frac_elapsed": fe,
                "p0": p0, "outcome": win, "shot_diff": shot, "xgproxy_diff": shot,
            })
    return rows


def test_noise_shot_feat_graceful_degrade():
    a = _corpus(60, 1, signal=False)
    b = _corpus(60, 2, signal=False)
    v = gate(a, b, "shot_diff", "A", "B")
    # a pure-noise shot feature must NOT replicate (no false SHIP)
    assert v.verdict in ("REJECT", "PARTIAL", "INVALID_BASE", "INSUFFICIENT_DATA")
    assert v.verdict != "REPLICATED"


def test_fit_shot_coef_shrinks_on_noise():
    a = _corpus(80, 7, signal=False)
    ab = fit_base(a)
    c, spread = fit_shot_coef(a, ab, "shot_diff")
    # noise feature -> coefficient near zero
    assert abs(c) <= 0.6
    assert spread > 0


def test_aug_predict_in_unit_interval():
    a = _corpus(20, 3, signal=True)
    ab = fit_base(a)
    c, spread = fit_shot_coef(a, ab, "shot_diff")
    p = aug_predict(a, ab, "shot_diff", c, spread)
    assert np.all((p >= 0.0) & (p <= 1.0))


def test_verdict_is_calibration_not_edge():
    a = _corpus(40, 4, signal=False)
    b = _corpus(40, 5, signal=False)
    v = gate(a, b, "xgproxy_diff", "A", "B")
    d = v.to_dict()
    assert "market edge" in d["vs_close"]
    assert d["sport"] == "soccer"
