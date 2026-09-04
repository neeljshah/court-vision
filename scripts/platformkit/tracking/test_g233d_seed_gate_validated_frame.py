"""Focused contract tests for the G233d remote measurement wrapper."""
import json

from scripts.platformkit.tracking import g233d_seed_gate_validated_frame as subject


def test_fixed_validated_seed_contract_and_unchanged_modules():
    assert subject.VIDEO == "/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
    assert subject.SEED_FRAME == 19599
    assert subject.IMAGE_POINTS == ((350.0, 400.0), (835.0, 420.0), (390.0, 696.0), (990.0, 730.0))
    assert subject.SPORT == "wnba"
    assert subject.FRAME_COUNT == 1200
    assert subject.SOURCE_MODULES[-1].endswith("g222_direct_to_seed_propagation")


def test_worker_uses_wnba_model_direct_detector_and_named_denominator():
    worker = subject._worker_source({name: "cHJpbnQoMSk=" for name in subject.SOURCE_MODULES})
    assert 'court_points_for_sport("wnba")' in worker
    assert 'sys.path.insert(0, "/workspace/nba-ai-system")' in worker
    assert "from src.tracking.player_detection import FeetDetector" in worker
    assert "all direct-detector player boxes with finite projections" in worker
    assert 'select=eq(n' not in worker
    assert json.loads(json.dumps(subject.IMAGE_POINTS)) == [[350.0, 400.0], [835.0, 420.0], [390.0, 696.0], [990.0, 730.0]]


def test_remote_result_selects_json_after_detector_output(monkeypatch):
    class Completed:
        returncode = 0
        stderr = b""
        stdout = "detector progress: \u2588\n{\"temp_dir\":\"/tmp/g233d_seed_x\"}\n".encode("utf-8")

    monkeypatch.setattr(subject.subprocess, "run", lambda *args, **kwargs: Completed())
    assert subject._remote_run("worker", __import__("pathlib").Path("config"), "pod") == {"temp_dir": "/tmp/g233d_seed_x"}
