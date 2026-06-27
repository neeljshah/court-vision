"""Per-file, OFFLINE, sport-agnostic test for the GENERIC in-game detail-layer gate.

Does NOT touch any real parquet. Builds TWO synthetic, independent corpora of as-of
states in the FROZEN schema {game_id, state_diff, frac_elapsed, p0, outcome} and runs
the true A->B / B->A cross-corpus replication, all on a GOAL-DIFF scale (leads are
+/-1..3, NOT basketball +/-10) to prove the BASE slope is FIT, not hardcoded:

  * BOTH informative: p0 truly predicts the winner in EACH corpus and helps MOST early
    (noisy live margin) -> +PRIOR beats BASE both ways -> REPLICATED.
  * NOISE prior (p0 constant 0.5): the surface fits w->0 (trust BASE) so +PRIOR can only
    MATCH BASE -> REJECT (graceful degrade).
  * ONE informative only -> cannot beat in BOTH directions -> PARTIAL / REJECT.

Also asserts: DM clusters by GAME not state (n_clusters == n_games), and the base slope
is fit (non-trivial, scale-appropriate) on the goal-diff corpus.

CLI: python -m pytest tests/platformkit/test_ingame_gate_generic.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame.ingame_gate_generic import (
    cross_direction,
    decide,
    fit_base,
    gate_cross,
    load_states,
)


def _make_corpus(n_games, informative, seed, gid0=0, n_ticks=8, scale=1.0):
    """Flat list of frozen-schema as-of states on an arbitrary lead SCALE.

    `scale` sets the lead unit (1.0 = goal-diff +/-1..3; 10.0 = point-diff). Hidden
    strength in (0,1) = P(ref win). If informative, p0 = strength (real pregame signal)
    and EARLY margins are noisy so p0 carries info the live margin lacks; else p0 = 0.5.
    gid0 offsets game_ids so two corpora are disjoint.
    """
    rng = np.random.default_rng(seed)
    states = []
    for g in range(n_games):
        gid = gid0 + g
        strength = float(rng.uniform(0.15, 0.85))
        y = int(rng.uniform() < strength)
        p0 = strength if informative else 0.5
        margin_final = float(rng.normal((1.0 if y else -1.0) * 0.9 * scale, 1.0 * scale))
        for t in range(n_ticks):
            frac = (t + 0.5) / n_ticks
            track = 0.1 + 0.85 * frac
            noise = (1.2 * scale) * (1.0 - 0.7 * frac)
            diff = float(track * margin_final + rng.normal(0.0, noise))
            states.append({
                "game_id": gid, "asof_idx": t, "state_diff": diff,
                "frac_elapsed": float(frac), "p0": p0, "outcome": y,
            })
    return states


def test_replicates_when_informative_in_both_goal_scale():
    a = _make_corpus(400, True, seed=11, gid0=0, scale=1.0)        # goal-diff scale
    b = _make_corpus(400, True, seed=22, gid0=100000, scale=1.0)
    v = gate_cross(a, b, sport="soccer")
    assert v.verdict == "REPLICATED", (v.verdict, v.a_to_b, v.b_to_a)
    assert v.a_to_b["prior_beats_base"] and v.b_to_a["prior_beats_base"]
    assert v.a_to_b["brier_prior"] < v.a_to_b["brier_base"]
    assert v.b_to_a["dm_p"] < 0.05 and v.a_to_b["dm_p"] < 0.05
    assert "$" not in str(v.to_dict())


def test_reject_when_p0_is_noise():
    a = _make_corpus(400, False, seed=33, gid0=0, scale=1.0)       # p0 == 0.5 noise
    b = _make_corpus(400, False, seed=44, gid0=100000, scale=1.0)
    v = gate_cross(a, b, sport="soccer")
    assert v.verdict == "REJECT", (v.verdict, v.a_to_b, v.b_to_a)
    # graceful degrade: noise prior cannot beat base -> +PRIOR ~ BASE
    assert v.a_to_b["brier_prior"] >= v.a_to_b["brier_base"] - 1e-6


def test_partial_or_reject_when_informative_in_only_one():
    a = _make_corpus(400, True, seed=5, gid0=0, scale=1.0)
    b = _make_corpus(400, False, seed=6, gid0=100000, scale=1.0)
    v = gate_cross(a, b, sport="mlb")
    assert v.verdict in ("PARTIAL", "REJECT"), (v.verdict, v.a_to_b, v.b_to_a)
    assert v.verdict != "REPLICATED"


def test_dm_clusters_by_game_not_state():
    a = _make_corpus(60, True, seed=7, gid0=0, n_ticks=10, scale=1.0)
    b = _make_corpus(60, True, seed=8, gid0=100000, n_ticks=10, scale=1.0)
    d = cross_direction(a, b)
    n_games_b = len({s["game_id"] for s in b})
    assert d["n_test_games"] == n_games_b, (d["n_test_games"], n_games_b)
    # many states per game -> clusters << states
    assert d["n_test_games"] < d["n_test_states"]


def test_base_slope_is_fit_not_hardcoded():
    # goal-diff scale (+/-1..3): a hardcoded basketball slope would mis-fit; fit recovers
    # a LARGE per-unit slope because one goal moves the prob a lot.
    goal = _make_corpus(300, True, seed=9, scale=1.0)
    pt = _make_corpus(300, True, seed=9, scale=10.0)    # 10x lead units
    a_goal, b_goal = fit_base(goal)
    a_pt, b_pt = fit_base(pt)
    # the per-unit slope must SHRINK by roughly the scale factor (fit, not constant)
    assert a_goal > a_pt, (a_goal, a_pt)
    assert a_goal > 0.0 and a_pt > 0.0
    # the goal-scale slope is far larger than any basketball ~0.06 constant
    assert a_goal > 0.2


def test_load_states_validates_schema(tmp_path):
    import pandas as pd
    good = pd.DataFrame({
        "sport": ["x"] * 3, "game_id": [1, 1, 2], "asof_idx": [0, 1, 0],
        "state_diff": [1.0, -2.0, 0.5], "frac_elapsed": [0.1, 0.5, 0.2],
        "p0": [0.6, 0.6, 0.4], "outcome": [1, 1, 0],
    })
    p = tmp_path / "x_states__a.parquet"
    good.to_parquet(p)
    rows = load_states(str(p))
    assert len(rows) == 3 and rows[0]["game_id"] == 1
    bad = good.copy(); bad.loc[0, "frac_elapsed"] = 1.5
    pb = tmp_path / "x_states__bad.parquet"
    bad.to_parquet(pb)
    try:
        load_states(str(pb))
        assert False, "expected ValueError on out-of-range frac_elapsed"
    except ValueError:
        pass


def test_decide_logic():
    beat = {"prior_beats_base": True}
    miss = {"prior_beats_base": False}
    assert decide(beat, beat) == "REPLICATED"
    assert decide(beat, miss) == "PARTIAL"
    assert decide(miss, miss) == "REJECT"


def test_decide_degenerate_base_never_replicated():
    # HONESTY GUARD: a degenerate BASE in either direction caps the verdict below
    # REPLICATED -- even if prior_beats_base were (wrongly) True there. A genuine
    # beat in the OTHER (non-degenerate) direction yields PARTIAL; otherwise INVALID.
    degen = {"prior_beats_base": False, "base_degenerate": True}
    good = {"prior_beats_base": True, "base_degenerate": False}
    miss = {"prior_beats_base": False, "base_degenerate": False}
    assert decide(degen, degen) == "INVALID_BASE"
    assert decide(degen, good) == "PARTIAL"
    assert decide(good, degen) == "PARTIAL"
    assert decide(degen, miss) == "INVALID_BASE"
    # a degenerate base must NEVER produce REPLICATED, even if both flags were set
    assert decide({"prior_beats_base": True, "base_degenerate": True},
                  {"prior_beats_base": True, "base_degenerate": True}) != "REPLICATED"


def _make_degenerate_corpus(n_games, seed, gid0=0, n_ticks=8):
    """Frozen-schema states where state_diff carries NO signal about the outcome but
    p0 is INFORMATIVE -- a vacuous in-game BASE with a real pregame prior.

    margins are pure noise (independent of y); outcome is driven only by hidden
    strength, which p0 reveals. So the (state,time) BASE fits a ~zero slope (Brier
    ~ base-rate) while +PRIOR trivially beats the coin-flip BASE. The guard must
    label this INVALID_BASE, NEVER REPLICATED.
    """
    rng = np.random.default_rng(seed)
    states = []
    for g in range(n_games):
        gid = gid0 + g
        strength = float(rng.uniform(0.15, 0.85))
        y = int(rng.uniform() < strength)
        p0 = strength                       # informative pregame prior
        for t in range(n_ticks):
            frac = (t + 0.5) / n_ticks
            diff = float(rng.normal(0.0, 1.0))   # signal-free margin
            states.append({
                "game_id": gid, "asof_idx": t, "state_diff": diff,
                "frac_elapsed": float(frac), "p0": p0, "outcome": y,
            })
    return states


def test_degenerate_base_yields_invalid_base_not_replicated():
    a = _make_degenerate_corpus(400, seed=101, gid0=0)
    b = _make_degenerate_corpus(400, seed=202, gid0=100000)
    v = gate_cross(a, b, sport="tennis")
    # base carries no in-game signal -> degenerate in both directions
    assert v.a_to_b["base_degenerate"] and v.b_to_a["base_degenerate"], (
        v.a_to_b.get("base_check"), v.b_to_a.get("base_check"))
    # even though an informative p0 beats the coin-flip base, this is NOT a beat
    assert v.a_to_b["prior_beats_base"] is False
    assert v.b_to_a["prior_beats_base"] is False
    assert v.verdict == "INVALID_BASE", (v.verdict, v.a_to_b, v.b_to_a)
    assert v.verdict != "REPLICATED"
    # the base-vs-baserate check is surfaced for honesty
    assert "base_bss_vs_baserate" in v.a_to_b["base_check"]
