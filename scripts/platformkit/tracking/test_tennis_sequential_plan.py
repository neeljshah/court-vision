"""Synthetic coverage for the tennis sequential-plan evidence writer."""
from __future__ import annotations

import json

import numpy as np

from scripts.platformkit.tracking import tennis_sequential_plan as plan


class FakeCapture:
    def __init__(self, _: str) -> None:
        self.index = 0

    def isOpened(self) -> bool:
        return True

    def get(self, _: int) -> int:
        return 1000

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.index == 1000:
            return False, None
        frame = np.full((1, 1, 1), self.index, dtype=np.uint16)
        self.index += 1
        return True, frame

    def release(self) -> None:
        pass


def test_deterministic_selection_and_fail_reporting(tmp_path, monkeypatch) -> None:
    gate = lambda frame: "accepted" if int(frame[0, 0, 0]) % 100 == 0 else "rejected"
    first = plan.select_ranges(tmp_path / "fake.mp4", 5, 300, 9, FakeCapture, gate)
    second = plan.select_ranges(tmp_path / "fake.mp4", 5, 300, 9, FakeCapture, gate)
    assert first == second

    def fake_run(_: object, start: int, stop: int, __: object = None) -> dict[str, object]:
        failed = start == first[0][0]
        return {"source_frame_range": {"start": start, "stop": stop}, "decoded_frames": 300,
                "solved_frame_coverage": 0.9, "drift_checked_reuses": 4,
                "harness_verdict": "FAIL" if failed else "PASS",
                "harness_failures": ["jump_p95 9.00 > 8.00"] if failed else [],
                "harness_metrics": {"jump_p95": 9.0 if failed else 1.0}}

    monkeypatch.setattr(plan, "select_ranges", lambda *_: first)
    monkeypatch.setattr(plan, "run_range", fake_run)
    report = plan.build_report(tmp_path / "fake.mp4", 5, 300, 9)
    output = tmp_path / "sequential_plan.json"
    output.write_text(json.dumps(report), encoding="utf-8")
    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert {"video", "selection", "ranges", "summary"} <= set(loaded)
    assert len(loaded["ranges"]) == len(first)
    assert loaded["ranges"][0]["harness_verdict"] == "FAIL"
    assert loaded["ranges"][0]["harness_failures"]


def test_seconds_ranges_convert_for_each_source_fps() -> None:
    assert plan.seconds_to_frames(306.0, 312.0, 25.0) == (7650, 7800)
    assert plan.seconds_to_frames(306.0, 312.0, 50.0) == (15300, 15600)
