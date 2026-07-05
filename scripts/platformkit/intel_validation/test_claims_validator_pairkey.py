"""Per-file test for the pair-keyed entity_key extension to claims_validator
(mission spine 5, lane tennis-h2h-claims -- FIRST real exercise of the
pair-keyed contract path).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_claims_validator_pairkey.py -q

Acceptance criteria:
  1. entity_key as a LIST of columns (e.g. [p1_id, p2_id]) is independently
     recomputable: a well-formed pair-keyed claim -> VERIFIED.
  2. A claimed value that disagrees with the recompute -> MISMATCH (still
     fails closed with a pair-keyed id_col, no crash on the dict-key path).
  3. Back-compat: every EXISTING real ranking-claims artifact (scalar
     entity_key, i.e. player_id/pitcher_id/team_id, including claims that
     predate the entity_key field entirely) still VERIFIES unchanged.
"""
from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.platformkit.intel_validation.claims_validator import (
    validate_claim,
    validate_claims_file,
)


def _write_pair_source(tmp_path) -> str:
    df = pd.DataFrame({
        "p1_id": [1, 1, 2],
        "p2_id": [2, 3, 3],
        "wins_p1": [3, 1, 4],
        "meetings": [4, 2, 5],
    })
    path = tmp_path / "pair_source.parquet"
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)
    return str(path)


def _base_pair_claim(source_path: str) -> dict:
    return {
        "claim_id": "fixture_h2h_claim",
        "kind": "ranking",
        "question": "fixture pair-keyed dominance ranking",
        "criteria": {
            "metric": "dominance",
            "formula": "wins_p1 / meetings",
            "min_sample": {"meetings": 2},
            "direction": "desc",
            "value_precision": 3,
            "entity_key": ["p1_id", "p2_id"],
        },
        "ranking": [
            {"rank": 1, "p1_id": 2, "p2_id": 3, "value": 0.8, "n": 5},
            {"rank": 2, "p1_id": 1, "p2_id": 2, "value": 0.75, "n": 4},
        ],
        "source_files": [source_path],
        "computed_at": "2026-07-04T00:00:00+00:00",
        "n_considered": 3,
        "n_excluded_below_floor": 0,
        "caveats": ["fixture -- descriptive only, no market edge claimed"],
    }


def test_pairkeyed_wellformed_claim_verifies(tmp_path):
    source_path = _write_pair_source(tmp_path)
    claim = _base_pair_claim(source_path)
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_pairkeyed_mismatch_fails_closed_no_crash(tmp_path):
    source_path = _write_pair_source(tmp_path)
    claim = _base_pair_claim(source_path)
    claim["ranking"][0]["value"] = 0.999  # disagrees with recomputed 0.8
    verdict = validate_claim(claim)
    assert verdict.verdict == "MISMATCH"
    assert verdict.first_divergence is not None


def test_pairkeyed_wrong_pair_is_mismatch_not_crash(tmp_path):
    source_path = _write_pair_source(tmp_path)
    claim = _base_pair_claim(source_path)
    claim["ranking"][0]["p1_id"] = 999  # no such pair in recomputed top ranks
    verdict = validate_claim(claim)
    assert verdict.verdict == "MISMATCH"


def test_backcompat_scalar_entity_key_claims_still_verify():
    """Live proof: every real scalar-entity_key claims artifact this repo
    ships (including tennis_hold_claims, which predates entity_key on some
    rows) still validates identically after the pair-keyed extension."""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    fixtures = [
        ("data/cache/intel_claims/tennis_hold_claims.jsonl", 2, 2, 0, 0),
        ("data/cache/intel_claims/mlb_pitcher_claims.jsonl", 1, 1, 0, 0),
        ("data/cache/intel_claims/soccer_intl_strength_claims.jsonl", 1, 1, 0, 0),
    ]
    for rel, n_claims, n_verified, n_mismatch, n_unverifiable in fixtures:
        path = repo_root / rel
        if not path.exists():
            import pytest
            pytest.skip(f"proof claims artifact not present in this checkout: {rel}")
        summary = validate_claims_file(path)
        assert summary.n_claims == n_claims, rel
        assert summary.n_verified == n_verified, (rel, summary.details)
        assert summary.n_mismatch == n_mismatch, (rel, summary.details)
        assert summary.n_unverifiable == n_unverifiable, (rel, summary.details)
