"""Per-file test for the in-game CLV verdict daemon.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        scripts/platformkit/ingame/test_ingame_clv_verdict_daemon.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import ingame_clv_verdict_daemon as D


def _fake_grade(sport):
    return {"sport": sport, "verdict": "MATCH", "msg": "ok", "mean_clv": 0.04,
            "n_markets": 70}


def test_collect_assembles_doc_and_no_dollar():
    doc = D.collect(("mlb", "soccer_intl"), grade_fn=_fake_grade)
    assert {r["sport"] for r in doc["sports"]} == {"mlb", "soccer_intl"}
    assert doc["sports"][0]["verdict"] == "MATCH"
    assert "updated_at" in doc
    assert doc["edge_claimed"] is False     # cv_honesty F-check-2 contract
    blob = json.dumps(doc).lower()
    # no profit/ROI claim (the honest note legitimately says "not a $ edge", so $ is allowed)
    for banned in ("roi", "pnl", "profit", "p_l", "stake"):
        assert banned not in blob
    assert "not a $ edge" in blob          # the honest disclaimer is present


def test_collect_isolates_failing_sport():
    def _boom(sport):
        if sport == "soccer_intl":
            raise RuntimeError("no series")
        return _fake_grade(sport)

    doc = D.collect(("mlb", "soccer_intl"), grade_fn=_boom)
    verds = {r["sport"]: r["verdict"] for r in doc["sports"]}
    assert verds["mlb"] == "MATCH"
    assert verds["soccer_intl"] == "ERROR"      # isolated, did not kill the sweep


def test_write_verdict_atomic(tmp_path):
    p = tmp_path / "ops" / "ingame_clv_verdict.json"
    D.write_verdict({"updated_at": "x", "sports": []}, path=p)
    assert p.exists()
    assert json.loads(p.read_text(encoding="ascii"))["updated_at"] == "x"


def test_run_max_ticks_and_survives_raise(tmp_path):
    calls = {"n": 0}

    def _raise(sport):
        calls["n"] += 1
        raise ValueError("grade failed")

    ticks = D.run(grade_fn=_raise, sleep=lambda s: None, max_ticks=3,
                  verdict_path=tmp_path / "v.json")
    assert ticks == 3                            # survived 3 raising sweeps


def test_run_should_stop_breaks_first(tmp_path):
    ran = {"n": 0}

    def _g(sport):
        ran["n"] += 1
        return _fake_grade(sport)

    ticks = D.run(grade_fn=_g, sleep=lambda s: None, should_stop=lambda: True,
                  verdict_path=tmp_path / "v.json")
    assert ticks == 0 and ran["n"] == 0
