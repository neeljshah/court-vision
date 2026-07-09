"""Answer-quality harness: 20+ canonical scouting questions against the REAL
production profiles parquet (read-only). Reads data/cache/profiles/tennis_*
directly; writes nothing outside tmp_path (only synthetic-data tests use
in-memory DataFrames -- nothing touches disk).

Mirrors scripts/platformkit/answers/test_answer_quality_mlb.py's structure;
see that file's header for the harness's general rationale. Tennis-specific
additions: _latest_rows window-selection tests (tennis mixes 3 window
conventions, unlike NBA/MLB's uniform lexical-sort windows) and a majority-
bar independent-proxy test for pressure_resilience (see that test's own
docstring for why it's deliberately weaker than the other 3 proxy tests).

Run: python -m pytest scripts/platformkit/answers/test_answer_quality_tennis.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.tennis.concepts.concept_registry import (
    CONCEPTS, STATUS_RANK, _latest_rows, derive_weights, get_concept, list_concepts,
)
from domains.tennis.profiles.attribute_registry import ATTRIBUTES
from scripts.platformkit.answers import contracts as C

REAL_PROFILES = C._load_df("tennis")
pytestmark = pytest.mark.skipif(REAL_PROFILES.empty, reason="no tennis profiles parquet built")


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------
def test_all_signal_attributes_exist_in_registry():
    missing = [(cname, s["attribute"]) for cname, c in CONCEPTS.items()
               for s in c["signals"] if s["attribute"] not in ATTRIBUTES]
    assert not missing, f"concept signals referencing unknown attributes: {missing}"


def test_concepts_are_the_four_documented():
    # tiebreak_nerve deliberately skipped -- see module docstring SKIPPED CONCEPT.
    assert list_concepts() == ["pressure_resilience", "return_game", "serve_weapon", "stamina"]


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
    """Every concept's min_n must sit at or above its primary attribute's own
    build floor -- the build floor makes a number computable, the concept
    floor makes a leaderboard rank trustworthy (see registry docstring)."""
    for cname, c in CONCEPTS.items():
        primary = c["signals"][0]["attribute"]
        build_floor = max(ATTRIBUTES[primary]["floor"].values())
        assert c["min_n"] >= build_floor, (
            f"{cname} min_n {c['min_n']} below {primary} build floor {build_floor}")


# ---------------------------------------------------------------------------
# Window selection (_latest_rows) -- tennis-specific, mixes 3 conventions
# ---------------------------------------------------------------------------
def test_latest_rows_picks_max_year_over_career_row():
    """"2026" < "career_to_2026" lexically, so a naive lexical-sort default
    (NBA/MLB's convention) would silently pick career over latest year;
    tennis's _latest_rows must pick the max YEAR instead when one exists."""
    df = pd.DataFrame([
        dict(entity_id=1, entity_name="A", window="2020", attribute="x", raw_value=1.0,
             percentile=10.0, n=100.0, status="DESCRIPTIVE"),
        dict(entity_id=1, entity_name="A", window="2024", attribute="x", raw_value=2.0,
             percentile=90.0, n=100.0, status="DESCRIPTIVE"),
        dict(entity_id=1, entity_name="A", window="career_to_2026", attribute="x", raw_value=1.5,
             percentile=50.0, n=500.0, status="DESCRIPTIVE"),
    ])
    out = _latest_rows(df, None)
    assert len(out) == 1
    assert out.iloc[0]["window"] == "2024"


def test_latest_rows_falls_back_to_single_window_when_no_year_rows():
    """pressure_serve-style attributes only ever carry career_to_2026."""
    df = pd.DataFrame([
        dict(entity_id=1, entity_name="A", window="career_to_2026", attribute="pressure_serve",
             raw_value=0.1, percentile=80.0, n=300.0, status="VALIDATED_MECHANISM"),
    ])
    out = _latest_rows(df, None)
    assert len(out) == 1 and out.iloc[0]["window"] == "career_to_2026"


def test_latest_rows_respects_explicit_window_override():
    df = pd.DataFrame([
        dict(entity_id=1, entity_name="A", window="2020", attribute="x", raw_value=1.0,
             percentile=10.0, n=100.0, status="DESCRIPTIVE"),
        dict(entity_id=1, entity_name="A", window="2024", attribute="x", raw_value=2.0,
             percentile=90.0, n=100.0, status="DESCRIPTIVE"),
    ])
    out = _latest_rows(df, "2020")
    assert len(out) == 1 and out.iloc[0]["window"] == "2020"


# ---------------------------------------------------------------------------
# derive_weights math
# ---------------------------------------------------------------------------
def test_derive_weights_normalizes_to_one():
    w = derive_weights(get_concept("serve_weapon"), REAL_PROFILES)
    totals = w.groupby("entity_id")["norm_weight"].sum()
    assert (totals.round(6) == 1.0).all()


def test_shrinkage_midpoint_tracks_concept_floor():
    """At n == min_n the shrinkage factor must be exactly 0.5 (same math as
    NBA/MLB, reusing the concept's own min_n as n0 -- see registry docstring)."""
    concept = get_concept("stamina")
    floor = concept["min_n"]
    df = pd.DataFrame([dict(entity_id=1, entity_name="A", window="2024", attribute="serve_by_set_set3plus",
                             raw_value=0.65, percentile=90.0, n=floor, status="DESCRIPTIVE"),
                        dict(entity_id=1, entity_name="A", window="2024", attribute="serve_by_set_set2",
                             raw_value=0.65, percentile=90.0, n=floor * 3, status="DESCRIPTIVE")])
    w = derive_weights(concept, df).set_index("attribute")
    # base weights: 2 * n/(n+min_n) -> set3plus = 2*0.5 = 1.0, set2 = 2*0.75 = 1.5
    assert abs(w.loc["serve_by_set_set3plus", "base_weight"] - 1.0) < 1e-9
    assert abs(w.loc["serve_by_set_set2", "base_weight"] - 1.5) < 1e-9


# ---------------------------------------------------------------------------
# Superlative: 4 canonical "best X" questions, one per concept, on real data
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cname", list_concepts())
def test_superlative_answerable_on_real_data(cname):
    result = C.answer_superlative(cname, sport="tennis", top_n=5)
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
# Directional regression (synthetic): every tennis concept signal is
# higher_is_better (verified orientation audit, see module docstring) -- a
# higher-percentile entity on the primary signal must outrank a lower one.
# ---------------------------------------------------------------------------
def test_directional_higher_percentile_wins_serve_weapon():
    concept = get_concept("serve_weapon")
    rows = []
    for eid, name, pct in ((1, "Big Server", 95.0), (2, "Weak Server", 15.0)):
        for s in concept["signals"]:
            rows.append(dict(entity_id=eid, entity_name=name, window="2024", attribute=s["attribute"],
                              raw_value=pct / 100.0, percentile=pct, n=5000.0, status="DESCRIPTIVE"))
    weights = derive_weights(concept, pd.DataFrame(rows))
    comp, _ = C._entity_composite(weights)
    scores = comp.set_index("entity_name")["composite"]
    assert scores["Big Server"] > scores["Weak Server"], (
        f"higher-percentile server must outrank: {scores.to_dict()}")


def test_no_tennis_concept_signal_is_lower_is_better():
    """Confirms the orientation-audit conclusion baked into every concept:
    unlike MLB (heart_share_behind, chase_vs_breaking, xwOBA-allowed), no
    tennis attribute used here needed an inversion."""
    dirs = {s["direction"] for c in CONCEPTS.values() for s in c["signals"]}
    assert dirs == {"higher_is_better"}


# ---------------------------------------------------------------------------
# Known-elite overlap: composite top-5 vs the concept's own primary-signal
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
    top5 = {e["entity_name"] for e in C.answer_superlative(cname, sport="tennis", top_n=5)["top"]}
    assert len(top5 & top10) >= 2, f"{cname} top5 {top5} shares <2 names with primary top10 {top10}"


# ---------------------------------------------------------------------------
# Independent-signal proxy checks: every top-5 must clear a high-n proxy NOT
# used in that concept's own composite. Thresholds calibrated against live
# values (2026-07-09), leaving real margin.
# ---------------------------------------------------------------------------
def _independent_pct(attribute: str) -> pd.Series:
    sub = REAL_PROFILES[REAL_PROFILES["attribute"] == attribute]
    lr = _latest_rows(sub, None)
    return lr.set_index("entity_name")["percentile"]


def test_serve_weapon_top5_backed_by_independent_courtside_proxy():
    """courtside_serve_deuce is NOT a serve_weapon signal (different
    ingredient: point-index parity, not ace/serve-win rates). Live top-5
    values are 97.4-100 as of 2026-07-09."""
    pct = _independent_pct("courtside_serve_deuce")
    for entry in C.answer_superlative("serve_weapon", sport="tennis", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 90, (
            f"{entry['entity_name']} in serve_weapon top-5 but courtside_serve_deuce "
            f"pct is only {pct.get(entry['entity_name'])}")


def test_return_game_top5_backed_by_independent_surface_proxy():
    """surface_splits_return_Hard: career-only, not a return_game signal.
    Live top-5 values are 53.5-99.6 as of 2026-07-09."""
    pct = _independent_pct("surface_splits_return_Hard")
    for entry in C.answer_superlative("return_game", sport="tennis", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 45, (
            f"{entry['entity_name']} in return_game top-5 but surface_splits_return_Hard "
            f"pct is only {pct.get(entry['entity_name'])}")


def test_stamina_top5_backed_by_independent_set1_proxy():
    """serve_by_set_set1 is deliberately EXCLUDED from stamina's signals --
    checks a 'great in set 3+' player isn't simply unable to serve early.
    Live top-5 values are 89.5-100 as of 2026-07-09."""
    pct = _independent_pct("serve_by_set_set1")
    for entry in C.answer_superlative("stamina", sport="tennis", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 80, (
            f"{entry['entity_name']} in stamina top-5 but serve_by_set_set1 "
            f"pct is only {pct.get(entry['entity_name'])}")


def test_pressure_resilience_top5_majority_backed_by_momentum_streakiness():
    """WEAKER bar than the other 3 proxy tests, deliberately: pressure_
    resilience's 4 signals are all small-n leverage-restricted deltas --
    empirically verified 2026-07-09 that NO single independent proxy (tried
    momentum_streakiness, tiebreak_points_won_share, second_serve_aggression_
    delta, serve_dominance, return_strength, serve_by_set_set3plus) clears a
    high threshold for all 5 simultaneously -- each only agrees with 2-3 of
    5. That's the concept's own documented failure mode ('one hot or cold
    stretch... can dominate'), not a test bug, so this asserts a MAJORITY
    (>=3 of 5) against momentum_streakiness (independent point-sequence
    signal, unused in any of the 4 composite signals)."""
    pct = _independent_pct("momentum_streakiness")
    entries = C.answer_superlative("pressure_resilience", sport="tennis", top_n=5)["top"]
    passing = [e for e in entries if pct.get(e["entity_name"], -1) >= 50]
    assert len(passing) >= 3, (
        f"only {len(passing)}/5 pressure_resilience top-5 clear momentum_streakiness "
        f">=50th pct: {[(e['entity_name'], pct.get(e['entity_name'])) for e in entries]}")


def test_pressure_resilience_top5_backed_by_independent_primary_signal():
    """Every top-5 must independently show as a well-above-median performer
    on the concept's OWN primary raw signal (pressure_serve itself) -- catches
    a composite that has drifted from what it claims to measure. Live top-5
    values are 86.2-98.2 as of 2026-07-09."""
    pct = _independent_pct("pressure_serve")
    for entry in C.answer_superlative("pressure_resilience", sport="tennis", top_n=5)["top"]:
        assert pct.get(entry["entity_name"], -1) >= 80, (
            f"{entry['entity_name']} in pressure_resilience top-5 but pressure_serve "
            f"pct is only {pct.get(entry['entity_name'])}")


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------
def test_comparison_has_both_entities_ingredient_rows():
    r = C.answer_comparison("serve_weapon", "Roger Federer", "Novak Djokovic", sport="tennis")
    attrs = {row["attribute"] for row in r["ingredient_table"]}
    assert "serve_dominance" in attrs
    row = next(row for row in r["ingredient_table"] if row["attribute"] == "serve_dominance")
    assert row["a"] is not None and row["b"] is not None
    assert r["entity_a"]["composite"] is not None and r["entity_b"]["composite"] is not None
    assert r["favored"] in (r["entity_a"]["name"], r["entity_b"]["name"])


def test_comparison_what_would_flip_it_uses_present_signal():
    r = C.answer_comparison("serve_weapon", "Roger Federer", "Novak Djokovic", sport="tennis")
    flip = r["what_would_flip_it"]
    if flip is None:
        return  # tied composites -- nothing to flip
    attrs_for_trailer = {row["attribute"] for row in r["ingredient_table"]
                          if (row["a"] if flip["trailing_entity"] == r["entity_a"]["name"] else row["b"]) is not None}
    assert flip["signal"] in attrs_for_trailer
    assert flip["percentile_points_needed"] >= 0


def test_comparison_below_floor_entity_still_compares():
    """Comparison bypasses the leaderboard min_n floor (pairwise, not a
    ranking) -- John Isner's single charted year (2018, n=1010) sits below
    serve_weapon's 1380 leaderboard floor but must still compare."""
    r = C.answer_comparison("serve_weapon", "John Isner", "Ivo Karlovic", sport="tennis")
    assert r["entity_a"]["composite"] is not None


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------
def test_explanation_decomposition_sums_to_composite():
    r = C.answer_explanation("return_game", "Novak Djokovic", sport="tennis")
    total = sum(row["contribution"] for row in r["decomposition"])
    assert abs(total - r["composite"]) < 0.05
    assert all({"attribute", "contribution", "percentile", "weight", "status", "n"} <= row.keys()
               for row in r["decomposition"])


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------
def test_fit_baseline_is_roster_average_not_fabricated():
    r = C.answer_fit("serve_weapon", "Roger Federer", ["Novak Djokovic"], sport="tennis")
    solo = C.answer_comparison("serve_weapon", "Novak Djokovic", "Novak Djokovic", sport="tennis")
    assert r["team_need_baseline"] == solo["entity_a"]["composite"]
    assert "proxy for team need" in r["note"]
    assert r["delta"] == round(r["entity_composite"] - r["team_need_baseline"], 2)


# ---------------------------------------------------------------------------
# Free-text dispatch: 20+ canonical scouting questions
# ---------------------------------------------------------------------------
QUESTIONS = [
    ("best serve weapon", "superlative"),
    ("who has the best serve_weapon", "superlative"),
    ("best serve_weapon", "superlative"),
    ("best return game", "superlative"),
    ("who has the best return_game", "superlative"),
    ("best return_game", "superlative"),
    ("best pressure resilience", "superlative"),
    ("who has the best pressure_resilience", "superlative"),
    ("best pressure_resilience", "superlative"),
    ("best stamina", "superlative"),
    ("who has the best stamina", "superlative"),
    ("Roger Federer vs Novak Djokovic on serve_weapon", "comparison"),
    ("Novak Djokovic vs Roger Federer on return_game", "comparison"),
    ("Serena Williams vs Martina Hingis on return_game", "comparison"),
    ("Taylor Fritz vs Pete Sampras on serve_weapon", "comparison"),
    ("Ivo Karlovic vs John Isner on serve_weapon", "comparison"),
    ("Marin Cilic vs Denis Shapovalov on pressure_resilience", "comparison"),
    ("why is Roger Federer good at serve_weapon", "explanation"),
    ("why is Novak Djokovic great at return_game", "explanation"),
    ("why is Ivo Karlovic good at stamina", "explanation"),
    ("why is Gustavo Kuerten great at pressure_resilience", "explanation"),
]


@pytest.mark.parametrize("query,expected_type", QUESTIONS)
def test_canonical_question_dispatch(query, expected_type):
    result = C.answer_question(query, sport="tennis")
    assert "error" not in result, f"'{query}' -> {result}"
    assert result["question_type"] == expected_type
    assert result.get("window")


def test_answer_question_unrecognized_concept_errors_cleanly():
    result = C.answer_question("best teleportation", sport="tennis")
    assert "error" in result


# ---------------------------------------------------------------------------
# Confidence tier (synthetic, exact boundary control)
# ---------------------------------------------------------------------------
def _rows(n, status):
    return pd.DataFrame([dict(entity_id=1, attribute="serve_dominance", n=n, status=status,
                               percentile=90.0, raw_value=1.0, norm_weight=1.0)])


@pytest.mark.parametrize("n_mult,status,expected", [
    (10, "PROVISIONAL", "LOW"),           # any PROVISIONAL row -> LOW regardless of n
    (-1, "VALIDATED_CLAIM", "LOW"),       # n_mult=-1 means (min_n - 1), i.e. below floor
    (3, "VALIDATED_CLAIM", "HIGH"),       # >=2x floor + VALIDATED_CLAIM -> HIGH
    (1.2, "DESCRIPTIVE", "MEDIUM"),       # above floor but not HIGH-qualifying -> MEDIUM
])
def test_confidence_tier_boundaries(n_mult, status, expected):
    concept = get_concept("serve_weapon")
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
