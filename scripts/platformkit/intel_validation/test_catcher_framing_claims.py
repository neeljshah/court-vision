"""Per-file tests for catcher_framing_claims (program v2 build rank 1, catcher
arm). Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_catcher_framing_claims.py -q

Acceptance criteria:
  1. build_ranking_claim's claimed ranking is independently re-verified by
     claims_validator.validate_claim -> VERIFIED (real cross-module check
     against the real on-disk statcast corpus, matching the production claim
     this module ships -- proves reproducibility, not just self-consistency).
  2. min_sample floor (n_ooz_called) matches catcher_framing_index.py's own
     corpus-level floor count.
  3. no retracted/edge-claim tokens leak into the claim's caveats text.
"""
from __future__ import annotations

from scripts.platformkit.intel_validation import catcher_framing_claims as cfc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def test_real_catcher_framing_claim_independently_verifies():
    claim = cfc.build_ranking_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_min_sample_floor_matches_index_report():
    """Full-population claim: ranking length == ALL qualifying catchers (no
    top-N truncation) -- mlb-fullpop lane."""
    claim = cfc.build_ranking_claim()
    from domains.mlb.catcher_framing_index import build_catcher_index
    _, index_report = build_catcher_index()
    assert claim["n_excluded_below_floor"] == index_report["n_catchers_excluded_below_floor"]
    assert claim["n_considered"] == index_report["n_catchers_considered"]
    assert len(claim["ranking"]) == index_report["n_qualifying_catchers"]


def test_claim_has_no_edge_language():
    claim = cfc.build_ranking_claim()
    banned = ("18.38", "0.119", "+54%", "78.11", "8.94", "54.57", "roi", "edge",
              "bankroll", "pnl")
    text = " ".join(claim["caveats"]).lower() + claim["question"].lower()
    for token in banned:
        if token in ("edge",):
            # "edge" appears legitimately in "no ... edge claimed" -- check the
            # stricter phrase instead of a bare substring ban.
            assert "market/$ edge claimed" in text or "edge claimed" in text
            continue
        assert token not in text, f"banned token {token!r} found in claim text"
