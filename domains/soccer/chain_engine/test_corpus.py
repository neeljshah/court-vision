import pytest

from domains.soccer.chain_engine.corpus import (
    MATCH_META, time_bucket, score_bucket, load_match_meta, split_fit_test,
    build_possession_frame, N_TIME_BUCKETS, N_SCORE_BUCKETS,
)


def test_time_bucket_caps_at_75plus():
    assert time_bucket(0) == 0
    assert time_bucket(14) == 0
    assert time_bucket(15) == 1
    assert time_bucket(89) == 5
    assert time_bucket(120) == N_TIME_BUCKETS - 1


def test_score_bucket_trailing_tied_leading():
    assert score_bucket(-2) == 0
    assert score_bucket(0) == 1
    assert score_bucket(3) == 2
    assert 0 <= score_bucket(-1) < N_SCORE_BUCKETS


@pytest.mark.skipif(not MATCH_META.exists(), reason="match_meta.parquet not on disk")
def test_split_fit_test_is_per_corpus_and_ordered():
    meta = load_match_meta()
    fit, test = split_fit_test(meta)
    assert len(fit) > 0 and len(test) > 0
    assert len(fit) + len(test) == len(meta)
    for tag in ("A", "B"):
        f = fit[fit["corpus"] == tag]["match_date"]
        t = test[test["corpus"] == tag]["match_date"]
        if len(f) and len(t):
            assert f.max() <= t.min()   # walk-forward: fit strictly precedes test


@pytest.mark.skipif(not MATCH_META.exists(), reason="match_meta.parquet not on disk")
def test_build_possession_frame_invariants():
    meta = load_match_meta()
    small = meta[meta["corpus"] == "A"].head(3)
    df = build_possession_frame(small)
    assert len(df) > 0
    assert df["time_bucket"].between(0, N_TIME_BUCKETS - 1).all()
    assert df["score_bucket"].between(0, N_SCORE_BUCKETS - 1).all()
    shots = df[df["had_shot"]]
    assert shots["xg"].notna().all()
    assert (shots["xg"] >= 0).all() and (shots["xg"] <= 1.0001).all()
