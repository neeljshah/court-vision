import json

from scripts.platformkit.tracking import g252_projection_accuracy_in_pixels as subject


def test_geometry_covers_every_required_line_type():
    kinds = [kind for kind, _ in subject.court_line_geometry()]
    assert set(kinds) == set(subject.LINE_TYPES)
    assert kinds.count("baseline") == 2
    assert kinds.count("sideline") == 2


def test_analysis_retains_no_candidate_samples_and_pools_them():
    labels = {0: "VALID", 1: "INVALID", 2: "CANNOT_JUDGE"}
    line_types = {line: {"sample_points": 1, "no_candidate": 0, "distances_px": [2.0]} for line in subject.LINE_TYPES}
    line_types["arc"] = {"sample_points": 2, "no_candidate": 1, "distances_px": [3.0]}
    records = [{"source_frame": frame, "line_types": line_types} for frame in labels]
    report = subject.analyze({"records": records}, labels)
    valid = report["distributions"]["VALID"]
    assert valid["arc"] == {"sample_points": 2, "found": 1, "no_candidate": 1, "median": 3.0, "p90": 3.0, "max": 3.0}
    assert valid["pooled"]["sample_points"] == 7
    assert valid["pooled"]["no_candidate"] == 1


def test_worker_is_single_pass_and_has_a_bounded_normal_search():
    worker = subject._worker_source({0: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]})
    compile(worker, "g252_worker", "exec")
    assert "for index in range(FRAME_COUNT):" in worker
    assert "capture.set(cv2.CAP_PROP_POS_FRAMES" not in worker
    assert "np.arange(-RADIUS,RADIUS+1" in worker
    assert "cv2.Canny(gray,LOW,HIGH" in worker


def test_g247_reader_rejects_nonmatching_denominator(tmp_path):
    path = tmp_path / "g247.json"
    path.write_text(json.dumps({"records": [{"source_frame": 0, "homography_image_to_court": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}]}), encoding="ascii")
    try:
        subject.read_g247(path, {1: "VALID"})
    except ValueError as exc:
        assert "complete fixed" in str(exc)
    else:
        raise AssertionError("expected a denominator mismatch")
