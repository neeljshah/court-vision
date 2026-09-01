"""Focused contract checks for the run-clip output guard."""
from scripts.run_clip import _tracking_output_summary


def test_tracking_output_summary_counts_rows_and_frame_span(tmp_path):
    path = tmp_path / "tracking_data.csv"
    path.write_text(
        "frame,player_id\n0,1\n0,2\n3,1\n8,2\n",
        encoding="utf-8",
    )

    assert _tracking_output_summary(str(path)) == (4, 3, 0, 8)


def test_tracking_output_summary_ignores_invalid_frame_values(tmp_path):
    path = tmp_path / "tracking_data.csv"
    path.write_text("frame,player_id\ninvalid,1\n", encoding="utf-8")

    assert _tracking_output_summary(str(path)) == (0, 0, -1, -1)
