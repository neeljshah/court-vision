"""Regression audit for the durable G65 labels used by G44B."""
from __future__ import annotations

import csv
from pathlib import Path


def test_g65_labels_keep_the_g44b_ground_truth_denominators() -> None:
    """The G44B memo must be reproducible without detector output."""
    root = Path(__file__).resolve().parents[3]
    labels_path = root / "docs" / "evidence" / "tracking" / "g65_ball_labels" / "labels.csv"
    with labels_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 150
    assert len({(row["clip"], row["source_frame"]) for row in rows}) == 150
    visible = [row for row in rows if row["ball_visible"] == "true"]
    uncertain = [row for row in rows if row["uncertain"] == "true"]
    assert len(visible) == 41
    assert len(uncertain) == 109
    assert all(row["uncertain_reason"] for row in uncertain)
    assert all(row["center_x_image_px"] and row["center_y_image_px"] for row in visible)

    inside = [
        row for row in visible
        if float(row["center_y_image_px"]) < float(row["frame_height_image_px"]) * 2.0 / 3.0
    ]
    assert len(inside) == 32
