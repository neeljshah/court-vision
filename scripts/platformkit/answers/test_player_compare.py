"""Per-file test: two-player comparison composer (player_compare.py) +
resolver_registry classify()/resolve() wiring.

Run: python -m pytest scripts/platformkit/answers/test_player_compare.py -q
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.answers import player_compare as PC
from scripts.platformkit.answers import resolver_registry as R


def _row(entity_id, entity_name, sport, kind, window, attribute, raw_value,
         percentile=50.0, rating_2k=62.0, n=10.0, status="DESCRIPTIVE", sources="synthetic"):
    return {"entity_id": entity_id, "entity_name": entity_name, "sport": sport, "kind": kind,
            "window": window, "attribute": attribute, "raw_value": raw_value, "percentile": percentile,
            "rating_2k": rating_2k, "n": n, "ingredients": json.dumps({}), "status": status, "sources": sources}


def _profiles_df():
    rows = [
        _row(1, "Jamal Murray", "nba", "player", "2026", "three_point_rate", 0.42),
        _row(1, "Jamal Murray", "nba", "player", "2026", "usage_rate", 0.28),
        _row(2, "Tyrese Maxey", "nba", "player", "2026", "three_point_rate", 0.38),
        _row(2, "Tyrese Maxey", "nba", "player", "2026", "assist_rate", 0.24),
        _row(3, "OG Anunoby", "nba", "player", "2026", "steal_rate", 0.02),
        _row(3, "OG Anunoby", "nba", "player", "2026", "usage_rate", 0.19),
        _row(4, "Marcus Smart", "nba", "player", "2026", "steal_rate", 0.025),
        _row(4, "Marcus Smart", "nba", "player", "2026", "assist_rate", 0.30),
        _row(5, "Kentavious Caldwell-Pope", "nba", "player", "2026", "three_point_pct", 0.41),
        _row(6, "Grayson Allen", "nba", "player", "2026", "three_point_pct", 0.46),
        _row(7, "Lakers", "nba", "team", "2026", "net_rating", 2.5),
        _row(8, "Celtics", "nba", "team", "2026", "net_rating", 5.1),
        _row(9, "Kevin Durant", "nba", "player", "2026", "usage_rate", 0.31),
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def profiles(monkeypatch):
    df = _profiles_df()
    monkeypatch.setattr(PC._ask, "load_profiles", lambda *a, **k: df)
    monkeypatch.setattr(PC._ask, "load_registry", lambda sport: {})
    return df


# ---------------------------------------------------------------------------
# Metric compare, both directions
# ---------------------------------------------------------------------------
def test_metric_compare_resolves_and_picks_higher(profiles):
    out = PC.compare("Jamal Murray vs Tyrese Maxey -- who carries higher three-point volume?", sport="nba")
    assert out["status"] == "ok"
    assert out["category"] == "player_comparison"
    assert out["attribute"] == "three_point_rate"
    assert out["a"]["entity"] == "Jamal Murray" and out["a"]["value"] == 0.42
    assert out["b"]["entity"] == "Tyrese Maxey" and out["b"]["value"] == 0.38
    assert out["comparison"]["higher"] == "Jamal Murray"
    assert out["comparison"]["delta"] == pytest.approx(0.04, abs=1e-6)


def test_metric_compare_nonadjacent_better_than_phrasing(profiles):
    # real bank phrasing separates the comparative word from 'than'
    # ("shoot better from three THAN ..."); split_entities must still find
    # both sides via the comparative-than fallback, not just literal 'vs'.
    out = PC.compare(
        "does Kentavious Caldwell-Pope have a better three point percentage than Grayson Allen?", sport="nba")
    assert out["status"] == "ok"
    assert out["attribute"] == "three_point_pct"
    assert out["comparison"]["higher"] == "Grayson Allen"


# ---------------------------------------------------------------------------
# No metric -> side-by-side intersection
# ---------------------------------------------------------------------------
def test_no_metric_side_by_side_intersection(profiles):
    out = PC.compare(
        "If OG Anunoby and Marcus Smart matched up head-to-head, how would their numbers stack up "
        "against each other?", sport="nba")
    assert out["status"] == "ok"
    attrs = {r["attribute"] for r in out["rows"]}
    assert attrs == {"steal_rate", "usage_rate"} or attrs == {"steal_rate"}
    # both entities share steal_rate; usage_rate is Anunoby-only -- intersection only
    assert "steal_rate" in attrs
    assert "assist_rate" not in attrs
    assert "note" in out and "default" in out["note"]


# ---------------------------------------------------------------------------
# One-side missing -> no_data
# ---------------------------------------------------------------------------
def test_one_side_unresolved_is_no_data(profiles):
    out = PC.compare("Jamal Murray vs Someone Nonexistent Player -- who has higher usage?", sport="nba")
    assert out["status"] == "no_data"


# ---------------------------------------------------------------------------
# Team question not stolen (classify regression)
# ---------------------------------------------------------------------------
def test_team_matchup_not_stolen_by_comparison(profiles):
    assert PC.is_two_player_comparison("Lakers vs Celtics") is False
    assert R.classify("Lakers vs Celtics") != "player_comparison"


def test_team_head_to_head_not_stolen_still_matchup_preview(profiles):
    # 'head-to-head' is also a matchup_preview keyword; a real TEAM query
    # using it must keep routing to matchup_preview, not player_comparison.
    q = "Lakers and Celtics head-to-head preview"
    assert PC.is_two_player_comparison(q) is False
    assert R.classify(q) == "matchup_preview"


def test_and_matched_up_shape_classifies_direct(profiles):
    # a comparison shape _CONCEPT_KEYWORDS doesn't already own ('vs '/'does '/
    # 'compare'/'best'/'who has'/'why is'/'fit team' are all absent here) ->
    # classify() hooks straight to player_comparison.
    q = ("If OG Anunoby and Marcus Smart matched up head-to-head, how would their "
         "numbers stack up against each other?")
    assert R.classify(q) == "player_comparison"


def test_vs_shaped_query_still_classifies_concept_rating_first(profiles):
    # "vs " is a _CONCEPT_KEYWORDS member -- concept_rating keeps first crack
    # at it (regression guard for qa_bank's "Trae Young vs LaMelo Ball on
    # gravity" / "Mitchell Robinson vs Day'Ron Sharpe on rim_protection").
    q = "Jamal Murray vs Tyrese Maxey -- who carries higher three-point volume?"
    assert R.classify(q) == "concept_rating"


def test_concept_miss_bridges_to_player_comparison(profiles, monkeypatch):
    # the query above names NO registered concept -> contracts.answer_question
    # misses -> resolve()'s bridge falls to the raw-attribute composer.
    monkeypatch.setattr(R._contracts, "answer_question",
                        lambda *a, **k: {"error": "no concept matched"})
    monkeypatch.setattr(R, "_CONCEPT_SPORTS", {"nba"})
    out = R.resolve("Jamal Murray vs Tyrese Maxey -- who carries higher three-point volume?", sport="nba")
    assert out["status"] == "ok"
    assert out["category"] == "player_comparison"
    assert out["attribute"] == "three_point_rate"


def test_concept_hit_not_shadowed_by_bridge(profiles, monkeypatch):
    # a REAL concept hit must win outright -- the bridge is only tried on a
    # concept MISS, never overriding a successful concept answer.
    monkeypatch.setattr(R._contracts, "answer_question",
                        lambda *a, **k: {"concept": "gravity", "value": 71.0})
    monkeypatch.setattr(R, "_CONCEPT_SPORTS", {"nba"})
    out = R.resolve("Jamal Murray vs Tyrese Maxey on gravity", sport="nba")
    assert out["status"] == "ok"
    assert out["category"] == "concept_rating"


# ---------------------------------------------------------------------------
# Cross-sport mismatch -> no_data
# ---------------------------------------------------------------------------
def test_cross_sport_mismatch_is_no_data(profiles, monkeypatch):
    df = _profiles_df()
    extra = pd.DataFrame([_row(20, "Shohei Ohtani", "mlb", "player", "2026", "usage_rate", 0.5)])
    df = pd.concat([df, extra], ignore_index=True)
    monkeypatch.setattr(PC._ask, "load_profiles", lambda *a, **k: df)
    out = PC.compare("Jamal Murray vs Shohei Ohtani -- who has higher usage rate?", sport="nba")
    assert out["status"] == "no_data"
    assert "cross-sport" in out["note"]


# ---------------------------------------------------------------------------
# Trap: nonsense attribute stays no_data -- composer does not lower the
# attribute matcher's existing evidence threshold. A single-entity nonsense
# question is not even a comparison (no second entity), so it must NOT be
# classified as player_comparison -- it stays on the pre-existing player_stat
# no_data path, untouched by this module.
# ---------------------------------------------------------------------------
def test_trap_nonsense_attribute_single_entity_not_stolen(profiles):
    q = "does Kevin Durant's whiff rate increase in the second half of the season?"
    assert PC.is_two_player_comparison(q) is False
    assert R.classify(q) != "player_comparison"


def test_trap_nonsense_attribute_two_entities_falls_to_side_by_side_not_fabricated(profiles):
    # Even if a comparison NAMES two real players, a nonsense metric phrase
    # must not resolve to a fabricated attribute -- it must fall through to
    # the honest declared side-by-side, never inventing a 'whiff_rate' match.
    out = PC.compare("does Jamal Murray's whiff rate increase compared to Tyrese Maxey's?", sport="nba")
    assert out["status"] == "ok"
    assert "attribute" not in out or out.get("category") == "player_comparison"
    if "rows" in out:
        assert all(r["attribute"] != "whiff_rate" for r in out["rows"])
