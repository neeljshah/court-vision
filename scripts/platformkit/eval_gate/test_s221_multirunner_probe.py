"""Per-file construct test for the S221 multi-runner queue probe."""
from __future__ import annotations

from scripts.platformkit.eval_gate import s221_multirunner_probe as probe


def test_s221_enumerates_all_lifecycles_horizons_and_bindings(tmp_path):
    summary = probe.run_probe(tmp_path)
    cases = summary["cases"]

    assert summary["n"] == 12
    assert len(cases) == 12
    assert {(case["horizon_seconds"], case["lifecycle"], case["sport_binding"])
            for case in cases} == {
                (horizon, lifecycle, binding)
                for horizon in probe.HORIZONS
                for lifecycle in probe.LIFECYCLES
                for binding, _ in probe.BINDINGS
            }
    assert all(case["runner_b_double_claimed"] == 0 for case in cases)
    assert all(case["sport_null_queued_startup"] == 0 for case in cases)
    assert sum(case["sigterm_handler_exercised"] for case in cases) == 4
    assert summary["differential"] == []
    assert "sigterm_restart | bound | 901 | 0 | 0" in probe.render_table(summary)
