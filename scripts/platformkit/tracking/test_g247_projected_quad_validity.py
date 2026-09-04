import csv
import json

import numpy as np

from scripts.platformkit.tracking import g247_projected_quad_validity as subject


def test_fixed_predecessor_contract():
    assert subject.g242.SEED_FRAME == 19599
    assert subject.g242.SAMPLE_STRIDE == 2000
    assert len(subject.g242.SAMPLE_FRAMES) == 89
    assert subject.QUAD_PERIMETER_ROLE_INDICES == (0, 1, 3, 2)


def test_quad_checks_use_role_order_to_form_a_convex_perimeter():
    corners = np.array(((0, 0), (4, 0), (0, 3), (4, 3)), dtype=float)
    checks = subject.quad_checks(np.eye(3), corners, 10, 10, seed_signed_area=12.0)
    assert checks["is_convex"] is True
    assert checks["winding_inverted_relative_seed"] is False
    assert checks["corner_order_consistent_with_seed"] is True
    assert checks["projected_area_ratio_to_seed"] == 1.0
    assert checks["outside_corner_fraction"] == 0.0


def test_analysis_keeps_all_three_g244_classes_and_inclusive_overlap():
    labels = {0: "VALID", 1: "INVALID", 2: "CANNOT_JUDGE"}
    records = []
    for frame, scale in enumerate((1.0, 2.0, 3.0)):
        corners = (np.array(((0, 0), (4, 0), (0, 3), (4, 3)), dtype=float) * scale).tolist()
        records.append({"source_frame": frame, "homography_image_to_court": np.eye(3).tolist(),
                        "projected_court_corners_px_role_order": corners})
    report = {"seed": {"projected_court_corners_px_role_order": records[0]["projected_court_corners_px_role_order"]}, "records": records}
    analysis = subject.analyze(report, labels)
    assert analysis["validity_counts"] == {"VALID": 1, "INVALID": 1, "CANNOT_JUDGE": 1}
    assert analysis["valid_invalid_range_overlap"]["projected_area_ratio_to_seed"]["valid_in_invalid_range"] == 0
    assert all("quad_checks" in row for row in records)


def test_worker_is_one_pass_and_stops_on_embedded_control_counts():
    payload = {name: "cHJpbnQoMSk=" for name in subject.g242.SOURCE_MODULES}
    worker = subject._worker_source(payload, ((350.0, 400.0),) * 4, b"x", {0: (1, 1)})
    compile(worker, "g247_worker", "exec")
    assert "for index in range(FRAMES):" in worker
    assert "capture.set(cv2.CAP_PROP_POS_FRAMES" not in worker
    assert "COUNTS.get(row" in worker
    assert "render_overlay" not in worker


def test_expected_counts_are_named_complete_g242_rows(tmp_path):
    path = tmp_path / "table.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("source_frame", "matches", "inliers"))
        writer.writeheader()
        for frame in range(89):
            writer.writerow({"source_frame": frame, "matches": 4, "inliers": 4})
    assert subject._expected_counts(path)[88] == (4, 4)
