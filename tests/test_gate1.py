"""tests/test_gate1.py — Gate 1 CLV validation script tests.

Uses a temporary SQLite DB and a temp residuals JSON for full isolation.
All 4 required scenarios are covered:
  1. Empty DB (no prop_lines table) → exit 1, "INSUFFICIENT DATA"
  2. 60 rows, 40 wins → beat_rate 66.7%, reported correctly
  3. 30 rows → INSUFFICIENT DATA (< 50 bets)
  4. 60 rows, 30 wins (50%) → FAIL reported
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


# ── fixture helpers ───────────────────────────────────────────────────────────

def _make_schema(conn: sqlite3.Connection) -> None:
    """Create minimal prop_lines + prop_outcomes tables."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS prop_lines (
            id          TEXT PRIMARY KEY,
            sport       TEXT NOT NULL,
            game_id     TEXT NOT NULL,
            player_id   TEXT NOT NULL,
            bookmaker   TEXT NOT NULL,
            market      TEXT NOT NULL,
            line        REAL NOT NULL,
            over_odds   REAL,
            under_odds  REAL,
            is_opening  INTEGER DEFAULT 0,
            is_closing  INTEGER DEFAULT 0,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS prop_outcomes (
            sport        TEXT NOT NULL,
            game_id      TEXT NOT NULL,
            player_id    TEXT NOT NULL,
            market       TEXT NOT NULL,
            actual_value REAL NOT NULL,
            closing_line REAL,
            result       TEXT,
            clv          REAL,
            settled_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (sport, game_id, player_id, market)
        );
    """)


def _insert_rows(
    conn: sqlite3.Connection,
    n_win: int,
    n_lose: int,
) -> None:
    """Insert n_win over-wins and n_lose over-losses into both tables.

    Synthetic setup:
      - player_id = 'P1', game_id = '2024-01-15_BOS_LAL'
      - market = 'player_points', close_line = 25.0
      - predicted = 26.5 → bet_over = True
      - Win row: actual_value = 26.0, result = 'over'
      - Lose row: actual_value = 24.0, result = 'under'
    """
    for i in range(n_win + n_lose):
        row_id = f"row_{i}"
        # Vary game_id so PK is unique in prop_outcomes (player+game+market)
        game_id = f"2024-01-{15 + i:02d}_BOS_LAL"
        conn.execute(
            """INSERT INTO prop_lines
               (id, sport, game_id, player_id, bookmaker, market,
                line, over_odds, under_odds, is_closing)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row_id, "basketball_nba", game_id, "P1",
             "pinnacle", "player_points",
             25.0, -110.0, -110.0, 1),
        )
        if i < n_win:
            actual = 26.0
            result = "over"
        else:
            actual = 24.0
            result = "under"
        conn.execute(
            """INSERT INTO prop_outcomes
               (sport, game_id, player_id, market, actual_value, result)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("basketball_nba", game_id, "P1",
             "player_points", actual, result),
        )
    conn.commit()


def _make_residuals(tmp_path: Path, n_win: int, n_lose: int) -> Path:
    """Write a residuals JSON matching the rows inserted by _insert_rows."""
    records = []
    for i in range(n_win + n_lose):
        records.append({
            "player_id": "P1",
            "player_name": "test player",
            "game_date": f"2024-01-{15 + i:02d}",  # ISO format
            "season": "2024-25",
            "stat": "pts",
            "predicted": 26.5,   # > 25.0 line → bet over
            "actual": 26.0 if i < n_win else 24.0,
            "line": 25.0,
            "edge_pct": 0.06,
            "direction": "over",
        })
    path = tmp_path / "residuals.json"
    path.write_text(json.dumps(records))
    return path


def _run(db_path: Path, residuals_path: Path, min_bets: int = 50) -> tuple[int, str]:
    """Run run_gate1.py as a subprocess and return (exit_code, stdout)."""
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent.parent / "scripts" / "run_gate1.py"),
            "--db", str(db_path),
            "--residuals", str(residuals_path),
            "--min-bets", str(min_bets),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


# ── tests ─────────────────────────────────────────────────────────────────────

class TestGate1EmptyDB:
    """Test 1: Empty DB (no prop_lines table) → exit 1, INSUFFICIENT DATA."""

    def test_exit_code_is_1(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.db"
        # Create a real SQLite file but with no tables
        conn = sqlite3.connect(str(db_path))
        conn.close()
        residuals_path = tmp_path / "res.json"
        residuals_path.write_text("[]")

        code, _ = _run(db_path, residuals_path)
        assert code == 1

    def test_output_contains_insufficient_data(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.db"
        conn = sqlite3.connect(str(db_path))
        conn.close()
        residuals_path = tmp_path / "res.json"
        residuals_path.write_text("[]")

        _, output = _run(db_path, residuals_path)
        assert "INSUFFICIENT DATA" in output


class TestGate160WinsPass:
    """Test 2: 60 rows, 40 wins → beat_rate 66.7%, reported correctly."""

    def test_beat_rate_reported_correctly(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _make_schema(conn)
        _insert_rows(conn, n_win=40, n_lose=20)
        conn.close()
        residuals_path = _make_residuals(tmp_path, n_win=40, n_lose=20)

        _, output = _run(db_path, residuals_path)
        # 40/60 = 66.666...% → should appear as 66.67%
        assert "66.67%" in output

    def test_n_bets_is_60(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _make_schema(conn)
        _insert_rows(conn, n_win=40, n_lose=20)
        conn.close()
        residuals_path = _make_residuals(tmp_path, n_win=40, n_lose=20)

        _, output = _run(db_path, residuals_path)
        assert "n_bets:     60" in output


class TestGate130RowsInsufficient:
    """Test 3: 30 rows → INSUFFICIENT DATA (< 50 bets)."""

    def test_exit_code_is_1(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _make_schema(conn)
        _insert_rows(conn, n_win=20, n_lose=10)
        conn.close()
        residuals_path = _make_residuals(tmp_path, n_win=20, n_lose=10)

        code, _ = _run(db_path, residuals_path)
        assert code == 1

    def test_output_contains_insufficient_data(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _make_schema(conn)
        _insert_rows(conn, n_win=20, n_lose=10)
        conn.close()
        residuals_path = _make_residuals(tmp_path, n_win=20, n_lose=10)

        _, output = _run(db_path, residuals_path)
        assert "INSUFFICIENT DATA" in output


class TestGate160Wins50PctFail:
    """Test 4: 60 rows, 30 wins (50%) → FAIL reported."""

    def test_exit_code_is_1(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _make_schema(conn)
        _insert_rows(conn, n_win=30, n_lose=30)
        conn.close()
        residuals_path = _make_residuals(tmp_path, n_win=30, n_lose=30)

        code, _ = _run(db_path, residuals_path)
        assert code == 1

    def test_output_contains_fail(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _make_schema(conn)
        _insert_rows(conn, n_win=30, n_lose=30)
        conn.close()
        residuals_path = _make_residuals(tmp_path, n_win=30, n_lose=30)

        _, output = _run(db_path, residuals_path)
        assert "FAIL" in output

    def test_beat_rate_reported_as_50(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        _make_schema(conn)
        _insert_rows(conn, n_win=30, n_lose=30)
        conn.close()
        residuals_path = _make_residuals(tmp_path, n_win=30, n_lose=30)

        _, output = _run(db_path, residuals_path)
        assert "50.00%" in output
