"""Answer-quality harness: 20+ canonical scouting questions against the REAL
production profiles parquet (read-only). Reads data/cache/profiles/nba_*
directly; writes nothing outside tmp_path (only synthetic-data tests use
tmp_path, and even those never touch it -- everything here is in-memory).

Run: python -m pytest scripts/platformkit/answers/test_answer_quality_nba.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_nba.concepts.concept_registry import (
    CONCEPTS, STATUS_RANK, derive_weights, get_concept, list_concepts,
)
from domains.basketball_nba.profiles.attribute_registry import ATTRIBUTES
from scripts.platformkit.answers import contracts as C

REAL_PROFILES = C._load_df("nba")
pytestmark = pytest.mark.skipif(REAL_PROFILES.empty, reason="no nba profiles parquet built")


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------
def test_all_signal_attributes_exist_in_registry():
    missing = [(cname, s["attribute"]) for cname, c in CONCEPTS.items()
               for s in c["signals"] if s["attribute"] not in ATTRIBUTES]
    assert not missing, f"concept signals referencing unknown attributes: {missing}"


@pytest.mark.parametrize("cname", list_concepts())
def test_concept_has_required_fields(cname):
    c = get_concept(cname)
    for field in ("name", "description", "signals", "context_qualifiers", "failure_modes", "min_n"):
        assert field in c, f"{cname} missing '{field}'"
    assert c["signals"], f"{cname} has no signals"
    assert c["context_qualifiers"], f"{cname} has no context_qualifiers"
    assert c["failure_modes"], f"{cname} has no failure_modes"
    assert c["min_n"] > 0
    for s in c["signals"]:
        assert s.get("attribute") and s.get("direction") in ("higher_is_better", "lower_is_better")
        assert s.get("weight_basis"), f"{cname}:{s['attribute']} has no weight_basis rationale"


def test_unknown_concept_raises_keyerror():
    with pytest.raises(KeyError):
        get_concept("does_not_exist")


# ---------------------------------------------------------------------------
# derive_weights math
# ---------------------------------------------------------------------------
def test_derive_weights_normalizes_to_one():
    w = derive_weights(get_concept("gravity"), REAL_PROFILES)
    totals = w.groupby("entity_id")["norm_weight"].sum()
    assert (totals.round(6) == 1.0).all()


# ---------------------------------------------------------------------------
# Superlative: 8 canonical "best X" questions, one per concept, on real data
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cname", list_concepts())
def test_superlative_answerable_on_real_data(cname):
    result = C.answer_superlative(cname, top_n=5)
    assert result["top"], f"'best {cname}' produced zero ranked entities on real data"
    for entry in result["top"]:
        assert entry["n"] is not None and entry["n"] >= result["min_n"]
        assert entry["confidence"] in ("HIGH", "MEDIUM", "LOW")
        assert entry["ingredients"], "answer object missing ingredients"
        for attr, ing in entry["ingredients"].items():
            for field in ("raw_value", "percentile", "n", "status", "weight", "contribution"):
                assert field in ing, f"{cname}/{attr} ingredient missing '{field}'"
    assert len(result["runners_up"]) <= 2


def test_min_n_filter_excludes_low_n_entities():
    concept = {"name": "toy", "signals": [{"attribute": "toy_attr", "direction": "higher_is_better", "weight_basis": "x"}],
               "context_qualifiers": ["x"], "failure_modes": ["x"], "min_n": 100.0}
    df = pd.DataFrame([
        dict(entity_id=1, entity_name="High N", window="w1", attribute="toy_attr", raw_value=1.0,
             percentile=90.0, n=500.0, status="DESCRIPTIVE", ingredients="{}", sources="x", sport="nba", kind="player"),
        dict(entity_id=2, entity_name="Low N", window="w1", attribute="toy_attr", raw_value=2.0,
             percentile=99.0, n=10.0, status="DESCRIPTIVE", ingredients="{}", sources="x", sport="nba", kind="player"),
    ])
    weights = derive_weights(concept, df)
    filtered = C._apply_min_n(weights, concept, None)
    assert set(filtered["entity_id"]) == {1}


def _independent_primary_percentile(attribute: str) -> pd.Series:
    """entity_name -> latest-window percentile on ONE raw attribute, computed
    directly from the production parquet -- independent of contracts.py/
    derive_weights, used to sanity-check the composite is backed by real
    component strength, not manufactured from nothing."""
    g = REAL_PROFILES[REAL_PROFILES["attribute"] == attribute].sort_values("window").groupby("entity_id").tail(1)
    return g.set_index("entity_name")["percentile"]


def test_gravity_top5_backed_by_independent_primary_signal():
    """Every superlative top-5 name must independently show as an above-
    median (>=50th pct) performer on the concept's own primary raw signal --
    catches a composite that has drifted away from what it claims to measure,
    without over-fitting to an exact top-N intersection under multi-signal blending."""
    pct = _independent_primary_percentile("gravity")
    for entry in C.answer_superlative("gravity", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 50, (
            f"{entry['entity_name']} in gravity top-5 but raw gravity percentile "
            f"is only {pct.get(entry['entity_name'])}")


def test_rim_protection_top5_backed_by_independent_primary_signal():
    pct = _independent_primary_percentile("rim_pressure_def")
    for entry in C.answer_superlative("rim_protection", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 50, (
            f"{entry['entity_name']} in rim_protection top-5 but raw rim_pressure_def "
            f"percentile is only {pct.get(entry['entity_name'])}")


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def test_comparison_has_both_entities_ingredient_rows():
    r = C.answer_comparison("gravity", "Trae Young", "LaMelo Ball")
    attrs = {row["attribute"] for row in r["ingredient_table"]}
    assert "gravity" in attrs
    gravity_row = next(row for row in r["ingredient_table"] if row["attribute"] == "gravity")
    assert gravity_row["a"] is not None and gravity_row["b"] is not None
    assert r["entity_a"]["composite"] is not None and r["entity_b"]["composite"] is not None
    assert r["favored"] in (r["entity_a"]["name"], r["entity_b"]["name"])


def test_comparison_what_would_flip_it_uses_present_signal():
    r = C.answer_comparison("gravity", "Trae Young", "LaMelo Ball")
    flip = r["what_would_flip_it"]
    assert flip is not None
    attrs_for_trailer = {row["attribute"] for row in r["ingredient_table"]
                          if (row["a"] if flip["trailing_entity"] == r["entity_a"]["name"] else row["b"]) is not None}
    assert flip["signal"] in attrs_for_trailer
    assert flip["percentile_points_needed"] >= 0


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------
def test_explanation_decomposition_sums_to_composite():
    r = C.answer_explanation("rim_protection", "Mitchell Robinson")
    total = sum(row["contribution"] for row in r["decomposition"])
    assert abs(total - r["composite"]) < 0.05
    assert all({"attribute", "contribution", "percentile", "weight", "status", "n"} <= row.keys()
               for row in r["decomposition"])


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------
def test_fit_baseline_is_roster_average_not_fabricated():
    r = C.answer_fit("gravity", "Trae Young", ["LaMelo Ball"])
    solo = C.answer_superlative("gravity", top_n=600)
    by_name = {e["entity_name"]: e["composite"] for e in solo["top"] + solo["runners_up"]}
    # roster of one -> baseline should equal that one player's own composite
    melo = C.answer_comparison("gravity", "LaMelo Ball", "LaMelo Ball")  # self-compare to get composite cheaply
    assert r["team_need_baseline"] == melo["entity_a"]["composite"]
    assert "proxy for team need" in r["note"]
    assert r["delta"] == round(r["entity_composite"] - r["team_need_baseline"], 2)


# ---------------------------------------------------------------------------
# Confidence tier (synthetic, exact boundary control)
# ---------------------------------------------------------------------------
def _rows(n, status):
    return pd.DataFrame([dict(entity_id=1, attribute="gravity", n=n, status=status,
                               percentile=90.0, raw_value=1.0, norm_weight=1.0)])


def test_confidence_low_for_provisional():
    concept = get_concept("gravity")
    assert C._confidence_tier(_rows(concept["min_n"] * 10, "PROVISIONAL"), concept) == "LOW"


def test_confidence_low_below_floor():
    concept = get_concept("gravity")
    assert C._confidence_tier(_rows(concept["min_n"] - 1, "VALIDATED_CLAIM"), concept) == "LOW"


def test_confidence_high_when_well_sampled_validated():
    concept = get_concept("gravity")
    assert C._confidence_tier(_rows(concept["min_n"] * 3, "VALIDATED_CLAIM"), concept) == "HIGH"


def test_confidence_medium_otherwise():
    concept = get_concept("gravity")
    assert C._confidence_tier(_rows(concept["min_n"] * 1.2, "DESCRIPTIVE"), concept) == "MEDIUM"


# ---------------------------------------------------------------------------
# Free-text dispatch: 12 canonical scouting questions
# ---------------------------------------------------------------------------
QUESTIONS = [
    ("best gravity", "superlative"),
    ("who has the best rim_protection", "superlative"),
    ("best creation", "superlative"),
    ("best playmaking", "superlative"),
    ("best clutch", "superlative"),
    ("best motor", "superlative"),
    ("best spacing", "superlative"),
    ("best versatility", "superlative"),
    ("Trae Young vs LaMelo Ball on gravity", "comparison"),
    ("Mitchell Robinson vs Day'Ron Sharpe on rim_protection", "comparison"),
    ("why is LaMelo Ball good at gravity", "explanation"),
    ("why is Mitchell Robinson great at rim_protection", "explanation"),
]


@pytest.mark.parametrize("query,expected_type", QUESTIONS)
def test_canonical_question_dispatch(query, expected_type):
    result = C.answer_question(query)
    assert "error" not in result, f"'{query}' -> {result}"
    assert result["question_type"] == expected_type
    assert result.get("window")


def test_answer_question_unrecognized_concept_errors_cleanly():
    result = C.answer_question("best teleportation")
    assert "error" in result


# ---------------------------------------------------------------------------
# Scope guard: this module must never route toward forecasts
# ---------------------------------------------------------------------------
def test_module_does_not_import_forecast_engines():
    import inspect
    src = inspect.getsource(C)
    for forbidden in ("live_engine", "win_probability", "predict_matchup", "basketball_sim"):
        assert forbidden not in src, f"contracts.py must not reference {forbidden} (see ANSWER_RULES.md)"
