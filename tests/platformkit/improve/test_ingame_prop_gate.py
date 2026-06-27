"""tests.platformkit.improve.test_ingame_prop_gate -- in-game calib-gate contract.

Asserts the gate can ONLY ever HOLD or REMOVE proven-bad (REJECT) buckets:
  (a) default-allow: empty/missing meta, unknown bucket, non-dict row -> place.
  (b) non-REJECT verdicts (SHIP / HOLD / INSUFFICIENT_DATA) -> place.
  (c) REJECT bucket -> suppress; a different (unmeasured) bucket still places.
  (d) configurable suppress set is honoured.
  (e) gate_if_enabled: None unless CV_INGAME_CALIB_GATE truthy (default OFF == no-op).
  (f) make_gate binds the meta once and is row-callable.

Per-file test only. ASCII; stdlib deps. Builds meta dicts in-memory (no disk dependency).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[3]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from scripts.platformkit.improve import ingame_prop_gate as G


def _meta(*groups, suppress=None):
    m = {"groups": list(groups)}
    if suppress is not None:
        m["suppress_verdicts"] = suppress
    return m


def _row(sport="mlb", frac=0.2):
    return {"sport": sport, "frac_elapsed": frac}


def test_default_allow_when_no_meta():
    assert G.allow(_row(), meta={}) is True
    assert G.allow(_row(), meta=None, meta_path=Path("does_not_exist.json")) is True
    assert G.allow("not-a-dict", meta={"groups": []}) is True


def test_non_reject_verdicts_place():
    for v in ("SHIP", "HOLD", "INSUFFICIENT_DATA"):
        m = _meta({"sport": "mlb", "bucket": "early", "verdict": v})
        assert G.allow(_row(frac=0.2), meta=m) is True, v


def test_reject_bucket_is_suppressed():
    m = _meta({"sport": "mlb", "bucket": "early", "verdict": "REJECT"})
    assert G.allow(_row(frac=0.2), meta=m) is False          # early -> suppressed
    assert G.allow(_row(frac=0.5), meta=m) is True           # mid not measured -> place
    assert G.allow(_row(sport="soccer_intl", frac=0.2), meta=m) is True  # other sport -> place


def test_unknown_bucket_allows():
    m = _meta({"sport": "mlb", "bucket": "early", "verdict": "REJECT"})
    assert G.allow(_row(frac=2.0), meta=m) is True           # out of range -> default-allow


def test_configurable_suppress_set():
    m = _meta({"sport": "mlb", "bucket": "early", "verdict": "HOLD"},
              suppress=["HOLD", "REJECT"])
    assert G.allow(_row(frac=0.2), meta=m) is False          # HOLD now suppressed


def test_gate_if_enabled_flag(monkeypatch, tmp_path):
    monkeypatch.delenv("CV_INGAME_CALIB_GATE", raising=False)
    assert G.gate_if_enabled() is None                       # default OFF -> no-op
    monkeypatch.setenv("CV_INGAME_CALIB_GATE", "1")
    g = G.gate_if_enabled(meta_path=tmp_path / "none.json")  # missing meta -> default-allow gate
    assert callable(g)
    assert g(_row()) is True


def test_make_gate_is_row_callable(tmp_path):
    # point at a missing meta so the bound gate is deterministic (default-allow), not
    # whatever the live on-disk meta currently says.
    g = G.make_gate(tmp_path / "none.json")
    assert callable(g)
    assert g(_row()) is True
    # with a constructed REJECT meta the gate suppresses the matching bucket:
    bound = lambda row: G.allow(row, meta=_meta(
        {"sport": "mlb", "bucket": "early", "verdict": "REJECT"}))
    assert bound(_row(frac=0.2)) is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
