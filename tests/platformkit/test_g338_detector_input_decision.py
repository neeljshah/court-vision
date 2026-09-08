"""G338 hand-pinned construct: scorer, sealed decision rule, and prereg seal reader."""
from pathlib import Path

import pytest

from scripts.platformkit.tracking.g338_detector_input_decision import (
    decide,
    intersects_frame,
    persistence_share,
    summarize,
    verify_seal,
    wholly_in_frame,
)
from scripts.platformkit.tracking.g338_detector_input_arms import _frame, _resolve_frame
import scripts.platformkit.tracking.g338_detector_input_arms as g338_arms


def _record(frame, box, ball=0):
    return {"frame_index": frame, "boxes": [box], "frame_w": 100, "frame_h": 50,
            "homography": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "map_w": 94, "map_h": 50,
            "ms": 10.0, "gpu_mib": 123, "ball_count": ball}


def test_g325_intersection_and_wholly_inside_are_distinct():
    assert intersects_frame([-2, 4, 8, 20], 100, 50)
    assert not wholly_in_frame([-2, 4, 8, 20], 100, 50)
    assert not intersects_frame([-10, 4, 0, 20], 100, 50)


def test_scorer_keeps_empty_frames_and_pins_all_proxy_denominators():
    records = [_record(1, [10, 10, 20, 16], 0), _record(2, [10, 10, 20, 16], 1),
               _record(3, [10, 10, 20, 16], 2)]
    out = summarize(records)
    assert out["n_frames"] == 3 and out["n_boxes"] == 3
    assert out["height_n"] == 3 and out["height_share"] == 1.0
    assert out["court_n"] == 3 and out["court_share"] == 1.0
    assert out["persistence_n"] == 3 and out["persistence_share"] == 1.0
    assert out["ball_per_frame"] == 1.0 and out["gpu_mib"] == 123


def test_persistence_requires_three_consecutive_frames():
    box = [10, 10, 20, 20]
    assert persistence_share([[box], [box], [box]]) == (3, 3)
    assert persistence_share([[box], [box]]) == (0, 2)


def test_smallest_input_rule_uses_four_sections_and_throughput():
    metrics = ("band_share", "height_share", "wholly_in_frame_share", "court_share", "persistence_share")
    by_section = {}
    for section in range(6):
        base = {field: 0.70 for field in metrics} | {"ms_per_frame": 100.0}
        mid = {field: (0.80 if section < 4 else 0.70) for field in metrics} | {"ms_per_frame": 110.0}
        slow = {field: 0.80 for field in metrics} | {"ms_per_frame": 140.0}
        by_section[str(section)] = {640: base, 960: mid, 1280: slow}
    out = decide(by_section)
    assert out["recommended_imgsz"] == 960
    assert out["sections_qualified"] == {640: 0, 960: 4, 1280: 0}


def test_prereg_seal_reads_file_and_normalizes_line_endings_without_git_show(tmp_path):
    source = Path("docs/evidence/tracking/g338_prereg_2026-09-08.md").read_bytes()
    crlf = tmp_path / "prereg.md"
    crlf.write_bytes(source.replace(b"\n", b"\r\n"))
    assert verify_seal(crlf) == "c1e93fb53c7957f9f74bce9867f55685080d3f568f05f67ddbca6408c9c87e6c"


def test_frame_raises_and_caller_resolve_frame_records_it(monkeypatch):
    # B2: an undecodable sealed index (here, a path that cannot open) makes the helper
    # raise, never a silent None; no real video decode happens for a nonexistent path.
    with pytest.raises(RuntimeError):
        _frame("does-not-exist-g338.mp4", 0)

    # The caller (_resolve_frame) wraps that raise, records the index once, and returns
    # None so the finisher can skip it -- construct-only, _frame itself is monkeypatched.
    monkeypatch.setattr(g338_arms, "UNDECODABLE", [])
    monkeypatch.setattr(g338_arms, "_frame",
                         lambda path, index: (_ for _ in ()).throw(RuntimeError("decode failed")))
    assert _resolve_frame(3, "does-not-exist-g338.mp4", 42) is None
    assert _resolve_frame(3, "does-not-exist-g338.mp4", 42) is None
    assert g338_arms.UNDECODABLE == [{"section": "000003", "frame_index": 42}]
