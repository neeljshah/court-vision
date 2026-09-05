"""Focused G292 pins for the frozen G289 population and G273 crop geometry."""
from pathlib import Path

from scripts.platformkit.tracking.g292_jump_endpoint_content import (
    CROP_HEIGHT, CROP_WIDTH, ENDPOINT_COUNT, EXPECTED_ELIGIBLE, SAMPLE_SIZE,
    endpoint_map, read_steps, read_verdicts, select_evenly,
)


ROOT = Path(__file__).resolve().parents[2]
STEPS = ROOT / "docs/evidence/tracking/g289_implausible_step_decomposition_artifact/steps.csv"


def test_committed_g289_large_jump_population_and_one_per_bin_sample():
    rows = read_steps(STEPS)
    selected = select_evenly(rows)
    assert len(rows) == EXPECTED_ELIGIBLE == 1897
    assert len(selected) == SAMPLE_SIZE == 36
    assert len({row["time_bin"] for row in selected}) == SAMPLE_SIZE
    assert len(endpoint_map(selected)) == ENDPOINT_COUNT == 72


def test_g273_matched_native_crop_geometry():
    assert (CROP_WIDTH, CROP_HEIGHT) == (512, 640)


def test_committed_g287_baseline_uses_its_landed_order_field():
    baseline = ROOT / "docs/evidence/tracking/g287_unconditioned_footpoint_content_artifact/blind_verdicts.csv"
    rows = read_verdicts(baseline, mandatory_detail=False)
    assert len(rows) == 72
    assert sum(row["category"] in {"A", "B"} for row in rows.values()) == 32
