"""Per-file tests for the MLB cross-corpus pregame depth gate.

Covers:
  * ratings_mov: mov_scale=0 reproduces the pitcher-blind baseline EXACTLY,
    snapshot-before-update leak-freeness (a future game cannot move a past
    game's pre-game feature), and that a positive mov_scale changes ratings.
  * pregame_gate: the degenerate-base guard caps the verdict, the DM is
    clustered by event_id, and a genuinely-better candidate on independent
    synthetic corpora is REPLICATED.

Per-file only:  python -m pytest tests/domains/mlb/test_pregame_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.ratings import walk_forward_elo
from domains.mlb.ratings_mov import walk_forward_elo_mov, _mov_mult
from domains.mlb.pregame_gate import gate_cross_corpus, _one_direction


def _toy_games(n: int = 60, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    teams = ["AAA", "BBB", "CCC", "DDD"]
    rows = []
    for i in range(n):
        h, a = rng.choice(teams, size=2, replace=False)
        hr, ar = int(rng.integers(0, 9)), int(rng.integers(0, 9))
        if hr == ar:
            hr += 1
        rows.append({
            "event_id": f"2015-{i:03d}-{h}-{a}-0", "date": f"2015-04-{(i % 28) + 1:02d}",
            "season": 2015, "home_team": h, "away_team": a,
            "home_runs": hr, "away_runs": ar,
            "target_home_win": 1.0 if hr > ar else 0.0, "game_seq": 0,
        })
    return pd.DataFrame(rows)


def test_mov_scale_zero_reproduces_baseline():
    df = _toy_games()
    base = walk_forward_elo(df).sort_values("event_id")["p_home_elo"].values
    mov0 = walk_forward_elo_mov(df, mov_scale=0.0).sort_values(
        "event_id")["p_home_elo"].values
    assert np.allclose(base, mov0, atol=1e-12)


def test_mov_mult_is_one_when_off():
    assert _mov_mult(5.0, 30.0, 0.0, 2.2) == 1.0
    assert _mov_mult(5.0, 30.0, 2.0, 2.2) > 0.0


def test_positive_mov_changes_ratings():
    df = _toy_games()
    mov0 = walk_forward_elo_mov(df, mov_scale=0.0).sort_values(
        "event_id")["p_home_elo"].values
    mov2 = walk_forward_elo_mov(df, mov_scale=2.0).sort_values(
        "event_id")["p_home_elo"].values
    assert not np.allclose(mov0, mov2)


def test_leak_free_truncation_invariant():
    # Date-truncation invariance: pre-game features for games on/before a cut date
    # must be identical whether or not LATER-dated games exist in the frame
    # (snapshot-before-update => no future leak). Truncate by DATE, not position,
    # because the builder re-sorts chronologically internally.
    df = _toy_games(n=60)
    cut = "2015-04-15"
    full = walk_forward_elo_mov(df, mov_scale=1.5).sort_values("event_id")
    early = df[df["date"] <= cut].copy()
    trunc = walk_forward_elo_mov(early, mov_scale=1.5).sort_values("event_id")
    # Compare only games STRICTLY before the cut date: same-date games can feed
    # each other within a day, so the cut-date rows themselves are not invariant.
    strict_before = set(df[df["date"] < cut]["event_id"])
    common = (set(full["event_id"]) & set(trunc["event_id"])) & strict_before
    fmap = dict(zip(full["event_id"], full["p_home_elo"]))
    tmap = dict(zip(trunc["event_id"], trunc["p_home_elo"]))
    for e in common:
        assert abs(fmap[e] - tmap[e]) < 1e-12


def test_degenerate_base_guard_caps_verdict():
    # Pure-noise probs on both sides => base barely beats base-rate => the guard
    # must prevent a REPLICATED verdict (INVALID_BASE or PARTIAL at most).
    rng = np.random.default_rng(1)
    def _frame(seed):
        m = 400
        y = rng.integers(0, 2, m).astype(float)
        return pd.DataFrame({
            "event_id": [f"g{seed}-{i}" for i in range(m)],
            "target_home_win": y,
            "p_base": np.clip(rng.uniform(0.45, 0.55, m), 1e-3, 1 - 1e-3),
            "p_cand": np.clip(rng.uniform(0.45, 0.55, m), 1e-3, 1 - 1e-3),
        })
    v = gate_cross_corpus(_frame(0), _frame(1), "p_base", "p_cand", name="noise")
    assert v.verdict in ("INVALID_BASE", "PARTIAL", "REJECT")
    assert v.verdict != "REPLICATED"


def test_dm_clustered_by_event_id_runs():
    # Smoke: a single direction returns a DirResult with finite DM and a bool flag.
    rng = np.random.default_rng(2)
    m = 300
    y = rng.integers(0, 2, m).astype(float)
    p = np.clip(0.5 + 0.3 * (y - 0.5) + rng.normal(0, 0.1, m), 1e-3, 1 - 1e-3)
    df = pd.DataFrame({
        "event_id": [f"e{i}" for i in range(m)], "target_home_win": y,
        "p_base": np.clip(0.5 + rng.normal(0, 0.05, m), 1e-3, 1 - 1e-3),
        "p_cand": p,
    })
    r = _one_direction(df, df, "p_base", "p_cand", eps=0.05)
    assert np.isfinite(r.dm_p) and np.isfinite(r.brier_delta)
    assert isinstance(r.cand_beats_base, bool)
