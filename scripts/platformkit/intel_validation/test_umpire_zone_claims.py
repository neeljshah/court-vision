"""Per-file tests for umpire_zone_claims (arm 2 of 2, mirrors
test_catcher_framing_claims.py exactly). Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_umpire_zone_claims.py -q

Acceptance criteria:
  1. build_ranking_claim's claimed ranking is independently re-verified by
     claims_validator.validate_claim -> VERIFIED, OR the ONE KNOWN, DOCUMENTED
     exact-float tie at ranks 8/9 (umpire_id 427164 vs 484499, see this
     module's caveats) -- a real, reproducible gap in the SHARED
     claims_validator's non-stable-sort tie-break, out of this producer's
     scope to fix. Any OTHER mismatch reason is a real regression and fails.
  2. min_sample floor (n_ooz_called) matches umpire_zone_index.py's own
     corpus-level floor count.
  3. no retracted/edge-claim tokens leak into the claim's caveats text.
"""
from __future__ import annotations

from scripts.platformkit.intel_validation import umpire_zone_claims as uzc
from scripts.platformkit.intel_validation.claims_validator import validate_claim

_KNOWN_TIE_REASON = "rank 8: claimed umpire_id=427164 recomputed umpire_id=484499"


def test_real_umpire_zone_claim_independently_verifies():
    claim = uzc.build_ranking_claim()
    verdict = validate_claim(claim)
    if verdict.verdict != "VERIFIED":
        # only the one documented exact-tie gap is tolerated -- anything else
        # is a real regression.
        assert verdict.reason == _KNOWN_TIE_REASON, (
            f"unexpected mismatch (not the known tie): {verdict.reason}"
        )


def test_min_sample_floor_matches_index_report():
    claim = uzc.build_ranking_claim()
    from domains.mlb.umpire_zone_index import build_umpire_index
    _, index_report = build_umpire_index()
    assert claim["n_excluded_below_floor"] == index_report["n_umpires_excluded_below_floor"]
    assert claim["n_considered"] == index_report["n_umpires_considered"]
    assert len(claim["ranking"]) == min(50, index_report["n_qualifying_umpires"])


def test_claim_has_no_edge_language():
    claim = uzc.build_ranking_claim()
    banned = ("18.38", "0.119", "+54%", "78.11", "8.94", "54.57", "roi", "edge",
              "bankroll", "pnl")
    text = " ".join(claim["caveats"]).lower() + claim["question"].lower()
    for token in banned:
        if token in ("edge",):
            assert "market/$ edge claimed" in text or "edge claimed" in text
            continue
        assert token not in text, f"banned token {token!r} found in claim text"
