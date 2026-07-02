"""Per-file tests for ingame_outcome_verdict (offline; synthetic grade files)."""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_outcome_verdict as ov


def _write_game(dirp, gid, outcome, model_p, market_p, n=60, inning=7):
    """Write a grade file: n ticks in one inning, constant model/market prob."""
    d = dirp / "mlb"
    d.mkdir(parents=True, exist_ok=True)
    fp = d / ("%s.jsonl" % gid)
    with fp.open("w", encoding="utf-8") as fh:
        for i in range(n):
            fh.write(json.dumps({
                "sport": "mlb", "game_id": gid, "ts": "2026-06-30T20:%02d:00Z" % (i % 60),
                "model_prob": model_p, "market_prob": market_p,
                "state_summary": "home_score=3 away_score=1 inning=%d half=bottom" % inning,
                "side": "home",
            }) + "\n")
    return fp


def test_model_better_than_venue(tmp_path):
    # 10 games, home won (y=1); model=0.8 (Brier .04), market=0.55 (Brier .2025).
    grade = tmp_path / "grade"
    outc = {}
    for i in range(10):
        gid = "G%d" % i
        _write_game(grade, gid, 1, 0.8, 0.55, n=60, inning=7)
        outc[gid] = 1
    doc = ov.build_verdict(sport="mlb", grade_dir=grade,
                           outcome_fn=lambda g: outc.get(g))
    v = doc["segments"]["I7"]
    assert v["verdict"] == "BETTER_THAN_VENUE", v
    assert v["brier_model"] < v["brier_market"]
    assert v["delta_ci95"][1] < 0  # CI upper below 0
    assert "I7" in doc["better_segments"]
    assert doc["edge_claimed"] is False


def test_model_worse_than_venue(tmp_path):
    grade = tmp_path / "grade"
    outc = {}
    for i in range(10):
        gid = "W%d" % i
        _write_game(grade, gid, 1, 0.55, 0.8, n=60, inning=8)  # model worse
        outc[gid] = 1
    doc = ov.build_verdict(sport="mlb", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
    v = doc["segments"]["I8"]
    assert v["verdict"] == "WORSE_THAN_VENUE", v
    assert "I8" in doc["worse_segments"]


def test_insufficient_below_min_games(tmp_path):
    grade = tmp_path / "grade"
    outc = {}
    for i in range(3):  # below MIN_GAMES_PER_SEG
        gid = "S%d" % i
        _write_game(grade, gid, 1, 0.8, 0.55, n=60, inning=6)
        outc[gid] = 1
    doc = ov.build_verdict(sport="mlb", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
    assert doc["segments"]["I6"]["verdict"] == "INSUFFICIENT_DATA"


def test_unlabeled_games_skipped(tmp_path):
    grade = tmp_path / "grade"
    for i in range(10):
        _write_game(grade, "U%d" % i, 1, 0.8, 0.55, n=60, inning=5)
    # outcome_fn returns None for everything -> nothing labeled -> all INSUFFICIENT
    doc = ov.build_verdict(sport="mlb", grade_dir=grade, outcome_fn=lambda g: None)
    assert doc["n_labeled"] == 0
    assert doc["segments"]["I5"]["verdict"] == "INSUFFICIENT_DATA"


def test_write_and_render(tmp_path):
    grade = tmp_path / "grade"
    outc = {}
    for i in range(9):
        gid = "R%d" % i
        _write_game(grade, gid, 1, 0.8, 0.55, n=60, inning=7)
        outc[gid] = 1
    doc = ov.build_verdict(sport="mlb", grade_dir=grade, outcome_fn=lambda g: outc.get(g))
    out = tmp_path / "verdict.json"
    ov.write_doc(doc, out)
    assert out.exists()
    reloaded = json.loads(out.read_text())
    assert reloaded["component"] == ov.COMPONENT
    txt = ov.render(doc)
    assert "OUTCOME-GATED" in txt and "$ edge" in txt
