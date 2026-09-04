"""Focused tests for G211's reducer."""
from scripts.platformkit.tracking.g211_per_frame_cost import STAGES, floor_shifted, remote_script, summarize

def test_partition_is_additive() -> None:
    raw={"json":{"timing.json":{},"frames.json":{"frames":[dict(zip((*STAGES,"total"),(1,2,3,4,5,6,7,28)))]}},"text":{"cleanup_bytes.txt":"28 /tmp/g211"}}
    got=summarize(raw)
    assert got["mean_unattributed_seconds"] == 0.0
    assert got["cleanup_bytes"] == "28 /tmp/g211"
    assert got["distribution_seconds"] == {"median":28.0,"p90":28.0,"max":28.0}

def test_floor_shift_cutoff() -> None:
    assert not floor_shifted("load average: 20.00, 1, 1","load average: 25.00, 1, 1")
    assert floor_shifted("load average: 20.00, 1, 1","load average: 28.00, 1, 1")

def test_remote_run_probes_disk_before_creating_temporary_root() -> None:
    script = remote_script("unit", 1200)
    assert script.index("dd if=/dev/zero") < script.index('mkdir -p "$ROOT"')
    assert "du -sm /workspace/nba-ai-system/data" in script
    assert 'du -sb "$ROOT" "$DATA"' in script
