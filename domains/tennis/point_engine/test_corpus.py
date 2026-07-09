import pytest

from domains.tennis.point_engine.corpus import (
    SLAM_POINTS, score_bucket, set_bucket, N_SCORE_BUCKETS, N_SET_BUCKETS,
    build_point_frame,
)


def test_score_bucket_normal_and_deuce_region():
    assert score_bucket(0, 0) == 0
    assert score_bucket(3, 1) == 13          # 40-15
    assert score_bucket(3, 3) == 16          # deuce
    assert score_bucket(4, 3) == 17          # ad server (server "AD")
    assert score_bucket(3, 4) == 18          # ad returner
    for s in range(4):
        for r in range(4):
            assert 0 <= score_bucket(s, r) < N_SCORE_BUCKETS


def test_set_bucket_caps_at_3plus():
    assert set_bucket(1) == 0
    assert set_bucket(2) == 1
    assert set_bucket(3) == 2
    assert set_bucket(5) == N_SET_BUCKETS - 1


@pytest.mark.skipif(not SLAM_POINTS.exists(), reason="slam_points.parquet not on disk")
def test_build_point_frame_invariants():
    df = build_point_frame((2011,))
    assert len(df) > 1000
    assert set(df["server_won"].unique()) <= {0, 1}
    assert df["score_bucket"].between(0, 18).all()
    assert df["set_bucket"].between(0, 2).all()
    assert df["server_id"].notna().all() and df["returner_id"].notna().all()
    assert (df["server_id"] != df["returner_id"]).all()
