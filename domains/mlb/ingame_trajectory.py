"""domains.mlb.ingame_trajectory -- leak-free within-game score-margin TRAJECTORY
features for the MLB in-game win-prob RUNG 7 (evolving-state conditioning).

The static state model (mlb_winprob_v2) sees only the CURRENT margin/inning; it is
blind to HOW the game arrived there. These three path-dependent features are pure,
causal functions of the ordered score-margin sequence up to (and including) the
current tick -- never a future row -- so they are computable IDENTICALLY on the
train/val pitch_states parquets (margin = state_diff, ordered by asof_idx) and on
the 2026 grade-corpus ticks (margin = home_score - away_score, in capture order),
with NO cross-corpus id bridge and NO external savant join. This is the ONE
evolving-state class derivable leak-free on both corpora:
  lead_changes : cumulative count of margin sign-flips so far (volatile game?)
  recent_swing : margin[now] - margin[now-window]  (signed recent scoring momentum)
  path_vol     : std of the margin path so far        (how bumpy the road was)

Truncation-invariant by construction: row i depends only on margins[0..i], so
truncating a game at i yields identical features. `window` is the ONLY knob (a
real cadence tuning param -- pitch-level tick density differs slightly between the
parquet and the live grade stream; default 40 ticks ~= 1.5 innings of pitches).

Per-file test: domains/mlb/test_ingame_trajectory.py
"""
from __future__ import annotations

import numpy as np

N_TRAJ_FEATS = 3
DEFAULT_WINDOW = 40


def trajectory_feats(margins: np.ndarray, window: int = DEFAULT_WINDOW) -> np.ndarray:
    """(N,) ordered score-margin path -> (N, 3) [lead_changes, recent_swing, path_vol],
    each row causal (uses margins[0..i] only). Empty in -> (0,3)."""
    m = np.asarray(margins, dtype=float).ravel()
    n = m.shape[0]
    if n == 0:
        return np.zeros((0, N_TRAJ_FEATS), dtype=float)
    # cumulative lead-change count: flip when the sign vs the last NONZERO margin flips
    lead = np.zeros(n, dtype=float)
    last_sign = 0
    cnt = 0
    for i in range(n):
        s = 0 if m[i] == 0 else (1 if m[i] > 0 else -1)
        if s != 0 and last_sign != 0 and s != last_sign:
            cnt += 1
        if s != 0:
            last_sign = s
        lead[i] = float(cnt)
    idx = np.arange(n)
    prev = np.maximum(idx - window, 0)
    recent_swing = m - m[prev]
    # expanding std of the path so far (population std; row 0 -> 0.0)
    csum = np.cumsum(m)
    csum2 = np.cumsum(m * m)
    k = idx + 1.0
    mean = csum / k
    var = np.maximum(csum2 / k - mean * mean, 0.0)
    path_vol = np.sqrt(var)
    return np.column_stack([lead, recent_swing, path_vol])


def per_game_trajectory(margins: np.ndarray, game_ids: np.ndarray,
                        window: int = DEFAULT_WINDOW) -> np.ndarray:
    """Row-aligned (N,3) trajectory features, computed independently WITHIN each game.
    Rows are assumed already grouped/ordered per game (parquet: sort by game_id,asof_idx;
    ticks: capture order). Contiguous-group scan -- no future leak across game bounds."""
    g = np.asarray([str(x) for x in game_ids])
    n = g.shape[0]
    out = np.zeros((n, N_TRAJ_FEATS), dtype=float)
    if n == 0:
        return out
    start = 0
    for i in range(1, n + 1):
        if i == n or g[i] != g[start]:
            out[start:i] = trajectory_feats(margins[start:i], window)
            start = i
    return out


if __name__ == "__main__":  # ponytail: one runnable self-check, no framework
    m = np.array([0, 1, 1, -1, -2, 0, 3], dtype=float)
    f = trajectory_feats(m, window=2)
    assert f.shape == (7, 3)
    # lead changes: +1 (idx0->1 sets +), flip to - at idx3, flip back to + at idx6 => 2
    assert f[-1, 0] == 2.0, f[-1, 0]
    # recent_swing at last idx (window=2): m[6]-m[4] = 3-(-2)=5
    assert f[-1, 1] == 5.0, f[-1, 1]
    assert f[0, 2] == 0.0 and f[-1, 2] > 0.0
    # per-game isolation: two games never bleed
    mg = np.array([0, 5, 0, -5], dtype=float)
    gg = np.array(["a", "a", "b", "b"])
    pf = per_game_trajectory(mg, gg, window=40)
    assert pf[2, 0] == 0.0 and pf[3, 0] == 0.0  # game b starts fresh, one team leads
    assert pf[1, 1] == 5.0 and pf[3, 1] == -5.0
    print("ingame_trajectory self-check OK")

__all__ = ["N_TRAJ_FEATS", "DEFAULT_WINDOW", "trajectory_feats", "per_game_trajectory"]
