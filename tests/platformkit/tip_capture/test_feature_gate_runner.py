"""Per-file test for tip_capture.feature_gate_runner. Synthetic tip_capture +
ingame_grade jsonl corpora in tmp_path only -- no real data/ read.

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/tip_capture/test_feature_gate_runner.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.tip_capture import feature_gate_runner as gr  # noqa: E402


def _write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _build_corpus(tip_dir: Path, grade_dir: Path, sport: str, n_games: int, seed: int = 0):
    """n_games synthetic single-tick games: home_win alternates 0/1 (balanced,
    every walk-forward split sees both classes). foul_count_tail is genuinely
    informative (drawn from a class-separated distribution); recent_scoring_run
    is pure noise (drawn independent of the label); score_margin/frac_elapsed
    (the baseline) carry no signal either."""
    import numpy as np
    rng = np.random.default_rng(seed)
    for i in range(n_games):
        game_id = f"{sport}_{i:04d}"
        home_win = i % 2
        date_str = f"2026-01-{(i % 28) + 1:02d}" if i < 28 else f"2026-02-{(i - 28) % 28 + 1:02d}"
        margin = int(rng.integers(-3, 4))
        foul_n = int(rng.integers(4, 8)) if home_win else int(rng.integers(0, 3))
        swing = int(rng.integers(-10, 10))
        events = (
            [{"home_score": 0, "away_score": 0, "text": ""}]
            + [{"text": "shooting foul"} for _ in range(foul_n)]
            + [{"home_score": max(swing, 0), "away_score": max(-swing, 0), "text": ""}]
        )
        row = {
            "capture_ts": f"{date_str}T20:00:00Z", "sport": sport, "game_id": game_id,
            "home": "Home Team", "away": "Away Team",
            "period": 4, "inning": None, "clock": 200.0,
            "score_home": 50 + margin, "score_away": 50,
            "payload": {"pbp_tail": {"status": "ok", "events": events}},
        }
        _write_jsonl(tip_dir / sport / f"ingame_{date_str}.jsonl", [row])
        _write_jsonl(grade_dir / sport / f"{game_id}.jsonl",
                     [{"game_id": game_id, "settled": True, "home_win": home_win}])


def test_informative_feature_passes(tmp_path):
    tip_dir, grade_dir, out = tmp_path / "tip", tmp_path / "grade", tmp_path / "out.json"
    _build_corpus(tip_dir, grade_dir, "nba", n_games=100, seed=1)
    artifact = gr.run(tip_dir, grade_dir, out, min_test_games=20)
    result = artifact["features"]["nba"]["foul_count_tail"]
    assert result["verdict"] == "PASS", result
    assert result["ci"][0] > 0


def test_noise_feature_does_not_pass(tmp_path):
    tip_dir, grade_dir, out = tmp_path / "tip", tmp_path / "grade", tmp_path / "out.json"
    _build_corpus(tip_dir, grade_dir, "nba", n_games=100, seed=2)
    artifact = gr.run(tip_dir, grade_dir, out, min_test_games=20)
    result = artifact["features"]["nba"]["recent_scoring_run"]
    assert result["verdict"] != "PASS", result


def test_tiny_corpus_is_insufficient(tmp_path):
    tip_dir, grade_dir, out = tmp_path / "tip", tmp_path / "grade", tmp_path / "out.json"
    _build_corpus(tip_dir, grade_dir, "nba", n_games=10, seed=3)
    artifact = gr.run(tip_dir, grade_dir, out, min_test_games=30)
    for result in artifact["features"]["nba"].values():
        assert result["verdict"] == "INSUFFICIENT", result


def test_artifact_shape_and_honesty(tmp_path):
    tip_dir, grade_dir, out = tmp_path / "tip", tmp_path / "grade", tmp_path / "out.json"
    _build_corpus(tip_dir, grade_dir, "nba", n_games=40, seed=4)
    artifact = gr.run(tip_dir, grade_dir, out, min_test_games=10)
    assert artifact["edge_claimed"] is False
    assert "as_of" in artifact
    assert set(artifact["corpora"]["nba"]) == {"n_games", "n_ticks", "date_range"}
    assert artifact["corpora"]["nba"]["n_games"] == 40
    assert out.is_file()
    hist = out.parent / "live_feature_gate_history.jsonl"
    assert hist.is_file()
    last_line = hist.read_text(encoding="utf-8").strip().splitlines()[-1]
    hist_row = json.loads(last_line)
    assert hist_row["corpora"]["nba"]["n_games"] == 40


def test_empty_tip_dir_returns_no_sports(tmp_path):
    tip_dir, grade_dir, out = tmp_path / "tip", tmp_path / "grade", tmp_path / "out.json"
    artifact = gr.run(tip_dir, grade_dir, out)
    assert artifact["corpora"] == {}
    assert artifact["features"] == {}
    assert artifact["edge_claimed"] is False


def test_frac_elapsed_basketball_and_mlb():
    assert abs(gr.frac_elapsed({"period": 1, "clock": 720.0}) - 0.0) < 1e-9
    assert abs(gr.frac_elapsed({"period": 4, "clock": 0.0}) - 1.0) < 1e-9
    assert gr.frac_elapsed({"period": 5, "clock": 100.0}) == 1.0
    assert abs(gr.frac_elapsed({"inning": 9, "period": None}) - 1.0) < 1e-9
    assert gr.frac_elapsed({}) != gr.frac_elapsed({})  # NaN != NaN
