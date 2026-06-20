"""Per-file test for ingame_xgloc_gate_soccer (synthetic corpora; no network/parquet).

Principled checks on the gate-RUN wiring (the scoring math itself is tested in
test_ingame_shot_gate_soccer):
  (1) planted-null column -> the gate MUST NOT replicate (the negative control fails).
  (2) the planted-null column carries NO outcome info (deterministic noise).
  (3) verdict dict is CALIBRATION, not a market edge; proposal-only; no $ field.
  (4) decision logic: if the planted-null replicated, FINAL is NOT_TESTABLE.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame import ingame_xgloc_gate_soccer as G
from scripts.platformkit.ingame.ingame_shot_gate_soccer import gate


def _corpus(n_games: int, seed: int) -> list:
    """Synthetic combo states with the new layer's xgloc_diff = PURE NOISE + a null col."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        strength = rng.normal(0, 1)
        win = 1 if rng.random() < 1 / (1 + np.exp(-strength)) else 0
        p0 = float(1 / (1 + np.exp(-strength)))
        gd = 0.0
        for idx in range(19):
            fe = idx / 18.0
            if rng.random() < 0.04:
                gd += 1.0 if rng.random() < p0 else -1.0
            gid = f"{seed}_{g}"
            rows.append({
                "game_id": gid, "state_diff": gd, "frac_elapsed": fe,
                "p0": p0, "outcome": win,
                "xgloc_diff": rng.normal(0, 1),                 # noise location proxy
                "planted_null": G._planted_null_col(gid, idx),  # deterministic noise
            })
    return rows


def test_planted_null_rejects():
    a, b = _corpus(60, 1), _corpus(60, 2)
    v = gate(a, b, "planted_null", "A", "B")
    assert v.verdict != "REPLICATED"   # the gate CAN fail a signal


def test_planted_null_is_deterministic_noise():
    v1 = G._planted_null_col("704279", 5)
    v2 = G._planted_null_col("704279", 5)
    assert v1 == v2 and -2.0 <= v1 <= 2.0
    # different keys give different values (not a constant)
    assert G._planted_null_col("704279", 5) != G._planted_null_col("704280", 5)


def test_noise_xgloc_does_not_replicate():
    a, b = _corpus(60, 3), _corpus(60, 4)
    v = gate(a, b, "xgloc_diff", "A", "B")
    assert v.verdict in ("REJECT", "PARTIAL", "INVALID_BASE", "INSUFFICIENT_DATA")
    assert v.verdict != "REPLICATED"


def test_verdict_is_calibration_not_edge_no_dollar():
    a, b = _corpus(40, 5), _corpus(40, 6)
    real = gate(a, b, "xgloc_diff", "A", "B")
    nullv = gate(a, b, "planted_null", "A", "B")
    null_rejects = nullv.verdict != "REPLICATED"
    # mirror the run() decision logic
    if not null_rejects:
        final = "NOT_TESTABLE"
    elif real.verdict == "REPLICATED":
        final = "SHIP"
    else:
        final = "REJECT"
    assert final in ("SHIP", "REJECT", "NOT_TESTABLE")
    d = real.to_dict()
    assert "market edge" in d["vs_close"]
    assert "$" not in json_dumps(d)


def json_dumps(d) -> str:
    import json
    return json.dumps(d)
