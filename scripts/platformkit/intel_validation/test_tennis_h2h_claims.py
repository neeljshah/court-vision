"""Per-file tests for tennis_h2h_claims (mission spine 5, lane
tennis-h2h-fullpairs).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_tennis_h2h_claims.py -q

Acceptance criteria:
  1. build_pair_table aggregates match rows into one row per (p1_id,p2_id)
     pair with correct wins_p1/meetings.
  2. build_ranking_claim's claimed ranking is independently re-verified by
     claims_validator.validate_claim -> VERIFIED (the real pair-keyed
     cross-module check, the FIRST production use of that path).
  3. min_sample floor (meetings) actually excludes below-floor pairs from
     the emitted ranking, and full population (no top-N cap) holds on the
     real on-disk h2h.parquet.
  4. Below-floor pairs are honestly counted, never silently dropped from
     n_considered.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import tennis_h2h_claims as thc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_h2h() -> pd.DataFrame:
    # 3 pairs: (1,2) 2 meetings, (1,3) 1 meeting (below floor 3), (2,3) 4 meetings
    return pd.DataFrame({
        "p1_id": [1, 1, 1, 2, 2, 2, 2],
        "p2_id": [2, 2, 3, 3, 3, 3, 3],
        "winner": [1, 2, 2, 1, 1, 2, 1],
        "p1_name": ["Alice", "Alice", "Alice", "Bob", "Bob", "Bob", "Bob"],
        "p2_name": ["Bob", "Bob", "Carol", "Carol", "Carol", "Carol", "Carol"],
    })


def test_build_pair_table_aggregates_wins_and_meetings():
    table = thc.build_pair_table(_fixture_h2h())
    assert len(table) == 3  # 3 distinct pairs

    pair_12 = table[(table["p1_id"] == 1) & (table["p2_id"] == 2)].iloc[0]
    assert pair_12["meetings"] == 2
    assert pair_12["wins_p1"] == 1  # one win (winner=1), one loss (winner=2)

    pair_13 = table[(table["p1_id"] == 1) & (table["p2_id"] == 3)].iloc[0]
    assert pair_13["meetings"] == 1
    assert pair_13["wins_p1"] == 0  # winner=2 (p3 won, since p1_id=3 there means p1=Carol)

    pair_23 = table[(table["p1_id"] == 2) & (table["p2_id"] == 3)].iloc[0]
    assert pair_23["meetings"] == 4
    assert pair_23["wins_p1"] == 3  # winner=1 three times, winner=2 once


def test_min_sample_floor_excludes_low_meetings_pairs(tmp_path, monkeypatch):
    monkeypatch.setattr(thc, "MIN_MEETINGS", 3)
    monkeypatch.setattr(thc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(thc, "_PAIR_PARQUET_OUT", tmp_path / "tennis_h2h_pairs_atp.parquet")
    monkeypatch.setattr(thc, "REPO_ROOT", tmp_path.parent)

    def _fake_read_parquet(path, *a, **kw):
        return _fixture_h2h()

    monkeypatch.setattr(pd, "read_parquet", _fake_read_parquet)
    claim = thc.build_ranking_claim()

    ranked_pairs = {(r["p1_id"], r["p2_id"]) for r in claim["ranking"]}
    # only (2,3) has meetings=4 >= floor 3; (1,2)=2 and (1,3)=1 are excluded
    assert ranked_pairs == {(2, 3)}
    assert claim["n_excluded_below_floor"] == 2
    assert claim["n_considered"] == 3
    assert len(claim["ranking"]) == 1


def test_real_atp_h2h_claim_independently_verifies():
    """Cross-module check against the REAL on-disk h2h.parquet -- proves the
    emitted pair-keyed ranking is independently reproducible by
    claims_validator (list entity_key path), not just self-consistent. This
    is the FIRST production exercise of the pair-keyed contract path
    (previously only fixture-tested in test_claims_validator_pairkey.py)."""
    claim = thc.build_ranking_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_atp_h2h_claim_is_full_pair_population():
    """The production ranking must cover EVERY qualifying pair above the
    min_sample floor, not a top-N slice."""
    claim = thc.build_ranking_claim()
    n_qualifying = claim["n_considered"] - claim["n_excluded_below_floor"]
    assert len(claim["ranking"]) == n_qualifying
    assert n_qualifying > 100, "expected the real ATP h2h qualifying pool to be large"
    assert claim["n_considered"] > n_qualifying, "some below-floor pairs must exist to prove honest counting"


def test_real_atp_h2h_claim_criteria_uses_pair_entity_key():
    claim = thc.build_ranking_claim()
    assert claim["criteria"]["entity_key"] == ["p1_id", "p2_id"]
    assert claim["criteria"]["min_sample"] == {"meetings": thc.MIN_MEETINGS}
