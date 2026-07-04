"""Per-file test for settle_stamp (W3): stamp once, idempotent, and the aggregate
OUTCOME arm can then READ the label.

Checks:
  (1) stamp_final writes a home_win label exactly once; a 2nd call is a no-op ('already').
  (2) a non-final / unreadable / tie event is SKIPPED (no fabricated label).
  (3) after stamping, inplay_aggregate_grade._settled_outcome reads the label back, so the
      OUTCOME arm has its held-out binary outcome (was INSUFFICIENT_DATA forever without it).
  (4) home_win derived from a FINAL ESPN event dict matches the final scores.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.ingame import settle_stamp as ss
from scripts.platformkit.ingame import inplay_aggregate_grade as agg
from scripts.platformkit.ingame import live_grade as lg


def _seed_capture(grade_dir: Path, sport: str, game_id: str) -> Path:
    """Write a couple of paired capture rows (model_prob + market_prob) like the daytrader."""
    p = lg._grade_path(sport, game_id, grade_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"sport": sport, "game_id": game_id, "ts": "2026-06-19T18:00:00Z",
         "market_prob": 0.55, "model_prob": 0.60, "side": "home", "state_summary": "live"},
        {"sport": sport, "game_id": game_id, "ts": "2026-06-19T18:05:00Z",
         "market_prob": 0.58, "model_prob": 0.63, "side": "home", "state_summary": "live"},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_stamp_once_then_idempotent(tmp_path):
    p = _seed_capture(tmp_path, "nba", "G1")
    r1 = ss.stamp_final("nba", "G1", home_win=1, grade_dir=tmp_path)
    assert r1["status"] == "stamped" and r1["home_win"] == 1.0
    assert "$" not in json.dumps(r1) and r1["edge_claimed"] is False
    # second call is a no-op
    r2 = ss.stamp_final("nba", "G1", home_win=1, grade_dir=tmp_path)
    assert r2["status"] == "already"
    # exactly ONE settle row exists
    n_settle = sum(1 for line in p.read_text(encoding="utf-8").splitlines()
                   if line.strip() and json.loads(line).get("settled") is True)
    assert n_settle == 1


def test_non_final_event_skipped(tmp_path):
    _seed_capture(tmp_path, "nba", "G2")
    in_progress = {"competitions": [{"status": {"type": {"state": "in",
                   "name": "STATUS_IN_PROGRESS", "completed": False}},
                   "competitors": [
                       {"homeAway": "home", "score": "70"},
                       {"homeAway": "away", "score": "65"}]}]}
    r = ss.stamp_final("nba", "G2", ev=in_progress, grade_dir=tmp_path)
    assert r["status"] == "skipped" and r["home_win"] is None


def test_tie_event_skipped(tmp_path):
    _seed_capture(tmp_path, "soccer", "G3")
    final_tie = {"competitions": [{"status": {"type": {"name": "STATUS_FULL_TIME",
                 "completed": True}}, "competitors": [
                     {"homeAway": "home", "score": "1"},
                     {"homeAway": "away", "score": "1"}]}]}
    r = ss.stamp_final("soccer", "G3", ev=final_tie, grade_dir=tmp_path)
    assert r["status"] == "skipped"


def test_home_win_derived_from_final_event(tmp_path):
    _seed_capture(tmp_path, "mlb", "G4")
    final = {"competitions": [{"status": {"type": {"name": "STATUS_FINAL",
             "completed": True}}, "competitors": [
                 {"homeAway": "home", "score": "5"},
                 {"homeAway": "away", "score": "3"}]}]}
    r = ss.stamp_final("mlb", "G4", ev=final, grade_dir=tmp_path)
    assert r["status"] == "stamped" and r["home_win"] == 1.0


def test_outcome_arm_can_read_stamp(tmp_path):
    # before stamping: aggregate has no settled outcome for this game.
    p = _seed_capture(tmp_path, "nba", "G5")
    assert agg._settled_outcome(p) is None
    ss.stamp_final("nba", "G5", home_win=0, grade_dir=tmp_path)
    # after stamping: the OUTCOME arm reads the held-out binary label.
    assert agg._settled_outcome(p) == 0.0


def test_stamp_does_not_corrupt_capture_rows(tmp_path):
    # the paired capture rows must remain loadable (grader still reads model/market pairs).
    p = _seed_capture(tmp_path, "nba", "G6")
    ss.stamp_final("nba", "G6", home_win=1, grade_dir=tmp_path)
    pairs = lg._load_pairs(p)  # validity-guarded loader: settle row has no probs -> excluded
    assert len(pairs) == 2
    assert all(0.0 <= r["model_prob"] <= 1.0 for r in pairs)


# --------------------------------------------------------------------------------------- #
# tennis: nested/athlete-shaped raw ESPN event (REUSES ingame_live_state's team-then-athlete
# / sets-won fallback, same fixture convention as test_ingame_live_state.py's tennis tests).
# --------------------------------------------------------------------------------------- #

def _tennis_final_event(*, winner_home: bool):
    """One flattened tennis match event ({"competitions":[<match>]}), shaped exactly like
    settled_finals._tennis_final_matches / ingame_live_state._tennis_matches emit: no .team,
    no numeric .score, only .athlete + .linescores + .winner."""
    home_ls = [{"winner": winner_home}, {"winner": winner_home}]
    away_ls = [{"winner": not winner_home}, {"winner": not winner_home}]
    return {"id": "179877", "competitions": [{
        "status": {"type": {"name": "STATUS_FINAL", "completed": True}},
        "competitors": [
            {"homeAway": "home", "athlete": {"shortName": "Player A"}, "linescores": home_ls},
            {"homeAway": "away", "athlete": {"shortName": "Player B"}, "linescores": away_ls},
        ],
    }]}


def test_home_win_derived_from_tennis_event_home_wins(tmp_path):
    _seed_capture(tmp_path, "tennis", "T1")
    r = ss.stamp_final("tennis", "T1", ev=_tennis_final_event(winner_home=True),
                        grade_dir=tmp_path)
    assert r["status"] == "stamped" and r["home_win"] == 1.0


def test_home_win_derived_from_tennis_event_away_wins(tmp_path):
    _seed_capture(tmp_path, "tennis", "T2")
    r = ss.stamp_final("tennis", "T2", ev=_tennis_final_event(winner_home=False),
                        grade_dir=tmp_path)
    assert r["status"] == "stamped" and r["home_win"] == 0.0


def test_tennis_in_progress_event_skipped(tmp_path):
    _seed_capture(tmp_path, "tennis", "T3")
    in_progress = {"id": "X", "competitions": [{
        "status": {"type": {"name": "STATUS_IN_PROGRESS", "state": "in", "completed": False}},
        "competitors": [
            {"homeAway": "home", "athlete": {"shortName": "A"}, "linescores": [{"winner": True}]},
            {"homeAway": "away", "athlete": {"shortName": "B"}, "linescores": [{"winner": False}]},
        ],
    }]}
    r = ss.stamp_final("tennis", "T3", ev=in_progress, grade_dir=tmp_path)
    assert r["status"] == "skipped" and r["home_win"] is None


# --------------------------------------------------------------------------------------- #
# flat settled_finals-style game dict: the REAL shape inplay_capture_loop._stamp_final
# passes as `ev` in production (settled_since returns {home,away,home_score,away_score,...},
# never a nested 'competitions' key). Regression guard for the bug this lane closes.
# --------------------------------------------------------------------------------------- #

def test_home_win_derived_from_flat_settled_finals_game(tmp_path):
    _seed_capture(tmp_path, "nba", "G7")
    flat_game = {"sport": "nba", "game_id": "G7", "commence": "2026-07-01T00:00:00Z",
                 "home": "BOS", "away": "LAL", "home_score": 110.0, "away_score": 100.0,
                 "key": "x"}
    r = ss.stamp_final("nba", "G7", ev=flat_game, grade_dir=tmp_path)
    assert r["status"] == "stamped" and r["home_win"] == 1.0


def test_home_win_flat_shape_away_win_and_tie(tmp_path):
    _seed_capture(tmp_path, "mlb", "G8")
    flat_away_win = {"home": "NYY", "away": "BOS", "home_score": 2.0, "away_score": 5.0}
    r = ss.stamp_final("mlb", "G8", ev=flat_away_win, grade_dir=tmp_path)
    assert r["status"] == "stamped" and r["home_win"] == 0.0

    _seed_capture(tmp_path, "mlb", "G9")
    flat_tie = {"home": "NYY", "away": "BOS", "home_score": 3.0, "away_score": 3.0}
    r2 = ss.stamp_final("mlb", "G9", ev=flat_tie, grade_dir=tmp_path)
    assert r2["status"] == "skipped" and r2["home_win"] is None


def test_home_win_flat_shape_missing_scores_skipped(tmp_path):
    _seed_capture(tmp_path, "soccer", "G10")
    flat_missing = {"home": "ARS", "away": "CHE"}
    r = ss.stamp_final("soccer", "G10", ev=flat_missing, grade_dir=tmp_path)
    assert r["status"] == "skipped" and r["home_win"] is None
