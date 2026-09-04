"""Focused regression checks for the committed-data G244 calculation."""
from scripts.platformkit.tracking.g244_homography_validity_signal import analyze


def test_recomputes_g244_blind_labels_and_g241b_cut_drops() -> None:
    report = analyze()
    g242 = report["g242"]
    assert g242["validity_counts"] == {"VALID": 27, "INVALID": 28, "CANNOT_JUDGE": 34}
    assert g242["g242_scene_inventory_marginals"]["blind"] == g242["g242_scene_inventory_marginals"]["g242_reported"]
    assert g242["valid_invalid_range_overlap"]["matches"] == {
        "valid_in_invalid_range": 25,
        "invalid_in_valid_range": 24,
        "invalid_range_min": 114.0,
        "invalid_range_max": 652.0,
        "valid_range_min": 130.0,
        "valid_range_max": 2000.0,
    }
    assert report["matrix_sanity_availability"]["status"] == "NOT_REPRODUCIBLE_FROM_COMMITTED_G242_DATA"
    g241b = report["g241b"]
    assert g241b["cut_drops"] == {"3933": 128.0, "9823": 165.0}
    assert g241b["overlap"]["named_cuts_inside_ordinary_range"] == 2
    assert g241b["overlap"]["ordinary_drops_inside_named_cut_range"] == 0
