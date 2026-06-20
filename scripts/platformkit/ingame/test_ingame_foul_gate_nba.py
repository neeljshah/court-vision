"""Per-file tests for ingame_foul_gate_nba.py -- synthetic states, no real corpora.

Covers: (1) sparse-bucket c=0, (2) planted-null collapse, (3) zero-c noop,
(4) nonzero-c changes preds, (5) informative foul -> nontrivial correction,
(6) planted-null REJECT, (7) decide() logic, (8) to_dict() keys + no $ fields,
(9) outside-segment rows unchanged, (10) cross_direction output keys + no $ fields.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_foul_gate_nba.py -q
"""
from __future__ import annotations
import sys
import numpy as np
from scripts.platformkit.ingame.ingame_foul_gate_nba import (
    FoulVerdict, _N_TBUCKET, _tbucket,
    apply_foul_correction, cross_direction, decide, fit_foul_correction, run_gate,
)

_FORBIDDEN = {"dollar", "pnl", "roi", "edge", "profit", "stake",
              "units_wagered", "wager", "bankroll", "kelly"}


def _make_states(seed: int, n_games: int = 300, states_per_game: int = 8,
                 informative_foul: bool = False) -> list:
    """Synthetic foul-state dicts. informative_foul=True correlates foul_diff with outcome."""
    rng = np.random.default_rng(seed)
    states = []
    for g in range(n_games):
        q = float(np.clip(0.5 + 0.25 * rng.standard_normal(), 0.05, 0.95))
        y = int(rng.random() < q)
        p0 = float(np.clip(q + 0.10 * rng.standard_normal(), 0.02, 0.98))
        for k in range(states_per_game):
            secs = 2880.0 * (1.0 - (k + 1) / (states_per_game + 1))
            frac = 1.0 - secs / 2880.0
            sigma = 0.20 * (secs / 2880.0) + 0.03
            p_live = float(np.clip(q + sigma * rng.standard_normal(), 0.02, 0.98))
            score_diff = (2 * y - 1) * frac * 12.0 + 4.0 * rng.standard_normal()
            foul_diff = (float((2 * y - 1) * 2.0 + 1.5 * rng.standard_normal())
                         if informative_foul else float(2.0 * rng.standard_normal()))
            states.append({
                "game_id": int(seed * 100000 + g),
                "seconds_remaining": secs,
                "frac_elapsed": frac,
                "score_diff": score_diff,
                "foul_diff": foul_diff,
                "home_fouls": max(0.0, rng.poisson(3)),
                "away_fouls": max(0.0, rng.poisson(3)),
                "p0": p0,
                "p_live": p_live,
                "outcome": y,
            })
    return states


def _m0(states: list) -> np.ndarray:
    from scripts.platformkit.eval_gate.ingame_blend import blended_predictions, fit_weight_surface
    return blended_predictions(states, fit_weight_surface(states, min_cell=20))


def _all_keys(obj) -> set:
    keys: set = set()
    if isinstance(obj, dict):
        keys.update(obj.keys())
        for v in obj.values():
            keys |= _all_keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            keys |= _all_keys(v)
    return keys


# ---------------------------------------------------------------------------
# Test 1: sparse bucket (<50 states) -> c=0
# ---------------------------------------------------------------------------
def test_sparse_bucket_gives_c0():
    """Buckets with < 50 states must yield c=0 (no overfit on tiny cells)."""
    states = _make_states(seed=1, n_games=10, states_per_game=3)
    m0 = np.array([s["p0"] for s in states], float)
    c_by, _ = fit_foul_correction(states, m0)
    for t in range(_N_TBUCKET):
        assert c_by[t] == 0.0, f"Sparse bucket {t} should yield c=0, got {c_by[t]}"


# ---------------------------------------------------------------------------
# Test 2: planted-null foul_diff (shuffled) -> c stays near 0
# ---------------------------------------------------------------------------
def test_planted_null_c_collapses():
    """Shuffled foul_diff must not give |c|>0 that improves Brier (planted-null)."""
    rng = np.random.default_rng(7)
    states = _make_states(seed=7, n_games=400, states_per_game=8)
    fd = np.array([s["foul_diff"] for s in states], float)
    rng.shuffle(fd)
    for i, s in enumerate(states):
        s["foul_diff"] = float(fd[i])
    c_by, _ = fit_foul_correction(states, _m0(states))
    assert sum(abs(v) for v in c_by.values()) < 0.5, (
        "Planted-null: total |c| should be near 0; grid-includes-0 design prevents overfit"
    )


# ---------------------------------------------------------------------------
# Test 3: zero-c correction is a strict no-op
# ---------------------------------------------------------------------------
def test_zero_c_is_noop():
    """With c=0 for all buckets, M1 must equal M0 exactly (logit+0 == identity)."""
    states = _make_states(seed=2, n_games=50)
    m0 = np.array([s["p0"] for s in states], float)
    m1 = apply_foul_correction(states, m0, {t: 0.0 for t in range(_N_TBUCKET)}, 2.5)
    np.testing.assert_allclose(m1, m0, atol=1e-9,
                               err_msg="c=0 everywhere must be a strict no-op (M1==M0)")


# ---------------------------------------------------------------------------
# Test 4: nonzero c changes predictions
# ---------------------------------------------------------------------------
def test_nonzero_c_changes_predictions():
    """With c=0.3 for all buckets, M1 must differ from M0 when foul_diff != 0."""
    states = _make_states(seed=3, n_games=50, informative_foul=True)
    m0 = np.array([s["p0"] for s in states], float)
    m1 = apply_foul_correction(states, m0, {t: 0.3 for t in range(_N_TBUCKET)}, 2.0)
    assert not np.allclose(m1, m0, atol=1e-9), "c!=0 should change predictions"
    assert np.all((m1 >= 0.0) & (m1 <= 1.0)), "M1 must be valid probabilities"


# ---------------------------------------------------------------------------
# Test 5: informative foul signal -> nontrivial_correction True in >= 1 direction
# ---------------------------------------------------------------------------
def test_informative_foul_nontrivial_correction():
    """With a correlated foul_diff, at least one direction must find nontrivial c."""
    states_a = _make_states(seed=42, n_games=1000, states_per_game=8, informative_foul=True)
    states_b = _make_states(seed=43, n_games=1000, states_per_game=8, informative_foul=True)
    result = run_gate(states_a, states_b)
    assert result.a_to_b.get("nontrivial_correction") or result.b_to_a.get("nontrivial_correction"), (
        "At least one direction must find nontrivial_correction on informative foul data"
    )
    assert result.verdict in ("SHIP", "PARTIAL", "REJECT")


# ---------------------------------------------------------------------------
# Test 6: planted-null (shuffled foul_diff) -> REJECT in both directions
# ---------------------------------------------------------------------------
def test_planted_null_rejects():
    """Shuffling foul_diff across both corpora must yield REJECT (no real signal)."""
    rng = np.random.default_rng(99)
    states_a = _make_states(seed=99, n_games=400, states_per_game=8)
    states_b = _make_states(seed=100, n_games=400, states_per_game=8)
    for states in (states_a, states_b):
        fd = np.array([s["foul_diff"] for s in states], float)
        rng.shuffle(fd)
        for i, s in enumerate(states):
            s["foul_diff"] = float(fd[i])
    result = run_gate(states_a, states_b)
    beats_a = result.a_to_b.get("foul_beats_m0", False)
    beats_b = result.b_to_a.get("foul_beats_m0", False)
    assert not beats_a and not beats_b, (
        f"Planted-null must not beat M0; A->B={beats_a}, B->A={beats_b}"
    )
    assert result.verdict == "REJECT", f"Planted-null must REJECT; got {result.verdict}"


# ---------------------------------------------------------------------------
# Test 7: decide() covers all branches
# ---------------------------------------------------------------------------
def test_decide_all_branches():
    assert decide({"foul_beats_m0": True}, {"foul_beats_m0": True}) == "SHIP"
    assert decide({"foul_beats_m0": True}, {"foul_beats_m0": False}) == "PARTIAL"
    assert decide({"foul_beats_m0": False}, {"foul_beats_m0": True}) == "PARTIAL"
    assert decide({"foul_beats_m0": False}, {"foul_beats_m0": False}) == "REJECT"
    assert decide({}, {}) == "REJECT"          # missing key treated as False
    assert decide({"foul_beats_m0": True}, {}) == "PARTIAL"


# ---------------------------------------------------------------------------
# Test 8: FoulVerdict.to_dict() keys + no forbidden $ fields
# ---------------------------------------------------------------------------
def test_verdict_dict_structure_and_no_dollar():
    """to_dict() must have required keys, mention CALIBRATION in vs_close, no $ fields."""
    states_a = _make_states(seed=20, n_games=200)
    states_b = _make_states(seed=21, n_games=200)
    d = run_gate(states_a, states_b).to_dict()
    required = {"verdict", "layer", "reference_model", "candidate_model",
                "design", "vs_close", "a_to_b", "b_to_a", "coverage", "caveats"}
    assert not (required - set(d.keys())), f"Missing keys: {required - set(d.keys())}"
    assert d["verdict"] in ("SHIP", "PARTIAL", "REJECT")
    assert "calibration" in d["vs_close"].lower(), (
        f"vs_close should mention calibration (no $): {d['vs_close']}"
    )
    found = _FORBIDDEN & _all_keys(d)
    assert not found, f"Forbidden $ fields in to_dict(): {found}"


# ---------------------------------------------------------------------------
# Test 9: outside-segment rows unchanged (c=0 in all buckets except bucket 3)
# ---------------------------------------------------------------------------
def test_outside_segment_rows_unchanged():
    """Rows whose time bucket has c=0 must be unchanged by apply_foul_correction."""
    states = _make_states(seed=4, n_games=60, states_per_game=8)
    m0 = np.array([s["p0"] for s in states], float)
    c_by = {t: (0.4 if t == 3 else 0.0) for t in range(_N_TBUCKET)}
    m1 = apply_foul_correction(states, m0, c_by, 2.0)
    fracs = np.array([s["frac_elapsed"] for s in states], float)
    outside = _tbucket(fracs) != 3
    np.testing.assert_allclose(m1[outside], m0[outside], atol=1e-9,
                               err_msg="Rows in c=0 buckets must not change")
    # Inside bucket 3 with nonzero foul_diff must differ
    inside = _tbucket(fracs) == 3
    fds = np.array([s["foul_diff"] for s in states], float)
    signal = inside & (np.abs(fds) > 0.01)
    if signal.any():
        assert not np.allclose(m1[signal], m0[signal], atol=1e-9)


# ---------------------------------------------------------------------------
# Test 10: cross_direction output has required keys + no $ fields
# ---------------------------------------------------------------------------
def test_cross_direction_keys_and_no_dollar():
    """cross_direction dict must have required numeric/bool keys; no forbidden $ fields."""
    states_a = _make_states(seed=30, n_games=150)
    states_b = _make_states(seed=31, n_games=150)
    result = cross_direction(states_a, states_b)
    assert isinstance(result, dict)
    required = {"n_train_states", "n_test_states", "n_test_games",
                "brier_m0", "brier_m1", "brier_delta",
                "foul_beats_m0", "nontrivial_correction",
                "c_by_bucket", "elapsed_breakdown"}
    assert not (required - set(result.keys())), (
        f"Missing keys: {required - set(result.keys())}"
    )
    found = _FORBIDDEN & _all_keys(result)
    assert not found, f"Forbidden $ fields in cross_direction: {found}"


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    fns = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {name}: {exc}")
    print(f"\n{passed}/{len(fns)} tests passed.")
    sys.exit(0 if passed == len(fns) else 1)
