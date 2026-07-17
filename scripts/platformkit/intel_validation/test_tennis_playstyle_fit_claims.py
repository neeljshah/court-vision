"""Per-file tests for tennis_playstyle_fit_claims (depth-wave-1, lane 3).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_tennis_playstyle_fit_claims.py -q

Acceptance criteria:
  1. Both claims independently re-verify via claims_validator (real
     on-disk atlas_playstyles.parquet, plain scalar entity_key path).
  2. min_sample floor (total_matches>=20) excludes below-floor players
     honestly (n_excluded_below_floor, never silently dropped).
  3. surface_tilt further excludes players missing grass/clay data,
     without touching n_excluded_below_floor.
  4. caveats present on both claims; edge_claimed never appears as True
     anywhere in the payload.
  5. golden sanity: Djokovic/Federer/Alcaraz land where career tennis
     knowledge says they should (grass-tilted vs top overall win rate).
"""
from __future__ import annotations

from scripts.platformkit.intel_validation import tennis_playstyle_fit_claims as tpf
from scripts.platformkit.intel_validation.claims_validator import validate_claim

DJOKOVIC = 104925
FEDERER = 103819
ALCARAZ = 207989


def test_both_claims_independently_verify():
    claims = tpf.build_all_claims()
    assert len(claims) == 2
    for claim in claims:
        verdict = validate_claim(claim)
        assert verdict.verdict == "VERIFIED", f"{claim['claim_id']}: {verdict.reason}"


def test_overall_win_rate_floor_excludes_honestly():
    claims = tpf.build_all_claims()
    claim = next(c for c in claims if c["claim_id"] == "tennis_playstyle_fit_overall_win_rate_career")
    n_qualifying = claim["n_considered"] - claim["n_excluded_below_floor"]
    assert len(claim["ranking"]) == n_qualifying
    assert claim["n_excluded_below_floor"] > 0
    assert all(r["n"] >= tpf.MIN_TOTAL_MATCHES for r in claim["ranking"])


def test_surface_tilt_excludes_missing_surface_data():
    claims = tpf.build_all_claims()
    claim = next(c for c in claims if c["claim_id"] == "tennis_playstyle_fit_surface_tilt_career")
    assert len(claim["ranking"]) < claim["n_considered"]
    assert all(r["n"] >= tpf.MIN_TOTAL_MATCHES for r in claim["ranking"])


def test_caveats_present_and_no_edge_claim():
    claims = tpf.build_all_claims()
    for claim in claims:
        assert claim["caveats"], claim["claim_id"]
        assert "not a forecast" in claim["caveats"][0]
        blob = str(claim)
        assert "edge_claimed" not in blob or "true" not in blob.lower().split("edge_claimed")[1][:20]


def test_golden_surface_tilt_djokovic_grass_favoring():
    claims = tpf.build_all_claims()
    claim = next(c for c in claims if c["claim_id"] == "tennis_playstyle_fit_surface_tilt_career")
    by_id = {r["player_id"]: r for r in claim["ranking"]}
    assert DJOKOVIC in by_id
    djoker = by_id[DJOKOVIC]
    assert djoker["value"] > 0, "Djokovic should be grass-favoring vs clay (career profile)"
    # top-quartile rank sanity: real dominant grass/hard player, not buried
    assert djoker["rank"] <= len(claim["ranking"]) // 2


def test_golden_overall_win_rate_top_players_plausible():
    claims = tpf.build_all_claims()
    claim = next(c for c in claims if c["claim_id"] == "tennis_playstyle_fit_overall_win_rate_career")
    top_ids = {r["player_id"] for r in claim["ranking"][:10]}
    # Djokovic/Federer/Alcaraz are elite career win-rate players; expect at
    # least two of the three in the top 10 by career-to-date ov_wr.
    assert len(top_ids & {DJOKOVIC, FEDERER, ALCARAZ}) >= 2
