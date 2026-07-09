"""Answer-quality harness: 20+ canonical scouting questions against the REAL
production profiles parquet (read-only). Reads data/cache/profiles/mlb_*
directly; writes nothing outside tmp_path (only synthetic-data tests use
tmp_path, and even those never touch it -- everything here is in-memory).

Mirrors scripts/platformkit/answers/test_answer_quality_nba.py's structure;
see that file's header for the harness's general rationale.

Run: python -m pytest scripts/platformkit/answers/test_answer_quality_mlb.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.mlb.concepts.concept_registry import (
    CONCEPTS, STATUS_RANK, derive_weights, get_concept, list_concepts,
)
from domains.mlb.profiles.attribute_registry import ATTRIBUTES
from scripts.platformkit.answers import contracts as C

REAL_PROFILES = C._load_df("mlb")
pytestmark = pytest.mark.skipif(REAL_PROFILES.empty, reason="no mlb profiles parquet built")


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
    w = derive_weights(get_concept("stuff"), REAL_PROFILES)
    totals = w.groupby("entity_id")["norm_weight"].sum()
    assert (totals.round(6) == 1.0).all()


# ---------------------------------------------------------------------------
# Superlative: 6 canonical "best X" questions, one per concept, on real data
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cname", list_concepts())
def test_superlative_answerable_on_real_data(cname):
    result = C.answer_superlative(cname, sport="mlb", top_n=5)
    assert result["top"], f"'best {cname}' produced zero ranked entities on real data"
    for entry in result["top"]:
        assert entry["n"] is not None and entry["n"] >= result["min_n"]
        assert entry["confidence"] in ("HIGH", "MEDIUM", "LOW")
        assert entry["ingredients"], "answer object missing ingredients"
        for attr, ing in entry["ingredients"].items():
            for field in ("raw_value", "percentile", "n", "status", "weight", "contribution"):
                assert field in ing, f"{cname}/{attr} ingredient missing '{field}'"
    assert len(result["runners_up"]) <= 2


# ---------------------------------------------------------------------------
# Role scoping: pitcher concepts never surface a pure batter and vice versa
# ---------------------------------------------------------------------------
def _batter_only_ids() -> set:
    """entity_ids with a batter-only attribute (BB_rate) but no pitcher-only
    attribute (velo_band) -- excludes Ohtani, the one genuine two-way player."""
    batters = set(REAL_PROFILES[REAL_PROFILES["attribute"] == "BB_rate"]["entity_id"])
    pitchers = set(REAL_PROFILES[REAL_PROFILES["attribute"] == "velo_band"]["entity_id"])
    return batters - pitchers


def _pitcher_only_ids() -> set:
    batters = set(REAL_PROFILES[REAL_PROFILES["attribute"] == "BB_rate"]["entity_id"])
    pitchers = set(REAL_PROFILES[REAL_PROFILES["attribute"] == "velo_band"]["entity_id"])
    return pitchers - batters


@pytest.mark.parametrize("cname", ["stuff", "command", "contact_control"])
def test_pitcher_concept_never_returns_a_pure_batter(cname):
    pure_batters = _batter_only_ids()
    result = C.answer_superlative(cname, sport="mlb", top_n=20)
    hits = {e["entity_id"] for e in result["top"] + result["runners_up"]}
    assert not (hits & pure_batters), f"{cname} surfaced pure batter(s): {hits & pure_batters}"


@pytest.mark.parametrize("cname", ["discipline", "power", "clutch"])
def test_batter_concept_never_returns_a_pure_pitcher(cname):
    pure_pitchers = _pitcher_only_ids()
    result = C.answer_superlative(cname, sport="mlb", top_n=20)
    hits = {e["entity_id"] for e in result["top"] + result["runners_up"]}
    assert not (hits & pure_pitchers), f"{cname} surfaced pure pitcher(s): {hits & pure_pitchers}"


# ---------------------------------------------------------------------------
# Independent-signal + known-elite regression checks
# ---------------------------------------------------------------------------
def _independent_primary_percentile(attribute: str) -> pd.Series:
    """entity_name -> latest-window percentile on ONE raw attribute, computed
    directly from the production parquet -- independent of contracts.py/
    derive_weights, used to sanity-check the composite is backed by real
    component strength, not manufactured from nothing."""
    g = REAL_PROFILES[REAL_PROFILES["attribute"] == attribute].sort_values("window").groupby("entity_id").tail(1)
    return g.set_index("entity_name")["percentile"]


def test_stuff_top5_backed_by_independent_primary_signal():
    """Every superlative top-5 name must independently show as an above-
    median (>=50th pct) performer on the concept's own primary raw signal --
    catches a composite that has drifted away from what it claims to measure."""
    pct = _independent_primary_percentile("whiff_rate")
    for entry in C.answer_superlative("stuff", sport="mlb", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 50, (
            f"{entry['entity_name']} in stuff top-5 but raw whiff_rate percentile "
            f"is only {pct.get(entry['entity_name'])}")


def test_stuff_top5_contains_known_elite_arms():
    """The live top-5 must contain >=2 names from the whiff_rate top-10
    (computed here from the parquet, not hardcoded) -- regression guard on
    the primary signal actually driving the composite."""
    g = REAL_PROFILES[REAL_PROFILES["attribute"] == "whiff_rate"].sort_values("window").groupby("entity_id").tail(1)
    floor = get_concept("stuff")["min_n"]
    top10 = set(g[g["n"] >= floor].sort_values("percentile", ascending=False).head(10)["entity_name"])
    top5 = {e["entity_name"] for e in C.answer_superlative("stuff", sport="mlb", top_n=5)["top"]}
    assert len(top5 & top10) >= 2, f"top5 {top5} shares <2 names with whiff_rate top10 {top10}"


def test_directional_lower_xwoba_wins_contact_control():
    """Synthetic: A allows LOWER xwOBA than B -> since MLB percentiles are
    plain rank (not builder-oriented), A's raw xwoba_against_by_class_fastball
    percentile is LOWER than B's -- the concept must still rank A ahead via
    its lower_is_better flag. Fails if contracts ever treats an unoriented
    MLB percentile as if it were pre-oriented like NBA's zone_def_* columns."""
    concept = get_concept("contact_control")
    rows = []
    for eid, name, raw, pct in ((1, "Good Contact Suppression", 0.25, 10.0),
                                 (2, "Bad Contact Suppression", 0.45, 90.0)):
        for s in concept["signals"]:
            is_target = s["attribute"] == "xwoba_against_by_class_fastball"
            rows.append(dict(entity_id=eid, entity_name=name, window="w1", attribute=s["attribute"],
                             raw_value=raw if is_target else 0.30,
                             percentile=pct if is_target else 50.0,
                             n=2000.0, status="DESCRIPTIVE",
                             ingredients="{}", sources="x", sport="mlb", kind="player"))
    weights = derive_weights(concept, pd.DataFrame(rows))
    comp, _ = C._entity_composite(weights)
    scores = comp.set_index("entity_name")["composite"]
    assert scores["Good Contact Suppression"] > scores["Bad Contact Suppression"], (
        f"lower-xwOBA-allowed pitcher must outrank: {scores.to_dict()}")


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def test_comparison_has_both_entities_ingredient_rows():
    r = C.answer_comparison("power", "Aaron Judge", "Shohei Ohtani", sport="mlb")
    attrs = {row["attribute"] for row in r["ingredient_table"]}
    assert "contact_quality" in attrs
    row = next(row for row in r["ingredient_table"] if row["attribute"] == "contact_quality")
    assert row["a"] is not None and row["b"] is not None
    assert r["entity_a"]["composite"] is not None and r["entity_b"]["composite"] is not None
    assert r["favored"] in (r["entity_a"]["name"], r["entity_b"]["name"])


def test_comparison_what_would_flip_it_uses_present_signal():
    r = C.answer_comparison("power", "Aaron Judge", "Shohei Ohtani", sport="mlb")
    flip = r["what_would_flip_it"]
    if flip is None:
        return  # tied composites -- nothing to flip
    attrs_for_trailer = {row["attribute"] for row in r["ingredient_table"]
                          if (row["a"] if flip["trailing_entity"] == r["entity_a"]["name"] else row["b"]) is not None}
    assert flip["signal"] in attrs_for_trailer
    assert flip["percentile_points_needed"] >= 0


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------
def test_explanation_decomposition_sums_to_composite():
    r = C.answer_explanation("discipline", "Juan Soto", sport="mlb")
    total = sum(row["contribution"] for row in r["decomposition"])
    assert abs(total - r["composite"]) < 0.05
    assert all({"attribute", "contribution", "percentile", "weight", "status", "n"} <= row.keys()
               for row in r["decomposition"])


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------
def test_fit_baseline_is_roster_average_not_fabricated():
    r = C.answer_fit("power", "Aaron Judge", ["Shohei Ohtani"], sport="mlb")
    solo = C.answer_comparison("power", "Shohei Ohtani", "Shohei Ohtani", sport="mlb")  # self-compare for cheap composite
    assert r["team_need_baseline"] == solo["entity_a"]["composite"]
    assert "proxy for team need" in r["note"]
    assert r["delta"] == round(r["entity_composite"] - r["team_need_baseline"], 2)


# ---------------------------------------------------------------------------
# Free-text dispatch: 12 canonical scouting questions
# ---------------------------------------------------------------------------
QUESTIONS = [
    ("best stuff", "superlative"),
    ("who has the best command", "superlative"),
    ("best discipline", "superlative"),
    ("best power", "superlative"),
    ("best clutch", "superlative"),
    ("best contact_control", "superlative"),
    ("Aaron Judge vs Shohei Ohtani on power", "comparison"),
    ("Juan Soto vs Ha-Seong Kim on discipline", "comparison"),
    ("why is Juan Soto good at discipline", "explanation"),
    ("why is Aaron Judge great at power", "explanation"),
]


@pytest.mark.parametrize("query,expected_type", QUESTIONS)
def test_canonical_question_dispatch(query, expected_type):
    result = C.answer_question(query, sport="mlb")
    assert "error" not in result, f"'{query}' -> {result}"
    assert result["question_type"] == expected_type
    assert result.get("window")


def test_answer_question_unrecognized_concept_errors_cleanly():
    result = C.answer_question("best teleportation", sport="mlb")
    assert "error" in result


# ---------------------------------------------------------------------------
# Confidence tier (synthetic, exact boundary control -- reuses NBA's
# STATUS_RANK constant, imported and re-checked here for MLB's own concept)
# ---------------------------------------------------------------------------
def _rows(n, status):
    return pd.DataFrame([dict(entity_id=1, attribute="whiff_rate", n=n, status=status,
                               percentile=90.0, raw_value=1.0, norm_weight=1.0)])


def test_confidence_low_for_provisional():
    concept = get_concept("stuff")
    assert C._confidence_tier(_rows(concept["min_n"] * 10, "PROVISIONAL"), concept) == "LOW"


def test_confidence_low_below_floor():
    concept = get_concept("stuff")
    assert C._confidence_tier(_rows(concept["min_n"] - 1, "VALIDATED_CLAIM"), concept) == "LOW"


def test_confidence_high_when_well_sampled_validated():
    concept = get_concept("stuff")
    assert C._confidence_tier(_rows(concept["min_n"] * 3, "VALIDATED_CLAIM"), concept) == "HIGH"


def test_confidence_medium_otherwise():
    concept = get_concept("stuff")
    assert C._confidence_tier(_rows(concept["min_n"] * 1.2, "DESCRIPTIVE"), concept) == "MEDIUM"


# ---------------------------------------------------------------------------
# Scope guard: this module must never route toward forecasts
# ---------------------------------------------------------------------------
def test_module_does_not_import_forecast_engines():
    import inspect
    src = inspect.getsource(C)
    for forbidden in ("live_engine", "win_probability", "predict_matchup", "basketball_sim"):
        assert forbidden not in src, f"contracts.py must not reference {forbidden} (see ANSWER_RULES.md)"
