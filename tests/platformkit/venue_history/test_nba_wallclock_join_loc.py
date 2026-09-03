"""LOC rail for the NBA wall-clock join module."""
from pathlib import Path


def test_nba_wallclock_join_stays_within_300_lines() -> None:
    module = Path(__file__).resolve().parents[3] / "scripts/platformkit/venue_history/nba_wallclock_join.py"
    assert len(module.read_text(encoding="utf-8").splitlines()) <= 300
