"""Tests for signals/home_court_term.py.

Two mandatory assertions:
  1. Leak-safety — build() never uses game rows >= ctx.decision_time.
  2. Value sanity — the returned delta is a float in a reasonable range, and
     the league-level bias (~+3.5pp) is captured when ctx.is_home=True.

Run with:
    NBA_OFFLINE=1 python -m pytest tests/test_signal_home_court_term.py -v
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
import tempfile
from pathlib import Path

import pytest

# ---- path setup (mirror CLAUDE.md: sys.path.insert(0,'.') at repo root) ----
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signals.home_court_term import (
    HomeCourtTermSignal,
    _load_season_game_rows,
    _compute_calibrated_delta,
    _MIN_GAMES_TEAM,
)
from src.loop.signal import AsOfContext
from src.loop.store import PointInTimeStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_row(game_date: str, home_team: str, home_win: float,
              sim_win_prob: float) -> dict:
    return {
        "game_id": f"test_{game_date}_{home_team}",
        "game_date": game_date,
        "home_team": home_team,
        "away_team": "OPP",
        "home_win": home_win,
        "sim_win_prob": sim_win_prob,
    }


def _write_season_file(tmpdir: Path, season: str, rows: list) -> Path:
    """Write a fake season_games_<season>.json into tmpdir."""
    path = tmpdir / f"season_games_{season}.json"
    path.write_text(json.dumps({"v": 1, "rows": rows}), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 1. Leak-safety assertion
# ---------------------------------------------------------------------------

class TestLeakSafety:
    """Verify that no game row on or after decision_time is ever used."""

    def test_rows_before_decision_time_only(self, tmp_path: Path, monkeypatch) -> None:
        """_load_season_game_rows must exclude rows >= before_date."""
        season_dir = tmp_path / "nba"
        season_dir.mkdir()

        past_row = _make_row("2024-01-10", "BOS", 1.0, 0.45)
        today_row = _make_row("2024-01-20", "BOS", 1.0, 0.45)   # decision date
        future_row = _make_row("2024-01-25", "BOS", 0.0, 0.55)  # after decision

        _write_season_file(season_dir, "2023-24",
                           [past_row, today_row, future_row])

        # Monkeypatch the glob pattern inside the module
        import signals.home_court_term as mod
        original_glob = str(mod._ROOT / "data" / "nba" / "season_games_*.json")
        monkeypatch.setattr(
            mod, "_SEASON_GAMES_GLOB",
            str(season_dir / "season_games_*.json"),
        )

        before_date = "2024-01-20"
        rows = _load_season_game_rows(before_date)

        # Only the past_row should survive; today's and future rows are excluded
        assert len(rows) == 1, f"Expected 1 row, got {len(rows)}: {rows}"
        assert rows[0]["game_date"] == "2024-01-10"

    def test_build_uses_as_of_date(self, tmp_path: Path, monkeypatch) -> None:
        """Signal.build() must not return values influenced by future rows."""
        season_dir = tmp_path / "nba"
        season_dir.mkdir()

        # 20 past games: home wins 60% sim_prob 50%  -> residual +0.10
        past_rows = [
            _make_row(f"2024-01-{i:02d}", "BOS", 1.0, 0.50)
            for i in range(1, 11)
        ] + [
            _make_row(f"2024-01-{i:02d}", "BOS", 0.0, 0.50)
            for i in range(11, 15)
        ]
        # Future rows where BOS home_win=0 (would pull residual down if leaked)
        future_rows = [
            _make_row(f"2024-02-{i:02d}", "BOS", 0.0, 0.60)
            for i in range(1, 20)
        ]

        _write_season_file(season_dir, "2023-24", past_rows + future_rows)

        import signals.home_court_term as mod
        monkeypatch.setattr(
            mod, "_SEASON_GAMES_GLOB",
            str(season_dir / "season_games_*.json"),
        )

        decision_time = _dt.datetime(2024, 1, 20)  # before future rows
        ctx = AsOfContext(
            decision_time=decision_time,
            team="BOS",
            opp="NYK",
            is_home=True,
            scope="pregame",
        )

        sig = HomeCourtTermSignal(store=None)
        delta = sig.build(ctx)

        # Should be positive (BOS home residual > 0 in past rows)
        assert delta is not None, "delta should not be None for BOS with 14 past games"
        assert isinstance(delta, float), f"Expected float, got {type(delta)}"
        # Delta should be positive (model under-predicts home wins in past rows)
        assert delta > 0.0, (
            f"Expected positive delta for BOS home advantage, got {delta}"
        )
        # Should not be influenced by future rows (which would pull it negative)
        # If future rows leaked in, the residual would be pulled sharply down
        assert delta > -0.05, "Future rows appear to have leaked into the build"


# ---------------------------------------------------------------------------
# 2. Value-sanity assertion
# ---------------------------------------------------------------------------

class TestValueSanity:
    """Verify the returned delta is a valid SignalValue in a reasonable range."""

    def test_returns_float_for_home_team(self, tmp_path: Path, monkeypatch) -> None:
        """build() returns a float when is_home=True and data is available."""
        season_dir = tmp_path / "nba"
        season_dir.mkdir()

        # Simulate league-level +3.5pp gap (consistent with real data)
        rows = (
            [_make_row(f"2024-01-{i:02d}", "BOS", 1.0, 0.50) for i in range(1, 16)]
            + [_make_row(f"2024-01-{i:02d}", "LAL", 1.0, 0.52) for i in range(1, 11)]
            + [_make_row(f"2024-01-{i:02d}", "OKC", 0.0, 0.50) for i in range(1, 6)]
        )
        _write_season_file(season_dir, "2023-24", rows)

        import signals.home_court_term as mod
        monkeypatch.setattr(
            mod, "_SEASON_GAMES_GLOB",
            str(season_dir / "season_games_*.json"),
        )

        ctx = AsOfContext(
            decision_time=_dt.datetime(2024, 2, 1),
            team="BOS",
            opp="LAL",
            is_home=True,
            scope="pregame",
        )
        sig = HomeCourtTermSignal(store=None)
        delta = sig.build(ctx)

        assert sig.validate_output(delta), f"Output failed validate_output: {delta}"
        assert isinstance(delta, float), f"Expected float, got {type(delta)}"
        assert -1.0 < delta < 1.0, f"Delta out of probability range: {delta}"

    def test_returns_none_when_is_home_none(self) -> None:
        """build() returns None when is_home is unset (no home-court context)."""
        ctx = AsOfContext(
            decision_time=_dt.datetime(2024, 2, 1),
            team="BOS",
            is_home=None,
            scope="pregame",
        )
        sig = HomeCourtTermSignal(store=None)
        result = sig.build(ctx)
        assert result is None, f"Expected None for is_home=None, got {result}"

    def test_league_bias_captured(self, tmp_path: Path, monkeypatch) -> None:
        """League-mean residual ~3.5pp is present when team data is sparse."""
        season_dir = tmp_path / "nba"
        season_dir.mkdir()

        # 100 games for OTHER teams: home_win=1, sim_win_prob=0.50 -> residual +0.50
        # 2 games for the subject team: too few for team-specific estimate
        rows = (
            [_make_row(f"2024-01-{i:02d}", "MIL", 1.0, 0.518) for i in range(1, 51)]
            + [_make_row(f"2024-01-{i:02d}", "NYK", 1.0, 0.518) for i in range(1, 51)]
            + [_make_row("2024-01-01", "BOS", 1.0, 0.518)]  # only 1 BOS game
        )
        _write_season_file(season_dir, "2023-24", rows)

        import signals.home_court_term as mod
        monkeypatch.setattr(
            mod, "_SEASON_GAMES_GLOB",
            str(season_dir / "season_games_*.json"),
        )

        ctx = AsOfContext(
            decision_time=_dt.datetime(2024, 2, 1),
            team="BOS",
            opp="MIL",
            is_home=True,
            scope="pregame",
        )
        sig = HomeCourtTermSignal(store=None)
        delta = sig.build(ctx)

        # With only 1 BOS game (< _MIN_GAMES_TEAM), falls back to league mean
        # League mean from the 101 rows: home_win - sim_win_prob ~ 1.0 - 0.518 = 0.482
        assert delta is not None, "Should return league mean even with sparse team data"
        assert isinstance(delta, float)
        assert delta > 0.0, f"Expected positive league bias, got {delta}"

    def test_store_reinforcement_blends(self, tmp_path: Path, monkeypatch) -> None:
        """When the store has a prior calibrated_delta, it blends into the output."""
        season_dir = tmp_path / "nba"
        season_dir.mkdir()

        rows = [
            _make_row(f"2024-01-{i:02d}", "BOS", 1.0, 0.50)
            for i in range(1, 21)  # 20 games, residual +0.50
        ]
        _write_season_file(season_dir, "2023-24", rows)

        import signals.home_court_term as mod
        monkeypatch.setattr(
            mod, "_SEASON_GAMES_GLOB",
            str(season_dir / "season_games_*.json"),
        )

        # Write a prior into the store (simulates a previously shipped signal)
        store = PointInTimeStore(store_dir=tmp_path / "store", autoload=False)
        store.write_atlas(
            "team", "BOS", "home_court", "2024-01-01",
            {"calibrated_delta": 0.12, "n_games": 50},
            {"source": "shipped_signal:home_court_term", "n": 50,
             "confidence": "high", "as_of": "2024-01-01"},
        )

        ctx = AsOfContext(
            decision_time=_dt.datetime(2024, 2, 1),
            team="BOS",
            opp="MIL",
            is_home=True,
            scope="pregame",
            game_date="2024-02-01",
        )
        sig = HomeCourtTermSignal(store=store)
        delta = sig.build(ctx)

        # With a positive prior (0.12) and positive raw residual, delta should remain positive
        assert delta is not None
        assert isinstance(delta, float)
        assert delta > 0.0, (
            f"Expected positive delta with positive prior and raw residual, got {delta}"
        )
        assert sig.validate_output(delta)

    def test_hypothesis_metadata(self) -> None:
        """hypothesis() returns a well-formed Hypothesis with correct fields."""
        sig = HomeCourtTermSignal(store=None)
        h = sig.hypothesis()

        assert h.name == "home_court_term"
        assert h.target == "winprob"
        assert h.scope == "pregame"
        assert h.source == "seed"
        assert "home_court" in h.atlas_fields
        assert h.expected_verdict == "SHIP"
        assert h.priority == "P1"
        assert len(h.statement) > 20
        assert len(h.rationale) > 20

    def test_feature_names(self) -> None:
        """feature_names() returns ['home_court_term'] for a scalar signal."""
        sig = HomeCourtTermSignal(store=None)
        assert sig.feature_names() == ["home_court_term"]
