"""G206 regression tests for the pre-tracking route sidecar."""
import json

from scripts import run_clip


def test_sidecar_records_recomputable_uncapped_route_count(tmp_path, monkeypatch):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"route-source")
    monkeypatch.setattr(
        run_clip, "_validated_route_video_metadata",
        lambda _: ({"decoded_frames": 39035, "source_fps": 60.0,
                    "validation": "ffprobe_nb_frames_and_cv2_agree"}, None),
    )
    monkeypatch.setattr(run_clip, "_route_stride", lambda *_: 6)

    sidecar_path = run_clip._write_evaluated_count_sidecar(
        str(video), str(tmp_path), None, 0
    )
    sidecar = json.loads((tmp_path / "evaluated_frame_count.json").read_text())

    assert sidecar_path.endswith("evaluated_frame_count.json")
    assert sidecar == {
        "decoded_frames": 39035,
        "evaluated_frames": 6506,
        "formula": "ceil(decoded_frames / stride) when max_frames is null and start_frame is 0",
        "frame_count_validation": "ffprobe_nb_frames_and_cv2_agree",
        "max_frames": None,
        "reason": None,
        "schema_version": "g206-v1",
        "source_fps": 60.0,
        "source_frame_count": 39035,
        "source_path": str(video.resolve()),
        "source_size_bytes": len(b"route-source"),
        "start_frame": 0,
        "stride": 6,
    }


def test_sidecar_fails_closed_when_route_cap_is_detector_dependent(tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"route-source")

    sidecar = run_clip._evaluated_count_sidecar(str(video), 1200, 0)

    assert sidecar["evaluated_frames"] is None
    assert sidecar["reason"] == "max_frames_is_detector_dependent_in_this_route"
