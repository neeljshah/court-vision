import json

from scripts.platformkit.tracking import g254_projection_refinement_and_basin as subject


def test_perturbation_grid_is_fixed_and_covers_all_transform_families():
    rows = subject.perturbations()
    assert len(rows) == 43
    assert {row["family"] for row in rows} == {"identity", "translation", "rotation", "scale", "joint"}
    assert max(abs(float(row["tx"])) for row in rows) == 96.0
    assert max(abs(float(row["degrees"])) for row in rows) == 8.0


def test_worker_has_fixed_g252_reporting_and_no_label_input():
    worker = subject._worker_source([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    compile(worker, "g254_worker", "exec")
    assert "cv2.Canny" in worker
    assert "normal_offsets" in worker
    assert "G252 exact" in worker
    assert "ffmpeg" in worker
    assert "corner_pixel_targets" not in worker


def test_run_report_can_be_serialized_without_nan(tmp_path):
    payload = {"refinement": {"objective": 1.0}, "perturbations": []}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(payload, allow_nan=False), encoding="ascii")
    assert json.loads(path.read_text(encoding="ascii"))["refinement"]["objective"] == 1.0
