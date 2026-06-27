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
