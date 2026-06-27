"""Per-file, OFFLINE, deterministic unit test for the in-game CROSS-CORPUS gate.

Does NOT touch the real parquet. Builds TWO synthetic, independent corpora of in-game
states (different seeds = disjoint "seasons") and runs the true A->B / B->A replication:

  * BOTH informative: the pregame prior p0 truly predicts the winner in EACH corpus, and
    the edge is strongest EARLY (noisy live margin) -> cross_direction beats base both
    ways -> verdict REPLICATED.
  * ONE informative only: p0 is a real signal in corpus A but pure noise (0.5) in corpus
    B. Training on the informative corpus and testing on the noise corpus (and vice-versa)
    cannot beat base in BOTH directions -> verdict PARTIAL / NOT_REPLICATED (NOT replicated).

Also asserts: leak-freeness (the surface is fit on the TRAIN corpus only, the test corpus
is a disjoint season), and the Brier/DM wiring + no-$ discipline.

CLI: python -m pytest tests/platformkit/test_ingame_crossval_nba.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.ingame.ingame_crossval_nba import (
    cross_direction,
    decide,
    run_cross,
)
from scripts.platformkit.ingame.ingame_layer_gate_nba_io import (
    QSEC,
    p_live_from_margin,
)

_REG = 2880.0


def _make_corpus(n_games: int, informative: bool, seed: int, gid0: int = 0):
    """Flat list of leak-free as-of states for a synthetic season.

    Hidden 'strength' in (0,1) = P(home win). If informative, p0 = strength (real
    pregame signal) and EARLY margins are noisy so the prior carries info the live
    margin lacks; else p0 = 0.5 (noise). Outcome drawn from strength so favorites win.
    gid0 offsets game_ids so two corpora are guaranteed disjoint.
    """
    rng = np.random.default_rng(seed)
    states = []
    for g in range(n_games):
        gid = gid0 + g
        strength = float(rng.uniform(0.15, 0.85))
        y = int(rng.uniform() < strength)
        p0 = strength if informative else 0.5
        margin_final = float(rng.normal(8.0 if y else -8.0, 9.0))
        for q in (1, 2, 3):
            frac = 1.0 - QSEC[q] / _REG
            track = {1: 0.15, 2: 0.45, 3: 0.80}[q]
            noise = {1: 9.0, 2: 7.0, 3: 4.0}[q]
            diff = float(track * margin_final + rng.normal(0.0, noise))
            states.append({
                "game_id": gid, "period": q, "seconds_remaining": QSEC[q],
                "score_diff": diff, "p0": p0,
                "p_live": p_live_from_margin(diff, frac),
                "outcome": y, "margin_final": margin_final,
            })
    return states


def test_replicates_when_informative_in_both():
    a = _make_corpus(700, informative=True, seed=11, gid0=0)
    b = _make_corpus(700, informative=True, seed=22, gid0=100000)
    v = run_cross(a, b, require_quarter_pattern=True)
    assert v.verdict == "REPLICATED", (v.verdict, v.a_to_b, v.b_to_a)
    assert v.a_to_b["prior_beats_base"] and v.b_to_a["prior_beats_base"]
    assert v.a_to_b["brier_prior"] < v.a_to_b["brier_base"]
    assert v.b_to_a["brier_prior"] < v.b_to_a["brier_base"]
    assert v.a_to_b["dm_p"] < 0.05 and v.b_to_a["dm_p"] < 0.05
    # the per-quarter tell: prior helps most early, least late, in BOTH directions
    assert v.a_to_b["quarter_pattern_holds"] and v.b_to_a["quarter_pattern_holds"]


def test_not_replicated_when_informative_in_only_one():
    a = _make_corpus(700, informative=True, seed=33, gid0=0)
    b = _make_corpus(700, informative=False, seed=44, gid0=100000)
    v = run_cross(a, b, require_quarter_pattern=True)
    # Cannot beat base in BOTH directions -> NOT replicated (PARTIAL or NOT_REPLICATED).
    assert v.verdict in ("PARTIAL", "NOT_REPLICATED"), (v.verdict, v.a_to_b, v.b_to_a)
    assert v.verdict != "REPLICATED"


def test_decide_logic():
    beat = {"prior_beats_base": True, "quarter_pattern_holds": True}
    miss = {"prior_beats_base": False, "quarter_pattern_holds": False}
    assert decide(beat, beat) == "REPLICATED"
    assert decide(beat, miss) == "PARTIAL"
    assert decide(miss, miss) == "NOT_REPLICATED"
    # pattern required but absent in one direction -> downgrade to PARTIAL
    beat_no_pat = {"prior_beats_base": True, "quarter_pattern_holds": False}
    assert decide(beat, beat_no_pat, require_quarter_pattern=True) == "PARTIAL"
    assert decide(beat, beat_no_pat, require_quarter_pattern=False) == "REPLICATED"


def test_leak_free_disjoint_corpora_and_wiring():
    a = _make_corpus(120, informative=True, seed=5, gid0=0)
    b = _make_corpus(120, informative=True, seed=6, gid0=100000)
    a_ids = {s["game_id"] for s in a}
    b_ids = {s["game_id"] for s in b}
    assert a_ids.isdisjoint(b_ids), "corpora must be disjoint (no cross-season leak)"
    d = cross_direction(a, b)
    for k in ("brier_base", "brier_prior", "dm_p", "dm_stat",
              "n_train_states", "n_test_states", "prior_beats_base"):
        assert k in d
    v = run_cross(a, b)
    out = v.to_dict()
    assert out["vs_close"].startswith("UNPROVEN")
    assert "$" not in str(out)  # no dollar / edge field anywhere
