"""G289 reference census, endpoint capture, zero guard and exhaustive denominators."""
import csv
import json
import math

import pytest

from scripts.platformkit.tracking.g289_implausible_step_decomposition import (
    OUT, baseline, image_bucket, measure_steps, summarize,
)
from scripts.platformkit.tracking.verifier_footpoint_analyses import G267, steps


def test_committed_reproduction_and_partition(capsys):
    source = json.loads(G267.read_text(encoding="utf-8"))
    reference = baseline(source["frame_records"])
    assert capsys.readouterr().out == "BASELINE FIRST: 4090 / 29973 = 0.136456\n"
    rows = measure_steps(source["frame_records"], reference)
    result = summarize(rows)
    assert (result["implausible_steps"], result["eligible_steps"]) == (4090, 29973)
    assert f"{result['implausible_rate']:.6f}" == "0.136456"
    assert [p["count"] for p in result["partition"]] == [17, 157, 456, 749, 814, 1897]
    assert sum(p["count"] for p in result["partition"]) == 4090
    assert sum(p["share"] for p in result["partition"]) == 1.0
    assert result["partition_share_sum"] == 1.0
    assert result["image_le_20_count"] == 630
    assert (result["zero_pixel_steps"], result["zero_pixel_court_moved"],
            result["zero_pixel_implausible"]) == (1228, 1207, 17)
    assert sum(d["eligible_steps_with_midpoint_in_decile"] for d in result["y_deciles"]) == 29973
    assert sum(d["implausible"] for d in result["y_deciles"]) == 4090
    for group in result["gaps"].values():
        assert sum(d["count"] for d in group["distribution"]) == group["eligible_steps"]
        assert math.isclose(sum(d["share"] for d in group["distribution"]), 1)
    saved = json.loads((OUT / "summary.json").read_text())
    assert all(saved[key] == value for key, value in result.items())
    with (OUT / "steps.csv").open(newline="") as handle:
        archived = list(csv.DictReader(handle))
    assert len(archived) == len(rows)
    for actual, stored in zip(rows, archived):
        assert all(stored[k] == ("" if v is None else str(v)) for k, v in actual.items())
    # Cross-check endpoints against the original archived G267 implausible records.
    keyed = {(r["track_id"], r["before_source_frame"], r["after_source_frame"]): r
             for r in rows if r["implausible"]}
    for old in source["analysis"]["speed_ft_per_s"]["implausible_step_records"]:
        new = keyed.pop((old["track_id"], old["prior_source_frame"], old["source_frame"]))
        assert new["image_displacement_px"] == old["pixel_jump_px"]
        assert new["speed_ft_per_s"] == old["speed_ft_per_s"]
    assert not keyed


def test_capture_uses_verifier_pairing_and_guards_zero():
    def rec(frame, x, finite=True):
        return dict(source_frame=frame, detections=[dict(track_id=7, finite=finite,
                    foot_x_px=10.0, foot_y_px=20.0, court_x_ft=x, court_y_ft=0.0)])
    records = [rec(1, 0.0), rec(1, 1.0), rec(2, 999.0, False), rec(4, 7.0)]
    rows = measure_steps(records, steps(records))
    assert len(rows) == 1
    assert rows[0]["frame_gap"] == 3
    assert rows[0]["before_court_x_ft"] == 1.0
    assert rows[0]["court_displacement_ft"] == 6.0
    assert rows[0]["speed_ft_per_s"] == 60.0
    assert rows[0]["secant_scale_ft_per_px"] is None
    assert records[0]["detections"][0]["court_x_ft"] == 0.0
    assert type(records[0]["detections"][0]["court_x_ft"]) is float


def test_partition_boundaries_and_stop_on_wrong_baseline():
    assert [image_bucket(x) for x in (0, .001, 5, 5.001, 20, 20.001, 50, 50.001, 150, 151)] == [
        "0", "(0,5]", "(0,5]", "(5,20]", "(5,20]", "(20,50]", "(20,50]", "(50,150]", "(50,150]", ">150"]
    with pytest.raises(ValueError, match="STOP"):
        baseline([])
