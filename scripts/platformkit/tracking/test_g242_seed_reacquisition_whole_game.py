import csv
from pathlib import Path

from scripts.platformkit.tracking import g242_seed_reacquisition_whole_game as subject


def test_fixed_whole_game_seed_and_sample_contract():
    assert subject.VIDEO.endswith("wnba__wnba_01.mp4")
    assert subject.SEED_FRAME == 19599
    assert subject.SAMPLE_STRIDE == 2000
    assert subject.SAMPLE_FRAMES[0] == 0 and subject.SAMPLE_FRAMES[-1] == 174000
    assert subject.SEED_FRAME in subject.SAMPLE_FRAMES
    assert len(subject.SAMPLE_FRAMES) == 89


def test_csv_reader_requires_exact_native_seed_labels():
    labels = subject.read_seed_labels(Path("docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv"))
    assert labels == ((350.0, 400.0), (835.0, 420.0), (390.0, 696.0), (990.0, 730.0))


def test_source_payload_reads_a_named_source_root(tmp_path):
    for module in subject.SOURCE_MODULES:
        path = tmp_path.joinpath(*module.split(".")).with_suffix(".py")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x=1\n", encoding="ascii")
    assert len(subject._source_payload(tmp_path)) == 3


def test_worker_keeps_unchanged_g222_acceptance_and_one_sequential_pass():
    worker = subject._worker_source({name: "cHJpbnQoMSk=" for name in subject.SOURCE_MODULES}, ((350.0, 400.0),) * 4, b"x")
    assert "estimate_motion(seed_features" in worker
    assert "for index in range(FRAMES):" in worker
    assert "capture.set(cv2.CAP_PROP_POS_FRAMES" not in worker
    assert "select=eq(n" in worker
    assert "matrix_max_abs > 1e-12" in worker


def test_per_sample_table_has_the_named_unchanged_gate_columns(tmp_path):
    record = {"source_frame": 0, "signed_distance_frames": -19599, "acquired_g222_unchanged": True,
              "render_path": "acquired_renders/frame_000000.jpg",
              "direct_seed": {"matches": 10, "inliers": 8, "inlier_ratio": 0.8, "rms_reprojection_px": 0.5}}
    path = tmp_path / "table.csv"
    subject.write_per_sample_table({"records": [record]}, path)
    assert list(csv.DictReader(path.open(encoding="ascii"))) == [{"source_frame": "0", "signed_distance_frames": "-19599",
        "acquired_g222_unchanged": "True", "matches": "10", "inliers": "8", "inlier_ratio": "0.8",
        "rms_reprojection_px": "0.5", "render_path": "acquired_renders/frame_000000.jpg"}]
