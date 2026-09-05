"""Pin G298's immutable denominator, conventions, and paired arithmetic."""
from pathlib import Path
import json

import pytest

from scripts.platformkit.tracking.g298_compare import (
    ELIGIBLE_FEET, FRAME_COUNT, TOLERANCES, bottom_centre, exact_mcnemar, read_locations,
    compare, write_csv,
)


def test_committed_denominator_and_frames() -> None:
    path = Path(__file__).resolve().parents[3] / (
        "docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv")
    rows = read_locations(path)
    assert len(rows) == ELIGIBLE_FEET == 143
    assert FRAME_COUNT == 15
    assert sorted({int(r["source_frame"]) for r in rows}) == [
        19630, 19879, 20190, 20440, 20689, 20938, 21187, 21499,
        21686, 21935, 22247, 22496, 22683, 22994, 23368]
    assert TOLERANCES == (25, 50, 100)


def test_bottom_centre_matches_production_integer_clipping() -> None:
    assert bottom_centre([10, 20, 30, 90]) == (20, 90)
    assert bottom_centre([10.9, 20.2, 31.8, 90.9]) == (20, 90)
    assert bottom_centre([-10, 20, 2000, 1100]) == (960, 1080)


def test_exact_paired_discordance() -> None:
    result = exact_mcnemar([False] * 10, [True] * 10)
    assert result == {"lost": 0, "gained": 10, "discordant": 10, "nominal_p": 2 / 1024}
    assert exact_mcnemar([True, False], [True, False])["nominal_p"] == 1
    assert exact_mcnemar([True, False], [False, True])["nominal_p"] == 1


def test_missing_foot_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "incomplete.csv"
    path.write_text("source_frame,player_id,foot_x_px,foot_y_px\n19630,p01,10,20\n")
    with pytest.raises(AssertionError, match="143"):
        read_locations(path)


def test_empty_detection_frame_keeps_all_143_eligible(tmp_path: Path) -> None:
    located = Path(__file__).resolve().parents[3] / (
        "docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv")
    feet = read_locations(located)
    frames = sorted({int(r["source_frame"]) for r in feet})
    for arm in ("A", "A_repeat", "B", "C"):
        detections = [{"source_frame": r["source_frame"], "foot_x_px": r["foot_x_px"],
                       "foot_y_px": r["foot_y_px"]} for r in feet
                      if arm not in ("A", "A_repeat") or int(r["source_frame"]) != frames[0]]
        write_csv(tmp_path / f"{arm}.csv", detections)
        (tmp_path / f"{arm}_summary.json").write_text(json.dumps(
            {"frames": frames, "total_detections": len(detections)}))
    result = compare(located, tmp_path)
    assert result["A_byte_identical"] is True
    assert result["arms"]["A"]["counts_per_frame"][frames[0]] == 0
    for tolerance in TOLERANCES:
        assert result["arms"]["A"]["recall"][tolerance] == {
            "matched": 133, "eligible_denominator": 143, "recall": 133 / 143}
        assert result["arms"]["B"]["recall"][tolerance]["matched"] == 143
        assert result["paired_tests"]["A_vs_B"][tolerance]["gained"] == 10
