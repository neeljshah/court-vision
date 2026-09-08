"""Contract checks for the gpt-5.6-terra G304 extension locator output."""

import csv
from collections import Counter, defaultdict
from pathlib import Path


MODEL_LOCATOR = "gpt-5.6-terra"
CSV_PATH = Path("docs/evidence/tracking/g304_locator_pass2_terra_ext_2026-09-07.csv")
VOCABULARY = {
    "CORNER_NEAR_L", "CORNER_NEAR_R", "CORNER_FAR_L", "CORNER_FAR_R",
    "LANE_BASE_L", "LANE_BASE_R", "FT_LINE_L", "FT_LINE_R", "KEY_TOP",
    "THREE_PT_BASE_L", "THREE_PT_BASE_R", "CENTER_SIDELINE_NEAR",
    "CENTER_SIDELINE_FAR", "CENTER_CIRCLE_TOP", "CENTER_CIRCLE_BOTTOM",
}


def test_g304_locator_pass2_extension_schema_and_coverage() -> None:
    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert list(rows[0]) == [
        "row_id", "source_id", "arena", "classification", "negative_category",
        "landmark_name", "x", "y", "visible", "confidence", "note", "locator_name",
    ]
    assert {row["locator_name"] for row in rows} == {MODEL_LOCATOR}
    frames = defaultdict(list)
    for row in rows:
        assert row["classification"] == "ELIGIBLE"
        frames[row["row_id"]].append(row)
        if row["visible"] == "1":
            assert row["landmark_name"] in VOCABULARY
            assert 0 <= int(row["x"]) < 1920
            assert 0 <= int(row["y"]) < 1080
            assert 0.0 < float(row["confidence"]) <= 1.0
            assert row["note"] == "frame-boundary"
        else:
            assert row["landmark_name"] == row["x"] == row["y"] == ""
            assert row["confidence"] == "0.00"
            assert row["note"] == "shortfall: four vocabulary landmarks visible"

    assert len(frames) == 40
    assert Counter(row["source_id"] for values in frames.values() for row in values) == {
        "wnba_01": 90, "wnba_04": 125,
    }
    visible_counts = {
        row_id: sum(row["visible"] == "1" for row in values)
        for row_id, values in frames.items()
    }
    assert sum(row_id.startswith("wnba_01_") for row_id in frames) == 15
    assert sum(row_id.startswith("wnba_04_") for row_id in frames) == 25
    assert all(count == 6 for row_id, count in visible_counts.items() if row_id.startswith("wnba_01_"))
    assert all(count == 4 for row_id, count in visible_counts.items() if row_id.startswith("wnba_04_"))
