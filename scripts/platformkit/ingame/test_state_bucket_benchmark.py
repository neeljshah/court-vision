"""Per-file tests for state_bucket_benchmark.py -- MLB per-state MODEL-vs-MARKET benchmark.

OFFLINE + deterministic: grade files written to tmp_path; outcome resolver injected via
MlbOutcomeResolver(box_df=...) (no parquet, no network).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_state_bucket_benchmark.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

import scripts.platformkit.ingame.state_bucket_benchmark as sb
from scripts.platformkit.ingame.ingame_outcome_label import MlbOutcomeResolver


def _ts(i: int) -> str:
    return (datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
           + timedelta(seconds=30 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ticker(n: int) -> str:
    # KXMLBGAME-<YY><MON><DD><HHMM><AWAY+HOME> ; NYY@BOS, unique DAY per game so each
    # game gets its own (date, away, home) box-score key -- same-day/same-teams would
    # collide into an ambiguous "doubleheader" the resolver correctly refuses to guess.
    return "KXMLBGAME-26JUN%02d1200NYYBOS" % (1 + (n % 28))


def _write_game(grade_dir: Path, gid: str, rows: list) -> None:
    p = grade_dir / "mlb" / ("%s.jsonl" % gid)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for i, (model_p, market_p, home_score, away_score, inning) in enumerate(rows):
            fh.write(json.dumps({
                "sport": "mlb", "game_id": gid, "ts": _ts(i), "side": "home",
                "model_prob": model_p, "market_prob": market_p,
                "state_summary": "home_score=%s away_score=%s inning=%s half=top" % (
                    home_score, away_score, inning),
            }) + "\n")


def _box_df(n_games: int, home_win: bool = True) -> pd.DataFrame:
    rows = []
    for n in range(n_games):
        rows.append({
            "event_id": str(1000 + n), "home_abbr": "BOS", "away_abbr": "NYY",
            "home_score": 5 if home_win else 2, "away_score": 2 if home_win else 5,
            "status": "STATUS_FINAL", "date": "2026-06-%02d" % (1 + (n % 28)),
            "start_time": "",
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------- #
def test_margin_and_phase_bucket() -> None:
    assert sb.margin_bucket(7.0, 1.0) == "leading_big"
    assert sb.margin_bucket(1.0, 1.0) == "tied"
    assert sb.margin_bucket(1.0, 3.0) == "trailing"
    assert sb.margin_bucket(0.0, 4.0) == "trailing_big"
    assert sb.phase_bucket(2) == "early"
    assert sb.phase_bucket(5) == "mid"
    assert sb.phase_bucket(9) == "late"
    assert sb.phase_bucket(None) == "unknown"


def test_load_bucketed_ticks_resolves_and_buckets(tmp_path: Path) -> None:
    grade_dir = tmp_path / "ingame_grade"
    n_games = 10
    # tied|early state for every tick, model always leans toward the true winner (home
    # win planted in the box), market copies (constant 0.5) -> model should score a
    # strictly lower Brier in this bucket.
    for n in range(n_games):
        gid = _ticker(n)
        rows = [(0.7, 0.5, 0.0, 0.0, 2)] * 12
        _write_game(grade_dir, gid, rows)
    resolver = MlbOutcomeResolver(box_df=_box_df(n_games, home_win=True))
    ticks, counts = sb.load_bucketed_ticks(grade_dir, resolver)
    assert counts["n_games_with_pairs"] == n_games
    assert counts["n_resolved"] == n_games
    assert counts["n_unresolved"] == 0
    assert len(ticks) == n_games * 12
    assert all(t["bucket"] == "early|tied" for t in ticks)
    assert all(t["outcome"] == 1.0 for t in ticks)


def test_unresolvable_games_are_dropped_not_fabricated(tmp_path: Path) -> None:
    grade_dir = tmp_path / "ingame_grade"
    _write_game(grade_dir, _ticker(0), [(0.6, 0.5, 0.0, 0.0, 1)] * 5)
    resolver = MlbOutcomeResolver(box_df=pd.DataFrame(columns=[
        "event_id", "home_abbr", "away_abbr", "home_score", "away_score",
        "status", "date", "start_time"]))
    ticks, counts = sb.load_bucketed_ticks(grade_dir, resolver)
    assert ticks == []
    assert counts["n_unresolved"] == 1
    assert counts["n_resolved"] == 0


def test_model_ahead_verdict_with_enough_games(tmp_path: Path) -> None:
    """Model consistently closer to the (planted) true outcome than a market that never
    moves off 0.5 -> MODEL_AHEAD once >= MIN_GAMES games back the bucket."""
    grade_dir = tmp_path / "ingame_grade"
    n_games = sb.MIN_GAMES + 4
    for n in range(n_games):
        gid = _ticker(n)
        rows = [(0.85, 0.5, 3.0, 1.0, 8)] * 20   # leading|late, home actually wins
        _write_game(grade_dir, gid, rows)
    resolver = MlbOutcomeResolver(box_df=_box_df(n_games, home_win=True))
    doc = sb.build_benchmark(grade_dir, resolver)
    bucket = next(b for b in doc["buckets"] if b["bucket"] == "late|leading")
    assert bucket["n_games"] == n_games
    assert bucket["verdict"] == "MODEL_AHEAD"
    assert bucket["model"]["brier"] < bucket["market"]["brier"]
    assert doc["edge_claimed"] is False
    assert doc["units"].startswith("probability")


def test_insufficient_data_below_min_games(tmp_path: Path) -> None:
    grade_dir = tmp_path / "ingame_grade"
    n_games = 3
    for n in range(n_games):
        _write_game(grade_dir, _ticker(n), [(0.9, 0.5, 3.0, 1.0, 8)] * 10)
    resolver = MlbOutcomeResolver(box_df=_box_df(n_games, home_win=True))
    doc = sb.build_benchmark(grade_dir, resolver)
    bucket = next(b for b in doc["buckets"] if b["bucket"] == "late|leading")
    assert bucket["n_games"] == n_games < sb.MIN_GAMES
    assert bucket["verdict"] == "INSUFFICIENT_DATA"


def test_market_copy_model_never_beats(tmp_path: Path) -> None:
    """A model that IS the market (model_prob == market_prob) must score MATCH/
    INSUFFICIENT_DATA, never MODEL_AHEAD -- the correctness anchor for the paired-Brier
    verdict, mirroring inplay_clv_replay's naive_market_follow_model guard."""
    grade_dir = tmp_path / "ingame_grade"
    n_games = sb.MIN_GAMES + 5
    for n in range(n_games):
        _write_game(grade_dir, _ticker(n), [(0.5, 0.5, 0.0, 0.0, 2)] * 10)
    resolver = MlbOutcomeResolver(box_df=_box_df(n_games, home_win=True))
    doc = sb.build_benchmark(grade_dir, resolver)
    bucket = next(b for b in doc["buckets"] if b["bucket"] == "early|tied")
    assert bucket["verdict"] in ("MATCH", "INSUFFICIENT_DATA")
    assert bucket["brier_delta_market_minus_model"] == pytest.approx(0.0, abs=1e-9)


def test_write_benchmark_output_shape(tmp_path: Path) -> None:
    grade_dir = tmp_path / "ingame_grade"
    n_games = sb.MIN_GAMES + 1
    for n in range(n_games):
        _write_game(grade_dir, _ticker(n), [(0.8, 0.5, 2.0, 0.0, 3)] * 8)
    resolver = MlbOutcomeResolver(box_df=_box_df(n_games, home_win=True))
    out_path = tmp_path / "out" / "mlb_state_bucket_benchmark.json"
    history_path = tmp_path / "out" / "scoreboard_history.jsonl"
    doc = sb.write_benchmark(out_path, grade_dir, resolver, history_path=history_path)
    assert history_path.is_file()  # never touches the real data/cache history
    assert out_path.is_file()
    reloaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert reloaded["sport"] == "mlb"
    assert reloaded["edge_claimed"] is False
    assert reloaded["calibration_scoreboard"]["per_sport"][0]["sport"] == "mlb"
    assert doc["pooled"]["n_ticks"] == n_games * 8
