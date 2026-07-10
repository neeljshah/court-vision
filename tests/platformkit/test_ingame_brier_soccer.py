"""Per-file smoke tests for scripts/platformkit/benchmarks/crps_market/ingame_soccer
-- minute-timeline detection, checkpoint-row anchoring, and the end-to-end paired-
Brier run on synthetic game files. No real corpus reads (the CLI itself exercises
the real ingame_grade_joined/soccer_intl corpus).

Run: python -m pytest tests/platformkit/test_ingame_brier_soccer.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.benchmarks.crps_market.ingame_soccer import (
    CHECKPOINTS, checkpoint_row, has_minute_timeline, load_game_rows, run,
)


def test_checkpoints_are_minute_60_and_75():
    assert CHECKPOINTS == (60, 75)


def test_has_minute_timeline_true_when_minute_present():
    rows = [{"state_summary": "home_score=0.0 away_score=0.0 minute=1"}]
    assert has_minute_timeline(rows) is True


def test_has_minute_timeline_false_for_live_only_format():
    rows = [{"state_summary": "live"}, {"state_summary": "live"}]
    assert has_minute_timeline(rows) is False


def test_checkpoint_row_finds_first_row_at_or_past_minute():
    rows = [
        {"state_summary": "minute=58", "model_prob": 0.1},
        {"state_summary": "minute=60", "model_prob": 0.2},
        {"state_summary": "minute=61", "model_prob": 0.3},
    ]
    got = checkpoint_row(rows, 60)
    assert got == {"state_summary": "minute=60", "model_prob": 0.2}


def test_checkpoint_row_none_when_minute_never_reached():
    rows = [{"state_summary": "minute=10"}, {"state_summary": "minute=45"}]
    assert checkpoint_row(rows, 75) is None


def test_load_game_rows_skips_malformed_lines(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text('{"a": 1}\nnot json\n{"a": 2}\n', encoding="utf-8")
    rows = load_game_rows(p)
    assert rows == [{"a": 1}, {"a": 2}]


def _game_line(game_id: str, minute: int, model_prob: float, market_prob: float,
               outcome: float) -> str:
    return json.dumps({
        "sport": "soccer_intl", "game_id": game_id, "ts": "2026-07-01T00:00:00Z",
        "model_prob": model_prob, "market_prob": market_prob, "side": "home",
        "state_summary": "home_score=0.0 away_score=0.0 minute=%d" % minute,
        "outcome": outcome, "close_source": "soccer_outcome:espn_finals_parquet",
        "close_prob": outcome, "close_ts": "2026-07-01T02:00:00Z", "edge_claimed": False,
    })


def test_run_end_to_end_underpowered_below_n30(tmp_path, monkeypatch):
    # 3 games, model perfectly right (brier=0) vs market wrong (brier=1) at
    # both checkpoints -- a real effect, but n=3 << 30 must still read
    # UNDERPOWERED (never "tie"), per the same rule ingame_mlb.py applies.
    game_dir = tmp_path / "soccer_intl"
    game_dir.mkdir()
    for i in range(3):
        lines = [_game_line("G%d" % i, m, model_prob=1.0, market_prob=0.0, outcome=1.0)
                for m in (60, 75)]
        (game_dir / ("G%d.jsonl" % i)).write_text("\n".join(lines) + "\n", encoding="utf-8")

    # one older-format game with no minute field -- must be excluded, not guessed
    (game_dir / "OLD.jsonl").write_text(
        json.dumps({"state_summary": "live", "model_prob": 0.5, "market_prob": 0.5,
                   "outcome": 1.0}) + "\n", encoding="utf-8")

    monkeypatch.setattr("scripts.platformkit.benchmarks.crps_market.ingame_soccer._GAME_DIR",
                        game_dir)
    monkeypatch.setattr("scripts.platformkit.benchmarks.crps_market.ingame_soccer._OUT",
                        tmp_path / "out.json")
    monkeypatch.setattr("scripts.platformkit.benchmarks.crps_market.ingame_soccer._LEDGER",
                        tmp_path / "ledger.jsonl")

    doc = run(max_games=10)
    assert doc["n_no_minute_timeline"] == 1
    assert doc["metric"] == "brier"
    for key in ("home_win_prob|minute_60", "home_win_prob|minute_75"):
        bucket = doc["checkpoints"][key]
        assert bucket["n"] == 3
        assert bucket["verdict"] == "UNDERPOWERED"
        assert bucket["model_brier_mean"] == 0.0
        assert bucket["market_brier_mean"] == 1.0

    ledger_path = tmp_path / "ledger.jsonl"
    assert ledger_path.exists()
    ledger_lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(ledger_lines) == 2
    assert all(json.loads(l)["sport"] == "soccer_intl" for l in ledger_lines)


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
