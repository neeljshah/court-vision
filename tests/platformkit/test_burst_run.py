"""Burst-runner isolation + RSS-guard + report-shape tests.

Every step callable is monkeypatched so no network/disk-heavy real work runs;
the point is the ORCHESTRATION contract: one step raising never stops the rest,
the 3GB RSS guard aborts the remainder, and the report shape is stable.
"""
import json

import scripts.platformkit.burst_run as B


def _patch_all_ok(monkeypatch):
    """Make every step a fast no-op that records it ran."""
    ran = []
    for _name, _slow, fnname in B._STEP_SPECS:
        # bind fnname per-iteration
        monkeypatch.setattr(B, fnname,
                            (lambda n=fnname: (lambda: (ran.append(n) or {"ok": True})))())
    return ran


def test_report_shape_all_ok(tmp_path, monkeypatch):
    ran = _patch_all_ok(monkeypatch)
    monkeypatch.setattr(B, "_rss_mb", lambda: 100.0)
    rep = B.run_burst(rss_fn=lambda: 100.0, report_path=tmp_path / "r.json")

    assert rep["edge_claimed"] is False
    assert "started" in rep and rep["honest_note"]
    assert len(rep["steps"]) == len(B._STEP_SPECS)
    assert len(ran) == len(B._STEP_SPECS)
    for s in rep["steps"]:
        assert set(s) == {"name", "status", "secs", "rss_mb_after"}
        assert s["status"] == "ok"
    # report was written to disk with the same shape
    disk = json.loads((tmp_path / "r.json").read_text(encoding="ascii"))
    assert disk["edge_claimed"] is False
    assert len(disk["steps"]) == len(B._STEP_SPECS)


def test_one_step_raises_others_still_run(tmp_path, monkeypatch):
    ran = []

    def _boom():
        raise RuntimeError("kaboom")

    for name, _slow, fnname in B._STEP_SPECS:
        if name == "analytics_verify":
            monkeypatch.setattr(B, fnname, _boom)
        else:
            monkeypatch.setattr(B, fnname,
                                (lambda n=name: (lambda: (ran.append(n) or {})))())

    rep = B.run_burst(rss_fn=lambda: 50.0, report_path=tmp_path / "r.json")

    # the raising step is isolated: recorded as error, all others ran + are ok
    by = {s["name"]: s["status"] for s in rep["steps"]}
    assert by["analytics_verify"].startswith("error")
    assert "kaboom" in by["analytics_verify"]
    for name, _slow, _fn in B._STEP_SPECS:
        if name != "analytics_verify":
            assert by[name] == "ok"
    assert len(ran) == len(B._STEP_SPECS) - 1  # every non-raising step still executed


def test_rss_guard_aborts_remaining(tmp_path, monkeypatch):
    _patch_all_ok(monkeypatch)
    # RSS reads over the cap on the first post-step check -> abort before the rest
    monkeypatch.setattr(B, "_rss_mb", lambda: 9999.0)
    rep = B.run_burst(rss_fn=lambda: 9999.0, rss_limit_mb=3072.0,
                      report_path=tmp_path / "r.json")

    assert "aborted_reason" in rep
    assert "exceeded" in rep["aborted_reason"]
    # only the first step ran; the guard skipped the remainder
    assert len(rep["steps"]) == 1


def test_skip_slow_marks_network_steps(tmp_path, monkeypatch):
    _patch_all_ok(monkeypatch)
    rep = B.run_burst(skip_slow=True, rss_fn=lambda: 100.0,
                      report_path=tmp_path / "r.json")
    by = {s["name"]: s["status"] for s in rep["steps"]}
    slow = {n for n, s, _ in B._STEP_SPECS if s}
    for name, status in by.items():
        if name in slow:
            assert status == "skipped_slow"
        else:
            assert status == "ok"


def test_steps_subset_filters(tmp_path, monkeypatch):
    _patch_all_ok(monkeypatch)
    rep = B.run_burst(steps=["freshness_sla"], rss_fn=lambda: 100.0,
                      report_path=tmp_path / "r.json")
    assert [s["name"] for s in rep["steps"]] == ["freshness_sla"]
