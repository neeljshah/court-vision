"""Focused tests for G211's reducer."""
from scripts.platformkit.tracking.g211_per_frame_cost import STAGES, floor_shifted, summarize

def test_partition_is_additive() -> None:
    raw={"json":{"timing.json":{},"frames.json":{"frames":[dict(zip((*STAGES,"total"),(1,2,3,4,5,6,7,28)))]}},"text":{}}
    got=summarize(raw)
    assert got["mean_unattributed_seconds"] == 0.0
    assert got["distribution_seconds"] == {"median":28.0,"p90":28.0,"max":28.0}

def test_floor_shift_cutoff() -> None:
    assert not floor_shifted("load average: 20.00, 1, 1","load average: 25.00, 1, 1")
    assert floor_shifted("load average: 20.00, 1, 1","load average: 28.00, 1, 1")
