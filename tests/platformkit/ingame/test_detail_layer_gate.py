"""THE CRITICAL TEST for the negative-control backbone (detail_layer_gate).

A harness that can only PASS signals is worthless. These tests prove the merge+dispatch
wrapper FAILS bad detail columns:
  * PURE-NOISE detail (random, leak-free)   -> NOT REPLICATED (REJECT/PARTIAL-not-replicated).
  * detail IDENTICAL to base state_diff      -> degenerate/no-new-info -> NOT REPLICATED.
  * trivially-LEAKING detail (= outcome)     -> NOT a false SHIP/REPLICATED on held-out data.

All scoring is INHERITED from ingame_gate_generic.gate_cross (DM-by-game + degenerate
guard); these tests only assert the wrapper routes signals through it honestly.

Per-file run:
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
    tests/platformkit/ingame/test_detail_layer_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit.ingame.detail_layer_gate import (
    gate_detail_layer,
    merge_detail_onto_base,
)

# A real in-game beat requires REPLICATED across both directions; anything else (REJECT,
# PARTIAL, INVALID_BASE, INSUFFICIENT_DATA) is the harness REFUSING to ship.
_NOT_REPLICATED = {"REJECT", "PARTIAL", "INVALID_BASE", "INSUFFICIENT_DATA"}


def _base_corpus(seed: int, n_games: int = 40, ticks: int = 24):
    """Synthetic in-game BASE state corpus with a GENUINE state_diff->outcome signal.

    outcome ~ Bernoulli(sigmoid(0.45 * final_state_diff)) so BASE (state,time) is
    NON-degenerate -- pass/fail is then driven by the DETAIL column, not capped by the
    honesty guard. Rows keyed (game_id, asof_idx); state_diff drifts toward the final lead.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_games):
        gid = seed * 10_000 + g
        final = float(rng.normal(0.0, 8.0))
        win = int(rng.random() < 1.0 / (1.0 + np.exp(-0.45 * final)))
        for k in range(ticks):
            frac = (k + 1) / ticks
            sd = final * frac + float(rng.normal(0.0, 4.0)) * (1.0 - frac)
            rows.append({"game_id": gid, "asof_idx": k, "state_diff": sd,
                         "frac_elapsed": frac, "outcome": win})
    return pd.DataFrame(rows)


def _detail_noise(base: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Pure-noise, leak-free detail keyed to the same (game_id, asof_idx)."""
    rng = np.random.default_rng(seed + 777)
    return pd.DataFrame({
        "game_id": base["game_id"].values, "asof_idx": base["asof_idx"].values,
        "detail": rng.normal(0.0, 1.0, len(base)),
    })


def _detail_copy_state(base: pd.DataFrame) -> pd.DataFrame:
    """Detail IDENTICAL to base state_diff -- no new information beyond BASE."""
    return pd.DataFrame({
        "game_id": base["game_id"].values, "asof_idx": base["asof_idx"].values,
        "detail": base["state_diff"].values,
    })


def _detail_leak(base: pd.DataFrame) -> pd.DataFrame:
    """Trivially-leaking detail: the outcome itself (a future-leak, not a real signal)."""
    return pd.DataFrame({
        "game_id": base["game_id"].values, "asof_idx": base["asof_idx"].values,
        "detail": base["outcome"].astype(float).values,
    })


# --------------------------------------------------------------------- the controls
def test_pure_noise_detail_is_not_shipped():
    """The KEYSTONE negative control: a random leak-free detail MUST NOT replicate."""
    a, b = _base_corpus(1), _base_corpus(2)
    da, db = _detail_noise(a, 1), _detail_noise(b, 2)
    v = gate_detail_layer(a, da, b, db, col="detail", sport="noisetest")
    assert v.verdict in _NOT_REPLICATED, f"noise detail wrongly shipped: {v.verdict}"
    assert v.verdict != "REPLICATED"
    # graceful degrade: BASE+detail must not BEAT BASE in either direction on a noise prior
    for d in (v.a_to_b, v.b_to_a):
        assert not d.get("prior_beats_base"), "noise detail flagged as beating base"


def test_detail_identical_to_base_is_not_shipped():
    """Detail == base state_diff carries no new info -> NOT REPLICATED (no false ship)."""
    a, b = _base_corpus(3), _base_corpus(4)
    da, db = _detail_copy_state(a), _detail_copy_state(b)
    v = gate_detail_layer(a, da, b, db, col="detail", sport="copytest")
    assert v.verdict in _NOT_REPLICATED, f"redundant detail wrongly shipped: {v.verdict}"
    assert v.verdict != "REPLICATED"


def test_leaking_detail_is_caught_not_false_ship():
    """A detail that equals the outcome is a future-leak, NOT a held-out signal.

    HONEST LESSON: a cross-corpus held-out gate alone does NOT catch a column that IS the
    label -- the leak is identical in both train and held-out corpora, so it "replicates".
    leak-free is a RAILS precondition, so the backbone's merge LEAK GUARD must refuse such
    a column (ValueError) rather than let the gate mistake it for a real in-game edge.
    """
    import pytest
    a, b = _base_corpus(5), _base_corpus(6)
    da, db = _detail_leak(a), _detail_leak(b)
    with pytest.raises(ValueError, match="LEAK GUARD"):
        gate_detail_layer(a, da, b, db, col="detail", sport="leaktest")


def test_near_leaking_detail_is_caught():
    """A detail that is the outcome plus tiny noise (corr ~ ceiling) is still a leak."""
    import pytest
    a, b = _base_corpus(9), _base_corpus(10)
    rng = np.random.default_rng(123)

    def near(base):
        d = _detail_leak(base)
        d["detail"] = d["detail"].values + rng.normal(0.0, 1e-6, len(d))
        return d

    with pytest.raises(ValueError, match="LEAK GUARD"):
        gate_detail_layer(a, near(a), b, near(b), col="detail", sport="nearleak")


# --------------------------------------------------------------------- merge guards
def test_merge_requires_join_keys_and_column():
    """Malformed corpora fail honest (ValueError), never silent 0-fill."""
    a = _base_corpus(7)
    import pytest
    with pytest.raises(ValueError):
        merge_detail_onto_base(a, pd.DataFrame({"game_id": [1]}), "detail")  # no asof_idx
    with pytest.raises(ValueError):
        merge_detail_onto_base(a.drop(columns=["state_diff"]),
                               _detail_noise(a, 7), "detail")  # base missing col


def test_merge_disjoint_keys_raises():
    """No overlap on (game_id, asof_idx) -> honest error, not an empty silent ship."""
    a = _base_corpus(8)
    bad = _detail_noise(a, 8).copy()
    bad["game_id"] = bad["game_id"] + 10_000_000  # force disjoint keys
    import pytest
    with pytest.raises(ValueError):
        merge_detail_onto_base(a, bad, "detail")
