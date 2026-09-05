"""Pin G299 extent classification, eligible denominators, and the full census."""
import json
import math

import pytest

from scripts.platformkit.tracking.g289_implausible_step_decomposition import measure_steps
from scripts.platformkit.tracking.g299_static_track_share import (
    BANDS, OUT, band_for, distribution, per_track, summarize, verified_step_rows,
)
from scripts.platformkit.tracking.verifier_footpoint_analyses import load_detections, steps


def _records(paths: dict[int, list[tuple[float, float]]]) -> list[dict]:
    return [dict(source_frame=i * 2, detections=[
        dict(track_id=tid, finite=True, foot_x_px=points[i][0], foot_y_px=points[i][1],
             court_x_ft=points[i][0], court_y_ft=points[i][1])
        for tid, points in paths.items() if i < len(points)
    ]) for i in range(max(map(len, paths.values())))]


def _tracks(paths: dict[int, list[tuple[float, float]]]) -> list[dict]:
    records = _records(paths)
    return per_track(records, measure_steps(records, steps(records)))


def test_cut_uses_footpoint_diagonal_not_net_path_axis_or_median():
    tracks = _tracks({
        1: [(0, 0)] * 10 + [(18, 18)] + [(0, 0)] * 9,
        2: [(0, 0), (10, 0)] * 10,
        3: [(0, 0)] * 19 + [(15, 20)],
    })
    assert tracks[0]["footpoint_bbox_diagonal_px"] == math.hypot(18, 18)
    assert tracks[0]["median_step_displacement_px"] == 0
    assert tracks[1]["path_length_px"] == 190  # >25, but extent is only 10.
    assert tracks[1]["footpoint_bbox_diagonal_px"] == 10
    assert tracks[2]["footpoint_bbox_diagonal_px"] == 25  # Strictly below, not <=.
    cuts = summarize(tracks)["cuts"]
    assert [c["static_ids"] for c in cuts] == [[], [2], [1, 2, 3]]
    assert cuts[1]["static_detections"] == 20
    assert cuts[1]["all_retained_detections"] == 60


def test_short_ids_excluded_from_eligible_denominator_but_detections_retained():
    tracks = _tracks({1: [(0, 0)] * 20, 2: [(0, 0)] * 19,
                      3: [(0, 0)] * 19 + [(100, 0)], 4: [(0, 0)]})
    result = summarize(tracks)
    assert result["all_ids"] == 4
    assert result["eligible_ids"] == 2
    assert result["excluded_short_ids"] == [2, 4]
    assert result["excluded_short_detections"] == 20
    for cut in result["cuts"]:
        assert cut["eligible_ids"] == 2  # Must not divide by all four IDs.
        assert cut["static_ids"] == [1]
        assert cut["static_id_share"] == .5
        assert cut["static_detections"] == 20
        assert cut["all_retained_detections"] == 60
        assert cut["detection_share"] == pytest.approx(1 / 3)
    assert tracks[-1]["path_length_px"] == 0
    assert tracks[-1]["median_step_displacement_px"] is None


def test_bands_keep_inclusive_bounds_gaps_and_empty_static_denominator():
    for name, (lo, hi) in BANDS.items():
        assert band_for(lo) == band_for(hi) == name
    assert band_for(89.5) == band_for(980.5) == band_for(989) == "other"
    tracks = _tracks({1: [(0, 850)] * 19 + [(0, 980)]})
    for cut in summarize(tracks)["cuts"]:
        assert sum(b["all_band_detections"] for b in cut["bands"]) == 20
        assert all(b["share_static_detections"] is None for b in cut["bands"])


def test_distribution_names_undefined_singletons_and_interpolates():
    result = distribution([None, 0, 10])
    assert (result["ids_total"], result["ids_defined"], result["ids_undefined"]) == (3, 2, 1)
    assert result["p25"] == 2.5
    assert result["median"] == 5
    assert distribution([])["median"] is None


def test_committed_census_reconciles_every_step_and_archived_summary():
    records = load_detections()
    rows = verified_step_rows(records)  # Every G289 field, using imported steps().
    assert len(rows) == 29973
    assert sum(r["image_displacement_px"] == 0 for r in rows) == 1228
    tracks = per_track(records, rows)
    result = summarize(tracks)
    archived = json.loads((OUT / "summary.json").read_text(encoding="ascii"))
    assert all(archived[k] == v for k, v in result.items())
    assert (result["all_ids"], result["eligible_ids"], result["all_retained_detections"]) == (98, 84, 30071)
    assert result["excluded_short_detections"] == 81
    assert sum(t["step_count"] for t in tracks) == 29973
    for cut in result["cuts"]:
        assert cut["eligible_ids"] == 84
        assert cut["static_id_count"] == cut["static_detections"] == cut["detection_share"] == 0
        assert [b["all_band_detections"] for b in cut["bands"]] == [24, 1084, 9561, 19, 19383]
    assert result["distributions"]["eligible_ids"]["footpoint_bbox_diagonal_px"]["min"] == pytest.approx(99.8761391127)
