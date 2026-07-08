"""Per-file tests for wnba_lineup_exposure_claims.

_rel() (reused from wnba_claims.py) requires source_files to live UNDER
REPO_ROOT (no try/except fallback, unlike claims_factory's _to_source_ref),
so fixtures are written to a scratch file under data/cache/ and removed in a
finally block -- never left on disk, never touching the real atlas output.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/intel_validation/test_wnba_lineup_exposure_claims.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation.claims_validator_batch import validate_claims_file_batched
from scripts.platformkit.intel_validation.wnba_lineup_exposure_claims import (
    REPO_ROOT, build_lineup_exposure_claim, write_claims,
)

_SCRATCH = REPO_ROOT / "data" / "cache" / "_test_scratch_lineup_exposure.parquet"


def _write_snapshot(path) -> None:
    df = pd.DataFrame([
        {"lineup_id": "T1__p1_p2_p3_p4_p5", "team_id": "T1",
         "lineup_player_ids": "p1,p2,p3,p4,p5", "lineup_player_names": "A,B,C,D,E",
         "n_games": 10, "minutes": 200.0, "minutes_share": 0.5,
         "pts_for": 400.0, "pts_against": 380.0, "net_pts": 20.0},
        {"lineup_id": "T1__p1_p2_p3_p4_p6", "team_id": "T1",
         "lineup_player_ids": "p1,p2,p3,p4,p6", "lineup_player_names": "A,B,C,D,F",
         "n_games": 2, "minutes": 30.0, "minutes_share": 0.075,
         "pts_for": 40.0, "pts_against": 50.0, "net_pts": -10.0},
    ])
    df.to_parquet(path, index=False)


def test_build_lineup_exposure_claim_ranks_and_applies_floor(tmp_path):
    try:
        _write_snapshot(_SCRATCH)
        claim = build_lineup_exposure_claim(_SCRATCH)
    finally:
        _SCRATCH.unlink(missing_ok=True)

    assert claim["edge_claimed"] is False
    assert claim["n_considered"] == 2
    assert claim["n_excluded_below_floor"] == 1  # n_games=2 < floor 3
    assert len(claim["ranking"]) == 1
    row = claim["ranking"][0]
    assert row["lineup_id"] == "T1__p1_p2_p3_p4_p5"
    assert row["value"] == 0.5
    assert row["pts_for"] == 400.0 and row["pts_against"] == 380.0 and row["net_pts"] == 20.0


def test_claim_round_trips_through_claims_validator_batch(tmp_path):
    try:
        _write_snapshot(_SCRATCH)
        claim = build_lineup_exposure_claim(_SCRATCH)
        out_path = write_claims([claim], tmp_path / "claims.jsonl")
        summary = validate_claims_file_batched(out_path)
    finally:
        _SCRATCH.unlink(missing_ok=True)

    assert summary.n_claims == 1
    assert summary.n_verified == 1
    assert summary.n_mismatch == 0
