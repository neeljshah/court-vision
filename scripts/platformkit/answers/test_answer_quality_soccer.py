"""Answer-quality harness: 15+ canonical scouting questions against the REAL
production profiles parquet (read-only). Reads data/cache/profiles/soccer_*
directly; writes nothing outside tmp_path (only synthetic-data tests use
in-memory DataFrames -- nothing touches disk).

Mirrors scripts/platformkit/answers/test_answer_quality_mlb.py's structure;
see that file's header for the harness's general rationale. Soccer-specific:
every call passes kind="team" (soccer has no player-entity profiles, unlike
every other sport's default kind="player").

Run: python -m pytest scripts/platformkit/answers/test_answer_quality_soccer.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.soccer.concepts.concept_registry import (
    CONCEPTS, STATUS_RANK, _latest_rows, derive_weights, get_concept, list_concepts,
)
from domains.soccer.profiles.attribute_registry import REGISTRY as ATTRIBUTES
from scripts.platformkit.answers import contracts as C

REAL_PROFILES = C._load_df("soccer", kind="team")
pytestmark = pytest.mark.skipif(REAL_PROFILES.empty, reason="no soccer team profiles parquet built")


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------
def test_all_signal_attributes_exist_in_registry():
    missing = [(cname, s["attribute"]) for cname, c in CONCEPTS.items()
               for s in c["signals"] if s["attribute"] not in ATTRIBUTES]
    assert not missing, f"concept signals referencing unknown attributes: {missing}"


def test_concepts_are_the_three_documented():
    # set_piece_threat (disguised single column) and press_intensity (zero
    # signals exist) deliberately skipped -- see module docstring.
    assert list_concepts() == ["solidity", "threat", "transition"]


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


def test_no_concept_mixes_statsbomb_and_footballdata_entity_spaces():
    """Every concept's signals must all resolve to entity_ids present in the
    SAME corpus window -- mixing statsbomb (numeric ids) and footballdata
    (name-string ids) would silently degrade a composite to 1 real signal
    per entity (see module docstring ENTITY-SPACE LANDMINE)."""
    for cname, c in CONCEPTS.items():
        for s in c["signals"]:
            sub = REAL_PROFILES[REAL_PROFILES["attribute"] == s["attribute"]]
            windows = set(sub["window"].unique())
            assert windows == {"statsbomb_2015_2021"}, (
                f"{cname}:{s['attribute']} unexpectedly spans windows {windows}")


# ---------------------------------------------------------------------------
# derive_weights math
# ---------------------------------------------------------------------------
def test_derive_weights_normalizes_to_one():
    w = derive_weights(get_concept("threat"), REAL_PROFILES)
    totals = w.groupby("entity_id")["norm_weight"].sum()
    assert (totals.round(6) == 1.0).all()


def test_shrinkage_midpoint_tracks_concept_floor():
    concept = get_concept("solidity")
    floor = concept["min_n"]
    df = pd.DataFrame([dict(entity_id=1, entity_name="A", window="statsbomb_2015_2021",
                             attribute="defensive_solidity", raw_value=0.01, percentile=90.0,
                             n=floor, status="DESCRIPTIVE"),
                        dict(entity_id=1, entity_name="A", window="statsbomb_2015_2021",
                             attribute="defensive_counter_threat", raw_value=0.01, percentile=90.0,
                             n=floor * 3, status="DESCRIPTIVE")])
    w = derive_weights(concept, df).set_index("attribute")
    # base weights: 2 * n/(n+min_n) -> primary = 2*0.5 = 1.0, secondary = 2*0.75 = 1.5
    assert abs(w.loc["defensive_solidity", "base_weight"] - 1.0) < 1e-9
    assert abs(w.loc["defensive_counter_threat", "base_weight"] - 1.5) < 1e-9


# ---------------------------------------------------------------------------
# Superlative: 3 canonical "best X" questions, one per concept, on real data
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cname", list_concepts())
def test_superlative_answerable_on_real_data(cname):
    result = C.answer_superlative(cname, sport="soccer", kind="team", top_n=5)
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
# Directional regression (synthetic): every soccer concept signal is
# higher_is_better (percentile is builder-pre-oriented, see module docstring)
# -- a higher-percentile entity on the primary signal must outrank a lower one.
# ---------------------------------------------------------------------------
def test_directional_higher_percentile_wins_threat():
    concept = get_concept("threat")
    rows = []
    for eid, name, pct in ((1, "Strong Attack", 95.0), (2, "Weak Attack", 15.0)):
        for s in concept["signals"]:
            rows.append(dict(entity_id=eid, entity_name=name, window="statsbomb_2015_2021",
                              attribute=s["attribute"], raw_value=pct / 100.0, percentile=pct,
                              n=100.0, status="DESCRIPTIVE"))
    weights = derive_weights(concept, pd.DataFrame(rows))
    comp, _ = C._entity_composite(weights)
    scores = comp.set_index("entity_name")["composite"]
    assert scores["Strong Attack"] > scores["Weak Attack"]


def test_no_soccer_concept_signal_is_lower_is_better():
    """Confirms the orientation-audit conclusion baked into every concept:
    soccer's builder pre-orients percentile via the registry's own
    higher_is_better flag, so every concept signal here (including the
    RAW-lower-is-better solidity signals) is consumed as higher_is_better."""
    dirs = {s["direction"] for c in CONCEPTS.values() for s in c["signals"]}
    assert dirs == {"higher_is_better"}


# ---------------------------------------------------------------------------
# Known-plausible overlap: composite top-5 vs the concept's own primary-signal
# top population (computed live from the parquet, never hardcoded)
# ---------------------------------------------------------------------------
def _primary_top(cname: str, n: int = 5) -> set[str]:
    concept = get_concept(cname)
    primary = concept["signals"][0]["attribute"]
    sub = REAL_PROFILES[REAL_PROFILES["attribute"] == primary]
    lr = _latest_rows(sub, None)
    lr = lr[lr["n"] >= concept["min_n"]]
    return set(lr.sort_values("percentile", ascending=False).head(n)["entity_name"])


@pytest.mark.parametrize("cname", list_concepts())
def test_top5_shares_at_least_2_names_with_primary_signal_top5(cname):
    # only 9 qualified teams in the whole corpus -- top5 of 9 is more than
    # half the population, so this checks the composite doesn't reorder away
    # from the primary signal entirely, not a strict top10-style bar.
    top5_primary = _primary_top(cname, 5)
    top5 = {e["entity_name"] for e in C.answer_superlative(cname, sport="soccer", kind="team", top_n=5)["top"]}
    assert len(top5 & top5_primary) >= 2, f"{cname} top5 {top5} shares <2 names with primary top5 {top5_primary}"


# ---------------------------------------------------------------------------
# Independent-signal proxy checks: every top-5 must clear a proxy attribute
# NOT used in that concept's own composite. Thresholds calibrated against
# live values (2026-07-09), leaving real margin given the small 9-team corpus.
# ---------------------------------------------------------------------------
def _independent_pct(attribute: str) -> pd.Series:
    sub = REAL_PROFILES[REAL_PROFILES["attribute"] == attribute]
    lr = _latest_rows(sub, None)
    return lr.set_index("entity_name")["percentile"]


def test_threat_top5_backed_by_independent_directness_proxy():
    """shots_per_possession is NOT a threat signal (it's transition's
    secondary). Live top-5 values are 55.6-100 as of 2026-07-09."""
    pct = _independent_pct("shots_per_possession")
    for entry in C.answer_superlative("threat", sport="soccer", kind="team", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 45, (
            f"{entry['entity_name']} in threat top-5 but shots_per_possession "
            f"pct is only {pct.get(entry['entity_name'])}")


def test_solidity_top5_backed_by_independent_directness_proxy():
    """shots_per_possession is NOT a solidity signal. Live top-5 values are
    33.3-100 as of 2026-07-09."""
    pct = _independent_pct("shots_per_possession")
    for entry in C.answer_superlative("solidity", sport="soccer", kind="team", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 25, (
            f"{entry['entity_name']} in solidity top-5 but shots_per_possession "
            f"pct is only {pct.get(entry['entity_name'])}")


def test_transition_top5_backed_by_independent_buildup_proxy():
    """buildup_quality is NOT a transition signal. Live top-5 values are
    33.3-100 as of 2026-07-09."""
    pct = _independent_pct("buildup_quality")
    for entry in C.answer_superlative("transition", sport="soccer", kind="team", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 25, (
            f"{entry['entity_name']} in transition top-5 but buildup_quality "
            f"pct is only {pct.get(entry['entity_name'])}")


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def test_comparison_has_both_entities_ingredient_rows():
    r = C.answer_comparison("threat", "Chelsea FCW", "Arsenal WFC", sport="soccer", kind="team")
    attrs = {row["attribute"] for row in r["ingredient_table"]}
    assert "buildup_quality" in attrs
    row = next(row for row in r["ingredient_table"] if row["attribute"] == "buildup_quality")
    assert row["a"] is not None and row["b"] is not None
    assert r["entity_a"]["composite"] is not None and r["entity_b"]["composite"] is not None
    assert r["favored"] in (r["entity_a"]["name"], r["entity_b"]["name"])


def test_comparison_what_would_flip_it_uses_present_signal():
    r = C.answer_comparison("solidity", "Manchester City WFC", "Everton LFC", sport="soccer", kind="team")
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
    r = C.answer_explanation("transition", "Chelsea FCW", sport="soccer", kind="team")
    total = sum(row["contribution"] for row in r["decomposition"])
    assert abs(total - r["composite"]) < 0.05
    assert all({"attribute", "contribution", "percentile", "weight", "status", "n"} <= row.keys()
               for row in r["decomposition"])


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------
def test_fit_baseline_is_roster_average_not_fabricated():
    r = C.answer_fit("threat", "Chelsea FCW", ["Arsenal WFC"], sport="soccer", kind="team")
    solo = C.answer_comparison("threat", "Arsenal WFC", "Arsenal WFC", sport="soccer", kind="team")
    assert r["team_need_baseline"] == solo["entity_a"]["composite"]
    assert "proxy for team need" in r["note"]
    assert r["delta"] == round(r["entity_composite"] - r["team_need_baseline"], 2)


# ---------------------------------------------------------------------------
# Free-text dispatch: 15+ canonical scouting questions
# ---------------------------------------------------------------------------
QUESTIONS = [
    ("best threat", "superlative"),
    ("who has the best threat", "superlative"),
    ("best solidity", "superlative"),
    ("who has the best solidity", "superlative"),
    ("best transition", "superlative"),
    ("who has the best transition", "superlative"),
    ("Chelsea FCW vs Arsenal WFC on threat", "comparison"),
    ("Arsenal WFC vs Chelsea FCW on solidity", "comparison"),
    ("Manchester City WFC vs Everton LFC on transition", "comparison"),
    ("Chelsea FCW vs West Ham United LFC on transition", "comparison"),
    ("Reading WFC vs Brighton & Hove Albion WFC on threat", "comparison"),
    ("why is Chelsea FCW good at threat", "explanation"),
    ("why is Arsenal WFC great at solidity", "explanation"),
    ("why is Manchester City WFC good at transition", "explanation"),
    ("why is Everton LFC great at threat", "explanation"),
]


@pytest.mark.parametrize("query,expected_type", QUESTIONS)
def test_canonical_question_dispatch(query, expected_type):
    result = C.answer_question(query, sport="soccer", kind="team")
    assert "error" not in result, f"'{query}' -> {result}"
    assert result["question_type"] == expected_type
    assert result.get("window")


def test_answer_question_unrecognized_concept_errors_cleanly():
    result = C.answer_question("best teleportation", sport="soccer", kind="team")
    assert "error" in result


def test_answer_question_defaults_to_player_kind_and_finds_nothing_for_soccer():
    """Documents the kind="player" default trap: soccer is team-only, so
    calling without kind="team" resolves zero entities (raises, same as any
    unmatched entity) -- verifies the fix (contracts.answer_question now
    accepts kind=) actually threads through to answer_comparison."""
    with pytest.raises(ValueError, match="no entity matched"):
        C.answer_question("Chelsea FCW vs Arsenal WFC on threat", sport="soccer")


# ---------------------------------------------------------------------------
# Confidence tier (synthetic, exact boundary control)
# ---------------------------------------------------------------------------
def _rows(n, status):
    return pd.DataFrame([dict(entity_id=1, attribute="buildup_quality", n=n, status=status,
                               percentile=90.0, raw_value=1.0, norm_weight=1.0)])


@pytest.mark.parametrize("n_mult,status,expected", [
    (10, "PROVISIONAL", "LOW"),
    (-1, "VALIDATED_CLAIM", "LOW"),
    (3, "VALIDATED_CLAIM", "HIGH"),
    (1.2, "DESCRIPTIVE", "MEDIUM"),
])
def test_confidence_tier_boundaries(n_mult, status, expected):
    concept = get_concept("threat")
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
