"""Focused construction checks for the G235 process-only measurement runner."""
from scripts.platformkit.tracking.g235_build_court_crash_confirmation import (
    patched_method_source,
    remote_script,
)


def test_guarded_runner_injects_only_runtime_guard_and_observer() -> None:
    baseline = patched_method_source(False)
    guarded = patched_method_source(True)
    assert "_capture(locals())" in baseline
    assert "if False:" in baseline
    assert "if True:" in guarded
    assert "if _rw <= 0 or _rh <= 0:" in guarded
    assert "UnifiedPipeline._build_court = original" in guarded
    assert 'needle = "map_2d = cv2.resize(map_img, (_rw, _rh))"' in baseline


def test_remote_script_runs_probe_before_creating_tracking_directory() -> None:
    script = remote_script("reproduction")
    assert "dd if=/dev/zero" in script
    assert script.index("dd if=/dev/zero") < script.index('mkdir -p "$ROOT"')
    assert "rm -rf \"$ROOT\" \"$DATA_DIR\"" in script
