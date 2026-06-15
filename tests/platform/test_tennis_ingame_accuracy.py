"""Per-file test for scripts/platformkit/proof_tennis/ingame_accuracy.py.

ATP in-game (UNBLOCKED leak-free): the realized state is the set-1 leader ROLE (fixed by the
set result), the label is the match outcome. Structural asserts robust to corpus/data-limited
state. Forecaster quality; Brier never MAE; no edge.

Run: python -m pytest tests/platform/test_tennis_ingame_accuracy.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.proof_tennis import ingame_accuracy as mod


def test_brier_helper():
    assert mod._brier(np.array([0.5, 0.5]), np.array([1.0, 0.0])) == 0.25


def test_parse_sets_winner_ordered_and_rejects_junk():
    # winner-ordered tokens, tiebreak stripped, completed sets kept
    assert mod._parse_sets("6-3 6-1") == [(6, 3), (6, 1)]
    assert mod._parse_sets("6-7(5) 7-6(6) 6-1") == [(6, 7), (7, 6), (6, 1)]
    # retirements / walkovers / blanks / incomplete -> None (skipped, never leaked)
    assert mod._parse_sets("6-3 RET") is None
    assert mod._parse_sets("W/O") is None
    assert mod._parse_sets("") is None
    assert mod._parse_sets(None) is None
    assert mod._parse_sets("3-3") is None  # incomplete set


def test_p_set_inversion_is_monotone_and_centered():
    # neutral match prob -> ~0.5 per-set prob; favored -> >0.5
    assert abs(mod._p_set_from_match(0.5, 3) - 0.5) < 0.02
    assert mod._p_set_from_match(0.8, 3) > 0.5
    assert mod._p_set_from_match(0.2, 3) < 0.5


def test_run_ingame_is_sharper_than_static():
    rep = mod.run()
    if rep.get("status") != "ok":
        assert rep["status"] in ("no_data", "data_limited")
        return
    assert rep["n_after_set1"] >= 60
    # LEAK GUARD: set-1 leaders win most but NOT all matches — base rate strictly < 1.0 proves
    # the label is the genuine future outcome, not the winner-order leaked in.
    assert 0.55 < rep["base_rate_set1_leader_wins"] < 0.95
    # THE result (cross-sport pattern): COMBINED (pregame Elo prior + 1-0 set lead) is sharpest —
    # beats BOTH pregame-Elo-alone and score-only-conditional.
    assert rep["combined_beats_pregame"] is True
    assert rep["combined_beats_score_only"] is True
    assert rep["brier_combined"] < rep["brier_pregame_elo"]
    assert rep["brier_combined"] <= rep["brier_score_only"]
    # all Brier on a sane [0, 0.5] scale
    for k in ("brier_pregame_elo", "brier_score_only", "brier_combined"):
        assert 0.0 < rep[k] < 0.5
