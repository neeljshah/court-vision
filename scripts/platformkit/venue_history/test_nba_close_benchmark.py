"""Tests for scripts.platformkit.venue_history.nba_close_benchmark. Offline,
synthetic fixtures only (games.parquet + close corpus are both injected via
tmp_path, never the real disk corpora)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.platformkit.venue_history import nba_close_benchmark as ncb


def _write_games_parquet(path: Path, rows) -> None:
    """rows: list of (game_id, date, home, away, season, home_win)."""
    df = pd.DataFrame(rows, columns=["game_id", "date", "home_team", "away_team",
                                     "season", "home_win"])
    df["date"] = pd.to_datetime(df["date"])
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), str(path))


def _write_close_corpus(path: Path, rows) -> None:
    """rows: list of (game_id, close_prob_home)."""
    df = pd.DataFrame(rows, columns=["game_id", "close_prob_home"])
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), str(path))


def test_run_benchmark_missing_corpus_is_honest_error(tmp_path: Path) -> None:
    rep = ncb.run_benchmark(corpus_path=tmp_path / "nope.parquet",
                            games_parquet=tmp_path / "games.parquet")
    assert "error" in rep
    assert "not found" in rep["error"]


def test_run_benchmark_empty_corpus_is_honest_error(tmp_path: Path) -> None:
    corpus_fp = tmp_path / "empty.parquet"
    _write_close_corpus(corpus_fp, [])
    games_fp = tmp_path / "games.parquet"
    _write_games_parquet(games_fp, [("g1", "2024-01-01", "BOS", "MIA", "2023-24", 1.0)])
    rep = ncb.run_benchmark(corpus_path=corpus_fp, games_parquet=games_fp)
    assert "error" in rep
    assert "empty" in rep["error"]


def test_run_benchmark_zero_overlap_is_honest_error(tmp_path: Path) -> None:
    games_fp = tmp_path / "games.parquet"
    _write_games_parquet(games_fp, [("g1", "2024-01-01", "BOS", "MIA", "2023-24", 1.0)])
    corpus_fp = tmp_path / "close.parquet"
    _write_close_corpus(corpus_fp, [("g_not_in_schedule", 0.6)])
    rep = ncb.run_benchmark(corpus_path=corpus_fp, games_parquet=games_fp)
    assert "error" in rep
    assert "0 games overlap" in rep["error"]


def test_run_benchmark_scores_only_overlapping_games_leak_free(tmp_path: Path) -> None:
    """A larger schedule feeds the walk-forward rating (so it has history to
    learn from), but Brier is computed ONLY on the subset present in the
    close corpus -- and the model's prediction for game g3 must not depend on
    g3's own outcome (leak-free), only on g1/g2 (which precede it)."""
    games_fp = tmp_path / "games.parquet"
    _write_games_parquet(games_fp, [
        ("g1", "2024-01-01", "BOS", "MIA", "2023-24", 1.0),
        ("g2", "2024-01-02", "BOS", "NYK", "2023-24", 1.0),
        ("g3", "2024-01-03", "BOS", "LAL", "2023-24", 0.0),
        ("g4", "2024-01-04", "MIA", "NYK", "2023-24", 1.0),
    ])
    corpus_fp = tmp_path / "close.parquet"
    _write_close_corpus(corpus_fp, [("g3", 0.55), ("g4", 0.50)])

    rep = ncb.run_benchmark(corpus_path=corpus_fp, games_parquet=games_fp)
    assert "error" not in rep
    assert rep["n_games_overlap"] == 2
    assert rep["n_games_schedule"] == 4
    assert rep["n_games_close_corpus"] == 2
    assert "brier" in rep["model"] and "brier" in rep["close"]
    assert rep["verdict"] in ("MATCHES_CLOSE_WITHIN_NOISE", "TRAILS_CLOSE")
    # brier_gap is model - close, sign-consistent with the two Brier values
    assert round(rep["model"]["brier"] - rep["close"]["brier"], 5) == rep["brier_gap_model_minus_close"]


def test_run_benchmark_verdict_never_claims_beats_close(tmp_path: Path) -> None:
    """Even when the model's Brier happens to be numerically lower than the
    close's on a tiny synthetic sample, the verdict vocabulary must never say
    the model 'beats' the close (see .claude/rules/no-edge-claims.md)."""
    games_fp = tmp_path / "games.parquet"
    _write_games_parquet(games_fp, [
        ("g1", "2024-01-01", "BOS", "MIA", "2023-24", 1.0),
        ("g2", "2024-01-02", "BOS", "NYK", "2023-24", 1.0),
    ])
    corpus_fp = tmp_path / "close.parquet"
    # A deliberately bad close price so the model (which learns BOS is strong
    # from g1) can score lower Brier on g2 -- still must not print "beats".
    _write_close_corpus(corpus_fp, [("g2", 0.05)])
    rep = ncb.run_benchmark(corpus_path=corpus_fp, games_parquet=games_fp)
    assert "error" not in rep
    assert "beats" not in rep["verdict"].lower()
    assert rep["verdict"] in ("MATCHES_CLOSE_WITHIN_NOISE", "TRAILS_CLOSE")
    assert "edge" not in rep["note"].lower() or "no $-edge" in rep["note"].lower() or "not edge" in rep["note"].lower()
