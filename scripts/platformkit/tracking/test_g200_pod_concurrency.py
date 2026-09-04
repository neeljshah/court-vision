"""Focused tests for the G200 scheduling-metric reducer."""
from scripts.platformkit.tracking.g200_pod_concurrency import summarize_arm


def test_summarize_arm_keeps_each_job_and_computes_scheduling_metrics() -> None:
    raw = {
        "json": {"arm.json": {"concurrency": 2, "total_wall_seconds": 120.0},
                 "job_1.json": {"job": 1, "wall_seconds": 60.0},
                 "job_2.json": {"job": 2, "wall_seconds": 90.0}},
        "text": {"parents.txt": "10\n20\n", "disk_guard.txt": "pass: wrote and removed 4 MiB\n"},
        "samples": [
            {"jobs": {"10": {"cpu_pct": 100.0, "rss_kib": 10}, "20": {"cpu_pct": 200.0, "rss_kib": 20}},
             "memory": {"used_bytes": 5}, "gpu": {"utilization_pct": 8.0, "memory_used_mib": 9.0}},
            {"jobs": {"10": {"cpu_pct": 300.0, "rss_kib": 30}, "20": {"cpu_pct": 400.0, "rss_kib": 40}},
             "memory": {"used_bytes": 7}, "gpu": {"utilization_pct": 6.0, "memory_used_mib": 11.0}},
        ],
    }
    result = summarize_arm(raw, baseline_seconds=30.0)
    assert result["jobs_per_minute"] == 1.0
    assert result["jobs"][0]["slowdown_factor_vs_n1"] == 2.0
    assert result["jobs"][1]["peak_rss_kib"] == 40
    assert result["mean_aggregate_cpu_pct"] == 500.0
    assert result["peak_gpu_memory_used_mib"] == 11.0
