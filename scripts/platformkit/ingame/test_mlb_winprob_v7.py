"""Per-file test for scripts.platformkit.ingame.mlb_winprob_v7 (rung-7).

Exercises the pure logic (eval-X trajectory alignment, paired bootstrap verdicts)
without a full HGB train -- the full train+benchmark is the deliverable run itself.
"""
import numpy as np

import scripts.platformkit.ingame.mlb_winprob_v7 as v7
from domains.mlb.ingame_trajectory import per_game_trajectory


def _tick(gid, margin, inning=5):
    return {"game_id": gid, "score_margin": float(margin), "inning": float(inning),
            "half_bottom": 0.0, "outs": 1.0, "base_state": 0.0, "balls": 0.0,
            "strikes": 0.0, "frac_elapsed": 0.5, "outcome": 1.0,
            "old_model_prob": 0.5, "market_prob": 0.5, "bucket": "mid|close"}


def test_eval_x_shapes_and_trajectory_tail():
    ticks = [_tick("g1", 0), _tick("g1", 1), _tick("g1", -1), _tick("g2", 2)]
    X8, X11 = v7._eval_X(ticks)
    assert X8.shape == (4, 8) and X11.shape == (4, 11)
    margins = np.array([t["score_margin"] for t in ticks])
    gids = np.array([t["game_id"] for t in ticks])
    assert np.allclose(X11[:, 8:], per_game_trajectory(margins, gids, v7.WINDOW))
    # g2 starts fresh -> its lead_changes col is 0
    assert X11[3, 8] == 0.0


def test_eval_x_empty():
    X8, X11 = v7._eval_X([])
    assert X8.shape == (0, 8) and X11.shape == (0, 11)


def test_paired_bootstrap_identical_is_zero():
    y = np.array([1.0, 0.0, 1.0, 0.0])
    p = np.array([0.6, 0.4, 0.7, 0.3])
    gids = ["a", "a", "b", "b"]
    r = v7.paired_game_bootstrap(p, p, y, gids, n_boot=200)
    assert abs(r["delta_brier"]) < 1e-12
    assert r["verdict"] in ("MATCH", "INSUFFICIENT")


if __name__ == "__main__":
    for fn in [test_eval_x_shapes_and_trajectory_tail, test_eval_x_empty,
               test_paired_bootstrap_identical_is_zero]:
        fn()
    print("all mlb_winprob_v7 tests OK")
