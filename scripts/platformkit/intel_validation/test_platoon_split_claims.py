"""Per-file tests for platoon_split_claims (LANE platoon-caveat-fix).
Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_platoon_split_claims.py -q

Acceptance criteria:
  1. build_ranking_claim's claimed ranking is independently re-verified by
     claims_validator.validate_claim -> VERIFIED against the real on-disk
     statcast corpus.
  2. min_sample floor counts match platoon_split_index.py's own corpus-level
     report.
  3. no retracted/edge-claim tokens leak into the claim's caveats text.
  4. the sample-floor caveat is DYNAMIC: pinned to match reality in BOTH
     branches (0 qualifiers -> honest-empty sentence; N>0 -> true count +
     no self-contradiction with the "(N/M batters qualify)" prefix), driven
     directly off _sample_floor_caveat given an index_report, not a
     hardcoded corpus-state assertion.
"""
from __future__ import annotations

from scripts.platformkit.intel_validation import platoon_split_claims as psc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def test_real_platoon_split_claim_independently_verifies():
    claim = psc.build_ranking_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_min_sample_floor_matches_index_report():
    claim = psc.build_ranking_claim()
    from domains.mlb.platoon_split_index import build_platoon_snapshot
    _, index_report = build_platoon_snapshot()
    assert claim["n_considered"] == index_report["n_batters_considered"]
    assert claim["n_excluded_below_floor"] == index_report["n_batters_excluded_below_floor"]
    assert len(claim["ranking"]) == min(50, index_report["n_qualifying_batters"])


def test_claim_has_no_edge_language():
    claim = psc.build_ranking_claim()
    banned = ("18.38", "0.119", "+54%", "78.11", "8.94", "54.57", "roi", "edge",
              "bankroll", "pnl")
    text = " ".join(claim["caveats"]).lower() + claim["question"].lower()
    for token in banned:
        if token in ("edge",):
            assert "market/$ edge claimed" in text or "edge claimed" in text
            continue
        assert token not in text, f"banned token {token!r} found in claim text"


def test_sample_floor_caveat_nonzero_branch_matches_reality():
    """Live corpus branch: N>0 qualifiers -> caveat states the TRUE count and
    does not claim the ranking is empty (this is the bug this LANE fixes)."""
    from domains.mlb.platoon_split_index import build_platoon_snapshot
    _, index_report = build_platoon_snapshot()
    caveat = psc._sample_floor_caveat(index_report)

    n_qual = index_report["n_qualifying_batters"]
    n_considered = index_report["n_batters_considered"]
    assert f"{n_qual}/{n_considered} batters qualify" in caveat
    if n_qual > 0:
        assert "legitimately empty" not in caveat
        assert "0 batters currently clear the floor" not in caveat
        assert str(n_qual) in caveat


def test_sample_floor_caveat_zero_branch_is_honest_empty():
    """Synthetic 0-qualifier report -> the honest-empty sentence, proving the
    caveat is derived from n_qualifying_batters, not hardcoded."""
    synthetic_report = {
        "n_qualifying_batters": 0,
        "n_batters_considered": 730,
        "seasons": [2022, 2023],
        "max_pa_vs_l_any_batter": 57,
        "max_pa_vs_r_any_batter": 61,
    }
    caveat = psc._sample_floor_caveat(synthetic_report)
    assert "0/730 batters qualify" in caveat
    assert "legitimately empty" in caveat
    assert "0 batters currently clear the floor" in caveat


def test_sample_floor_caveat_nonzero_synthetic_branch():
    """Synthetic N>0 report -> real-result sentence, no empty-ranking claim,
    no self-contradiction with the qualify-count prefix."""
    synthetic_report = {
        "n_qualifying_batters": 231,
        "n_batters_considered": 730,
        "seasons": [2022, 2023],
        "max_pa_vs_l_any_batter": 261,
        "max_pa_vs_r_any_batter": 641,
    }
    caveat = psc._sample_floor_caveat(synthetic_report)
    assert "231/730 batters qualify" in caveat
    assert "legitimately empty" not in caveat
    assert "real, non-empty result" in caveat
