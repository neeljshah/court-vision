"""Focused tests for time-based adapter sampling and reporting-only rates."""
from scripts.platformkit.tracking_timebase import per_second, sampling_plan, timebase_metrics


def test_common_frame_rates_target_a_tenth_second_without_gate_rescaling():
    slow = sampling_plan(25.0)
    standard = sampling_plan(30000 / 1001)
    fast = sampling_plan(60000 / 1001)

    assert slow.stride == 2 and slow.sample_interval_seconds == 0.08
    assert standard.stride == 3
    assert round(fast.sample_interval_seconds, 4) == 0.1001


def test_rates_are_derived_alongside_unchanged_raw_values():
    plan = sampling_plan(30.0)
    metrics = timebase_metrics({"median_step_distance": 0.4, "jump_p95": 2.0}, plan)

    assert metrics["median_step_distance_raw"] == 0.4
    assert metrics["median_step_distance_per_second"] == 4.0
    assert metrics["jump_p95_per_second"] == 20.0
    assert per_second(1.0, None) is None
