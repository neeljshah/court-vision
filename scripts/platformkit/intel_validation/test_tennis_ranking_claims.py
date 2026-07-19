"""Per-file tests for tennis_ranking_claims -- synthetic frames only (no real
corpus reads): hand-computed higher-rank-wins/rank_gap/bucket, tie/NaN
exclusion (leak-free identity: only a genuine pre-match rank difference ever
enters the aggregate), cut-ranking floor exclusion + two-direction symmetry,
seed_hold_rate hand-computed, and player last-seen-rank snapshot ordering.

Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_tennis_ranking_claims.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.intel_validation import tennis_ranking_claims as trc


def _matches_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": ["e1", "e2", "e3", "e4", "e5"],
        "date": ["2025-01-01", "2025-01-05", "2025-02-01", "2025-02-05", "2025-03-01"],
        "p1_id": [1, 3, 1, 5, 1], "p2_id": [2, 4, 5, 6, 2],
        "p1_name": ["Alice", "Carol", "Alice", "Eve", "Alice"],
        "p2_name": ["Bob", "Dan", "Eve", "Frank", "Bob"],
        "p1_rank": [10.0, 50.0, 10.0, 100.0, 5.0], "p2_rank": [20.0, 50.0, 100.0, 5.0, 20.0],
        "winner": [1, 1, 1, 2, 1],  # e2: tied ranks; e3: favorite(p1,10) wins; e4: favorite(p2,5) wins
        "surface": ["Hard", "Hard", "Clay", "Clay", "Hard"],
        "tourney_level": ["G", "A", "G", "A", "G"],
    })


def test_match_favorite_frame_ties_and_hand_computed():
    fav = trc._match_favorite_frame(_matches_frame())
    # e2 (tied rank 50/50) must be excluded -- "who is higher-ranked" is undefined
    assert "e2" not in set(fav["event_id"])
    assert len(fav) == 4

    row_e1 = fav.set_index("event_id").loc["e1"]
    assert row_e1["higher_rank_wins"] == True  # p1 rank=10 < p2 rank=20, winner=1 (favorite) -> True
    assert row_e1["rank_gap"] == pytest.approx(10.0)
    assert row_e1["rank_gap_bucket"] == "6-20"

    row_e4 = fav.set_index("event_id").loc["e4"]
    # p1_rank=100, p2_rank=5 -> favorite is p2; winner=2 -> favorite won -> True
    assert row_e4["higher_rank_wins"] == True
    assert row_e4["rank_gap_bucket"] == "50+"

    row_e3 = fav.set_index("event_id").loc["e3"]
    # p1_rank=10 (favorite), p2_rank=100, winner=1 -> favorite won -> True
    assert row_e3["higher_rank_wins"] == True


def test_bucket_rank_gap_boundaries():
    assert trc._bucket_rank_gap(5) == "1-5"
    assert trc._bucket_rank_gap(6) == "6-20"
    assert trc._bucket_rank_gap(20) == "6-20"
    assert trc._bucket_rank_gap(21) == "21-50"
    assert trc._bucket_rank_gap(50) == "21-50"
    assert trc._bucket_rank_gap(51) == "50+"


def _favorite_frame_for_cuts() -> pd.DataFrame:
    """A synthetic favorite-frame with a Hard-surface cut that clears a
    small floor and a Clay cut that does not."""
    rows = []
    for i in range(12):
        rows.append({"surface": "Hard", "tourney_level": "G", "higher_rank_wins": i < 9,  # 9/12 = 0.75
                      "rank_gap": 10, "rank_gap_bucket": "6-20"})
    for i in range(3):
        rows.append({"surface": "Clay", "tourney_level": "G", "higher_rank_wins": i < 1,  # 1/3, below floor
                      "rank_gap": 10, "rank_gap_bucket": "6-20"})
    return pd.DataFrame(rows)


def test_cut_ranking_claims_floor_exclusion_and_two_directions(tmp_path, monkeypatch):
    monkeypatch.setattr(trc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(trc, "_OUT_DIR", tmp_path / "intel_claims")
    monkeypatch.setattr(trc, "CUT_FLOOR", 10)

    claims = trc._cut_ranking_claims(_favorite_frame_for_cuts(), "surface", "surface", "atp")
    assert len(claims) == 2  # favorites_dominate + most_upset_prone
    for c in claims:
        # Clay (n=3) excluded by CUT_FLOOR=10; only Hard (n=12) qualifies
        assert {r["surface"] for r in c["ranking"]} == {"Hard"}
        assert c["n_excluded_below_floor"] == 1
        assert c["ranking"][0]["value"] == pytest.approx(0.75)

    desc_claim = next(c for c in claims if c["criteria"]["direction"] == "desc")
    asc_claim = next(c for c in claims if c["criteria"]["direction"] == "asc")
    assert desc_claim["ranking"][0]["value"] == asc_claim["ranking"][0]["value"]  # only 1 qualifier either way


def _write_parquet(df: pd.DataFrame, path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path)


def test_seed_hold_claim_hand_computed(tmp_path, monkeypatch):
    matches = pd.DataFrame({
        "event_id": ["e1", "e2", "e3", "e4"],
        "winner": [1, 2, 1, 1],
        "tourney_level": ["G", "G", "G", "G"],
    })
    meta = pd.DataFrame({
        "event_id": ["e1", "e2", "e3", "e4"],
        # e1: p1 seeded, p2 not -> seeded(p1) won (winner=1) -> seed_hold True
        # e2: p1 seeded, p2 not -> unseeded(p2) won (winner=2) -> seed_hold False
        # e3: both seeded -> excluded (undefined)
        # e4: neither seeded -> excluded (undefined)
        "p1_seed": [3.0, 5.0, 1.0, None], "p2_seed": [None, None, 2.0, None],
    })
    matches_path = tmp_path / "matches.parquet"
    meta_path = tmp_path / "asof_meta.parquet"
    _write_parquet(matches, matches_path)
    _write_parquet(meta, meta_path)

    monkeypatch.setattr(trc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(trc, "_OUT_DIR", tmp_path / "intel_claims")
    monkeypatch.setitem(trc._MATCHES, "atp", matches_path)
    monkeypatch.setattr(trc, "_ASOF_META_ATP", meta_path)
    monkeypatch.setattr(trc, "CUT_FLOOR", 2)  # only e1+e2 survive the exactly-one-seeded filter

    claim = trc._seed_hold_claim("atp")
    assert claim is not None
    row = claim["ranking"][0]
    assert row["tourney_level"] == "G"
    assert row["value"] == pytest.approx(0.5)  # 1 of 2 (e1,e2) seed holds
    assert row["n"] == 2


def test_player_rank_snapshot_keeps_last_seen_and_orders_ascending(tmp_path, monkeypatch):
    matches = pd.DataFrame({
        "event_id": ["e1", "e2", "e3"],
        "date": ["2025-01-01", "2025-02-01", "2025-03-01"],
        "p1_id": [1, 1, 2], "p2_id": [2, 3, 1],
        "p1_name": ["Alice", "Alice", "Bob"], "p2_name": ["Bob", "Carol", "Alice"],
        "p1_rank": [10.0, 8.0, 20.0], "p2_rank": [20.0, 30.0, 8.0],
    })
    matches_path = tmp_path / "matches.parquet"
    _write_parquet(matches, matches_path)
    monkeypatch.setattr(trc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(trc, "_OUT_DIR", tmp_path / "intel_claims")
    monkeypatch.setitem(trc._MATCHES, "atp", matches_path)

    claim = trc._player_rank_snapshot_claim("atp")
    assert claim is not None
    by_player = {r["player_id"]: r["value"] for r in claim["ranking"]}
    # Alice's last-seen rank is her e3 rank (8.0, most recent date), not e1's 10.0
    assert by_player[1] == pytest.approx(8.0)
    # ranking must be ascending by rank (lower rank number = better = rank 1)
    values = [r["value"] for r in claim["ranking"]]
    assert values == sorted(values)


def test_player_rank_snapshot_tied_values_order_deterministic(tmp_path, monkeypatch):
    """2026-07-18 regression: three players tied at rank=50.0 must always come
    out player_id-ASCENDING, regardless of the row order the source frame
    arrives in (simulating dict/groupby iteration-order nondeterminism)."""
    def _build(order: list[int]) -> list[dict]:
        rows = {
            1: {"event_id": "e1", "date": "2025-01-01", "p1_id": 1, "p2_id": 9,
                "p1_name": "P1", "p2_name": "X", "p1_rank": 50.0, "p2_rank": 900.0},
            2: {"event_id": "e2", "date": "2025-01-01", "p1_id": 2, "p2_id": 9,
                "p1_name": "P2", "p2_name": "X", "p1_rank": 50.0, "p2_rank": 900.0},
            3: {"event_id": "e3", "date": "2025-01-01", "p1_id": 3, "p2_id": 9,
                "p1_name": "P3", "p2_name": "X", "p1_rank": 50.0, "p2_rank": 900.0},
        }
        return [rows[i] for i in order]

    def _run(order: list[int]):
        matches = pd.DataFrame(_build(order))
        matches_path = tmp_path / f"matches_{'_'.join(map(str, order))}.parquet"
        _write_parquet(matches, matches_path)
        monkeypatch.setattr(trc, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(trc, "_OUT_DIR", tmp_path / "intel_claims")
        monkeypatch.setitem(trc._MATCHES, "atp", matches_path)
        claim = trc._player_rank_snapshot_claim("atp")
        assert claim is not None
        return [r["player_id"] for r in claim["ranking"] if r["value"] == pytest.approx(50.0)]

    order_a = _run([1, 2, 3])
    order_b = _run([3, 1, 2])  # shuffled input order -- output must not change
    assert order_a == [1, 2, 3]
    assert order_b == [1, 2, 3]
    assert order_a == order_b


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
