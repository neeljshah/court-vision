import pytest

from domains.tennis.point_engine.corpus_2026 import (
    POINTS_2026, MATCHES_2026, build_point_frame_2026, build_match_frame_2026,
)


@pytest.mark.skipif(not POINTS_2026.exists(), reason="mcp_2026 points.parquet not on disk")
def test_build_point_frame_2026_invariants():
    df = build_point_frame_2026()
    assert len(df) > 1000
    assert set(df["server_won"].unique()) <= {0, 1}
    assert df["score_bucket"].between(0, 18).all()
    assert df["set_bucket"].between(0, 2).all()
    assert df["server_id"].notna().all() and df["returner_id"].notna().all()
    assert (df["server_id"] != df["returner_id"]).all()


@pytest.mark.skipif(not MATCHES_2026.exists(), reason="mcp_2026 matches.parquet not on disk")
def test_build_match_frame_2026_invariants():
    df = build_match_frame_2026()
    assert len(df) > 100
    assert (df["total_games"] > 0).all()
    assert df["winner_id"].isin(list(df["player1id"]) + list(df["player2id"])).all()
    assert df["best_of"].isin([3, 5]).all()
    assert (df["first_server_id"].isin(df["player1id"]) |
            df["first_server_id"].isin(df["player2id"])).all()
