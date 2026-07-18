"""winprob_dispatch's state-bucket caveat seam (calibration_grid.caveats). The
subprocess is monkeypatched to a canned predict_matchup JSON -- this only
proves the ADDITIVE seam (state_bucket/bucket_calibration), never a real
predict_matchup or a real reliability map.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/answers/test_winprob_dispatch_caveats.py -q
"""
from __future__ import annotations

import json
import subprocess

import pytest

from scripts.platformkit.answers import winprob_dispatch as D
from scripts.platformkit.calibration_grid import caveats as CV


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


_FIXED = {
    "sport": "nba", "home": "BOS", "away": "LAL", "edge_claimed": False,
    "framing": "In-game conditional Brier, calibration only.",
    "ingame": {"p_home_win": 0.62, "proj_total": 210.0},
}


@pytest.fixture(autouse=True)
def _canned_subprocess(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(0, json.dumps(_FIXED), ""))


def test_ingame_state_attaches_state_bucket_and_calibration(monkeypatch):
    CV.load_reliability_map.cache_clear()
    r = D.dispatch("nba", "BOS", "LAL",
                   ingame_state={"elapsed": 20.0, "home_score": 60, "away_score": 55})
    assert r["status"] == "ok"
    assert r["state_bucket"] == "lead_+05_10|rem_24_36|reg"
    assert "bucket_calibration" in r
    assert r["bucket_calibration"]["state_bucket"] == r["state_bucket"]
    assert "can_price" in r["bucket_calibration"]


def test_no_ingame_state_never_adds_bucket_keys():
    r = D.dispatch("nba", "BOS", "LAL")
    assert "state_bucket" not in r
    assert "bucket_calibration" not in r


def test_caveat_lookup_failure_never_breaks_envelope(monkeypatch):
    def _raise(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(CV, "caveat_for", _raise)
    r = D.dispatch("nba", "BOS", "LAL",
                   ingame_state={"elapsed": 20.0, "home_score": 60, "away_score": 55})
    assert r["status"] == "ok"  # envelope status is untouched by a caveat failure
    assert r["state_bucket"] is None
    assert r["bucket_calibration"] == {"can_price": False, "reason": "caveat lookup failed"}


def test_mapped_state_returns_can_price_true(tmp_path, monkeypatch):
    key = "lead_+05_10|rem_24_36|reg"
    doc = {"sport": "nba", "buckets": {key: {
        "can_price": True, "reason": "ok", "n_games": 40,
        "model_brier": 0.18, "market_brier": 0.19}}}
    p = tmp_path / "nba_reliability_map.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setitem(CV._MAP_PATHS, "nba", p)
    CV.load_reliability_map.cache_clear()
    r = D.dispatch("nba", "BOS", "LAL",
                   ingame_state={"elapsed": 20.0, "home_score": 60, "away_score": 55})
    assert r["bucket_calibration"]["can_price"] is True
    assert r["bucket_calibration"]["n_games"] == 40
    CV.load_reliability_map.cache_clear()
