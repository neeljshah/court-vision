"""Per-file regression test for domains.baseball_kbo.ingame_base_fit (LANE
kbo-quarantine, supersedes kbo-base-fit). Locks the QUARANTINED verdict: the
synthesis-leak rail disqualifies this fit via pure_noise_control, mirroring
the committed NPB treatment (4414086d) -- HONEST_NEGATIVE, no params persisted.

Per-file test (do NOT run the full suite -- see repo rails):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_kbo/test_ingame_base_fit.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.baseball_kbo.ingame_base_fit import (
    _allocate_innings,
    _fit_intercept,
    _PARAMS_OUT,
    _VERDICT_OUT,
    base_predict_c,
    fit_and_gate,
    main,
    pure_noise_control,
    synthesize_states,
    synthesize_states_pure_noise,
)
from domains.baseball_kbo.ratings import walk_forward_elo


def test_fit_and_gate_verdict_honest_negative_quarantined():
    """QUARANTINED: the real corpus is disqualified by pure_noise_control, so
    the verdict must be HONEST_NEGATIVE, not DONE (matches NPB's treatment)."""
    result = fit_and_gate()
    assert result.verdict == "HONEST_NEGATIVE"
    p = result.payload
    assert p["disqualified_by_noise_control"] is True
    assert p["pure_noise_control"]["control_passes_as_nondegenerate"] is True


def test_pure_noise_control_passes_as_nondegenerate():
    """DECISIVE PROOF: the identical fit+guard pipeline on a zero-signal noise
    corpus still reports non-degenerate/positive BSS -- proves the real-corpus
    result is a synthesis artifact, not in-game skill."""
    games = pd.DataFrame({
        "date": pd.to_datetime(["2024-04-01", "2024-04-02"] * 150),
        "season": [2024] * 300,
        "home_team": ["KIA", "LG"] * 150, "away_team": ["LG", "KIA"] * 150,
        "home_score": [5.0, 2.0] * 150, "away_score": [2.0, 5.0] * 150,
        "home_win": [1.0, 0.0] * 150, "tied": [False] * 300,
    })
    ctrl = pure_noise_control(games, min_eval_games=50)
    assert ctrl["control_passes_as_nondegenerate"] is True


def test_no_params_persisted_only_verdict_written():
    """QUARANTINE invariant: ingame_base_params.json must never be (re)written;
    only the honest verdict artifact is persisted."""
    result = main()
    assert result.verdict == "HONEST_NEGATIVE"
    assert _VERDICT_OUT.exists()
    import json
    with open(_VERDICT_OUT) as f:
        v = json.load(f)
    assert v["verdict"] == "HONEST_NEGATIVE"
    assert v["params_persisted"] is False


def test_optimizer_moved_off_init():
    """Grid search must not just return the (a,b,c) starting point."""
    result = fit_and_gate()
    p = result.payload
    assert p["moved_off_init"] is True
    assert (p["grid_final"]["a"], p["grid_final"]["b"], p["grid_final"]["c"]) != \
           (p["grid_start"]["a"], p["grid_start"]["b"], p["grid_start"]["c"])


def test_states_source_labeled_synthetic():
    """states_source must be explicit -- never silently pass off synthesis as a
    real tick corpus."""
    result = fit_and_gate()
    assert result.payload["states_source"] == "synthetic_from_final_score"
    assert "SYNTHESIZED" in result.payload["states_source_note"]


def test_synthesize_states_terminal_checkpoint_dropped_by_default():
    """frac_elapsed=1.0 (tautological) must not appear in fit/eval states."""
    games = pd.DataFrame({
        "date": pd.to_datetime(["2024-04-01"]),
        "season": [2024],
        "home_team": ["KIA"], "away_team": ["LG"],
        "home_score": [5.0], "away_score": [2.0],
        "home_win": [1.0], "tied": [False],
    })
    games_elo = walk_forward_elo(games)
    states = synthesize_states(games_elo)
    fracs = sorted(set(round(s["frac_elapsed"], 6) for s in states))
    assert max(fracs) < 1.0
    assert len(states) == 8  # 9 innings - 1 dropped terminal


def test_synthesize_states_ties_dropped():
    """A tied game (home_win NaN) contributes zero states."""
    games = pd.DataFrame({
        "date": pd.to_datetime(["2024-04-01"]),
        "season": [2024],
        "home_team": ["KIA"], "away_team": ["LG"],
        "home_score": [3.0], "away_score": [3.0],
        "home_win": [float("nan")], "tied": [True],
    })
    games_elo = walk_forward_elo(games)
    states = synthesize_states(games_elo)
    assert states == []


def test_allocate_innings_sums_to_total():
    rng = np.random.default_rng(42)
    for total in (0, 1, 5, 12):
        alloc = _allocate_innings(total, rng)
        assert alloc.sum() == total
        assert len(alloc) == 9


def test_fit_intercept_moves_for_biased_states():
    """A synthetic corpus with home always winning should pull c positive
    (away from the 0.0 init) rather than the optimizer sticking at init."""
    states = [{"state_diff": 0.0, "frac_elapsed": 0.5, "p0": 0.5, "outcome": 1}
              for _ in range(50)]
    c = _fit_intercept(states, (0.5, 0.5))
    assert c > 0.0


def test_base_predict_c_matches_manual_sigmoid():
    states = [{"state_diff": 2.0, "frac_elapsed": 0.5, "p0": 0.5, "outcome": 1}]
    abc = (0.5, 0.5, 0.1)
    pred = base_predict_c(states, abc)
    expected = 1.0 / (1.0 + np.exp(-((0.5 + 0.5 * 0.5) * 2.0 + 0.1)))
    assert abs(float(pred[0]) - expected) < 1e-9


