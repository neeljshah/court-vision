"""Per-file test for ingame_edge_leverage_mlb (synthetic; no network/parquet).

  (1) planted-null does NOT replicate through the SAME gate (control fails).
  (2) planted-null is deterministic noise.
  (3) leverage_bucket -> ordinal score mapping (low/mid/high -> -1/0/+1; unknown -> 0).
  (4) leverage features on a base+prior-generated corpus do NOT replicate -> REJECT.
  (5) verdict dict is CALIBRATION/units-only -- no $ field.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame import ingame_edge_leverage_mlb as G
from scripts.platformkit.ingame.ingame_shot_gate_soccer import gate


def _corpus(n_games: int, seed: int) -> list:
    rng = np.random.default_rng(seed)
    buckets = ("low", "mid", "high")
    rows = []
    for g in range(n_games):
        strength = rng.normal(0, 1.0)
        p0 = float(1 / (1 + np.exp(-strength)))
        win = 1 if rng.random() < p0 else 0
        gid = f"{seed}_{g}"
        sd = 0.0
        for idx in range(18):
            fe = idx / 17.0
            if rng.random() < 0.12:
                sd += 1.0 if rng.random() < p0 else -1.0
            lev = G._LEV_MAP[buckets[rng.integers(0, 3)]]
            rows.append({
                "game_id": gid, "state_diff": sd, "frac_elapsed": fe, "p0": p0,
                "outcome": win,
                "leverage_score": lev, "leverage_x_prior": lev * (p0 - 0.5),
                "planted_null": G._planted_null_col(gid, idx),
            })
    return rows


def test_planted_null_rejects():
    a, b = _corpus(60, 1), _corpus(60, 2)
    assert gate(a, b, "planted_null", "A", "B").verdict != "REPLICATED"


def test_planted_null_is_deterministic_noise():
    assert G._planted_null_col("661", 4) == G._planted_null_col("661", 4)
    assert G._planted_null_col("661", 4) != G._planted_null_col("662", 4)
    assert -2.0 <= G._planted_null_col("661", 4) <= 2.0


def test_leverage_score_mapping():
    assert G._LEV_MAP["low"] == -1.0 and G._LEV_MAP["high"] == 1.0
    assert G._LEV_MAP["mid"] == 0.0
    assert G._LEV_MAP.get("garbage", 0.0) == 0.0


def test_leverage_features_do_not_replicate():
    a, b = _corpus(70, 3), _corpus(70, 4)
    for feat in ("leverage_score", "leverage_x_prior"):
        v = gate(a, b, feat, "A", "B")
        assert v.verdict != "REPLICATED"


def test_verdict_units_only_no_dollar():
    a, b = _corpus(50, 5), _corpus(50, 6)
    d = G._gate_one(a, b, "leverage_x_prior", "A", "B")
    if d["verdict"] != "SHIP":
        assert d["wired_into_served"] is False
    import json
    assert "$" not in json.dumps(d)
    assert "market edge" in d["real_layer"]["vs_close"]
