"""Per-file tests for ingame_tail_scan (synthetic corpus; planted venue miscalibration).

cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_tail_scan.py -q
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from scripts.platformkit.ingame import ingame_tail_scan as ts


def _write_game(dirp: Path, stem: str, ticks) -> None:
    with open(dirp / ("%s.jsonl" % stem), "w", encoding="utf-8") as fh:
        for mkt, mdl in ticks:
            fh.write(json.dumps({"sport": "mlb", "game_id": stem, "ts": "2026-01-01T00:00:00Z",
                                 "market_prob": mkt, "model_prob": mdl, "side": "home"}) + "\n")


def _plant(tmp_path: Path, n_games: int, mkt: float, mdl: float, win_rate: float,
           seed: int = 7):
    """Build n_games one-band games; outcomes drawn at win_rate; returns (dir, lookup)."""
    d = tmp_path / "grade" / "mlb"
    d.mkdir(parents=True)
    rng = random.Random(seed)
    outcomes = {}
    for i in range(n_games):
        stem = "G%03d" % i
        _write_game(d, stem, [(mkt, mdl)] * 10)
        outcomes[stem] = 1 if rng.random() < win_rate else 0
    return tmp_path / "grade", outcomes.get


def test_band_label_edges():
    assert ts._band_label(0.05) == "[0.00,0.10)"
    assert ts._band_label(0.10) == "[0.10,0.20)"
    assert ts._band_label(0.95) == "[0.90,1.00]"
    assert ts._band_label(1.0) == "[0.90,1.00]"


def test_insufficient_below_min_games(tmp_path):
    gd, lookup = _plant(tmp_path, n_games=ts.MIN_GAMES_BAND - 1, mkt=0.05, mdl=0.15,
                        win_rate=0.5)
    res = ts.scan(grade_dir=gd, outcome_lookup=lookup, iters=50)
    band = res["bands"]["[0.00,0.10)"]
    assert band["venue_verdict"] == "INSUFFICIENT_DATA"
    assert band["model_verdict"] == "INSUFFICIENT_DATA"
    assert res["edge_claimed"] is False


def test_planted_tail_underpricing_recovered(tmp_path):
    # venue says 5%, true rate ~30%, model says 30% -> VENUE_UNDERPRICES + MODEL_BETTER
    gd, lookup = _plant(tmp_path, n_games=60, mkt=0.05, mdl=0.30, win_rate=0.30)
    res = ts.scan(grade_dir=gd, outcome_lookup=lookup, iters=400)
    band = res["bands"]["[0.00,0.10)"]
    assert band["venue_verdict"] == "VENUE_UNDERPRICES"
    assert band["model_verdict"] == "MODEL_BETTER"
    pooled = res["pooled"]["TAILS"]
    assert pooled["venue_verdict"] == "VENUE_UNDERPRICES"


def test_calibrated_venue_reads_calibrated(tmp_path):
    # venue price == true rate == model -> CALIBRATED + MATCH (within noise)
    gd, lookup = _plant(tmp_path, n_games=80, mkt=0.50, mdl=0.50, win_rate=0.50, seed=11)
    res = ts.scan(grade_dir=gd, outcome_lookup=lookup, iters=400)
    band = res["bands"]["[0.50,0.65)"]
    assert band["venue_verdict"] == "CALIBRATED"
    assert band["model_verdict"] == "MATCH"


def test_unresolved_games_skipped(tmp_path):
    gd, _ = _plant(tmp_path, n_games=5, mkt=0.5, mdl=0.5, win_rate=0.5)
    res = ts.scan(grade_dir=gd, outcome_lookup=lambda stem: None, iters=50)
    assert res["n_games_resolved"] == 0
    assert res["n_games_unresolved"] == 5
    assert res["bands"] == {}


def test_away_side_flipped(tmp_path):
    d = tmp_path / "grade" / "mlb"
    d.mkdir(parents=True)
    with open(d / "A1.jsonl", "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"market_prob": 0.85, "model_prob": 0.85, "side": "away"}) + "\n")
    res = ts.scan(grade_dir=tmp_path / "grade", outcome_lookup=lambda s: 1, iters=50)
    assert "[0.10,0.20)" in res["bands"]  # 1-0.85 flipped to home space


def test_artifact_written(tmp_path):
    gd, lookup = _plant(tmp_path, n_games=10, mkt=0.5, mdl=0.5, win_rate=0.5)
    res = ts.scan(grade_dir=gd, outcome_lookup=lookup, iters=50)
    out = ts.write_artifact(res, out_path=tmp_path / "art.json")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["component"] == "m_ingame_tail_scan"
    assert loaded["edge_claimed"] is False
