"""Per-file test for the sport-blind tracking harness."""
import pandas as pd

from scripts.platformkit.tracking_harness import evaluate, SPORTS


def _good_game(n_frames=100, n_players=10):
    rows = []
    for f in range(n_frames):
        for pid in range(n_players):
            rows.append({"frame": f, "track_id": pid, "cls": "player",
                         "x": 10.0 + pid * 5 + f * 0.02, "y": 25.0})
        rows.append({"frame": f, "track_id": 99, "cls": "ball",
                     "x": 47.0, "y": 25.0})
    return pd.DataFrame(rows)


def test_good_game_passes():
    rep = evaluate(_good_game(), "basketball")
    assert rep.passed, rep.failures
    assert rep.coverage_pct == 1.0 and rep.ball_valid_pct == 1.0


def test_oob_and_teleport_fail():
    df = _good_game()
    df.loc[df["cls"] == "player", "x"] = 500.0  # everything out of bounds
    rep = evaluate(df, "basketball")
    assert not rep.passed and any("oob" in f for f in rep.failures)


def test_missing_ball_fails():
    df = _good_game()
    rep = evaluate(df[df["cls"] != "ball"], "basketball")
    assert not rep.passed and any("ball_valid" in f for f in rep.failures)


def test_all_sports_have_complete_configs():
    keys = {"bounds", "min_players", "ball_valid_min", "coverage_min",
            "oob_max", "jump_p95_max"}
    for sport, cfg in SPORTS.items():
        assert keys <= set(cfg), sport


def test_empty_input():
    rep = evaluate(pd.DataFrame(columns=["frame", "track_id", "cls", "x", "y"]),
                   "tennis")
    assert not rep.passed
