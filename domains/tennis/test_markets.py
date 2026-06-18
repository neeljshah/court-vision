"""Per-file coherence tests for domains.tennis.markets.

Run ONLY this file (full pytest freezes the box):
    python -m pytest domains/tennis/test_markets.py -q

Asserts the market surface is internally COHERENT and consistent with the engine:
  * correct-set-score probs sum to 1
  * P(2 total sets) == P(straight sets)  (best-of-3)
  * set handicap -1.5 ~= straight-sets prob
  * total games O/U monotone (non-increasing OVER) in the line
  * match_winner == 1 - opponent; per-set prob in (0,1)
  * point-model gaps are listed, not faked
"""
from __future__ import annotations

import numpy as np

from domains.tennis.match_engine import serve_probs_from_winprob, markets_from_engine
from domains.tennis.markets import price_all, POINT_MODEL_GAPS

_N = 30_000
_SEED = 0


def _holds(target_p: float, best_of: int = 3):
    return serve_probs_from_winprob(target_p, best_of, n_sims=1500, seed=_SEED)


def _surface(target_p: float = 0.62, best_of: int = 3):
    ph1, ph2 = _holds(target_p, best_of)
    return price_all(ph1, ph2, best_of, n_sims=_N, seed=_SEED), ph1, ph2


def test_set_score_sums_to_one():
    mk, _, _ = _surface()
    total = sum(mk["set_score"].values())
    assert abs(total - 1.0) < 1e-9, f"set-score dist sums to {total}, expected 1.0"


def test_two_sets_equals_straight_sets():
    """best-of-3: P(match ends in 2 sets) == P(p1 straight) + P(p2 straight)."""
    mk, _, _ = _surface()
    ss = mk["straight_sets"]["p1"] + mk["straight_sets"]["p2"]
    p_two = mk["total_sets"]["under"]  # under 2.5 sets == exactly 2 sets played
    assert abs(p_two - ss) < 1e-9, f"P(2 sets)={p_two} != P(straight sets)={ss}"


def test_total_sets_over_under_complementary():
    mk, _, _ = _surface()
    assert abs(mk["total_sets"]["over"] + mk["total_sets"]["under"] - 1.0) < 1e-9


def test_set_handicap_minus15_is_straight_sets():
    """Set handicap -1.5 for p1 (win by >=2 sets) == p1 straight-sets win (bo3)."""
    mk, _, _ = _surface(target_p=0.70)
    hcap = {h["line"]: h["cover"] for h in mk["set_handicap"]}
    ss_p1 = mk["straight_sets"]["p1"]
    assert abs(hcap[-1.5] - ss_p1) < 0.02, f"set hcap -1.5={hcap[-1.5]} vs straight={ss_p1}"


def test_set_handicap_plus15_is_not_straight_loss():
    """+1.5 sets for p1 (lose by <2) == p1 does NOT lose in straight sets == 1 - ss_p2."""
    mk, _, _ = _surface(target_p=0.45)
    hcap = {h["line"]: h["cover"] for h in mk["set_handicap"]}
    assert abs(hcap[1.5] - (1.0 - mk["straight_sets"]["p2"])) < 0.02


def test_games_ou_monotone_in_line():
    """OVER prob must be non-increasing as the line rises (both empirical and normal)."""
    mk, _, _ = _surface()
    ou = mk["total_games"]["ou"]
    overs = [r["over"] for r in ou]
    overs_n = [r["over_normal"] for r in ou]
    for a, b in zip(overs, overs[1:]):
        assert b <= a + 1e-9, f"empirical OVER not monotone: {overs}"
    for a, b in zip(overs_n, overs_n[1:]):
        assert b <= a + 1e-9, f"normal OVER not monotone: {overs_n}"


def test_games_ou_over_under_complementary():
    mk, _, _ = _surface()
    for r in mk["total_games"]["ou"]:
        assert abs(r["over"] + r["under"] - 1.0) < 1e-9


def test_match_winner_complementary():
    mk, _, _ = _surface(target_p=0.62)
    assert abs(mk["match_winner"]["p1"] + mk["match_winner"]["p2"] - 1.0) < 1e-9


def test_per_set_winprob_in_unit_interval():
    mk, _, _ = _surface(target_p=0.62)
    p = mk["per_set_winner"]["p1"]
    assert 0.0 < p < 1.0
    assert abs(p + mk["per_set_winner"]["p2"] - 1.0) < 1e-9


def test_coherent_with_markets_from_engine():
    """price_all match-win / straight-sets agree with markets_from_engine at same holds/seed."""
    ph1, ph2 = _holds(0.62)
    mk = price_all(ph1, ph2, 3, n_sims=_N, seed=_SEED)
    eng = markets_from_engine(ph1, ph2, 3, seed=_SEED, n_sims=_N)
    assert abs(mk["match_winner"]["p1"] - eng["match_win_p1"]) < 0.02
    assert abs(mk["straight_sets"]["p1"] - eng["straight_sets_p1"]) < 0.02


def test_point_model_gaps_listed_not_faked():
    mk, _, _ = _surface()
    names = {g["market"] for g in mk["needs_point_model"]}
    assert "tie_break_yes_no" in names
    assert names == {g["market"] for g in POINT_MODEL_GAPS}
    # none of the gap markets are silently priced in the surface
    assert "tie_break" not in mk


def test_favorite_plays_fewer_total_sets_than_coinflip():
    """Sanity: a strong favorite ends in straight sets more often than a 50/50 match."""
    fav, _, _ = _surface(target_p=0.80)
    even, _, _ = _surface(target_p=0.50)
    fav_two = fav["total_sets"]["under"]
    even_two = even["total_sets"]["under"]
    assert fav_two > even_two
