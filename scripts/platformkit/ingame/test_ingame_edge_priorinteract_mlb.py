"""Per-file test for ingame_edge_priorinteract_mlb (synthetic corpora; no network/parquet).

Checks the gate-RUN wiring (the scoring math itself is tested in
test_ingame_shot_gate_soccer):
  (1) the planted-null column does NOT replicate through the SAME gate (control fails).
  (2) the planted-null column is deterministic noise carrying no outcome info.
  (3) the signed run looks only BACKWARD (leak-free) and is 0 before a window exists.
  (4) prior-conditioned interaction features on a base+prior-generated corpus do NOT
      replicate (graceful-degrade) -> REJECT, never force-fed into the served model.
  (5) verdict dict is CALIBRATION/units-only -- no $ field; vs_close UNPROVEN.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame import ingame_edge_priorinteract_mlb as G
from scripts.platformkit.ingame.ingame_shot_gate_soccer import gate


def _corpus(n_games: int, seed: int) -> list:
    """Synthetic MLB-like states: outcome driven ONLY by p0 + an additive margin/time
    base (NO interaction signal), so an interaction candidate has nothing to explain.
    Derived features mirror load_states; null is the deterministic control column."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        strength = rng.normal(0, 1.0)
        p0 = float(1 / (1 + np.exp(-strength)))
        win = 1 if rng.random() < p0 else 0
        gid = f"{seed}_{g}"
        sd = 0.0
        prev = []
        for idx in range(18):
            fe = idx / 17.0
            if rng.random() < 0.10:
                sd += 1.0 if rng.random() < p0 else -1.0
            pc = p0 - 0.5
            run = G._signed_run(prev, sd)
            rows.append({
                "game_id": gid, "state_diff": sd, "frac_elapsed": fe, "p0": p0,
                "outcome": win,
                "prior_x_margin": pc * sd, "prior_x_time": pc * fe,
                "run_x_prior": run * pc,
                "planted_null": G._planted_null_col(gid, idx),
            })
            prev.append(sd)
    return rows


def test_planted_null_rejects():
    a, b = _corpus(60, 1), _corpus(60, 2)
    v = gate(a, b, "planted_null", "A", "B")
    assert v.verdict != "REPLICATED"   # the gate CAN fail a signal


def test_planted_null_is_deterministic_noise():
    v1 = G._planted_null_col("700123", 5)
    v2 = G._planted_null_col("700123", 5)
    assert v1 == v2 and -2.0 <= v1 <= 2.0
    assert G._planted_null_col("700123", 5) != G._planted_null_col("700124", 5)


def test_signed_run_is_backward_only_and_zero_before_window():
    assert G._signed_run([], 3.0) == 0.0            # no history -> no run
    assert G._signed_run([0.0], 1.0) == 1.0         # window not full -> vs first
    # full window: cur minus the diff _RUN_WINDOW ticks ago
    assert G._signed_run([0.0, 1.0, 1.0], 2.0) == 2.0 - 0.0


def test_interaction_features_do_not_replicate():
    a, b = _corpus(70, 3), _corpus(70, 4)
    for feat in ("prior_x_margin", "prior_x_time", "run_x_prior"):
        v = gate(a, b, feat, "A", "B")
        assert v.verdict in ("REJECT", "PARTIAL", "INVALID_BASE", "INSUFFICIENT_DATA")
        assert v.verdict != "REPLICATED"


def test_verdict_is_calibration_units_only_no_dollar():
    a, b = _corpus(50, 5), _corpus(50, 6)
    d = G._gate_one(a, b, "prior_x_margin", "A", "B")
    assert d["verdict"] in ("SHIP", "REJECT", "NOT_TESTABLE")
    if d["verdict"] != "SHIP":
        assert d["wired_into_served"] is False
    rl = d["real_layer"]
    assert "market edge" in rl["vs_close"]
    import json
    assert "$" not in json.dumps(d)
