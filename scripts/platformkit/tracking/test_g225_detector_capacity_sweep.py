"""Focused static contract checks for the G225 transient measurement runner."""
from scripts.platformkit.tracking.g225_detector_capacity_sweep import (
    MODELS, ROUTE_FILES, remote_script, sitecustomize_source,
)


def test_g225_has_exactly_three_model_arms_and_adapter_route():
    assert MODELS == ("yolov8n", "yolov8s", "yolov8m")
    script = remote_script("yolov8s", 2, "test")
    assert "-m scripts.platformkit.adapter_run basketball" in script
    assert "--max-frames 6000" in script
    assert "CV_DETECTOR_MODEL=\"yolov8s.pt\"" in script
    assert "cd /workspace/nba-ai-system" in script


def test_g225_captures_weight_raw_box_render_and_resource_evidence():
    source = sitecustomize_source()
    for required in ("loaded_weight.json", "raw_boxes.json", "raw_boxes_e%04d.jpg",
                     "resource_samples.jsonl", "disk_guard.txt"):
        assert required in source or required in remote_script("yolov8n", 1, "test")
    assert "scripts/platformkit/adapter_run.py" in ROUTE_FILES
    assert "scripts/platformkit/detection/shim.py" in ROUTE_FILES


def test_g225_removes_only_auto_downloaded_capacity_weights():
    source = open("scripts/platformkit/tracking/g225_detector_capacity_sweep.py", encoding="utf-8").read()
    assert "for name in ('yolov8s.pt', 'yolov8m.pt')" in source
    assert "downloaded_weight_cleanup.json" in source
