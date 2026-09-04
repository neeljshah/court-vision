"""Focused contract tests for G241b's corrected geometry-only wrapper."""

from scripts.platformkit.tracking import g241b_seed_horizon_to_failure as subject


def test_frozen_seed_and_target_contract():
    assert subject.VIDEO == "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
    assert subject.SEED_FRAME == 19599
    assert subject.IMAGE_POINTS == ((350.0, 400.0), (835.0, 420.0), (390.0, 696.0), (990.0, 730.0))
    assert subject.SPORT == "wnba"
    assert subject.CONTROL_FRAME_COUNT == 1200
    assert subject.DEFAULT_TARGET_FRAME_COUNT == 10000
    assert subject.SOURCE_MODULES[-1].endswith("g222_direct_to_seed_propagation")


def test_worker_keeps_geometry_gate_separate_from_advisory_detector():
    worker = subject._worker_source({name: "cHJpbnQoMSk=" for name in subject.SOURCE_MODULES}, 1200, True)
    assert 'g222.measure_paired(Path(VIDEO), paired, seed_frame=SEED_FRAME,' in worker
    assert 'frame_count=FRAME_COUNT, stride=1, render_distances=intervals)' in worker
    assert 'direct_seed_eligible": row["direct_seed_eligible"]' in worker
    assert 'from src.tracking.player_detection import FeetDetector' in worker
    assert 'advisory_detector_records' in worker
    assert 'court_points_for_sport("wnba")' in worker


def test_direct_geometry_rows_excludes_detector_payload():
    report = {"direct_geometry_records": [{"distance_frames": 1, "direct_seed_eligible": True}], "advisory_detector_records": [{"distance_frames": 1}]}
    assert subject.direct_geometry_rows(report) == [{"distance_frames": 1, "direct_seed_eligible": True}]


def test_explicit_pod_transport_uses_key_port_and_no_deploy_configuration():
    assert subject._ssh_options(__import__("pathlib").Path("id_rsa"), 40034) == [
        "-i", "id_rsa", "-p", "40034", "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=accept-new",
    ]
    assert subject._scp_options(__import__("pathlib").Path("id_rsa"), 40034)[2:4] == ["-P", "40034"]
