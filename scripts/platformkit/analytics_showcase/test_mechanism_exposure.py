"""Fixture-only tests for the pregame mechanism exposure join."""
from pathlib import Path

import pandas as pd

from scripts.platformkit.analytics_showcase.mechanism_exposure import (
    game_sheets, parse_mechanisms, sport_rollup,
)


FIXTURE = """### 14. Back-to-back (B2B) rest penalty
- **status**: CONFIRMED
- **measured LOCAL magnitude**: effect -1.0, n=10, p=0.01.

### Three-in-four fatigue
- **status**: REPLICATED
- **measured LOCAL magnitude**: effect -2.0, n=12, p=0.02.

### Unmatched confirmed mechanism
- **status**: CONFIRMED
- **measured LOCAL magnitude**: effect 1.0, n=8, p=0.03.

### Rejected mechanism
- **status**: REJECTED
- **measured LOCAL magnitude**: effect 9.0, n=99, p=0.90.

### Untested mechanism
- **status**: UNTESTED
"""


def _mechanisms(tmp_path: Path) -> list[dict]:
    path = tmp_path / "mechanisms.md"
    path.write_text(FIXTURE, encoding="ascii")
    return parse_mechanisms(path)


def _schedule() -> pd.DataFrame:
    rows = [
        ("2025-01-01", "BBB", "AAA"),  # intentionally empty; later rows cannot affect it
        ("2025-01-02", "CCC", "AAA"),  # AAA b2b
        ("2025-01-03", "DDD", "AAA"),  # AAA three-in-four
        ("2025-01-10", "EEE", "FFF"),  # rested game
        ("2025-01-15", "GGG", "HHH"),
        ("2025-01-16", "III", "GGG"),
    ]
    schedule = pd.DataFrame(rows, columns=["date", "home_team", "away_team"])
    schedule["date"] = pd.to_datetime(schedule["date"])
    schedule["game_id"] = [f"g{i}" for i in range(len(schedule))]
    return schedule


def test_parser_keeps_confirmed_and_drops_rejected_and_untested(tmp_path: Path) -> None:
    rows = _mechanisms(tmp_path)
    assert [row["mechanism"] for row in rows] == [
        "14. Back-to-back (B2B) rest penalty", "Three-in-four fatigue", "Unmatched confirmed mechanism"]
    assert rows[0]["ledger_quote"] == ["- **measured LOCAL magnitude**: effect -1.0, n=10, p=0.01."]


def test_b2b_fires_and_rested_game_is_empty(tmp_path: Path) -> None:
    sheets = game_sheets(_schedule(), _mechanisms(tmp_path))
    assert sheets[1]["exposures"][0]["trigger_evidence"]["name"] == "is_b2b"
    assert sheets[3]["exposures"] == []


def test_unmatched_confirmed_mechanism_is_not_wired(tmp_path: Path) -> None:
    rollup = sport_rollup(_mechanisms(tmp_path))
    assert "Unmatched confirmed mechanism" in rollup["not_wired"]


def test_future_schedule_row_never_affects_earlier_game(tmp_path: Path) -> None:
    sheets = game_sheets(_schedule(), _mechanisms(tmp_path))
    assert sheets[0]["exposures"] == []
