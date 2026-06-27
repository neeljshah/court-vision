"""Per-file tests for calibration_gate (stake only replicated-SHIP families).

  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/bestbets/test_calibration_gate.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.bestbets import calibration_gate as G


def _meta(tmp_path, groups):
    p = tmp_path / "prop_history_meta.json"
    p.write_text(json.dumps({"groups": groups}), encoding="utf-8")
    return p


def test_proven_families_only_ship_replicated(tmp_path):
    p = _meta(tmp_path, [
        {"sport": "mlb", "stat": "hits", "replicated_verdict": "SHIP_REPLICATED"},
        {"sport": "mlb", "stat": "strikeouts", "replicated_verdict": "SHIP_REPLICATED"},
        {"sport": "mlb", "stat": "rbi", "replicated_verdict": "REJECT"},        # excluded
        {"sport": "mlb", "stat": "all", "replicated_verdict": "SHIP_REPLICATED"},  # pooled -> excluded
        {"sport": "nba", "stat": "all", "replicated_verdict": "HOLD"},           # excluded
        {"sport": "soccer", "stat": "totalshots", "replicated_verdict": "INSUFFICIENT_DATA"},
    ])
    fam = G.proven_families(meta_path=p)
    assert fam["mlb"] == {"Hits", "Pitcher Strikeouts"}
    assert "nba" not in fam and "soccer" not in fam


def test_is_calibration_proven_enforced_when_meta_present(tmp_path):
    p = _meta(tmp_path, [
        {"sport": "mlb", "stat": "hits", "replicated_verdict": "SHIP_REPLICATED"},
    ])
    assert G.is_calibration_proven("mlb", "Hits", meta_path=p) is True
    assert G.is_calibration_proven("mlb", "RBIs", meta_path=p) is False   # not replicated
    assert G.is_calibration_proven("soccer_intl", "Goals", meta_path=p) is False  # sport unproven


def test_no_substring_false_match(tmp_path):
    # 'runs' replicated must NOT allow 'Home Runs' (explicit map, not substring).
    p = _meta(tmp_path, [
        {"sport": "mlb", "stat": "runs", "replicated_verdict": "SHIP_REPLICATED"},
    ])
    assert G.is_calibration_proven("mlb", "Runs", meta_path=p) is True
    assert G.is_calibration_proven("mlb", "Home Runs", meta_path=p) is False


def test_fails_open_when_meta_unreadable(tmp_path):
    missing = tmp_path / "nope.json"
    assert G.proven_families(meta_path=missing) is None
    # fail-open: a transient meta miss must not zero the slate
    assert G.is_calibration_proven("mlb", "Hits", meta_path=missing) is True
