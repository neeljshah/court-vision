"""Per-file tests for tennis_serve_asof_claims -- synthetic frames only (no
real corpus reads).

Acceptance criteria:
  1. _reshape_long melts p1_/p2_ wide rows into one row per player per match
     for all 3 metric columns at once (identity round-trip vs tennis_hold_
     claims's single-metric reshape).
  2. _season_snapshot keeps exactly one (most recent) row per player within
     the season window -- leak-free-by-construction identity: the row kept
     is the LATEST as-of snapshot, never a future one.
  3. min_sample floor (n_prior) excludes below-floor players from the
     emitted ranking, and the excluded count is reported honestly.
  4. The emitted claim independently re-verifies via claims_validator.
     validate_claim -> VERIFIED (real cross-module check against a
     synthetic on-disk snapshot, not the producer's own in-memory frame).

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_tennis_serve_asof_claims.py -q
"""
from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import tennis_serve_asof_claims as tsc


def _matches_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": ["e1", "e2", "e3"],
        "date": ["2025-01-01", "2025-02-01", "2025-03-01"],
        "p1_id": [1, 1, 3], "p2_id": [2, 4, 1],
        "p1_name": ["Alice", "Alice", "Carol"], "p2_name": ["Bob", "Dan", "Alice"],
    })


def _features_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": ["e1", "e2", "e3"],
        "p1_1st_win_asof": [0.70, 0.75, 0.55], "p2_1st_win_asof": [0.60, 0.65, 0.72],
        "p1_2nd_win_asof": [0.50, 0.52, 0.45], "p2_2nd_win_asof": [0.48, 0.49, 0.53],
        "p1_bp_saved_asof": [0.60, 0.62, 0.58], "p2_bp_saved_asof": [0.55, 0.56, 0.61],
        "p1_n_prior": [10, 15, 5], "p2_n_prior": [3, 4, 20],
    })


def test_reshape_long_melts_all_three_metrics_per_row():
    long_df = tsc._reshape_long(_matches_frame(), _features_frame())
    assert len(long_df) == 6  # 3 matches x 2 players
    assert set(long_df.columns) == {"player_id", "player_name", "date", "n_prior", *tsc._RAW_COLS}
    # Alice (id=1) appears in e1 (as p1), e2 (as p1), and e3 (as p2) -> 3 rows
    assert (long_df["player_id"] == 1).sum() == 3


def test_season_snapshot_keeps_most_recent_row_per_player():
    long_df = tsc._reshape_long(_matches_frame(), _features_frame())
    snap = tsc._season_snapshot(long_df, "2025")
    assert len(snap) == 4  # players 1,2,3,4
    alice = snap[snap["player_id"] == 1].iloc[0]
    # Alice's most recent 2025 row is e3 (date=2025-03-01, as p2: p2_1st_win_asof=0.72),
    # not e2's earlier 0.75 -- the leak-free-by-construction identity: LATEST row wins.
    assert alice["1st_win_asof"] == pytest.approx(0.72)


def test_min_sample_floor_excludes_low_n_prior(tmp_path, monkeypatch):
    monkeypatch.setattr(tsc, "MIN_N_PRIOR", 10)
    monkeypatch.setattr(tsc, "REPO_ROOT", tmp_path)
    matches_path = tmp_path / "matches.parquet"
    features_path = tmp_path / "asof_features.parquet"
    pq.write_table(pa.Table.from_pandas(_matches_frame(), preserve_index=False), matches_path)
    pq.write_table(pa.Table.from_pandas(_features_frame(), preserve_index=False), features_path)
    out_path = tmp_path / "tennis_serve_asof_snapshot_atp.parquet"

    snapshot_path, snapshot = tsc.build_snapshot(matches_path, features_path, out_path)
    claim = tsc.build_metric_claim("first_serve_win_pct_asof", snapshot_path, snapshot)

    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    # player 3 (Carol, e3 p1, n_prior=5) is below floor=10 -> excluded
    assert 3 not in ranked_ids
    # players 1 (n_prior=15 at e2), 2 (n_prior=3 -> ALSO excluded), 4 (n_prior=4 -> excluded)
    assert ranked_ids == {1}
    assert claim["n_excluded_below_floor"] == 3


def test_claim_independently_verifies_against_synthetic_snapshot(tmp_path, monkeypatch):
    """Cross-module check: write a synthetic snapshot + claim, then run the
    REAL claims_validator.validate_claim against it (both modules'
    REPO_ROOT monkeypatched to the same tmp_path so source_files resolves)."""
    monkeypatch.setattr(tsc, "MIN_N_PRIOR", 3)
    matches_path = tmp_path / "matches.parquet"
    features_path = tmp_path / "asof_features.parquet"
    pq.write_table(pa.Table.from_pandas(_matches_frame(), preserve_index=False), matches_path)
    pq.write_table(pa.Table.from_pandas(_features_frame(), preserve_index=False), features_path)
    out_path = tmp_path / "data" / "cache" / "intel_claims" / "tennis_serve_asof_snapshot_atp.parquet"

    monkeypatch.setattr(tsc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(claims_validator, "REPO_ROOT", tmp_path)

    snapshot_path, snapshot = tsc.build_snapshot(matches_path, features_path, out_path)
    claim = tsc.build_metric_claim("bp_saved_pct_asof", snapshot_path, snapshot)

    verdict = claims_validator.validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
