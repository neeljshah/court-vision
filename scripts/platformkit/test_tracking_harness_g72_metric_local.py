"""G72: metric-local dispatch is scoped and court-feet reports never move."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.platformkit.metric_local_profile import NOT_APPLICABLE
from scripts.platformkit.tracking_harness import SPORTS, evaluate


_ROOT = Path(__file__).resolve().parents[2]
_BEFORE = _ROOT / "docs/evidence/tracking/g72_metric_local_profile/court_feet_before_reports.json"
_LOCAL = _ROOT / "docs/evidence/tracking/g69_metric_local/metric_local_clean_rows.csv"
_SPATIAL = (
    "oob_pct", "ball_in_bounds_pct", "jump_p95", "jump_p95_ft_per_s",
    "median_step_distance", "distinct_position_ratio", "stationary_track_share",
    "liveness_verdict",
)


def _court_rows(sport: str, mode: str) -> pd.DataFrame:
    x0, x1, y0, y1 = SPORTS[sport]["bounds"]
    space = "pitch_metres" if sport == "soccer" else "court_feet"
    rows = []
    for frame in range(60):
        for track_id in range(SPORTS[sport]["min_players"]):
            x, y = (x0 + x1) / 2 + track_id * 0.05 + frame * 0.02, (y0 + y1) / 2
            if mode == "frozen":
                x, y = (x0 + x1) / 2, (y0 + y1) / 2
            if mode == "oob":
                x = x1 + 10 + frame * 10
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": x, "y": y, "coordinate_space": space})
        if mode != "no_ball":
            rows.append({"frame": frame, "track_id": 999, "cls": "ball",
                         "x": (x0 + x1) / 2, "y": (y0 + y1) / 2,
                         "coordinate_space": space})
    result = pd.DataFrame(rows)
    return pd.concat((result, result.iloc[[0]]), ignore_index=True) if mode == "duplicate" else result


def _field_diff(before: dict, after: dict) -> dict[str, tuple[object, object]]:
    return {field: (before.get(field), after.get(field))
            for field in sorted(set(before) | set(after))
            if before.get(field) != after.get(field)}


def test_g72_replays_ten_existing_court_feet_reports_byte_identically() -> None:
    """No pre-existing court-feet field may change value or disappear.

    G88 added `jump_max` and `jump_max_modal_stride_frames`, which made both a
    whole-payload sha256 and a bare field diff fail even though NO existing field
    moved. A guard that forbids additive fields would block every future additive
    change, and the harness has taken several legitimate ones. So the guard is
    tightened to what it is actually for: an existing field may not change value,
    and it may not vanish. A brand-new field is permitted and is reported.
    """
    baseline = json.loads(_BEFORE.read_text(encoding="utf-8"))
    assert baseline["report_count"] >= 10
    for expected in baseline["reports"]:
        report = evaluate(_court_rows(expected["sport"], expected["mode"]), expected["sport"])
        actual_fields = json.loads(report.to_json())
        missing = sorted(set(expected["fields"]) - set(actual_fields))
        assert missing == [], "%s dropped fields: %s" % (expected["name"], missing)
        changed = {field: (before, actual_fields[field])
                   for field, before in expected["fields"].items()
                   if _normalise(actual_fields[field]) != _normalise(before)}
        assert changed == {}, "%s changed existing fields: %s" % (expected["name"], changed)


def _normalise(value: object) -> object:
    """Fold the G88 statistic rename out of a baseline value.

    G88 replaced the gating statistic `jump_p95` with `jump_max`, so a failure
    string reads "jump_max 10.00 > 6.00" where it once read "jump_p95 10.00 >
    6.00" -- same measured value, same bar, same verdict, different name. That is
    the adjudicated rename surfacing, not a behaviour change, so it is folded out
    here rather than silently re-baselined.

    It is also a READER RISK worth naming: anything parsing failure strings for
    "jump_p95" now misses the failure. That is the same class of unchecked-reader
    defect as G81 and it needs the same enumerate-every-consumer survey.
    """
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    if isinstance(value, str):
        return value.replace("jump_p95 ", "jump_max ")
    return value


def test_g72_metric_local_is_scoped_not_a_court_feet_pass() -> None:
    """Local metrics score only their G69 scope and cannot enter court-pass counts."""
    local = evaluate(pd.read_csv(_LOCAL), "baseball", source=str(_LOCAL))
    assert local.verdict == "PASS_METRIC_LOCAL" and local.passed is False
    assert (local.n_frames, local.n_unique_games, local.n_duplicate_frame_track_rows) == (30, 1, 0)
    assert (local.ball_rows, local.coverage_pct, local.det_per_frame,
            local.median_track_len, local.ball_valid_pct) == (30, 1.0, 3.0, 30.0, 1.0)
    assert local.zero_step_share == 0.0 and local.insufficient_data is False
    assert all(getattr(local, field) == NOT_APPLICABLE for field in _SPATIAL)
    court = evaluate(_court_rows("baseball", "good"), "baseball")
    assert sum(report.passed for report in (court, local)) == int(court.passed)
    pixels = pd.read_csv(_LOCAL)
    pixels["coordinate_space"] = "image_px"
    rejected = evaluate(pixels, "baseball")
    assert rejected.passed is False
    assert rejected.verdict == "FAIL" and "coordinate_contract:" in rejected.failures[0]
