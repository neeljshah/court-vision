"""Per-file tests for mlb_pitcher_putaway_claims (matchup lane). Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_mlb_pitcher_putaway_claims.py -q

Acceptance criteria:
  1. The real claim's ranking is independently re-verified by
     claims_validator.validate_claim -> VERIFIED (cross-module check against
     the real on-disk statcast corpus).
  2. min_sample floor (n_k) matches the snapshot's own floor-applied count.
  3. no retracted/edge-claim tokens leak into the claim's caveats text.
"""
from __future__ import annotations

from scripts.platformkit.intel_validation import mlb_pitcher_putaway_claims as ppc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def test_real_putaway_claim_independently_verifies():
    claim = ppc.build_ranking_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_min_sample_floor_matches_snapshot_qualifying_count():
    claim = ppc.build_ranking_claim()
    _, snap_report = ppc.build_snapshot()
    assert claim["n_excluded_below_floor"] == (
        snap_report["n_pitchers_considered"] - snap_report["n_pitchers_qualifying"]
    )
    assert len(claim["ranking"]) == snap_report["n_pitchers_qualifying"]


def test_claim_has_no_edge_language():
    claim = ppc.build_ranking_claim()
    banned = ("18.38", "0.119", "+54%", "78.11", "8.94", "54.57", "roi", "bankroll", "pnl")
    text = " ".join(claim["caveats"]).lower() + claim["question"].lower()
    for token in banned:
        assert token not in text, f"banned token {token!r} found in claim text"
    assert "no forecasting/market/$ edge claimed" in text
