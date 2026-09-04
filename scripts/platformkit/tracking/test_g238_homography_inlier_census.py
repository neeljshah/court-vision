"""Focused construction checks for the isolated G238 observation runner."""

from scripts.platformkit.tracking.g238_homography_inlier_census import (
    instrumented_source,
    remote_script,
)


def test_observer_restores_methods_and_records_required_runtime_fields() -> None:
    source = instrumented_source()
    assert "UnifiedPipeline._get_homography = original_homography" in source
    assert "UnifiedPipeline._load_pano = original_pano" in source
    assert "inliers=inliers" in source
    assert "matches=int(mask.size)" in source
    assert "installed_m=True" in source
    assert "homography_calls" in source
    assert "reuse_or_suspension" in source
    assert "source.rfind(final_return)" in source
    assert "capture_pano('general_fallback'" in source


def test_remote_launcher_checks_load_and_disk_before_tracking_directory() -> None:
    source = remote_script("unit")
    assert "active_transient_routes" in source
    assert "dd if=/dev/zero" in source
    assert source.index("dd if=/dev/zero") < source.index('mkdir -p "$ROOT" "$DATA_DIR"')
    assert "rm -rf \"$ROOT\" \"$DATA_DIR\"" in source
