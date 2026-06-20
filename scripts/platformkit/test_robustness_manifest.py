"""Per-file test for scripts.platformkit.robustness_manifest (RB-E-2).

Proves the manifest enumerates every chaos surface + every supervised process, that
a FAILED chaos surface propagates to overall="failed", and that an untested surface
reads UNPROVEN (never proven-by-absence).
"""
from __future__ import annotations

from scripts.platformkit import robustness_manifest as rm


def test_build_manifest_enumerates_chaos_and_supervised():
    doc = rm.build_manifest()
    names = {s["name"] for s in doc["surfaces"]}
    # Chaos surfaces present.
    assert "feed_freshness" in names
    assert "composite_endpoint" in names
    assert "daemon_readiness" in names
    # Supervised procs enumerated (at least the autonomy monitor + paper loop).
    assert "m5_autonomy_monitor" in names
    assert "m1_paper" in names


def test_clean_run_is_proven():
    doc = rm.build_manifest()
    # With the real honest surfaces, nothing should be FAILED.
    assert doc["counts"].get(rm.FAILED, 0) == 0
    assert doc["overall"] in ("proven", "unproven")
    # No fabricated money VALUE ($ adjacent to a digit); the honest_note disclaimer
    # "No $ field" is allowed (it is the rail, not a money value).
    import re
    assert not re.search(r"\$\s*\d", str(doc))


def test_failed_chaos_surface_propagates_to_failed():
    bad = {
        "passed": False,
        "robustness_manifest": {
            "feed_freshness": "PROVEN",
            "composite_endpoint": "PROVEN",
            "daemon_readiness": "FAILED",  # the daemon surface failed
        },
    }
    doc = rm.build_manifest(chaos_report=bad)
    assert doc["overall"] == "failed"
    assert doc["counts"][rm.FAILED] >= 1
    # The heartbeat-bearing supervised procs inherit the FAILED daemon verdict.
    hb_rows = [s for s in doc["surfaces"]
               if s.get("kind") == "supervised_proc" and s.get("expects_heartbeat")]
    assert any(s["verdict"] == rm.FAILED for s in hb_rows)


def test_unknown_verdict_reads_unproven_not_green():
    weird = {"passed": True,
             "robustness_manifest": {"feed_freshness": "???"}}
    doc = rm.build_manifest(chaos_report=weird)
    feed = [s for s in doc["surfaces"] if s["name"] == "feed_freshness"][0]
    assert feed["verdict"] == rm.UNPROVEN  # never silently proven


def test_none_readiness_proc_is_enumerated_with_note():
    doc = rm.build_manifest()
    none_rows = [s for s in doc["surfaces"]
                 if s.get("kind") == "supervised_proc"
                 and s.get("expects_heartbeat") is False]
    # m1_producer / boards / ui are NONE/TCP-readiness -> enumerated, not dropped.
    assert none_rows
    for r in none_rows:
        assert "note" in r  # explicit exemption note, never a hidden gap


def test_overall_is_worst_of_verdicts():
    # Only PROVEN + one UNPROVEN -> overall unproven (not proven).
    rep = {"passed": True,
           "robustness_manifest": {"feed_freshness": "PROVEN",
                                   "composite_endpoint": "???"}}
    doc = rm.build_manifest(chaos_report=rep)
    assert doc["overall"] in ("unproven", "failed")


def test_honest_note_present_and_dollar_free():
    doc = rm.build_manifest()
    assert "UNPROVEN" in doc["honest_note"]
    assert "calibration not edge" in doc["honest_note"]
    assert "$ field" in doc["honest_note"]  # the phrase 'No $ field', not a value
