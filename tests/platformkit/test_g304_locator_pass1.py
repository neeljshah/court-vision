"""Validate the gpt-5.6-sol G304 pass-1 locator artifact."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
LOCATOR_CSV = (
    REPO
    / "docs"
    / "evidence"
    / "tracking"
    / "g304_locator_pass1_sol_2026-09-07.csv"
)
ELIGIBILITY_CSV = (
    REPO.parent
    / "nba-track-a3"
    / "docs"
    / "evidence"
    / "tracking"
    / "g304_eligibility_sol_2026-09-07.csv"
)
SCHEMA = (
    "locator_name",
    "row_id",
    "source_id",
    "arena",
    "classification",
    "negative_category",
    "unresolved_reason",
    "court_end",
    "record_type",
    "landmark_name",
    "x",
    "y",
    "visible",
    "confidence",
    "note",
)
VOCABULARY = {
    "CORNER_NEAR_L",
    "CORNER_NEAR_R",
    "CORNER_FAR_L",
    "CORNER_FAR_R",
    "LANE_BASE_L",
    "LANE_BASE_R",
    "FT_LINE_L",
    "FT_LINE_R",
    "KEY_TOP",
    "THREE_PT_BASE_L",
    "THREE_PT_BASE_R",
    "CENTER_SIDELINE_NEAR",
    "CENTER_SIDELINE_FAR",
    "CENTER_CIRCLE_TOP",
    "CENTER_CIRCLE_BOTTOM",
}
STRUCTURE = {
    "CORNER": "court_boundary",
    "LANE_BASE": "lane_boundary",
    "FT_LINE": "free_throw_line",
    "KEY_TOP": "free_throw_circle",
    "THREE_PT_BASE": "three_point_line",
    "CENTER_SIDELINE": "midcourt_sideline",
    "CENTER_CIRCLE": "center_circle",
}


def _structure(name: str) -> str:
    for prefix, structure in STRUCTURE.items():
        if name.startswith(prefix):
            return structure
    raise AssertionError(f"unmapped landmark: {name}")


def test_g304_locator_pass1_schema_ranges_and_cardinality() -> None:
    with ELIGIBILITY_CSV.open(newline="", encoding="utf-8") as handle:
        eligibility = list(csv.DictReader(handle))
    with LOCATOR_CSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == SCHEMA
        rows = list(reader)

    expected = {row["row_id"]: row for row in eligibility}
    actual: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        actual[row["row_id"]].append(row)
        assert row["locator_name"] == "gpt-5.6-sol"
    assert len(expected) == 60
    assert set(actual) == set(expected)
    assert Counter(row["classification"] for row in eligibility) == Counter(
        {"ELIGIBLE": 23, "NEGATIVE": 35, "UNRESOLVABLE": 2}
    )

    for row_id, source in expected.items():
        records = actual[row_id]
        assert {row["classification"] for row in records} == {
            source["classification"]
        }
        if source["classification"] == "ELIGIBLE":
            landmarks = [row for row in records if row["record_type"] == "LANDMARK"]
            shortfalls = [row for row in records if row["record_type"] == "SHORTFALL"]
            assert len({row["landmark_name"] for row in landmarks}) == len(landmarks)
            for landmark in landmarks:
                assert landmark["landmark_name"] in VOCABULARY
                assert landmark["visible"] == "TRUE"
                assert 0 <= int(landmark["x"]) < 1920
                assert 0 <= int(landmark["y"]) < 1080
                assert 0.0 <= float(landmark["confidence"]) <= 1.0
            if len(landmarks) >= 6:
                assert not shortfalls
                assert len({_structure(row["landmark_name"]) for row in landmarks}) >= 3
            else:
                assert len(shortfalls) == 1
                assert shortfalls[0]["visible"] == "FALSE"
                assert shortfalls[0]["landmark_name"] == ""
                assert shortfalls[0]["x"] == shortfalls[0]["y"] == ""
                assert shortfalls[0]["note"] == (
                    f"visible_named_landmarks={len(landmarks)};required=6"
                )
        else:
            assert len(records) == 1
            record = records[0]
            assert record["record_type"] == "FRAME"
            assert record["landmark_name"] == ""
            assert record["x"] == record["y"] == ""
            assert record["visible"] == "FALSE"
            if source["classification"] == "NEGATIVE":
                assert record["negative_category"] == source["negative_category"]
                assert record["unresolved_reason"] == ""
            else:
                assert record["negative_category"] == ""
                assert record["unresolved_reason"]
