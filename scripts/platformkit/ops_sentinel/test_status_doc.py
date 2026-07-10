"""Per-file test for status_doc. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_status_doc.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ops_sentinel import status_doc as sd


def test_write_doc_rolls_up_overall_from_worst_row(tmp_path):
    p = tmp_path / "status.json"
    ok = sd.write_doc(p, "guard_integrity",
                       [{"status": sd.GREEN}, {"status": sd.YELLOW}, {"status": sd.RED}],
                       now=100.0, honest_note="n/a")
    assert ok is True
    doc = sd.load_json(p)
    assert doc["overall"] == sd.RED
    assert doc["n_red"] == 1 and doc["n_yellow"] == 1 and doc["n_rows"] == 3
    assert doc["component"] == "guard_integrity"


def test_write_doc_never_raises_on_bad_row_shape(tmp_path):
    """Failure mode: a sentinel that hands write_doc a malformed row (missing
    'status', or an un-serialisable object) must degrade to a failed write --
    NOT crash the caller's tick and NOT leave a half-written status file
    downstream dashboards would choke parsing."""
    p = tmp_path / "status.json"
    ok = sd.write_doc(p, "disk_space", [{"status": object()}], now=1.0)
    assert ok is False
    assert not p.exists()
    assert not p.with_suffix(p.suffix + ".tmp").exists()


def test_load_json_missing_or_corrupt_returns_empty_dict(tmp_path):
    absent = tmp_path / "absent.json"
    assert sd.load_json(absent) == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="ascii")
    assert sd.load_json(bad) == {}
