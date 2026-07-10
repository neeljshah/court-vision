"""Per-file tests for frontier_probe_job (M11): registry parse, delta
detection, politeness cap, blocked-source honesty, cadence guard."""
from __future__ import annotations

import json
import time

from scripts.platformkit.data_frontier import frontier_probe_job as J


class _Resp:
    def __init__(self, status_code=200, text="", payload=None):
        self.status_code, self.text = status_code, text
        self._payload = payload

    def json(self):
        return self._payload


def _entry(name, **kw):
    e = {"name": name, "sport": "mlb", "expect": "csv_leaderboard",
         "url": "https://example.test/" + name, "params": {}}
    e.update(kw)
    return e


# 1. registry parse ------------------------------------------------------------
def test_registry_parses_and_is_well_formed():
    names = [e["name"] for e in J.REGISTRY]
    assert len(names) == len(set(names)), "duplicate source names"
    for e in J.REGISTRY:
        assert e["name"] and e["sport"] and e["url"].startswith("http")
        assert e.get("robots_disallowed") or e["expect"] in J._CHECKS
    assert any(e.get("robots_disallowed") for e in J.REGISTRY)  # honesty entry present


# 2. delta detection -----------------------------------------------------------
def test_delta_status_flip_and_new_fields_and_baseline():
    by_name = {"a": _entry("a"), "b": _entry("b"), "c": _entry("c")}
    prev = {"a": {"status": "SCHEMA_ONLY_VALUES_NULL", "fields": ["x"]},
            "b": {"status": "KEYLESS_CONFIRMED", "fields": ["x", "y"]}}
    cur = {"a": {"status": "KEYLESS_CONFIRMED", "fields": ["x"], "evidence": "populated"},
           "b": {"status": "KEYLESS_CONFIRMED", "fields": ["x", "y", "z"], "evidence": "grew"},
           "c": {"status": "KEYLESS_CONFIRMED", "fields": ["q"], "evidence": "first sight"}}
    rows = J.diff_deltas(prev, cur, by_name)
    changes = {(r["source"], r["change"]) for r in rows}
    assert ("a", "STATUS_FLIP") in changes
    assert ("b", "NEW_FIELDS") in changes
    assert not any(r["source"] == "c" for r in rows), "baseline must not file a delta"
    nf = next(r for r in rows if r["change"] == "NEW_FIELDS")
    assert nf["new_fields"] == ["z"] and nf["kind"] == "ACQUISITION_DELTA"


def test_no_delta_when_nothing_changed():
    by_name = {"a": _entry("a")}
    snap = {"a": {"status": "KEYLESS_CONFIRMED", "fields": ["x"], "evidence": "same"}}
    assert J.diff_deltas(snap, snap, by_name) == []


# 3. politeness cap ------------------------------------------------------------
def test_politeness_min_interval_between_probes(tmp_path):
    stamps = []

    def fetcher(url, **kw):
        stamps.append(time.monotonic())
        return _Resp(200, "a,b,c\n1,2,3\n")

    reg = [_entry("s1"), _entry("s2"), _entry("s3")]
    out = J.run_probe_cycle(registry=reg, fetcher=fetcher, min_interval_s=0.05,
                            status_path=tmp_path / "st.json",
                            deltas_path=tmp_path / "d.jsonl", force=True)
    assert out["probed"] == 3 and len(stamps) == 3
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert all(g >= 0.045 for g in gaps), "probes closer than the politeness cap: %s" % gaps


# 4. blocked-source honesty ----------------------------------------------------
def test_blocked_and_robots_sources_recorded_never_evaded(tmp_path):
    calls = []

    def fetcher(url, **kw):
        calls.append(url)
        return _Resp(403)

    reg = [_entry("blocked_one"),
           _entry("robots_one", robots_disallowed=True, expect="never_fetched")]
    out = J.run_probe_cycle(registry=reg, fetcher=fetcher, min_interval_s=0.0,
                            status_path=tmp_path / "st.json",
                            deltas_path=tmp_path / "d.jsonl", force=True)
    assert out["statuses"]["blocked_one"] == "BLOCKED_HTTP_403"
    assert out["statuses"]["robots_one"] == "ROBOTS_DISALLOWED_SKIPPED"
    assert all("robots_one" not in u for u in calls), "robots-disallowed source was fetched"
    assert out["deltas_filed"] == 0 and not (tmp_path / "d.jsonl").exists()
    saved = json.loads((tmp_path / "st.json").read_text())
    assert saved["sources"]["blocked_one"]["status"] == "BLOCKED_HTTP_403"


# 5. cadence guard -------------------------------------------------------------
def test_cadence_guard_skips_within_20h(tmp_path):
    st = tmp_path / "st.json"
    calls = []

    def fetcher(url, **kw):
        calls.append(url)
        return _Resp(200, "a,b,c\n1,2,3\n")

    reg = [_entry("s1")]
    first = J.run_probe_cycle(registry=reg, fetcher=fetcher, min_interval_s=0.0,
                              status_path=st, deltas_path=tmp_path / "d.jsonl")
    assert first["status"] == "ran" and len(calls) == 1
    second = J.run_probe_cycle(registry=reg, fetcher=fetcher, min_interval_s=0.0,
                               status_path=st, deltas_path=tmp_path / "d.jsonl")
    assert second["status"] == "skipped_cadence" and len(calls) == 1
    third = J.run_probe_cycle(registry=reg, fetcher=fetcher, min_interval_s=0.0,
                              status_path=st, deltas_path=tmp_path / "d.jsonl", force=True)
    assert third["status"] == "ran" and len(calls) == 2
