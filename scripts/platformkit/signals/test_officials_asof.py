"""Focused synthetic checks for leak-safe officiating priors."""
import subprocess
import sys

import numpy as np
import pandas as pd

from scripts.platformkit.signals.officials_asof import (
    build_officiating_priors,
    fit_expected_called_strike,
    report_runtime_availability,
)


def _nba_inputs(target_fouls: float = 10.0):
    games = pd.DataFrame([
        {"game_id": "n1", "game_date": "2024-01-01", "sport": "NBA", "decision_horizon": "2023-12-31T12:00:00Z"},
        {"game_id": "n2", "game_date": "2024-01-02", "sport": "NBA", "decision_horizon": "2024-01-01T12:00:00Z"},
        {"game_id": "n3", "game_date": "2024-01-03", "sport": "NBA", "decision_horizon": "2024-01-02T12:00:00Z"},
    ])
    assignments = pd.DataFrame([
        {"game_id": game, "crew_id": "crew-a", "captured_at": "2023-12-30T00:00:00Z"}
        for game in games.game_id
    ])
    logs = pd.DataFrame([
        {"game_id": "n1", "game_date": "2024-01-01", "crew_id": "crew-a", "fouls": 10, "free_throw_attempts": 20},
        {"game_id": "n2", "game_date": "2024-01-02", "crew_id": "crew-a", "fouls": 12, "free_throw_attempts": 18},
        {"game_id": "n3", "game_date": "2024-01-03", "crew_id": "crew-a", "fouls": target_fouls, "free_throw_attempts": 1000},
    ])
    empty_assignments = pd.DataFrame(columns=["game_id", "umpire_id", "captured_at"])
    empty_pitches = pd.DataFrame(columns=["game_id", "pitch_date", "season", "umpire_id", "called_strike"])
    return games, assignments, logs, empty_assignments, empty_pitches


def test_own_game_is_excluded_and_postgame_assignment_is_not_runtime_available():
    base = build_officiating_priors(*_nba_inputs())
    extreme = build_officiating_priors(*_nba_inputs(target_fouls=9999.0))
    assert base.loc[2, "crew_foul_rate_prior"] == extreme.loc[2, "crew_foul_rate_prior"]
    assert base.loc[0, "crew_foul_rate_prior"] != base.loc[0, "crew_foul_rate_prior"]

    games, assignments, logs, mlb_assignments, pitches = _nba_inputs()
    assignments.loc[assignments.game_id == "n2", "captured_at"] = "2024-01-03T00:00:00Z"
    result = build_officiating_priors(games, assignments, logs, mlb_assignments, pitches)
    assert bool(result.loc[0, "runtime_available"])
    assert not bool(result.loc[1, "runtime_available"])
    assert report_runtime_availability(result) == "runtime_available_fraction=0.666667"


def test_v2_expectation_fit_is_strictly_prior_season():
    pitches = pd.DataFrame([
        {"game_id": "old", "pitch_date": "2023-04-01", "season": 2023, "umpire_id": "u", "called_strike": 1, "balls": 0, "strikes": 0, "zone": 1},
        {"game_id": "new", "pitch_date": "2024-04-01", "season": 2024, "umpire_id": "u", "called_strike": 0, "balls": 0, "strikes": 0, "zone": 1},
    ])
    scored = fit_expected_called_strike(pitches)
    row = scored[scored.season == 2024].iloc[0]
    assert row.fit_window_date < pd.Timestamp(row.pitch_date)
    assert row.expected_called_strike == 1.0


def test_missing_local_data_reports_unavailable_and_exits_successfully(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "scripts.platformkit.signals.officials_asof", "--games", str(tmp_path / "missing.csv")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "UNAVAILABLE missing_path=" in result.stdout
    assert str(tmp_path / "missing.csv") in result.stdout
