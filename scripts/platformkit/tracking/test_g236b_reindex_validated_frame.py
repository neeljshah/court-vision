"""Focused construction checks for the G236b memory-only pod search."""
from scripts.platformkit.tracking.g236b_reindex_validated_frame import (
    COARSE_STRIDE,
    LABELLED_INDEX,
    VIDEO,
    _worker_source,
    remote_script,
)


def test_remote_script_guards_and_removes_its_only_pod_write() -> None:
    script = remote_script("YWJj")
    assert COARSE_STRIDE == 5
    assert 'dd if=/dev/zero of="$PROBE" bs=1M count=4 conv=fsync' in script
    assert script.index("dd if=/dev/zero") < script.index("base64 -d | env G236B_WORKER_SHA256=")
    assert 'rm -f "$PROBE"' in script
    assert "mkdir" not in script


def test_worker_uses_validated_native_resolution_and_named_baseline() -> None:
    worker = _worker_source("YWJj")
    assert VIDEO.endswith("/wnba__wnba_01.mp4")
    assert LABELLED_INDEX == 1600
    assert "label.shape != (1080, 1920, 3)" in worker
    assert 'select=between(n\\,' in worker
    assert "confirmation_mad_1920x1080" in worker
