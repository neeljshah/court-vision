"""G312 construct: the additive capped-coverage fields, and that nothing else moved.

n = 3 (CONSTRUCT). Synthetic CSV, stub harness, stub frame counter. Nothing here is a
measurement of tracking quality: the capped share is a scheduling number only.
Run this ONE file. Never a full pytest.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.platformkit import track_daemon_done as done

GAME = "construct_game"
DECODED = 100          # stub decoder denominator
FPS = 30.0             # -> sampling_plan stride 3
EMITTED_FRAMES = (0, 3, 6, 9, 12, 15, 18, 21)   # 8 distinct emitted frames
CAP = 30               # route max_frames -> ceil(30/3) = 10 attempted
# ceil(100/3) = 34 uncapped, so the cap binds: min(34, 10) = 10, share 8/10.
EXPECT_ATTEMPTED = 10
EXPECT_SHARE = 0.8

# The payload keys that existed BEFORE G312. Frozen here so a rename or a dropped key
# fails this test rather than silently changing the ledger schema.
PRE_EXISTING = frozenset((
    "passed", "failure_heads", "coverage_pct", "harness_coverage_pct",
    "coordinate_space", "rung", "evaluated_at", "csv_fsynced",
    "decoded_frames", "evaluated_frames", "stride"))
ADDED = frozenset(("route_max_frames", "attempted_frames_capped",
                   "coverage_attempted_capped_pct"))


def _stub_harness(frame, sport, source=""):
    return SimpleNamespace(passed=True, failures=[], coverage_pct=0.5)


def _build(tmp_path: Path, cap: int | None, *, fps: float | None = FPS) -> Path:
    """Write a synthetic game directory; omit the sidecar when cap is None."""
    tracking = tmp_path / "tracking"
    (tracking / GAME).mkdir(parents=True)
    if fps is None:   # no source_fps -> no stride -> nothing is capped
        rows = ["frame,track_id,cls,x,y,coordinate_space"]
        rows += ["%d,1,person,10.0,20.0,image_px" % frame for frame in EMITTED_FRAMES]
        (tracking / GAME / "tracking_data.csv").write_text("\n".join(rows) + "\n",
                                                           encoding="utf-8")
        (tracking / GAME / done.ROUTE_COUNT_SIDECAR).write_text(
            json.dumps({"schema_version": "g206-v1", "max_frames": cap}), encoding="utf-8")
        return tracking
    rows = ["frame,track_id,cls,x,y,source_fps,coordinate_space"]
    rows += ["%d,1,person,10.0,20.0,%s,image_px" % (frame, FPS) for frame in EMITTED_FRAMES]
    (tracking / GAME / "tracking_data.csv").write_text("\n".join(rows) + "\n",
                                                       encoding="utf-8")
    if cap is not None:
        (tracking / GAME / done.ROUTE_COUNT_SIDECAR).write_text(
            json.dumps({"schema_version": "g206-v1", "max_frames": cap}), encoding="utf-8")
    return tracking


def _adjudicate(tracking: Path) -> dict:
    return done.adjudicate(Path("unused.mp4"), "basketball", GAME, tracking,
                           harness=_stub_harness, frame_counter=lambda _video: DECODED,
                           publish=False)


def test_capped_fields_use_the_route_cap(tmp_path):
    """With the sidecar present the cap binds and the share is over the capped count."""
    payload = _adjudicate(_build(tmp_path, CAP))
    assert payload["evaluated_frames"] == 34          # ceil(100/3), unchanged
    assert payload["stride"] == 3
    assert payload["route_max_frames"] == CAP
    assert payload["attempted_frames_capped"] == EXPECT_ATTEMPTED
    assert payload["coverage_attempted_capped_pct"] == pytest.approx(EXPECT_SHARE, abs=1e-12)
    assert set(payload) == PRE_EXISTING | ADDED


@pytest.mark.parametrize("cap", [None, 0, -5, True, "3000"])
def test_missing_or_unusable_cap_yields_nulls(tmp_path, cap):
    """No cap, a non-positive cap, a bool or a string is null -- never a guessed default."""
    payload = _adjudicate(_build(tmp_path, cap))
    assert payload["route_max_frames"] is None
    assert payload["attempted_frames_capped"] is None
    assert payload["coverage_attempted_capped_pct"] is None


def test_valid_cap_with_unknown_stride_is_still_null(tmp_path):
    """codex-sol correction: a cap we cannot apply is not a cap we may report."""
    payload = _adjudicate(_build(tmp_path, CAP, fps=None))
    assert payload["stride"] is None and payload["evaluated_frames"] is None
    assert payload["route_max_frames"] is None
    assert payload["attempted_frames_capped"] is None
    assert payload["coverage_attempted_capped_pct"] is None


def test_pre_existing_keys_are_byte_identical(tmp_path):
    """The additive path cannot perturb one pre-existing field, cap present or absent."""
    with_cap = _adjudicate(_build(tmp_path / "a", CAP))
    without_cap = _adjudicate(_build(tmp_path / "b", None))

    def frozen(payload):   # evaluated_at is a wall clock; assert its type, not its value
        assert isinstance(payload["evaluated_at"], int)
        return json.dumps({key: payload[key] for key in sorted(PRE_EXISTING)
                           if key != "evaluated_at"}, sort_keys=True)

    assert frozen(with_cap) == frozen(without_cap)
    assert frozen(with_cap) == (
        '{"coordinate_space": "image_px", "coverage_pct": 0.08, "csv_fsynced": true, '
        '"decoded_frames": 100, "evaluated_frames": 34, "failure_heads": [], '
        '"harness_coverage_pct": 0.5, "passed": true, "rung": "IMAGE_PX_DECLARED", '
        '"stride": 3}')
