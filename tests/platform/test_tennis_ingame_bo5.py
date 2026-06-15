"""Per-file test for scripts/platformkit/proof_tennis/ingame_bo5.py.

Best-of-5 (Grand Slam) in-game coverage: richer realized set states (1-0, 2-0, 1-1, 2-1).
State = realized set-result role (NOT match outcome); label = match outcome; walk-forward Elo.
Structural asserts robust to corpus / data-limited states. Brier never MAE; no edge.

Run: python -m pytest tests/platform/test_tennis_ingame_bo5.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.proof_tennis import ingame_bo5 as mod


def test_brier_helper():
    assert mod._brier(np.array([0.5, 0.5]), np.array([1.0, 0.0])) == 0.25


def test_parse_sets_winner_ordered_and_rejects_junk():
    assert mod._parse_sets("6-3 6-1 6-4") == [(6, 3), (6, 1), (6, 4)]
    assert mod._parse_sets("6-7(5) 7-6(6) 6-1 6-2") == [(6, 7), (7, 6), (6, 1), (6, 2)]
    assert mod._parse_sets("6-3 RET") is None
    assert mod._parse_sets("W/O") is None
    assert mod._parse_sets("") is None
    assert mod._parse_sets(None) is None
    assert mod._parse_sets("4-2 4-1 4-3") is None  # short-set (NextGen) format excluded


def test_set_winner_deorder():
    # winner==1 (p1) won this set -> (wg,lg)=(6,3) -> p1 won it
    assert mod._set_winner_p1((6, 3), 1) == 1
    # winner==2 (p2) won the MATCH but this set token (6,3) is the SET winner's games:
    # if p2 is match winner, the set winner here is p2 unless... token is winner-ordered per set
    assert mod._set_winner_p1((6, 3), 2) == 0


def test_p_set_inversion_is_monotone_and_centered():
    assert abs(mod._p_set_from_match(0.5) - 0.5) < 0.02
    assert mod._p_set_from_match(0.8) > 0.5
    assert mod._p_set_from_match(0.2) < 0.5


def test_reprice_two_set_lead_sharper_than_one():
    # Bo5: a 2-0 lead at neutral per-set prob is closer to certainty than a 1-0 lead.
    p_10 = mod._reprice_leader(1, 0, 0.5)
    p_20 = mod._reprice_leader(2, 0, 0.5)
    p_21 = mod._reprice_leader(2, 1, 0.5)
    assert p_20 > p_10 > 0.5
    assert p_20 > p_21 > 0.5


def test_run_bo5_coverage_sharpens():
    rep = mod.run()
    if rep.get("status") != "ok":
        assert rep["status"] in ("no_data", "data_limited")
        return
    assert rep["format"] == "best_of_5"
    states = {s["state"]: s for s in rep["states"] if s.get("status") == "ok"}
    assert states, "expected at least one scored Bo5 set state"
    for name, s in states.items():
        # LEAK GUARD: leaders win most but NOT all -> base rate strictly < 1.0 (label is future).
        assert 0.45 < s["base_rate_leader_wins"] < 0.99, name
        # COMBINED (Elo prior + realized set state) sharpens the pregame prior.
        assert s["combined_beats_pregame"] is True, name
        assert s["combined_beats_score_only"] is True, name
        for k in ("brier_pregame_elo", "brier_score_only", "brier_combined"):
            assert 0.0 < s[k] < 0.5, (name, k)
    # the two-set lead (2-0) is the sharpest COMBINED forecast (most info -> lowest Brier).
    if "2-0 (after set 2)" in states and "1-0 (after set 1)" in states:
        assert states["2-0 (after set 2)"]["brier_combined"] < \
            states["1-0 (after set 1)"]["brier_combined"]
