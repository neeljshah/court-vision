import json

from scripts.platformkit.tracking import g248_projected_line_image_agreement as subject


def test_fixed_geometry_contains_required_marking_families():
    lines = subject.court_line_geometry()
    assert len(lines) == 19
    assert [[0.0, 0.0], [50.0, 0.0]] in lines
    assert [[17.0, 0.0], [17.0, 19.0]] in lines
    assert any(len(line) == 121 for line in lines)


def test_analysis_keeps_cannot_judge_separate_and_uses_inclusive_ranges():
    labels = {0: "VALID", 1: "INVALID", 2: "CANNOT_JUDGE"}
    records = []
    for frame, base in enumerate((1.0, 2.0, 3.0)):
        records.append({"source_frame": frame, "signals": {
            "edge_response_contrast": base, "line_detector_agreement": base / 10,
            "marking_contrast": base + 4, "coverage": base / 4,
        }})
    report = subject.analyze({"records": records}, labels)
    assert report["validity_counts"] == {"VALID": 1, "INVALID": 1, "CANNOT_JUDGE": 1}
    assert report["valid_invalid_range_overlap"]["edge_response_contrast"]["valid_in_invalid_range"] == 0
    assert report["distributions"]["coverage"]["CANNOT_JUDGE"]["n"] == 1


def test_worker_is_single_pass_and_uses_fixed_controls_and_lsd():
    worker = subject._worker_source({0: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]})
    compile(worker, "g248_worker", "exec")
    assert "for index in range(FRAME_COUNT):" in worker
    assert "capture.set(cv2.CAP_PROP_POS_FRAMES" not in worker
    assert "LSD_REFINE_STD" in worker
    assert '"near":NEAR,"far":FAR' in worker
    assert "def clip(a,b,width,height):" in worker
    assert "range(0,len(points),16000)" in worker


def test_g247_reader_rejects_a_nonmatching_denominator(tmp_path):
    path = tmp_path / "g247.json"
    path.write_text(json.dumps({"records": [{"source_frame": 0, "homography_image_to_court": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}]}), encoding="ascii")
    try:
        subject.read_g247(path, {1: "VALID"})
    except ValueError as exc:
        assert "same 89 frames" in str(exc)
    else:
        raise AssertionError("expected denominator mismatch")
