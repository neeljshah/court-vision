"""Per-file tests for tennis_hold_claims (mission spine 5, lane claims-breadth).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_tennis_hold_claims.py -q

Acceptance criteria:
  1. _reshape_long melts p1_/p2_ wide rows into one row per player per match.
  2. _season_snapshot keeps exactly one (most recent) row per player within
     the season window.
  3. build_ranking_claim's claimed ranking is independently re-verified by
     claims_validator.validate_claim -> VERIFIED (the real cross-module check).
  4. min_sample floor (n_prior) actually excludes below-floor players from
     the emitted ranking.
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import tennis_hold_claims as thc
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _fixture_matches() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": ["e1", "e2", "e3"],
        "date": [pd.Timestamp("2025-01-01").date(), pd.Timestamp("2025-02-01").date(),
                 pd.Timestamp("2025-03-01").date()],
        "p1_id": [1, 1, 2],
        "p2_id": [2, 3, 3],
        "p1_name": ["Alice", "Alice", "Carol"],
        "p2_name": ["Bob", "Carol", "Carol"],
    })


def _fixture_hold() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": ["e1", "e2", "e3"],
        "p1_hold_pct_asof": [0.70, 0.75, 0.60],
        "p2_hold_pct_asof": [0.50, 0.55, 0.65],
        "p1_n_prior": [10, 15, 5],
        "p2_n_prior": [3, 4, 20],
    })


def test_reshape_long_melts_p1_p2_into_one_row_each():
    long_df = thc._reshape_long(_fixture_matches(), _fixture_hold())
    # 3 matches x 2 players per match = 6 rows
    assert len(long_df) == 6
    assert set(long_df.columns) == {"player_id", "date", "hold_pct_asof", "n_prior"}
    # player 1 appears in e1 (as p1) and e2 (as p1) -> 2 rows
    assert (long_df["player_id"] == 1).sum() == 2


def test_season_snapshot_keeps_one_most_recent_row_per_player():
    long_df = thc._reshape_long(_fixture_matches(), _fixture_hold())
    snap = thc._season_snapshot(long_df, "2025")
    # 3 distinct players (1, 2, 3) -> exactly 3 rows, one each
    assert len(snap) == 3
    assert sorted(snap["player_id"].tolist()) == [1, 2, 3]
    # player 1's most recent 2025 row is e2 (p1_hold_pct_asof=0.75), not e1's 0.70
    p1_row = snap[snap["player_id"] == 1].iloc[0]
    assert p1_row["hold_pct_asof"] == 0.75


def test_min_sample_floor_excludes_low_n_prior_players(tmp_path, monkeypatch):
    # Player 2 (p1 in e3, n_prior=5) is below a 10-floor; player 3 (p2 in e3,
    # n_prior=20) and player 1 (n_prior=15 at e2) clear it.
    monkeypatch.setattr(thc, "MIN_N_PRIOR", 10)
    monkeypatch.setattr(thc, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(thc, "REPO_ROOT", tmp_path.parent)

    def _fake_build_tour_snapshot(tour):
        matches = _fixture_matches()
        hold = _fixture_hold()
        out_path = tmp_path / f"tennis_hold_snapshot_{tour}.parquet"
        long_df = thc._reshape_long(matches, hold)
        snapshot = thc._season_snapshot(long_df, thc.SEASON_WINDOW)
        n_considered = len(snapshot)
        n_excluded = int((snapshot["n_prior"] < thc.MIN_N_PRIOR).sum())
        import pyarrow as pa
        import pyarrow.parquet as pq
        write_cols = snapshot[["player_id", "hold_pct_asof", "n_prior"]].copy()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(write_cols, preserve_index=False), out_path)
        names = thc._name_lookup(matches)
        snapshot = snapshot.copy()
        snapshot["player_name"] = snapshot["player_id"].map(lambda pid: names.get(int(pid), "Unknown"))
        return out_path, snapshot, n_considered, n_excluded

    monkeypatch.setattr(thc, "build_tour_snapshot", _fake_build_tour_snapshot)
    claim = thc.build_ranking_claim("atp")
    ranked_ids = {r["player_id"] for r in claim["ranking"]}
    assert 2 not in ranked_ids  # excluded: n_prior=5 < floor 10
    assert claim["n_excluded_below_floor"] == 1
    # FULL POPULATION: both qualifiers (players 1 and 3) are ranked -- no
    # top-N slice truncates a 2-row qualifying pool.
    assert ranked_ids == {1, 3}
    assert len(claim["ranking"]) == 2


def test_real_atp_claim_independently_verifies():
    """Cross-module check against the REAL on-disk parquets (matches the
    production ATP claim this module ships) -- proves the emitted ranking
    is independently reproducible by claims_validator, not just self-consistent."""
    claim = thc.build_ranking_claim("atp")
    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason


def test_real_atp_claim_is_full_population_not_top_50():
    """The production ATP ranking must cover EVERY qualifying player above
    the min_sample floor, not a top-50 slice -- this is the uncap this
    module exists to prove. n_considered - n_excluded_below_floor is the
    true qualifying pool size; the ranking must match it exactly."""
    claim = thc.build_ranking_claim("atp")
    n_qualifying = claim["n_considered"] - claim["n_excluded_below_floor"]
    assert len(claim["ranking"]) == n_qualifying
    assert n_qualifying > 50, "expected the real ATP 2025 qualifying pool to exceed the old TOP_N=50 cap"
    assert not hasattr(thc, "TOP_N"), "TOP_N cap must be fully removed, not just unused"
