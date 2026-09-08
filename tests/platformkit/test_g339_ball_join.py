import csv

from scripts.platformkit.tracking.ball_join import join_tables, report_rows


def _write(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_join_reports_detected_and_nearest_player(tmp_path):
    tracking = tmp_path / "tracking_data.csv"
    ball = tmp_path / "ball_tracking.csv"
    _write(tracking, ["frame", "track_id", "x", "y"], [
        {"frame": "1", "track_id": "10", "x": "0", "y": "0"},
        {"frame": "1", "track_id": "11", "x": "8", "y": "0"},
        {"frame": "2", "track_id": "10", "x": "1", "y": "1"},
    ])
    _write(ball, ["frame", "ball_x2d", "ball_y2d", "detected", "ball_inferred"], [
        {"frame": "1", "ball_x2d": "3", "ball_y2d": "4", "detected": "1", "ball_inferred": "0"},
        {"frame": "3", "ball_x2d": "", "ball_y2d": "", "detected": "0", "ball_inferred": "1"},
    ])
    joined = join_tables(tracking, ball)
    assert [(row["frame"], row["players"], row["ball_detected"]) for row in joined] == [(1, 2, 1), (2, 1, 0), (3, 0, 0)]
    assert joined[0]["nearest_player"] == "10"
    assert joined[0]["nearest_player_distance_px"] == 5.0
    report = report_rows(joined)
    assert report[:3] == [{"metric": "frames", "n": 3}, {"metric": "frames_with_detected_ball", "n": 1}, {"metric": "frames_without_detected_ball", "n": 2}]
    assert report[3]["n"] == 1
