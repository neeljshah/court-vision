"""CV_INGAME_SHRINK — live box-score accuracy shrink (gated, default-OFF)."""
import os
import pytest

from src.prediction.live_engine import _apply_sparse_shrink, _snap_elapsed_min


def _rows():
    return [
        {"stat": "blk", "current": 2.0, "projected_final": 3.6, "q50": 3.6,
         "projection_source": "routed", "player_id": 1},
        {"stat": "stl", "current": 1.0, "projected_final": 2.2, "q50": 2.2,
         "projection_source": "routed", "player_id": 1},
        {"stat": "ast", "current": 4.0, "projected_final": 7.0, "q50": 7.0,
         "projection_source": "routed", "player_id": 1},
        {"stat": "pts", "current": 18.0, "projected_final": 24.0, "q50": 24.0,
         "projection_source": "routed", "player_id": 1},
    ]


@pytest.fixture(autouse=True)
def _clear_flag():
    saved = os.environ.pop("CV_INGAME_SHRINK", None)
    yield
    os.environ.pop("CV_INGAME_SHRINK", None)
    if saved is not None:
        os.environ["CV_INGAME_SHRINK"] = saved


def test_off_is_byte_identical():
    rows = _rows()
    before = [dict(r) for r in rows]
    out = _apply_sparse_shrink({"period": 3, "clock": "6:00"}, rows)
    assert out == before


def test_blk_stl_shrink_toward_current():
    os.environ["CV_INGAME_SHRINK"] = "1"
    rows = _rows()
    _apply_sparse_shrink({"period": 2, "clock": "6:00"}, rows)
    blk = next(r for r in rows if r["stat"] == "blk")
    stl = next(r for r in rows if r["stat"] == "stl")
    # w=0.9 -> 0.9*current + 0.1*projected
    assert blk["projected_final"] == pytest.approx(0.9 * 2.0 + 0.1 * 3.6)
    assert stl["projected_final"] == pytest.approx(0.9 * 1.0 + 0.1 * 2.2)
    assert "+shrink" in blk["projection_source"]
    assert blk["q50"] == blk["projected_final"]


def test_ast_is_untouched():
    os.environ["CV_INGAME_SHRINK"] = "1"
    rows = _rows()
    _apply_sparse_shrink({"period": 4, "clock": "1:00"}, rows)  # even late
    ast = next(r for r in rows if r["stat"] == "ast")
    assert ast["projected_final"] == 7.0
    assert "+shrink" not in ast["projection_source"]


def test_late_game_pts_shrinks_more_than_early():
    os.environ["CV_INGAME_SHRINK"] = "1"
    early = _rows()
    _apply_sparse_shrink({"period": 1, "clock": "8:00"}, early)
    late = _rows()
    _apply_sparse_shrink({"period": 4, "clock": "3:00"}, late)  # >=42 min elapsed
    pe = next(r for r in early if r["stat"] == "pts")["projected_final"]
    pl = next(r for r in late if r["stat"] == "pts")["projected_final"]
    # early: w=0.05 (near routed 24); late: w=0.7 (heavy toward current 18)
    assert pe > pl
    assert pl == pytest.approx(0.7 * 18.0 + 0.3 * 24.0)


def test_elapsed_min_parsing():
    assert _snap_elapsed_min({"period": 1, "clock": "12:00"}) == pytest.approx(0.0)
    assert _snap_elapsed_min({"period": 4, "clock": "0:00"}) == pytest.approx(48.0)
    assert _snap_elapsed_min({"period": 4, "clock": "6:00"}) == pytest.approx(42.0)
    assert _snap_elapsed_min({"period": 3, "clock": "6:00"}) == pytest.approx(30.0)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
