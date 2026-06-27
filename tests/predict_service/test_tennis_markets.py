"""Per-file test: predict_service.tennis_markets coherent-surface exposure.

ENGINE_COHERENCE_GAP lane. Asserts:
  * registry now lists the full coherent tennis surface (the new markets appear).
  * every served estimate has provenance + units + NO $ field + vs_close UNPROVEN.
  * the served numbers MATCH the underlying markets_for_matchup() MC matrix
    (coherence), and the engine invariants hold (set-score sums to 1; 2-sets ==
    straight; set-handicap -1.5 == straight-sets p1).
  * tie-break / within-set games are NOT served (honestly out of reach).
  * the verdict JSON writes to data/frontend/funnel/ (this lane's OWN file).

Degrades gracefully: when the tennis corpus is absent (fresh clone) the matrix
tests skip but the registry + shape + no-$ contract tests still run.

Run: python -m pytest tests/predict_service/test_tennis_markets.py -q
"""
from __future__ import annotations

import json
import os

from predict_service import registry
from predict_service.contracts import VS_CLOSE_UNPROVEN
from predict_service import tennis_markets as tm


# --------------------------------------------------------------------------- #
# registry: the new coherent markets appear in the served surface.
# --------------------------------------------------------------------------- #
def test_registry_lists_full_coherent_surface():
    markets = registry.capabilities("tennis")["markets"]
    for m in ("total_sets", "set_handicap", "correct_set_score", "set_score_dist",
              "game_handicap", "per_set_winner", "first_set_winner"):
        assert m in markets, "tennis registry missing coherent market %r" % m
    # moneyline + total_games stay too.
    assert "moneyline" in markets and "total_games" in markets


def test_registry_does_not_advertise_unpriceable_markets():
    """Tie-break / within-set games are out of reach (POINT_MODEL_GAPS) -> NOT served."""
    markets = registry.capabilities("tennis")["markets"]
    for banned in ("tie_break", "total_games_within_set", "game_handicap_within_set"):
        assert banned not in markets


def test_registry_note_no_dollar_edge():
    note = registry.capabilities("tennis").get("note", "").lower()
    for banned in ("$edge", "roi", "profit"):
        assert banned not in note


# --------------------------------------------------------------------------- #
# served estimate shape: provenance + units + NO $ + vs_close UNPROVEN.
# --------------------------------------------------------------------------- #
def _sample_surface():
    """A static markets_for_matchup-shaped surface for shape tests (no corpus needed)."""
    return {
        "match_winner": {"p1": 0.42, "p2": 0.58},
        "straight_sets": {"p1": 0.20, "p2": 0.30},
        "set_score": {"2-0": 0.20, "2-1": 0.22, "0-2": 0.30, "1-2": 0.28},
        "total_sets": {"mean": 2.5, "line": 2.5, "over": 0.50, "under": 0.50},
        "set_handicap": [{"side": "p1", "line": -1.5, "cover": 0.20},
                         {"side": "p1", "line": 1.5, "cover": 0.70}],
        "total_games": {"mean": 26.0, "sigma": 6.0,
                        "ou": [{"line": 22.5, "over": 0.65, "under": 0.35}]},
        "game_handicap": [{"side": "p1", "line": -2.5, "cover": 0.30}],
        "per_set_winner": {"p1": 0.43, "p2": 0.57, "note": "iid approx"},
    }


def test_estimates_have_provenance_units_no_dollar():
    ests = tm.estimates_from_surface(_sample_surface())
    assert ests, "no estimates produced from a valid surface"
    for e in ests:
        d = e.to_dict()
        # provenance present + names the MC matrix.
        assert d["provenance"]["model"] == "tennis_mc_matrix"
        assert d["provenance"]["phase"] == "pregame"
        # units: a probability in [0,1], NOT a $ amount.
        assert 0.0 <= d["prob"] <= 1.0
        # NO $ field anywhere on the served row.
        for k in d:
            assert "$" not in k and "dollar" not in k.lower()
        assert "edge" not in d and "ev" not in d


def test_served_markets_cover_requested_surface():
    ests = tm.estimates_from_surface(_sample_surface())
    types = {e.market_type for e in ests}
    for mt in ("moneyline", "total_sets", "set_handicap", "correct_set_score",
               "set_score_dist", "game_handicap", "per_set_winner",
               "first_set_winner", "total_games"):
        assert mt in types, "served estimates missing market_type %r" % mt


# --------------------------------------------------------------------------- #
# coherence: served numbers MATCH the underlying matrix + engine invariants.
# --------------------------------------------------------------------------- #
def test_coherence_check_passes_on_consistent_surface():
    surf = _sample_surface()
    ests = tm.estimates_from_surface(surf)
    coh = tm.coherence_check(surf, ests)
    assert coh["all_ok"] is True, "coherence failed: %r" % coh["checks"]
    # spell out the individual invariants the check enforces.
    assert coh["checks"]["moneyline_matches_matrix"]
    assert coh["checks"]["set_score_sums_to_one"]
    assert coh["checks"]["two_sets_eq_straight"]
    assert coh["checks"]["set_hcap_m15_eq_straight_p1"]


def test_coherence_catches_inconsistent_moneyline():
    """A served number that drifts from the matrix must FAIL the coherence check."""
    surf = _sample_surface()
    ests = tm.estimates_from_surface(surf)
    # corrupt one served cell so it no longer matches the matrix.
    for e in ests:
        if e.label == "moneyline_p1":
            e.prob = 0.99
    coh = tm.coherence_check(surf, ests)
    assert coh["all_ok"] is False
    assert coh["checks"]["moneyline_matches_matrix"] is False


# --------------------------------------------------------------------------- #
# end-to-end: real predictor (when corpus present) -> coherent + persisted.
# --------------------------------------------------------------------------- #
def test_build_and_write_verdict(tmp_path):
    verdict = tm.build_tennis_coherence(n_sims=3000, seed=0)
    assert verdict["sport"] == "tennis"
    assert verdict["edge_claimed"] is False
    assert verdict["real_money_enabled"] is False
    assert verdict["vs_close"] == VS_CLOSE_UNPROVEN
    # No $ FIELD / value anywhere (the canonical honest_note disclaimer text
    # legitimately says "no $ edge is claimed" -- exclude it, then assert clean).
    scrubbed = dict(verdict)
    scrubbed.pop("honest_note", None)
    blob = json.dumps(scrubbed).lower()
    assert "$" not in blob and "\"roi\"" not in blob and "dollar" not in blob

    if verdict["status"] == "ok":
        # real MC matrix: served estimates must be coherent with the matrix.
        assert verdict["coherence"]["all_ok"] is True, verdict["coherence"]["checks"]
        assert verdict["estimates"], "ok verdict with no estimates"
        for e in verdict["estimates"]:
            assert 0.0 <= e["prob"] <= 1.0
            assert e["provenance"]["model"] == "tennis_mc_matrix"

    # writes to THIS lane's own file under data/frontend/funnel/.
    path = tm.write_verdict(verdict, out_dir=str(tmp_path))
    assert os.path.basename(path) == "tennis_coherence.json"
    assert os.path.exists(path)
    reloaded = json.loads(open(path, encoding="ascii").read())
    assert reloaded["sport"] == "tennis"
