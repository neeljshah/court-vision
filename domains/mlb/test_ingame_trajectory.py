"""Per-file test for domains.mlb.ingame_trajectory (rung-7 evolving-state features)."""
import numpy as np

from domains.mlb.ingame_trajectory import per_game_trajectory, trajectory_feats


def test_empty():
    assert trajectory_feats(np.zeros(0)).shape == (0, 3)
    assert per_game_trajectory(np.zeros(0), np.array([])).shape == (0, 3)


def test_causal_and_lead_changes():
    m = np.array([0, 1, 1, -1, -2, 0, 3], dtype=float)
    f = trajectory_feats(m, window=2)
    # 2 sign flips: +->- at idx3, -->+ at idx6
    assert f[-1, 0] == 2.0
    # recent_swing window=2: m[6]-m[4] = 5
    assert f[-1, 1] == 5.0
    # path_vol expands and row0 is 0
    assert f[0, 2] == 0.0 and f[-1, 2] > 0.0


def test_truncation_invariant():
    m = np.array([0, 1, 2, 1, -1, -3, 0, 2], dtype=float)
    full = trajectory_feats(m, window=3)
    trunc = trajectory_feats(m[:5], window=3)
    # features for the first 5 rows must be identical whether or not future rows exist
    assert np.allclose(full[:5], trunc)


def test_per_game_isolation():
    m = np.array([0, 5, 3, 0, -5], dtype=float)
    g = np.array(["a", "a", "a", "b", "b"])
    pf = per_game_trajectory(m, g, window=40)
    # game b never inherits game a's lead-change count or margin
    assert pf[3, 0] == 0.0 and pf[4, 0] == 0.0
    assert pf[3, 1] == 0.0 and pf[4, 1] == -5.0


if __name__ == "__main__":
    for fn in [test_empty, test_causal_and_lead_changes, test_truncation_invariant,
               test_per_game_isolation]:
        fn()
    print("all ingame_trajectory tests OK")
