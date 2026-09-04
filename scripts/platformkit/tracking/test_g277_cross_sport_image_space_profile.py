import csv

from scripts.platformkit.tracking.g277_cross_sport_image_space_profile import analyse_csv, categorical_check, exclusion_reason, percentile, placements, schema_check


def test_variants_are_split_and_quantiles_interpolate():
    assert exclusion_reason("g172_x")
    assert exclusion_reason("g225_yolov8n_r2_x")
    assert exclusion_reason("g226c_x")
    assert exclusion_reason("g239_x")
    assert exclusion_reason("g240_x_r3_y")
    assert exclusion_reason("wnba_01") is None
    assert percentile([0.0, 10.0], 0.9) == 9.0


def test_streamed_consecutive_speed_and_wnba_placement(tmp_path):
    path = tmp_path / "tracking_data.csv"
    fields = "frame track_id cls x y coordinate_space observation calibration source_fps source_height source_duration".split()
    rows = [
        [1, "a", "player", 0, 0, "image_px", "observed", "none", 30, 100, 3],
        [2, "a", "player", 10, 0, "image_px", "observed", "none", 30, 100, 3],
        [4, "a", "player", 20, 0, "image_px", "observed", "none", 30, 100, 3],
        [1, "b", "player", 0, 0, "image_px", "observed", "none", 30, 100, 3],
    ]
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle); writer.writerow(fields); writer.writerows(rows)
    run = analyse_csv(path, "wnba_01")
    assert run["step_count"] == 1
    assert run["speed_median"] == 3.0
    assert run["track_count"] == 2
    assert run["track_length_median_frames"] == 2.0
    assert run["track_shorter_than_5_fraction"] == 1.0
    peers = [run, {**run, "run": "mlb_x", "sport": "mlb", "speed_median": 4.0}]
    placement = [item for item in placements(peers) if item["metric"] == "speed_median"][0]
    assert placement["ascending_rank_low"] == placement["ascending_rank_high"] == 1


def test_schema_check_flags_legacy_columns_without_reading_records(tmp_path):
    path = tmp_path / "tracking_data.csv"
    path.write_text("frame,player_id,x_position,y_position,observation\n1,x,1,2,observed\n")
    _, missing = schema_check(path)
    assert {"track_id", "cls", "x", "y"}.issubset(missing)
    assert categorical_check(path) == (1, {"cls": None, "observation": ["observed"]})


def test_blank_coordinate_marks_run_incomplete_without_silent_row_loss(tmp_path):
    path = tmp_path / "tracking_data.csv"
    fields = "frame track_id cls x y coordinate_space observation calibration source_fps source_height source_duration".split()
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle); writer.writerow(fields)
        writer.writerows([[1, "a", "player", "", 0, "image_px", "observed", "none", 30, 100, 3], [2, "a", "player", 1, 0, "image_px", "observed", "none", 30, 100, 3]])
    run = analyse_csv(path, "wnba_01")
    assert run["analysis_status"] == "data_incomplete"
    assert run["invalid_numeric_required_rows"] == 1
    assert run["speed_median"] is None
