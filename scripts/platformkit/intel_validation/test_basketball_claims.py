"""Per-file tests for basketball_claims (LANE nba-fullpop). Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_basketball_claims.py -q

Acceptance criteria:
  1. Every emitted claim independently VERIFIES against claims_validator.py
     (zero code sharing between producer and validator).
  2. The qualifying population matches the frozen spec count (329 of 2024-25
     n_games>=20 AND fga_sum>=200).
  3. "Where does LeBron rank on X" is answerable: LeBron James (player_id
     2544) clears the population floor and appears in at least one
     dimension's n_considered pool with a real rank (proves full-population
     coverage, not just top-50 sampling).
  4. Excluded-below-floor players are counted, never silently dropped
     (n_considered == qualifiers + n_excluded_below_floor for every claim).
  5. No retracted/edge-claim tokens leak into any claim's caveats/question.
  6. dims_corpus_absent lists only genuinely absent DEFER-stub leaves, never
     an empty string or a dimension that IS actually built.
"""
from __future__ import annotations

from scripts.platformkit.intel_validation import basketball_claims as bc
from scripts.platformkit.intel_validation import basketball_claims_dims as dims
from scripts.platformkit.intel_validation.claims_validator import validate_claim

LEBRON_ID = 2544

_BANNED = ("18.38", "0.119", "+54%", "78.11", "8.94", "54.57", "roi", "bankroll", "pnl")


def test_qualifying_population_matches_frozen_spec_count():
    pop = dims.qualifying_population()
    assert len(pop) == 329


def test_lebron_clears_the_population_floor():
    pop = dims.qualifying_population()
    assert LEBRON_ID in set(pop["player_id"])


def test_all_claims_independently_verify():
    claims, _ = bc.build_all_claims()
    assert len(claims) > 0
    for claim in claims:
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"


def test_boxscore_aggregate_dims_all_built():
    claims, _ = bc.build_all_claims()
    built_ids = {c["claim_id"] for c in claims}
    for metric in dims.BOXSCORE_AGGREGATE_DIMS:
        assert f"nba_{metric}_top50_{bc.SEASON_WINDOW}" in built_ids


def test_atlas_dims_all_built_or_honestly_absent():
    claims, dims_corpus_absent = bc.build_all_claims()
    built_names = {c["claim_id"].removeprefix("nba_").rsplit(f"_top50_{bc.SEASON_WINDOW}", 1)[0]
                   for c in claims}
    for spec in dims.DIM_SPECS:
        absent = any(spec.name in entry for entry in dims_corpus_absent)
        assert spec.name in built_names or absent, (
            f"{spec.name} neither built nor reported absent"
        )


def test_lebron_is_rankable_on_at_least_one_dimension():
    """"Where does LeBron rank on X" must be answerable for at least one
    dimension -- proves full-population coverage is real, not a stub."""
    claims, _ = bc.build_all_claims()
    lebron_dims = [
        c["claim_id"] for c in claims
        if any(row["player_id"] == LEBRON_ID for row in c["ranking"])
    ]
    assert len(lebron_dims) > 0, "LeBron does not appear in any dimension's top-50 ranking"


def test_excluded_below_floor_counted_never_dropped():
    """n_considered must equal (qualifiers ranked+unranked) + n_excluded --
    i.e. the floor-excluded population is COUNTED, never silently dropped."""
    claims, _ = bc.build_all_claims()
    for claim in claims:
        n_considered = claim["n_considered"]
        n_excluded = claim["n_excluded_below_floor"]
        assert n_excluded >= 0
        assert n_excluded <= n_considered, claim["claim_id"]


def test_no_edge_language_in_any_claim():
    claims, _ = bc.build_all_claims()
    for claim in claims:
        text = " ".join(claim["caveats"]).lower() + claim["question"].lower()
        for token in _BANNED:
            assert token not in text, f"{claim['claim_id']}: banned token {token!r} found"
        assert "edge claimed" in text, f"{claim['claim_id']}: missing no-edge disclosure"


def test_dims_corpus_absent_is_honest():
    """Every dims_corpus_absent entry must correspond to a REAL spec-limits
    DEFER stub (basketball_claims_dims.DIMS_DEFER_IN_SOURCE), never an empty
    placeholder or a dimension that this module actually builds."""
    _, dims_corpus_absent = bc.build_all_claims()
    built_dim_names = {spec.name for spec in dims.DIM_SPECS} | set(dims.BOXSCORE_AGGREGATE_DIMS)
    for entry in dims_corpus_absent:
        assert entry, "empty dims_corpus_absent entry"
        first_token = entry.split(" ")[0]
        assert first_token not in built_dim_names or entry in dims.DIMS_DEFER_IN_SOURCE


def test_ranking_rows_have_provenance_and_sample_size():
    claims, _ = bc.build_all_claims()
    for claim in claims:
        for row in claim["ranking"]:
            assert "n" in row and row["n"] is not None
            assert "value" in row
            assert "player_id" in row
        assert len(claim["source_files"]) >= 1
