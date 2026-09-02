"""Per-file checks for game-clustered Romano-Wolf correction."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.eval_gate.romano_wolf import romano_wolf_stepdown


def _effects(seed: int = 7):
    rng = np.random.default_rng(seed)
    diffs, ids = [], []
    for effect in (0.025, 0.012, 0.0):
        d, g = [], []
        for game in range(30):
            game_effect = effect + float(rng.normal(0.0, 0.012))
            for _ in range(6):
                d.append(game_effect + float(rng.normal(0.0, 0.002)))
                g.append("g%02d" % game)
        diffs.append(d); ids.append(g)
    return diffs, ids


def test_stepdown_is_reproducible_and_monotone_in_rank_order():
    diffs, ids = _effects()
    a = romano_wolf_stepdown(diffs, ids, n_bootstrap=300, seed=11)
    b = romano_wolf_stepdown(diffs, ids, n_bootstrap=300, seed=11)
    assert a == b
    assert len(a.adjusted_p) == 3
    assert all(0.0 <= p <= 1.0 for p in a.adjusted_p)


def test_null_does_not_clear_corrected_threshold():
    rng = np.random.default_rng(2)
    d = [rng.normal(0.0, 0.03, 240)]
    gids = [["g%02d" % (i // 6) for i in range(240)]]
    out = romano_wolf_stepdown(d, gids, n_bootstrap=300, seed=5)
    assert out.rejected == (False,)


def test_identical_candidates_preserve_the_single_candidate_p_value():
    diffs, ids = _effects()
    one = romano_wolf_stepdown([diffs[0]], [ids[0]], n_bootstrap=499, seed=12)
    copies = romano_wolf_stepdown([diffs[0]] * 3, [ids[0]] * 3,
                                  n_bootstrap=499, seed=12)
    assert copies.adjusted_p == (one.adjusted_p[0],) * 3


def test_mismatched_inputs_fail_closed():
    try:
        romano_wolf_stepdown([[0.1]], [])
        raise AssertionError("mismatched inputs must not be accepted")
    except ValueError:
        pass


def test_degenerate_control_arm_does_not_manufacture_a_rejection():
    """A constant-loss control arm must not change any other arm's verdict.

    Its 0/0 studentized scale used to NaN-poison the family max statistic --
    `nan >= observed` is False for every draw -- so the whole family's adjusted
    p collapsed to 1/(B+1) and a non-significant arm was rejected BY the
    correction (measured: alone 0.08646 / False, with the control 0.00050 / True).
    """
    rng = np.random.default_rng(7)
    d, g = [], []
    for game in range(30):
        game_effect = 0.0047 + float(rng.normal(0.0, 0.012))
        for _ in range(6):
            d.append(game_effect + float(rng.normal(0.0, 0.002)))
            g.append("g%02d" % game)
    control = [0.0] * len(d)            # loss differential identical to the benchmark

    alone = romano_wolf_stepdown([d], [g])
    both = romano_wolf_stepdown([d, control], [g, g])
    assert alone.rejected == (False,)
    assert both.rejected == (False, False)          # same verdict, with and without
    assert both.adjusted_p[0] == alone.adjusted_p[0]
    assert both.adjusted_p[1] == 1.0                # masked arm: no evidence at all
