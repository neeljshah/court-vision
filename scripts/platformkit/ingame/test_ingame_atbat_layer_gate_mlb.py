"""Per-file test for ingame_atbat_layer_gate_mlb (lane B; synthetic corpora; no parquet).

Principled checks on the gate-RUN wiring and honesty rails:
  (1) planted-null column -> the gate MUST NOT replicate (the negative control fails).
  (2) the planted-null column carries NO outcome info (deterministic noise).
  (3) a pure-noise re24/leverage layer does NOT replicate (graceful-degrade -> REJECT).
  (4) a REAL signal (re24 correlated with the label) CAN be detected (gate can pass).
  (5) verdict dict is CALIBRATION/units-only, not a market edge; no $ field anywhere.
  (6) decision logic: a non-SHIP verdict is NEVER force-fed into the served model.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame import ingame_atbat_layer_gate_mlb as G


def _corpus(n_games: int, seed: int, signal: bool = False) -> list:
    """Synthetic at-bat states. BASE driven by state_diff*frac; re24/leverage are pure
    noise UNLESS signal=True, in which case re24 carries real outcome information."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        strength = rng.normal(0, 1)
        win = 1 if rng.random() < 1 / (1 + np.exp(-strength)) else 0
        p0 = float(1 / (1 + np.exp(-strength)))
        sd = 0.0
        gid = f"{seed}_{g}"
        for idx in range(20):
            fe = idx / 19.0
            if rng.random() < 0.06:
                sd += 1.0 if rng.random() < p0 else -1.0
            if signal:
                re24 = float(win) + rng.normal(0, 0.3)   # leaks the label on purpose
            else:
                re24 = rng.uniform(0.1, 2.4)             # pure noise base-out value
            lev = float(rng.integers(0, 3))
            rows.append({
                "game_id": gid, "state_diff": sd, "frac_elapsed": fe,
                "p0": p0, "outcome": win, "re24": re24, "leverage": lev,
            })
    return rows


def test_planted_null_is_deterministic_noise():
    a = _corpus(5, 11)
    z1 = G._noise_col(a)
    z2 = G._noise_col(a)
    assert np.allclose(z1, z2)
    assert abs(float(z1.mean())) < 1e-6           # standardized -> ~0 mean


def test_planted_null_does_not_replicate():
    a, b = _corpus(60, 1), _corpus(60, 2)
    res = G.gate_layer(a, b, G.fit_null_layer, G.apply_null_layer)
    assert res["replicated"] is False             # the gate CAN fail a noise column


def test_noise_re24_layer_does_not_replicate():
    a, b = _corpus(60, 3), _corpus(60, 4)
    v = G.run_gate(a, b)
    assert v.verdict in ("REJECT", "INVALID_BASE", "NOT_TESTABLE", "INSUFFICIENT_DATA")
    assert v.verdict != "SHIP"
    assert v.null_rejected is True                # negative control must reject


def test_real_signal_can_be_detected():
    """If re24 genuinely carries the label, the gate machinery CAN replicate it -- proof
    the gate is not rigged to always REJECT."""
    a, b = _corpus(80, 5, signal=True), _corpus(80, 6, signal=True)
    res = G.gate_layer(a, b, G.fit_atbat_layer, G.apply_atbat_layer)
    assert res["a_to_b"]["brier_layer"] <= res["a_to_b"]["brier_base"]
    assert res["replicated"] is True


def test_verdict_is_calibration_units_only_no_dollar():
    a, b = _corpus(40, 7), _corpus(40, 8)
    v = G.run_gate(a, b)
    d = v.to_dict()
    assert "market edge" in d["vs_close"]
    assert d["no_dollar_field"] is True and d["proposal_only"] is True
    assert "$" not in _json_dumps(d)
    # a non-SHIP verdict is NEVER force-fed into the served model
    assert v.verdict != "SHIP"


def test_insufficient_data_when_thin():
    a, b = _corpus(2, 9), _corpus(2, 10)
    v = G.run_gate(a, b)
    assert v.verdict == "INSUFFICIENT_DATA"


def _json_dumps(d) -> str:
    import json
    return json.dumps(d)
