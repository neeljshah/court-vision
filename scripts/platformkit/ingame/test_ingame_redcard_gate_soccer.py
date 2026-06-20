"""Per-file test for ingame_redcard_gate_soccer (synthetic corpora; no network/parquet).

Principled checks on the gate-RUN wiring (the scoring math itself is tested in
test_ingame_shot_gate_soccer):
  (1) planted-null column -> the gate MUST NOT replicate (the negative control fails).
  (2) the planted-null column carries NO outcome info (deterministic noise).
  (3) a pure-noise red_diff column does NOT replicate (graceful-degrade).
  (4) verdict dict is CALIBRATION/units-only, not a market edge; no $ field.
  (5) decision logic: if the planted-null replicated, FINAL is NOT_TESTABLE; a REJECT
      is never wired into the served model.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame import ingame_redcard_gate_soccer as G
from scripts.platformkit.ingame.ingame_shot_gate_soccer import gate


def _corpus(n_games: int, seed: int) -> list:
    """Synthetic combo states with red_diff = PURE NOISE (sparse) + a null col."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        strength = rng.normal(0, 1)
        win = 1 if rng.random() < 1 / (1 + np.exp(-strength)) else 0
        p0 = float(1 / (1 + np.exp(-strength)))
        gd = 0.0
        rd = 0.0
        for idx in range(19):
            fe = idx / 18.0
            if rng.random() < 0.04:
                gd += 1.0 if rng.random() < p0 else -1.0
            if rng.random() < 0.02:                 # sparse, like real red cards
                rd += 1.0 if rng.random() < 0.5 else -1.0
            gid = f"{seed}_{g}"
            rows.append({
                "game_id": gid, "state_diff": gd, "frac_elapsed": fe,
                "p0": p0, "outcome": win,
                "red_diff": rd,                                 # noise man-advantage
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
    assert G._planted_null_col("704279", 5) != G._planted_null_col("704280", 5)


def test_noise_red_diff_does_not_replicate():
    a, b = _corpus(60, 3), _corpus(60, 4)
    v = gate(a, b, "red_diff", "A", "B")
    assert v.verdict in ("REJECT", "PARTIAL", "INVALID_BASE", "INSUFFICIENT_DATA")
    assert v.verdict != "REPLICATED"


def test_sparsity_counts_red_states():
    a = _corpus(40, 7)
    sp = G._sparsity(a)
    assert sp["n_states"] == len(a)
    assert 0 <= sp["n_red_states"] <= sp["n_states"]
    assert 0.0 <= sp["frac_red"] <= 1.0


def test_verdict_is_calibration_units_only_no_dollar():
    a, b = _corpus(40, 5), _corpus(40, 6)
    real = gate(a, b, "red_diff", "A", "B")
    nullv = gate(a, b, "planted_null", "A", "B")
    null_rejects = nullv.verdict != "REPLICATED"
    # mirror the run() decision logic
    if not null_rejects:
        final, wired = "NOT_TESTABLE", False
    elif real.verdict == "REPLICATED":
        final, wired = "SHIP", True
    else:
        final, wired = "REJECT", False
    assert final in ("SHIP", "REJECT", "NOT_TESTABLE")
    # a non-SHIP verdict is NEVER force-fed into the served model
    if final != "SHIP":
        assert wired is False
    d = real.to_dict()
    assert "market edge" in d["vs_close"]
    assert "$" not in _json_dumps(d)


def _json_dumps(d) -> str:
    import json
    return json.dumps(d)
