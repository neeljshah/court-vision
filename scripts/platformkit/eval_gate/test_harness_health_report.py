"""Per-file test for the harness_health artifact composer.

Plants two inputs in a tmp root, leaves the other three absent, and checks that
present sections read ok, absent sections read no_data (never an exception),
as_of is the MAX of the planted artifacts' own timestamps (never the wall clock),
and the written JSON round-trips.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.eval_gate import harness_health_report as H

OLD = "2026-08-01T00:00:00+00:00"
NEW = "2026-09-01T23:25:28.871310+00:00"


def _plant(root: Path) -> None:
    """Two present inputs (fwer ledger, gate manifest); golden / null_ship / retro absent."""
    fwer = root / H.FWER_REL
    fwer.parent.mkdir(parents=True, exist_ok=True)
    fwer.write_text(
        json.dumps({"at": OLD, "k_cumulative": 4, "predictor": "a", "sport": "mlb"}) + "\n"
        + json.dumps({"at": NEW, "k_cumulative": 9, "predictor": "b", "sport": "mlb"}) + "\n",
        encoding="ascii")
    manifest = root / H.MANIFEST_REL
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({
        "as_of": OLD,
        "rows": [{"name": "x", "status": "OK"}, {"name": "y", "status": "OK"},
                 {"name": "z", "status": "UNREADABLE"}],
    }), encoding="ascii")


def test_sections_present_and_absent(tmp_path):
    _plant(tmp_path)
    out = tmp_path / "artifact.json"
    payload = H.build(out_path=str(out), root=tmp_path)

    assert payload["fwer_ledger"]["status"] == "ok"
    assert payload["fwer_ledger"]["rows"] == 2
    assert payload["fwer_ledger"]["k_cumulative_max"] == 9
    assert payload["fwer_ledger"]["last_at"] == NEW
    assert payload["gate_manifest"]["status"] == "ok"
    assert payload["gate_manifest"]["rows_ok"] == 2
    assert payload["gate_manifest"]["rows_unreadable"] == 1

    for absent, rel in (("golden", H.GOLDEN_REL), ("null_ship", H.NULL_SHIP_REL),
                        ("retro_correction", H.RETRO_REL)):
        assert payload[absent]["status"] == "no_data", absent
        assert payload[absent]["path"] == rel

    # every section reports the path it tried, present or not
    assert payload["source_artifact"] == [H.GOLDEN_REL, H.NULL_SHIP_REL, H.RETRO_REL,
                                          H.FWER_REL, H.MANIFEST_REL]
    # handler-facing aliases exist even when their section is absent
    assert payload["retro_correction_survivors"] is None
    assert payload["multiplicity_ledger_K"] == 9


def test_as_of_is_max_planted_stamp_not_wall_clock(tmp_path):
    _plant(tmp_path)
    payload = H.build(out_path=str(tmp_path / "a.json"), root=tmp_path)
    assert payload["as_of"] == NEW           # max of the planted stamps
    assert payload["as_of_source"] == "fwer_ledger"
    assert payload["as_of"] != payload["generated_at"]
    assert payload["generated_at"] > NEW     # the wall clock is recorded separately


def test_written_json_round_trips(tmp_path):
    _plant(tmp_path)
    out = tmp_path / "artifact.json"
    payload = H.build(out_path=str(out), root=tmp_path)
    assert json.loads(out.read_text(encoding="ascii")) == payload


def test_unreadable_inputs_never_raise(tmp_path):
    (tmp_path / H.MANIFEST_REL).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / H.MANIFEST_REL).write_text("{not json", encoding="ascii")
    (tmp_path / H.FWER_REL).write_text("{not json\n", encoding="ascii")
    payload = H.build(out_path=str(tmp_path / "a.json"), root=tmp_path)
    assert payload["gate_manifest"]["status"] == "no_data"
    assert payload["fwer_ledger"]["rows"] == 0
    assert payload["fwer_ledger"]["k_cumulative_max"] is None


if __name__ == "__main__":
    raise SystemExit("run with: python -m pytest scripts/platformkit/eval_gate/"
                     "test_harness_health_report.py -q")
