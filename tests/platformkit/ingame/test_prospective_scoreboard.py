"""Per-file test for scripts.platformkit.ingame.prospective_scoreboard.

Run: python -m pytest tests/platformkit/ingame/test_prospective_scoreboard.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.ingame import prospective_scoreboard as ps


def _tick(ts, model_p, market_p, summary):
    return {"ts": ts, "model_prob": model_p, "market_prob": market_p,
            "side": "home", "state_summary": summary}


def _write_game(dirpath, name, rows):
    dirpath.mkdir(parents=True, exist_ok=True)
    p = dirpath / ("%s.jsonl" % name)
    with p.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return p


def _basketball_game(gdir, name, ts_prefix, y, model_p, market_p):
    rows = [
        _tick(ts_prefix + "T01:00:00Z", model_p, market_p,
              "home_score=30.0 away_score=28.0 clock=600.0 period=2"),
        _tick(ts_prefix + "T02:00:00Z", model_p, market_p,
              "home_score=80.0 away_score=75.0 clock=200.0 period=4"),
        {"settled": True, "home_win": y, "ts": ts_prefix + "T03:00:00Z"},
    ]
    _write_game(gdir, name, rows)


def test_parse_state_summary_tolerant():
    s = ps.parse_state_summary("home_score=4.0 clock=432.0 period=1 half=bottom count=2-2")
    assert s["period"] == 1 and s["clock"] == 432.0
    assert "half" not in s and "count" not in s
    assert ps.parse_state_summary(None) == {}


def test_checkpoint_pairs_basketball_and_mlb():
    game = {"y": 1, "first_ts": "x", "ticks": [
        ("t1", {"period": 1, "clock": 100}, 0.6, 0.55),
        ("t2", {"period": 2, "clock": 500}, 0.65, 0.6),
        ("t3", {"period": 4, "clock": 200}, 0.9, 0.85),
    ]}
    pairs = ps.checkpoint_pairs(game, "nba")
    assert pairs["end_q1"] == (0.65, 0.6)       # first period>=2 tick
    assert pairs["q4_under5"] == (0.9, 0.85)    # period 4, clock<=300
    mlb = {"y": 0, "first_ts": "x", "ticks": [("t", {"inning": 7}, 0.4, 0.45)]}
    mp = ps.checkpoint_pairs(mlb, "mlb")
    assert mp["end_inn3"] == (0.4, 0.45) and mp["end_inn6"] == (0.4, 0.45)
    assert "end_inn8" not in mp                  # honest gap: never reached


def test_prereg_exclusion(tmp_path):
    gdir = tmp_path / "nba"
    _basketball_game(gdir, "old", "2026-07-10", 1, 0.7, 0.6)   # pre-prereg
    _basketball_game(gdir, "new", "2026-07-25", 1, 0.7, 0.6)   # forward
    doc = ps.run(tmp_path, preregistered_at="2026-07-19T04:30:00Z")
    assert doc["n_excluded_pre_prereg"] == 1
    assert doc["sports"]["nba"]["n_settled_games_graded"] == 1


def test_unsettled_game_never_graded(tmp_path):
    gdir = tmp_path / "wnba"
    _write_game(gdir, "nofinal", [
        _tick("2026-07-25T01:00:00Z", 0.6, 0.5,
              "home_score=10.0 away_score=8.0 clock=300.0 period=2")])
    doc = ps.run(tmp_path)
    assert doc["sports"]["wnba"]["n_settled_games_graded"] == 0


def test_pending_below_min_games_even_when_model_ahead(tmp_path):
    gdir = tmp_path / "nba"
    for i in range(5):  # model closer to outcome than market, but n << MIN_GAMES
        _basketball_game(gdir, "g%d" % i, "2026-07-2%d" % (i + 1), 1, 0.9, 0.6)
    doc = ps.run(tmp_path)
    cp = doc["sports"]["nba"]["checkpoints"]["end_q1"]
    assert cp["n"] == 5 and cp["verdict"] == "PENDING"
    assert cp["delta_brier_mean"] > 0  # point estimate ahead, verdict still PENDING


def test_beats_provisional_needs_ci_and_n(tmp_path):
    gdir = tmp_path / "nba"
    for i in range(35):  # n >= MIN_GAMES, model uniformly closer -> CI lo > 0
        _basketball_game(gdir, "g%02d" % i, "2026-08-%02d" % (i % 28 + 1), 1, 0.9, 0.6)
    doc = ps.run(tmp_path)
    cp = doc["sports"]["nba"]["checkpoints"]["end_q1"]
    assert cp["n"] == 35
    assert cp["verdict"] == "BEATS_MARKET_PROVISIONAL"
    assert cp["delta_95ci"][0] > 0


def test_behind_market(tmp_path):
    gdir = tmp_path / "nba"
    for i in range(35):  # market uniformly closer -> CI hi < 0
        _basketball_game(gdir, "g%02d" % i, "2026-08-%02d" % (i % 28 + 1), 1, 0.6, 0.9)
    doc = ps.run(tmp_path)
    assert doc["sports"]["nba"]["checkpoints"]["end_q1"]["verdict"] == "BEHIND_MARKET"


def test_artifacts_written_and_history_appends(tmp_path):
    gdir = tmp_path / "nba"
    _basketball_game(gdir, "g", "2026-07-25", 1, 0.7, 0.6)
    out = tmp_path / "score.json"
    doc = ps.run(tmp_path)
    ps.write_artifacts(doc, out)
    ps.write_artifacts(doc, out)
    saved = json.loads(out.read_text())
    assert saved["edge_claimed"] is False and saved["preregistered_at"]
    hist = (tmp_path / "score_history.jsonl").read_text().strip().splitlines()
    assert len(hist) == 2  # appended, not overwritten
    assert json.loads(hist[0])["sports"]["nba"]["end_q1"]["verdict"] == "PENDING"
