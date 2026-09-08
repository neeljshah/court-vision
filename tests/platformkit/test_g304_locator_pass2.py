"""Schema and count rail for the gpt-5.6-terra G304 locator-pass artifact."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "docs/evidence/tracking/g304_locator_pass2_terra_2026-09-07.csv"
ELIGIBILITY_PATH = ROOT / "docs/evidence/tracking/g304_eligibility_sol_2026-09-07.csv"
FIELDS = [
    "row_id", "source_id", "arena", "classification", "negative_category",
    "landmark_name", "x", "y", "visible", "confidence", "note", "locator_name",
]
VOCABULARY = {
    "CORNER_NEAR_L", "CORNER_NEAR_R", "CORNER_FAR_L", "CORNER_FAR_R",
    "LANE_BASE_L", "LANE_BASE_R", "FT_LINE_L", "FT_LINE_R", "KEY_TOP",
    "THREE_PT_BASE_L", "THREE_PT_BASE_R", "CENTER_SIDELINE_NEAR",
    "CENTER_SIDELINE_FAR", "CENTER_CIRCLE_TOP", "CENTER_CIRCLE_BOTTOM",
}


def test_g304_locator_pass2_schema_coordinates_and_cardinality() -> None:
    with CSV_PATH.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    with ELIGIBILITY_PATH.open(newline="", encoding="ascii") as handle:
        eligibility = {row["row_id"]: row for row in csv.DictReader(handle)}

    assert list(rows[0]) == FIELDS
    assert set(row["row_id"] for row in rows) == set(eligibility)
    assert all(row["locator_name"] == "gpt-5.6-terra" for row in rows)

    by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_id[row["row_id"]].append(row)
        assert row["classification"] == eligibility[row["row_id"]]["classification"]
        assert 0.0 <= float(row["confidence"]) <= 1.0
        if row["landmark_name"]:
            assert row["landmark_name"] in VOCABULARY
            assert 0 <= int(row["x"]) < 1920
            assert 0 <= int(row["y"]) < 1080

    counts = Counter(row["classification"] for row in eligibility.values())
    assert counts == {"ELIGIBLE": 23, "NEGATIVE": 35, "UNRESOLVABLE": 2}
    for row_id, source in eligibility.items():
        annotated = by_id[row_id]
        if source["classification"] == "ELIGIBLE":
            visible = [item for item in annotated if item["visible"] == "1"]
            shortfall = [item for item in annotated if "shortfall:" in item["note"]]
            assert len(visible) >= 6 or len(shortfall) == 1
        elif source["classification"] == "NEGATIVE":
            assert len(annotated) == 1
            assert annotated[0]["negative_category"] == source["negative_category"]
            assert not annotated[0]["landmark_name"]
        else:
            assert len(annotated) == 1
            assert not annotated[0]["landmark_name"]
            assert annotated[0]["note"]
