"""Focused G305 construct test for additive registration instrumentation."""
import json
from pathlib import Path

from scripts.platformkit.tracking.g305_additive_registration_verdict import (
    CONSTRUCT_CASES,
    Q_TIMES_R_CONDITION,
    additive_record,
    canonical_passing_table,
    geometry_to_harness_homography,
    geometry_to_harness_point,
    harness_to_geometry_homography,
    harness_to_geometry_point,
    reflect_harness_table,
    registration_passed,
    run_construct,
    sha256_bytes,
    sha256_lf,
    write_construct_evidence,
)
from scripts.platformkit.tracking_harness import DEFAULT_CONFIG_VERSION


def test_g305_exhaustive_additive_construct(tmp_path):
    harness_path = Path(__file__).resolve().parents[3] / "scripts/platformkit/tracking_harness.py"
    before_hash = sha256_bytes(harness_path)
    table = canonical_passing_table()
    reflected_table = reflect_harness_table(table)
    original, reflected, record = run_construct()

    assert CONSTRUCT_CASES == (
        "near_left_corner", "near_right_corner", "far_left_corner", "far_right_corner",
        "asymmetric_interior_point", "original_harness_run", "reflected_harness_run",
        "worked_additive_record",
    )
    assert original.config_version == DEFAULT_CONFIG_VERSION
    assert original.passed and reflected.passed
    assert original.self_consistency_only is True and reflected.self_consistency_only is True
    assert original.verdict == reflected.verdict == "PASS"
    assert original.failures == reflected.failures == []
    assert (reflected_table["x"] == 94.0 - table["x"]).all()
    assert reflected_table.drop(columns=["x"]).equals(table.drop(columns=["x"]))

    corners = {
        "near_left_corner": ((0.0, 0.0), (0.0, 0.0)),
        "near_right_corner": ((50.0, 0.0), (0.0, 50.0)),
        "far_left_corner": ((0.0, 94.0), (94.0, 0.0)),
        "far_right_corner": ((50.0, 94.0), (94.0, 50.0)),
        "asymmetric_interior_point": ((13.25, 72.5), (72.5, 13.25)),
    }
    for geometry_point, harness_point in corners.values():
        assert geometry_to_harness_point(geometry_point) == harness_point
        round_trip = harness_to_geometry_point(harness_point)
        assert all(abs(actual - expected) <= 1e-9 for actual, expected in zip(round_trip, geometry_point))
    matrix = ((1.2, 0.1, 4.0), (0.05, 0.9, 8.0), (0.001, 0.002, 1.0))
    assert harness_to_geometry_homography(geometry_to_harness_homography(matrix)) == matrix

    accepted_e1 = {
        "sealed_g304_packet_available": True, "fixed_correspondence_count": 6,
        "correct_shot_end_orientation": True, "court_end_identified": True,
        "homography_finite": True, "rank_finite": True, "rank_observable": True,
        "held_out_errors_px": [8.0, 9.0, 10.0, 11.0, 12.0],
        "uncensored_per_frame_errors_px": [8.0, 9.0, 10.0, 11.0, 12.0],
    }
    assert registration_passed(accepted_e1) is True
    assert registration_passed({**accepted_e1, "held_out_errors_px": [8.0, 25.0],
                                "uncensored_per_frame_errors_px": [8.0, 25.0]}) is False
    assert registration_passed({**accepted_e1, "held_out_errors_px": [13.0] * 10,
                                "uncensored_per_frame_errors_px": [13.0] * 10}) is False
    assert record["registration_passed"] is None
    assert record["player_tracking_passed"] is True and record["ball_tracking_passed"] is True
    assert record["q"] is None and record["r"] is None and record["q_times_r"] is None
    assert record["q_times_r_necessary_condition"] == Q_TIMES_R_CONDITION
    q_record = additive_record(original, record["mode"], record["registration_evidence"], 0.8, 0.75)
    assert abs(q_record["q_times_r"] - 0.60) <= 1e-12
    assert record["harness_verdict_json"] == original.to_json()
    assert record["harness_verdict_record"] == json.loads(original.to_json())
    assert set(record["hashes"]) == {"harness_sha256", "schema_sha256", "liveness_sha256", "producer_sha256"}
    assert record["hashes"]["harness_sha256"] == before_hash

    paths = write_construct_evidence(tmp_path / "evidence")
    assert json.loads(paths[0].read_text(encoding="utf-8")) == json.loads(original.to_json())
    assert json.loads(paths[1].read_text(encoding="utf-8")) == json.loads(reflected.to_json())
    assert json.loads(paths[2].read_text(encoding="utf-8"))["harness_verdict_json"] == original.to_json()
    assert sha256_bytes(harness_path) == before_hash
    assert len(sha256_lf(harness_path)) == 64
