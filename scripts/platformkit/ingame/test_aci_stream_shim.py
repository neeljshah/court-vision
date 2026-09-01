"""Focused tests for the persisted paper-only ACI stream seam."""
from __future__ import annotations

import json

from scripts.platformkit.ingame import aci_stream_shim as shim


def _rows(n: int):
    ticks = [{"ts": "2026-01-01T00:%02d:00Z" % i, "segment": "all",
              "base_lo": 0.2, "base_hi": 0.8} for i in range(n)]
    return ticks + [{"ts": "2026-01-02T00:00:00Z", "settled": True, "home_win": 1}]


def test_settled_stream_waits_then_moves_down_after_coverage_errors(tmp_path):
    grade = tmp_path / "grade" / "nba"
    grade.mkdir(parents=True)
    (grade / "g1.jsonl").write_text("\n".join(json.dumps(row) for row in _rows(51)), encoding="utf-8")
    result = shim.update_stream("nba", grade_dir=tmp_path / "grade", state_dir=tmp_path / "state")
    assert result["n_graded"] == 51
    assert result["n_updated"] == 51
    assert result["alpha_t"] < 0.10
    repeat = shim.update_stream("nba", grade_dir=tmp_path / "grade", state_dir=tmp_path / "state")
    assert repeat["n_updated"] == 0
    assert repeat["alpha_t"] == result["alpha_t"]


def test_serving_applies_persisted_alpha_to_existing_static_band(tmp_path):
    state = tmp_path / "state" / "nba_all.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"alpha_t": 0.05, "n_graded": 51, "seen": []}), encoding="ascii")
    out = shim.apply_to_document({"static_interval": {"lo": 0.4, "hi": 0.6}}, "nba",
                                 state_dir=tmp_path / "state")
    assert out["static_interval"]["hi"] - out["static_interval"]["lo"] > 0.2
