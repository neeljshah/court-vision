"""Per-file tests for h2h_index_claims (program v2, lane tennis-h2h-claims --
FIRST real exercise of the pair-keyed claims contract path).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    domains/tennis/test_h2h_index_claims.py -q

Acceptance criteria:
  1. _canonical_pair_dominance aggregates UNDIRECTED -- matches where a pair
     appears with p1/p2 swapped across rows still aggregate into ONE pair row.
  2. min_sample floor (meetings) actually excludes below-floor pairs.
  3. build_h2h_dominance_claim's claimed ranking is independently re-verified
     by claims_validator.validate_claim -> VERIFIED (real cross-module check,
     entity_key=[p1_id, p2_id] pair-keyed path).
  4. build_playstyle_claim's claimed ranking is independently re-verified ->
     VERIFIED (scalar entity_key=player_id path, unchanged contract).
"""
from __future__ import annotations

import pandas as pd

from domains.tennis import h2h_index_claims as hic
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_h2h() -> pd.DataFrame:
    # Pair (1,2): 3 meetings, p1/p2 swapped across rows, id1 wins all 3.
    # Pair (2,3): 1 meeting, below a floor of 2.
    return pd.DataFrame({
        "p1_id": [1, 2, 1, 2],
        "p2_id": [2, 1, 2, 3],
        "p1_name": ["Alice", "Bob", "Alice", "Bob"],
        "p2_name": ["Bob", "Alice", "Bob", "Carol"],
        "winner": [1, 2, 1, 1],  # row0: p1(1) wins; row1: p2(1) wins; row2: p1(1) wins; row3: p1(2) wins
    })


def test_canonical_pair_dominance_is_undirected():
    table = hic._canonical_pair_dominance(_fixture_h2h())
    pair_1_2 = table[(table["lo_id"] == 1) & (table["hi_id"] == 2)]
    assert len(pair_1_2) == 1  # one aggregate row despite p1/p2 swapping across match rows
    row = pair_1_2.iloc[0]
    assert row["meetings"] == 3
    assert row["wins_lo"] == 3  # player 1 (lo_id) won all 3
    assert row["dominance"] == 1.0


def test_min_sample_floor_excludes_below_floor_pairs(monkeypatch, tmp_path):
    monkeypatch.setattr(hic, "MIN_MEETINGS", 2)
    monkeypatch.setattr(hic, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(hic, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pd, "read_parquet", lambda *_a, **_k: _fixture_h2h())

    def _fake_build_h2h_side_table():
        h2h = _fixture_h2h()
        table = hic._canonical_pair_dominance(h2h)
        n_considered = len(table)
        n_excluded = int((table["meetings"] < hic.MIN_MEETINGS).sum())
        return tmp_path / "side.parquet", table, n_considered, n_excluded

    monkeypatch.setattr(hic, "build_h2h_side_table", _fake_build_h2h_side_table)
    claim = hic.build_h2h_dominance_claim()
    pairs = {(r["p1_id"], r["p2_id"]) for r in claim["ranking"]}
    assert (2, 3) not in pairs  # excluded: meetings=1 < floor 2
    assert claim["n_excluded_below_floor"] == 1


def test_real_h2h_dominance_claim_independently_verifies():
    """Cross-module check against the REAL on-disk atlas_h2h.parquet --
    proves the pair-keyed ranking is independently reproducible by
    claims_validator's entity_key=[list] path, not just self-consistent."""
    claim = hic.build_h2h_dominance_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_playstyle_claim_independently_verifies():
    """Cross-module check against the REAL on-disk atlas_playstyles.parquet --
    scalar entity_key=player_id path, unchanged contract."""
    claim = hic.build_playstyle_claim()
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
