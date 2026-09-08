"""G304 adjudication batch 1: matching, 4 px threshold and the frame rule.

Synthetic construct only -- no packet file is opened, no registration is measured.
Run alone: python -m pytest tests/platformkit/test_g304_adjudication.py -q
"""
import csv

from scripts.platformkit.tracking.g304_adjudicate import (
    AGREEMENT_THRESHOLD_PX,
    FRAME_GOOD_RULE,
    FRAME_MIN_RESOLVED,
    FRAME_MIN_STRUCTURES,
    final_coordinate,
    frame_outcome,
    is_visible,
    load_locator,
    pair_items,
)


def test_threshold_and_frame_rule_are_the_spec_values():
    assert AGREEMENT_THRESHOLD_PX == 4
    assert FRAME_MIN_RESOLVED == 6
    assert FRAME_MIN_STRUCTURES == 3
    assert FRAME_GOOD_RULE == "p90 <= 12 px AND max <= 24 px"


def test_visible_flag_accepts_both_spellings():
    assert is_visible("TRUE") and is_visible("1")
    assert not is_visible("FALSE") and not is_visible("0") and not is_visible("")


def _write(path, rows, header):
    with open(path, "w", newline="", encoding="ascii") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def test_matching_is_row_id_plus_landmark_name(tmp_path):
    p1 = tmp_path / "p1.csv"
    p2 = tmp_path / "p2.csv"
    _write(p1, [
        {"row_id": "f1", "landmark_name": "KEY_TOP", "x": "100", "y": "200", "visible": "TRUE"},
        {"row_id": "f1", "landmark_name": "FT_LINE_L", "x": "300", "y": "400", "visible": "TRUE"},
        {"row_id": "f2", "landmark_name": "KEY_TOP", "x": "10", "y": "10", "visible": "FALSE"},
    ], ["row_id", "landmark_name", "x", "y", "visible"])
    _write(p2, [
        # same key, 3 px away -> agreement
        {"row_id": "f1", "landmark_name": "KEY_TOP", "x": "103", "y": "200", "visible": "1"},
        # same landmark name, different frame -> NOT the same item
        {"row_id": "f2", "landmark_name": "FT_LINE_L", "x": "301", "y": "400", "visible": "1"},
    ], ["row_id", "landmark_name", "x", "y", "visible"])

    items = {(i["row_id"], i["landmark_name"]): i
             for i in pair_items(load_locator(str(p1), ["f1", "f2"]),
                                 load_locator(str(p2), ["f1", "f2"]))}
    assert set(items) == {("f1", "KEY_TOP"), ("f1", "FT_LINE_L"), ("f2", "FT_LINE_L")}
    assert items[("f1", "KEY_TOP")]["presence"] == "both"
    assert items[("f1", "KEY_TOP")]["distance_px"] == 3
    assert items[("f1", "KEY_TOP")]["needs_adjudication"] is False
    # pass-1-only and pass-2-only both count as disagreements
    assert items[("f1", "FT_LINE_L")]["presence"] == "pass1_only"
    assert items[("f1", "FT_LINE_L")]["needs_adjudication"] is True
    assert items[("f2", "FT_LINE_L")]["presence"] == "pass2_only"
    assert items[("f2", "FT_LINE_L")]["needs_adjudication"] is True


def test_four_px_is_the_boundary(tmp_path):
    def dist_item(dx):
        p1, p2 = tmp_path / "a.csv", tmp_path / "b.csv"
        _write(p1, [{"row_id": "f", "landmark_name": "KEY_TOP", "x": "0", "y": "0", "visible": "TRUE"}],
               ["row_id", "landmark_name", "x", "y", "visible"])
        _write(p2, [{"row_id": "f", "landmark_name": "KEY_TOP", "x": str(dx), "y": "0", "visible": "1"}],
               ["row_id", "landmark_name", "x", "y", "visible"])
        return pair_items(load_locator(str(p1), ["f"]), load_locator(str(p2), ["f"]))[0]

    assert dist_item(4)["needs_adjudication"] is False   # exactly 4 px agrees
    assert dist_item(5)["needs_adjudication"] is True    # > 4 px must be adjudicated


def test_final_coordinate_follows_the_outcome():
    a, b = (100.0, 200.0), (104.0, 200.0)
    assert final_coordinate("agreed", a, b) == (102, 200)
    assert final_coordinate("pass1", a, b) == a
    assert final_coordinate("pass2", a, b) == b
    assert final_coordinate("both_wrong", a, b) is None
    assert final_coordinate("unidentifiable", a, None) is None


def test_frame_rule_needs_six_landmarks_across_three_structures():
    six_two_structures = ["FT_LINE_L", "FT_LINE_R", "LANE_BASE_L",
                          "LANE_BASE_R", "CORNER_FAR_L", "CORNER_FAR_R"]
    out = frame_outcome(six_two_structures)
    assert out["resolved_landmarks"] == 6
    assert out["structures"] == 3          # corners, lane, free-throw line
    assert out["e1_ready"] is True

    # six landmarks, only two structures -> short
    out = frame_outcome(["FT_LINE_L", "FT_LINE_R", "LANE_BASE_L", "LANE_BASE_R",
                         "FT_LINE_L", "LANE_BASE_R"])
    assert out["resolved_landmarks"] == 6 and out["structures"] == 2
    assert out["e1_ready"] is False

    # five landmarks across four structures -> short
    out = frame_outcome(["FT_LINE_L", "LANE_BASE_L", "KEY_TOP",
                         "CENTER_CIRCLE_TOP", "CENTER_SIDELINE_FAR"])
    assert out["resolved_landmarks"] == 5 and out["structures"] == 5
    assert out["e1_ready"] is False

    assert frame_outcome([])["e1_ready"] is False
