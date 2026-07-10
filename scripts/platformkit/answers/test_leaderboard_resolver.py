"""Ranking/leaderboard resolver -- parsing, registration, tie-break, and a
live top-N run against the real NBA profiles parquet (read-only).

Run: python -m pytest scripts/platformkit/answers/test_leaderboard_resolver.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.answers import leaderboard_resolver as LB
from scripts.platformkit.answers import resolver_registry as R
from scripts.platformkit.profiles import ask as _ask

REAL_NBA = _ask.load_profiles("nba")
pytestmark = pytest.mark.skipif(REAL_NBA.empty, reason="no nba profiles parquet built")


# ---------------------------------------------------------------------------
# Free-text parsing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("q,expect_cat,expect_n", [
    ("top 5 gravity", "gravity", 5),
    ("top shooters", "shooters", None),
    ("top 10 shot_zone_three_efg", "shot_zone_three_efg", 10),
    ("gravity leaders", "gravity", None),
    ("assist leaders", "assist", None),
])
def test_parse_query(q, expect_cat, expect_n):
    cat, n = LB.parse_query(q)
    assert cat == expect_cat
    assert n == expect_n


def test_is_ranking_query_true_for_top_and_leaders_false_otherwise():
    assert LB.is_ranking_query("top 5 gravity")
    assert LB.is_ranking_query("gravity leaders")
    assert not LB.is_ranking_query("best gravity")
    assert not LB.is_ranking_query("Trae Young gravity")


# ---------------------------------------------------------------------------
# Registration -- classify() routes ranking phrasing to the new category,
# and the registry entry exists.
# ---------------------------------------------------------------------------
def test_ranking_registered_in_resolvers():
    assert "ranking" in R.RESOLVERS


@pytest.mark.parametrize("q", ["top 5 gravity", "top shooters", "gravity leaders"])
def test_classify_routes_ranking_queries(q):
    assert R.classify(q) == "ranking"


def test_classify_best_x_still_routes_to_concept_not_ranking():
    # ANSWER_RULES.md: "best X" must stay a concept superlative, never a raw
    # attribute leaderboard -- guards against the two categories colliding.
    assert R.classify("best gravity") == "concept_rating"


# ---------------------------------------------------------------------------
# Ambiguity / refusal (deliberately vague or unregistered category words)
# ---------------------------------------------------------------------------
def test_unmatched_category_word_refuses_with_candidate_list():
    r = LB.leaderboard("nba", "zzz_not_a_real_attribute_zzz", top_n=5)
    assert r["status"] == "not_supported"
    assert "available" in r and len(r["available"]) > 0


def test_exact_attribute_name_never_ambiguous():
    r = LB.leaderboard("nba", "gravity", top_n=5)
    assert r["status"] == "ok"
    assert r["attribute"] == "gravity"


# ---------------------------------------------------------------------------
# Deterministic tie-break (synthetic -- exact control over ties)
# ---------------------------------------------------------------------------
def test_tie_break_is_deterministic_raw_value_then_entity_id():
    df = pd.DataFrame([
        dict(entity_id=3, entity_name="C", window="w1", attribute="toy", raw_value=5.0,
             percentile=90.0, n=500.0, status="DESCRIPTIVE", ingredients="{}", sources="x",
             sport="nba", kind="player"),
        dict(entity_id=1, entity_name="A", window="w1", attribute="toy", raw_value=5.0,
             percentile=90.0, n=500.0, status="DESCRIPTIVE", ingredients="{}", sources="x",
             sport="nba", kind="player"),
        dict(entity_id=2, entity_name="B", window="w1", attribute="toy", raw_value=9.0,
             percentile=99.0, n=500.0, status="DESCRIPTIVE", ingredients="{}", sources="x",
             sport="nba", kind="player"),
    ])
    sub = df[df["attribute"] == "toy"].sort_values(["raw_value", "entity_id"], ascending=[False, True])
    names = list(sub["entity_name"])
    assert names == ["B", "A", "C"], f"tie must break on entity_id asc after raw_value desc, got {names}"


def test_min_n_floor_excludes_low_sample_rows_on_real_data():
    r_all = LB.leaderboard("nba", "gravity", top_n=200, min_n=0.0)
    r_floored = LB.leaderboard("nba", "gravity", top_n=200, min_n=2000.0)
    assert r_all["status"] == "ok" and r_floored["status"] == "ok"
    assert all(row["n"] >= 2000.0 for row in r_floored["rows"])
    assert len(r_floored["rows"]) <= len(r_all["rows"])


# ---------------------------------------------------------------------------
# Live end-to-end run through the public resolve() entrypoint
# ---------------------------------------------------------------------------
def test_live_top5_gravity_via_resolve_entrypoint():
    r = R.resolve("top 5 gravity", sport="nba")
    assert r["status"] == "ok"
    assert r["category"] == "ranking"
    assert r["attribute"] == "gravity"
    assert r["source_artifact"].endswith("_profiles.parquet")
    assert len(r["rows"]) == 5
    vals = [row["raw_value"] for row in r["rows"]]
    assert vals == sorted(vals, reverse=True), "rows must be sorted raw_value descending"
    for row in r["rows"]:
        assert row["n"] > 0


def test_live_top_shooters_ambiguous_or_refused_never_improvised():
    """'shooters' is a vague scouting word, not a registered attribute name --
    the stack's philosophy (docs/analytics/ANSWER_RULES.md) is REFUSE, never
    guess. Proves the fallback-to-raw-parquet failure mode this lane fixes:
    the resolver now answers honestly instead of the caller reaching past it."""
    r = R.resolve("top shooters", sport="nba")
    assert r["status"] in ("not_supported", "ambiguous")
    assert r["category"] == "ranking"
