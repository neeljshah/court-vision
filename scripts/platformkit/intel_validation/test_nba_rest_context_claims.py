"""Per-file tests for nba_rest_context_claims (schedule/fatigue-conditioned
player splits), synthetic boxscore frame only (this worktree has no data/).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_nba_rest_context_claims.py -q

Acceptance:
  1. Leak-freeness: bucket assignment for a game never depends on a LATER
     game (appending a future row does not change earlier buckets).
  2. b2b classification + season-opener exclusion (opener never counted).
  3. Floor skip -- below-floor player excluded, honest n_excluded_below_floor.
  4. Caveat presence (DESCRIPTIVE_ONLY, non-random-schedule, floor text).
  5. Validator VERIFIED end-to-end on the snapshot this test builds.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import claims_validator
from scripts.platformkit.intel_validation import nba_rest_context_claims as rc

SEASON = "2024-25"


def _row(pid, name, date, fga, fta, pts, minutes):
    return {"game_id": f"{pid}_{date}", "date": pd.Timestamp(date), "season": SEASON,
            "player_id": pid, "player_name": name, "min": minutes, "pts": pts, "fga": fga, "fta": fta}


def _box() -> pd.DataFrame:
    rows = [
        # Alice: opener (excluded) + 2 b2b (gap=1, TS=1.0) + 2 rest2plus (gap>=2, TS=0.6)
        _row(1, "Alice", "2024-11-01", 5, 0, 10, 30),   # opener -- no prior date, excluded
        _row(1, "Alice", "2024-11-02", 5, 0, 10, 30),   # gap=1 -> b2b, TS=1.0
        _row(1, "Alice", "2024-11-05", 5, 0, 6, 30),    # gap=3 -> rest2plus, TS=0.6
        _row(1, "Alice", "2024-11-06", 5, 0, 10, 30),   # gap=1 -> b2b, TS=1.0
        _row(1, "Alice", "2024-11-10", 5, 0, 6, 30),    # gap=4 -> rest2plus, TS=0.6
        # Bob: opener + 1 b2b (below floor) + 2 rest2plus
        _row(2, "Bob", "2024-11-01", 5, 0, 5, 20),      # opener, excluded
        _row(2, "Bob", "2024-11-02", 5, 0, 5, 20),      # gap=1 -> b2b (only 1, below floor)
        _row(2, "Bob", "2024-11-06", 5, 0, 5, 20),      # gap=4 -> rest2plus
        _row(2, "Bob", "2024-11-10", 5, 0, 5, 20),      # gap=4 -> rest2plus
    ]
    return pd.DataFrame(rows)


@pytest.fixture()
def small_floors(monkeypatch):
    """Floors small enough for the compact synthetic fixture above (Alice:
    n_b2b=2, n_rest2plus=2, fga_total=20; Bob: n_b2b=1, below the b2b floor)."""
    monkeypatch.setattr(rc, "FLOOR_B2B", 2)
    monkeypatch.setattr(rc, "FLOOR_REST", 2)
    monkeypatch.setattr(rc, "FLOOR_FGA", 10)


def test_season_opener_excluded_from_both_buckets():
    rows = rc._rest_bucket_rows(_box(), SEASON)
    alice_dates = set(rows[rows["player_id"] == 1]["date"])
    assert pd.Timestamp("2024-11-01") not in alice_dates  # opener never bucketed


def test_b2b_and_rest_classification():
    rows = rc._rest_bucket_rows(_box(), SEASON)
    alice = rows[rows["player_id"] == 1].set_index("date")
    assert alice.loc[pd.Timestamp("2024-11-02"), "bucket"] == "b2b"       # gap=1
    assert alice.loc[pd.Timestamp("2024-11-05"), "bucket"] == "rest2plus"  # gap=3
    assert alice.loc[pd.Timestamp("2024-11-06"), "bucket"] == "b2b"       # gap=1
    assert alice.loc[pd.Timestamp("2024-11-10"), "bucket"] == "rest2plus"  # gap=4


def test_leak_free_appending_future_row_does_not_change_earlier_buckets():
    box = _box()
    rows_before = rc._rest_bucket_rows(box, SEASON)
    before_buckets = rows_before[rows_before["player_id"] == 1].set_index("date")["bucket"].to_dict()

    future = pd.concat([box, pd.DataFrame([_row(1, "Alice", "2024-12-25", 5, 0, 20, 30)])], ignore_index=True)
    rows_after = rc._rest_bucket_rows(future, SEASON)
    after_buckets = rows_after[rows_after["player_id"] == 1]
    after_buckets = after_buckets[after_buckets["date"] != pd.Timestamp("2024-12-25")].set_index("date")["bucket"].to_dict()

    assert before_buckets == after_buckets  # future row never retroactively changes earlier bucketing


def test_snapshot_values_and_floor_skip(small_floors):
    snap = rc.build_snapshot(_box(), SEASON)
    alice = snap[snap["player_id"] == 1].iloc[0]
    assert alice["n_b2b"] == 2 and alice["n_rest2plus"] == 2
    assert abs(alice["ts_b2b"] - 1.0) < 1e-9
    assert abs(alice["ts_rest2plus"] - 0.6) < 1e-9
    assert abs(alice["b2b_ts_drop"] - 0.4) < 1e-9

    claims = rc.build_claims_for_season(snap, SEASON, rc._OUT_DIR / "unused.parquet")
    drop_claim = next(c for c in claims if c["criteria"]["metric"] == "b2b_ts_drop")
    ranked_ids = {r["player_id"] for r in drop_claim["ranking"]}
    assert 1 in ranked_ids
    assert 2 not in ranked_ids  # Bob's n_b2b=1 < FLOOR_B2B=2
    assert drop_claim["n_excluded_below_floor"] == 1


def test_three_claims_built_with_expected_directions(small_floors):
    snap = rc.build_snapshot(_box(), SEASON)
    claims = rc.build_claims_for_season(snap, SEASON, rc._OUT_DIR / "unused.parquet")
    metrics = {c["criteria"]["metric"]: c["criteria"]["direction"] for c in claims}
    assert metrics == {"b2b_ts_drop": "asc", "b2b_min_delta": "desc", "b2b_pts36_delta": "desc"}


def test_honest_caveats_and_edge_claimed_false(small_floors):
    snap = rc.build_snapshot(_box(), SEASON)
    claims = rc.build_claims_for_season(snap, SEASON, rc._OUT_DIR / "unused.parquet")
    for claim in claims:
        assert claim["edge_claimed"] is False
        blob = json.dumps([claim["caveats"], claim["question"]]).lower()
        for word in ("roi", "pnl", "$", "bankroll", "edge"):
            assert word not in blob
        assert "descriptive" in blob
        assert "not random" in blob
        assert "floor" in blob.lower() or "n_b2b" in blob


def test_validator_verifies_end_to_end(small_floors, tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "REPO_ROOT", tmp_path.parent)
    snap = rc.build_snapshot(_box(), SEASON)
    snap_path = tmp_path / "snap.parquet"
    rc.write_snapshot(snap, snap_path)
    claims = rc.build_claims_for_season(snap, SEASON, snap_path)

    monkeypatch.setattr(claims_validator, "REPO_ROOT", tmp_path.parent)
    for claim in claims:
        verdict = claims_validator.validate_claim(claim)
        assert verdict.verdict == "VERIFIED", verdict.reason
