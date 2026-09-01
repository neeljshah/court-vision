"""Focused tests for geometry-only tracklet merging."""
import pandas as pd

from scripts.platformkit.tracking.tracklet_merge import apply_tracklet_map, merge_tracklets


def _fragment(track_id: str, frames: range, start_x: float, confidence: float = 0.8) -> list[dict]:
    return [{"frame": frame, "track_id": track_id, "cls": "player", "x": start_x + frame,
             "y": 10.0, "team": "home", "confidence": confidence, "game_id": "g1"}
            for frame in frames]


def test_nonoverlap_and_physical_geometry_merge_but_concurrent_players_do_not():
    rows = _fragment("first", range(0, 5), 0.0)
    rows += _fragment("second", range(15, 20), -7.0)
    rows += _fragment("concurrent_a", range(0, 20), 100.0)
    rows += _fragment("concurrent_b", range(0, 20), 130.0)
    table = pd.DataFrame(rows)
    mapping, report = merge_tracklets(table, "basketball", {"p99": 6.0})
    assert mapping["first"] == mapping["second"]
    assert mapping["concurrent_a"] != mapping["concurrent_b"]
    assert report.n_tracks_after < report.n_tracks_before
    assert report.coverage_after <= report.coverage_before
    after = apply_tracklet_map(table, mapping)
    assert int(after.duplicated(["game_id", "frame", "track_id"]).sum()) == 0


def test_concurrent_duplicate_culls_lower_confidence_track():
    rows = _fragment("winner", range(0, 20), 0.0, confidence=0.9)
    rows += _fragment("duplicate", range(0, 20), 1.0, confidence=0.4)
    for track_id, start_x in (("other_a", 20.0), ("other_b", 40.0),
                              ("other_c", 60.0), ("other_d", 80.0)):
        rows += _fragment(track_id, range(0, 20), start_x)
    table = pd.DataFrame(rows)
    mapping, report = merge_tracklets(table, "wnba", {"wnba": {"p99": 6.0}})
    assert mapping["duplicate"] == "winner"
    assert report.concurrent_duplicates_culled == 1
    assert report.n_tracks_after == 5
    assert report.coverage_after == 0.0
    assert report.coverage_before == 1.0


def test_coverage_after_is_reported_without_clamping():
    rows = _fragment("a", range(0, 20), 0.0)
    rows += _fragment("b", range(0, 20), 1.0)
    rows += _fragment("c", range(0, 20), 2.0)
    rows += _fragment("d", range(0, 20), 3.0)
    rows += _fragment("e", range(0, 20), 4.0)
    rows += _fragment("f", range(0, 20), 5.0)
    table = pd.DataFrame(rows)
    _, report = merge_tracklets(table, "basketball", 6.0)
    assert report.coverage_before == 1.0
    assert report.coverage_after == 0.0
