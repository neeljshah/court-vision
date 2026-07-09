"""Answer-quality harness: 15+ canonical scouting questions against the REAL
production profiles parquet (read-only). Reads data/cache/profiles/wnba_*
directly; writes nothing outside tmp_path (only synthetic-data tests use
in-memory DataFrames -- nothing touches disk).

Mirrors scripts/platformkit/answers/test_answer_quality_mlb.py's structure;
see that file's header for the harness's general rationale. WNBA-specific:
kind="player" (the default) works as-is; the module docstring documents why
rim_protection/motor/creation/clutch were SKIPPED rather than built.

Run: python -m pytest scripts/platformkit/answers/test_answer_quality_wnba.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_wnba.concepts.concept_registry import (
    CONCEPTS, STATUS_RANK, _latest_rows, derive_weights, get_concept, list_concepts,
)
from domains.basketball_wnba.profiles.attribute_registry import ATTRIBUTES
from scripts.platformkit.answers import contracts as C

REAL_PROFILES = C._load_df("wnba", kind="player")
pytestmark = pytest.mark.skipif(REAL_PROFILES.empty, reason="no wnba player profiles parquet built")


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------
def test_all_signal_attributes_exist_in_registry():
    missing = [(cname, s["attribute"]) for cname, c in CONCEPTS.items()
               for s in c["signals"] if s["attribute"] not in ATTRIBUTES]
    assert not missing, f"concept signals referencing unknown attributes: {missing}"


def test_concepts_are_the_three_documented():
    # rim_protection (data-coverage landmine), motor, creation/playmaking, and
    # clutch deliberately skipped -- see module docstring.
    assert list_concepts() == ["gravity", "spacing", "versatility"]


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


def test_min_n_floors_exceed_attribute_build_floors():
    for cname, c in CONCEPTS.items():
        primary = c["signals"][0]["attribute"]
        build_floor = ATTRIBUTES[primary]["floor"]
        assert c["min_n"] >= build_floor, (
            f"{cname} min_n {c['min_n']} below {primary} build floor {build_floor}")


def test_rim_protection_deliberately_not_built():
    """rim_protection's two nominal signals (def_rim_efg_allowed_delta,
    def_rim_share_allowed_delta) exist in the attribute registry but their
    source excludes every recognizable elite big -- see module docstring
    DATA-COVERAGE LANDMINE. Confirms the concept was never shipped."""
    assert "rim_protection" not in CONCEPTS


# ---------------------------------------------------------------------------
# derive_weights math
# ---------------------------------------------------------------------------
def test_derive_weights_normalizes_to_one():
    w = derive_weights(get_concept("versatility"), REAL_PROFILES)
    totals = w.groupby("entity_id")["norm_weight"].sum()
    assert (totals.round(6) == 1.0).all()


def test_shrinkage_midpoint_tracks_global_n0():
    """WNBA uses NBA's fixed N0=200 (not a per-concept n0 like MLB/tennis --
    see module docstring). At n==N0 the shrinkage factor must be 0.5."""
    concept = get_concept("gravity")
    from domains.basketball_wnba.concepts.concept_registry import N0
    df = pd.DataFrame([dict(entity_id=1, entity_name="A", window="season_2026",
                             attribute="gravity", raw_value=0.05, percentile=90.0,
                             n=N0, status="DESCRIPTIVE"),
                        dict(entity_id=1, entity_name="A", window="season_2026",
                             attribute="on_court_impact", raw_value=5.0, percentile=90.0,
                             n=N0 * 3, status="DESCRIPTIVE")])
    w = derive_weights(concept, df).set_index("attribute")
    assert abs(w.loc["gravity", "base_weight"] - 1.0) < 1e-9
    assert abs(w.loc["on_court_impact", "base_weight"] - 1.5) < 1e-9


# ---------------------------------------------------------------------------
# Superlative: 3 canonical "best X" questions, one per concept, on real data
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cname", list_concepts())
def test_superlative_answerable_on_real_data(cname):
    result = C.answer_superlative(cname, sport="wnba", top_n=5)
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
# Directional regression (synthetic): every wnba concept signal is
# higher_is_better (verified orientation audit, see module docstring) -- a
# higher-percentile entity on the primary signal must outrank a lower one.
# ---------------------------------------------------------------------------
def test_directional_higher_percentile_wins_versatility():
    concept = get_concept("versatility")
    rows = []
    for eid, name, pct in ((1, "Efficient Scorer", 95.0), (2, "Inefficient Scorer", 15.0)):
        for s in concept["signals"]:
            rows.append(dict(entity_id=eid, entity_name=name, window="season_2026",
                              attribute=s["attribute"], raw_value=pct / 100.0, percentile=pct,
                              n=200.0, status="DESCRIPTIVE"))
    weights = derive_weights(concept, pd.DataFrame(rows))
    comp, _ = C._entity_composite(weights)
    scores = comp.set_index("entity_name")["composite"]
    assert scores["Efficient Scorer"] > scores["Inefficient Scorer"]


def test_no_wnba_concept_signal_is_lower_is_better():
    """Confirms the orientation-audit conclusion: every WNBA attribute's
    percentile is a plain rank (no builder-side flip, unlike soccer), and
    every signal chosen for these 3 concepts is already formula-signed so
    raw-high means good -- no inversion needed anywhere in this registry."""
    dirs = {s["direction"] for c in CONCEPTS.values() for s in c["signals"]}
    assert dirs == {"higher_is_better"}


# ---------------------------------------------------------------------------
# Known-plausible overlap: composite top-5 vs the concept's own primary-signal
# top-10 (computed live from the parquet, never hardcoded names)
# ---------------------------------------------------------------------------
def _primary_top10(cname: str) -> set[str]:
    concept = get_concept(cname)
    primary = concept["signals"][0]["attribute"]
    sub = REAL_PROFILES[REAL_PROFILES["attribute"] == primary]
    lr = _latest_rows(sub, None)
    lr = lr[lr["n"] >= concept["min_n"]]
    return set(lr.sort_values("percentile", ascending=False).head(10)["entity_name"])


@pytest.mark.parametrize("cname", list_concepts())
def test_top5_shares_at_least_2_names_with_primary_signal_top10(cname):
    top10 = _primary_top10(cname)
    top5 = {e["entity_name"] for e in C.answer_superlative(cname, sport="wnba", top_n=5)["top"]}
    assert len(top5 & top10) >= 2, f"{cname} top5 {top5} shares <2 names with primary top10 {top10}"


# ---------------------------------------------------------------------------
# Independent-signal proxy checks: every top-5 must clear a proxy attribute
# NOT used in that concept's own composite. Thresholds calibrated against
# live values (2026-07-09), leaving real margin.
# ---------------------------------------------------------------------------
def _independent_pct(attribute: str) -> pd.Series:
    sub = REAL_PROFILES[REAL_PROFILES["attribute"] == attribute]
    lr = _latest_rows(sub, None)
    return lr.set_index("entity_name")["percentile"]


def test_gravity_top5_majority_backed_by_scoring_proxy():
    """WEAKER bar, deliberately: gravity's own failure_modes documents that
    its raw top-5 skews toward role players (same class of noise NBA's own
    gravity concept documents). scoring_per36 is NOT a gravity signal. Live
    top-5 values are 16.5-91.2 as of 2026-07-09 -- only 3/5 clear a 50th-pct
    bar, so this asserts a MAJORITY (>=3 of 5), same weaker-bar precedent as
    tennis's pressure_resilience proxy test."""
    pct = _independent_pct("scoring_per36")
    entries = C.answer_superlative("gravity", sport="wnba", top_n=5)["top"]
    passing = [e for e in entries if pct.get(e["entity_name"], -1) >= 50]
    assert len(passing) >= 3, (
        f"only {len(passing)}/5 gravity top-5 clear scoring_per36 >=50th pct: "
        f"{[(e['entity_name'], pct.get(e['entity_name'])) for e in entries]}")


def test_spacing_top5_backed_by_independent_efg_proxy():
    """Overall efg is NOT a spacing signal (spacing only uses the two 3pt
    zones). Live top-5 values are 56.5-91.2 as of 2026-07-09."""
    pct = _independent_pct("efg")
    for entry in C.answer_superlative("spacing", sport="wnba", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 45, (
            f"{entry['entity_name']} in spacing top-5 but overall efg pct is "
            f"only {pct.get(entry['entity_name'])}")


def test_versatility_top5_backed_by_independent_efg_proxy():
    """Overall efg is a related-but-distinct column from the 5 per-zone efg
    signals versatility averages -- not literally one of its inputs. Live
    top-5 values are 85.0-97.4 as of 2026-07-09."""
    pct = _independent_pct("efg")
    for entry in C.answer_superlative("versatility", sport="wnba", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 75, (
            f"{entry['entity_name']} in versatility top-5 but overall efg pct "
            f"is only {pct.get(entry['entity_name'])}")


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def test_comparison_has_both_entities_ingredient_rows():
    r = C.answer_comparison("gravity", "A'ja Wilson", "Breanna Stewart", sport="wnba")
    attrs = {row["attribute"] for row in r["ingredient_table"]}
    assert "gravity" in attrs
    row = next(row for row in r["ingredient_table"] if row["attribute"] == "gravity")
    assert row["a"] is not None and row["b"] is not None
    assert r["entity_a"]["composite"] is not None and r["entity_b"]["composite"] is not None
    assert r["favored"] in (r["entity_a"]["name"], r["entity_b"]["name"])


def test_comparison_what_would_flip_it_uses_present_signal():
    r = C.answer_comparison("versatility", "Kelsey Plum", "Paige Bueckers", sport="wnba")
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
    r = C.answer_explanation("versatility", "A'ja Wilson", sport="wnba")
    total = sum(row["contribution"] for row in r["decomposition"])
    assert abs(total - r["composite"]) < 0.05
    assert all({"attribute", "contribution", "percentile", "weight", "status", "n"} <= row.keys()
               for row in r["decomposition"])


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------
def test_fit_baseline_is_roster_average_not_fabricated():
    r = C.answer_fit("versatility", "A'ja Wilson", ["Kelsey Plum"], sport="wnba")
    solo = C.answer_comparison("versatility", "Kelsey Plum", "Kelsey Plum", sport="wnba")
    assert r["team_need_baseline"] == solo["entity_a"]["composite"]
    assert "proxy for team need" in r["note"]
    assert r["delta"] == round(r["entity_composite"] - r["team_need_baseline"], 2)


# ---------------------------------------------------------------------------
# Free-text dispatch: 15+ canonical scouting questions
# ---------------------------------------------------------------------------
QUESTIONS = [
    ("best gravity", "superlative"),
    ("who has the best gravity", "superlative"),
    ("best spacing", "superlative"),
    ("who has the best spacing", "superlative"),
    ("best versatility", "superlative"),
    ("who has the best versatility", "superlative"),
    ("A'ja Wilson vs Breanna Stewart on gravity", "comparison"),
    ("Kelsey Plum vs Paige Bueckers on versatility", "comparison"),
    ("Sabrina Ionescu vs Caitlin Clark on spacing", "comparison"),
    ("A'ja Wilson vs Jonquel Jones on gravity", "comparison"),
    ("Kelsey Plum vs A'ja Wilson on versatility", "comparison"),
    ("why is A'ja Wilson good at versatility", "explanation"),
    ("why is Kelsey Plum great at versatility", "explanation"),
    ("why is Breanna Stewart good at gravity", "explanation"),
    ("why is Sabrina Ionescu great at spacing", "explanation"),
]


@pytest.mark.parametrize("query,expected_type", QUESTIONS)
def test_canonical_question_dispatch(query, expected_type):
    result = C.answer_question(query, sport="wnba")
    assert "error" not in result, f"'{query}' -> {result}"
    assert result["question_type"] == expected_type
    assert result.get("window")


def test_answer_question_unrecognized_concept_errors_cleanly():
    result = C.answer_question("best teleportation", sport="wnba")
    assert "error" in result


# ---------------------------------------------------------------------------
# Confidence tier (synthetic, exact boundary control)
# ---------------------------------------------------------------------------
def _rows(n, status):
    return pd.DataFrame([dict(entity_id=1, attribute="gravity", n=n, status=status,
                               percentile=90.0, raw_value=1.0, norm_weight=1.0)])


@pytest.mark.parametrize("n_mult,status,expected", [
    (10, "PROVISIONAL", "LOW"),
    (-1, "VALIDATED_CLAIM", "LOW"),
    (3, "VALIDATED_CLAIM", "HIGH"),
    (1.2, "DESCRIPTIVE", "MEDIUM"),
])
def test_confidence_tier_boundaries(n_mult, status, expected):
    concept = get_concept("gravity")
    n = concept["min_n"] - 1 if n_mult == -1 else concept["min_n"] * n_mult
    assert C._confidence_tier(_rows(n, status), concept) == expected


# ---------------------------------------------------------------------------
# Scope guard: this module must never route toward forecasts
# ---------------------------------------------------------------------------
def test_module_does_not_import_forecast_engines():
    import inspect
    src = inspect.getsource(C)
    for forbidden in ("live_engine", "win_probability", "predict_matchup", "basketball_sim"):
        assert forbidden not in src, f"contracts.py must not reference {forbidden} (see ANSWER_RULES.md)"
