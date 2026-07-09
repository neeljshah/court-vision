"""Per-file test for heartbeat_coverage. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_heartbeat_coverage.py -q
"""
from __future__ import annotations

import os
from pathlib import Path

from supervisor.manifest import HEARTBEAT, HTTP, ProcSpec, ReadinessSpec

from scripts.platformkit.ops_sentinel import heartbeat_coverage as hc


def _spec(name: str, hb_path: str, fresh: float) -> ProcSpec:
    return ProcSpec(name=name, kind="py", module="x",
                    readiness=ReadinessSpec(kind=HEARTBEAT,
                                            heartbeat_path=hb_path,
                                            fresh_sec=fresh))


def test_fresh_stale_missing_and_na(tmp_path):
    fresh_hb = tmp_path / "fresh.txt"
    fresh_hb.write_text("beat")
    stale_hb = tmp_path / "stale.txt"
    stale_hb.write_text("beat")
    now = os.stat(stale_hb).st_mtime + 1000.0
    os.utime(fresh_hb, (now - 10.0, now - 10.0))

    specs = [
        _spec("m_fresh", str(fresh_hb), 600.0),
        _spec("m_stale", str(stale_hb), 600.0),          # age 1000 > 600
        _spec("m_missing", str(tmp_path / "absent.txt"), 600.0),
        ProcSpec(name="m_http", kind="py", module="x",
                 readiness=ReadinessSpec(kind=HTTP, http_path="/health")),
        ProcSpec(name="m_none", kind="py", module="x"),  # readiness NONE
    ]
    rows = hc.check_all(now=now, specs_fn=lambda: specs)
    by = {r["name"]: r for r in rows}
    assert by["m_fresh"]["status"] == "GREEN"
    assert by["m_stale"]["status"] == "RED" and by["m_stale"]["reason"] == "stale"
    assert by["m_missing"]["status"] == "RED" and by["m_missing"]["reason"] == "missing"
    assert by["m_http"]["status"] == "NA"
    assert by["m_none"]["status"] == "NA"


def test_broken_specs_fn_is_red_not_crash():
    def boom():
        raise RuntimeError("no supervisor")
    rows = hc.check_all(now=1.0, specs_fn=boom)
    assert len(rows) == 1 and rows[0]["status"] == "RED"


def test_tick_writes_status_doc(tmp_path):
    import json
    sp = tmp_path / "status.json"
    hb = tmp_path / "hb.txt"
    hb.write_text("beat")
    now = os.stat(hb).st_mtime + 1.0
    hc.tick(now=now, specs_fn=lambda: [_spec("m1", str(hb), 600.0)],
            status_path=sp)
    doc = json.loads(sp.read_text())
    assert doc["overall"] == "GREEN" and doc["rows"][0]["name"] == "m1"


def test_real_spec_list_loads_and_every_spec_gets_a_row():
    from supervisor.stack_specs import base_specs
    rows = hc.check_all(now=1e12, specs_fn=base_specs)  # read-only
    assert len(rows) == len(base_specs())
    # heartbeat-readiness specs never read NA; non-heartbeat never read GREEN/RED
    for spec, row in zip(base_specs(), rows):
        if spec.readiness.kind == HEARTBEAT:
            assert row["status"] in ("GREEN", "RED")
        else:
            assert row["status"] == "NA"
