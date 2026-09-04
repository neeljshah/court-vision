"""Focused construction checks for the G236 memory-only pod search."""
from scripts.platformkit.tracking.g236_label_reindex_existence import (
    COARSE_STRIDE,
    _worker_source,
    remote_script,
)


def test_remote_script_probes_before_streaming_worker_and_removes_probe() -> None:
    script = remote_script("YWJj")
    assert COARSE_STRIDE == 5
    assert "dd if=/dev/zero" in script
    assert script.index("dd if=/dev/zero") < script.index("base64 -d | env G236_WORKER_SHA256=")
    assert 'rm -f "$PROBE"' in script
    assert "du -sm \"$DATA_ROOT\" | awk '{print $1}'" in script
    assert "mkdir" not in script


def test_range_refinement_does_not_cap_ffmpeg_to_one_frame() -> None:
    worker = _worker_source("YWJj")
    assert 'select=between(n\\,' in worker
    assert '"-frames:v", "1"' not in worker
