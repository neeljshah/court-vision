"""Per-file test for ci_schedule (W4 external one-tick entrypoint). NO full pytest."""
from __future__ import annotations

from scripts.platformkit.progress import ci_schedule
from scripts.platformkit.autonomy.work_queue import ALLOWED_KINDS


def test_main_runs_one_tick_returns_zero():
    calls = []

    def _fake_run(now=None):
        calls.append(now)
        return type("R", (), {"overall": "ok", "degraded": []})()

    rc = ci_schedule.main(run_fn=_fake_run, now=10.0)
    assert rc == 0
    assert calls == [10.0]  # exactly one tick


def test_next_run_deterministic_and_monotonic():
    a = ci_schedule.next_run(100.0, cadence=ci_schedule.NIGHTLY)
    b = ci_schedule.next_run(100.0, cadence=ci_schedule.NIGHTLY)
    assert a == b  # deterministic
    assert ci_schedule.next_run(100.0) < ci_schedule.next_run(100.0 + 24 * 3600)


def test_descriptor_kinds_subset_of_allowed():
    for name, desc in ci_schedule.DESCRIPTORS.items():
        assert set(desc.kinds).issubset(ALLOWED_KINDS), name


def test_does_not_self_arm_autostart():
    d = ci_schedule.describe("NIGHTLY")
    assert d["self_arms_autostart"] is False


def test_run_tick_degrade_isolated():
    def _boom(now=None):
        raise RuntimeError("cadence dead")
    # a raising cadence must not crash the external trigger
    assert ci_schedule.run_tick(1.0, run_fn=_boom) is None
    assert ci_schedule.main(run_fn=_boom, now=1.0) == 0


def test_no_dollar_field():
    import json
    d = ci_schedule.describe("NIGHTLY")
    # No $ as a data KEY (the honest 'no $' disclaimer note is excluded).
    assert not any("$" in str(k) for k in d)
    d.pop("note", None)
    blob = json.dumps(d).lower()
    for tok in ("pnl", "roi", "bankroll", "profit", "usd"):
        assert tok not in blob


if __name__ == "__main__":
    import sys
    for fn in (test_main_runs_one_tick_returns_zero,
               test_next_run_deterministic_and_monotonic,
               test_descriptor_kinds_subset_of_allowed,
               test_does_not_self_arm_autostart, test_run_tick_degrade_isolated,
               test_no_dollar_field):
        fn()
        print("ok:", fn.__name__)
    sys.exit(0)
