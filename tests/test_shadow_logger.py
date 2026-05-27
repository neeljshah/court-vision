"""tests/test_shadow_logger.py — unit tests for shadow_logger.py.

Run with:
    python -m pytest tests/test_shadow_logger.py -q
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest

from src.prediction.shadow_logger import log_evaluation, log_batch, _COLUMNS


# ── helpers ──────────────────────────────────────────────────────────────

def _base_rec(**overrides) -> dict:
    """Minimal valid evaluation record."""
    rec = {
        "ts": "2026-05-26T01:00:00",
        "game_id": "0022300001",
        "period": 2,
        "clock_remaining": 360.0,
        "player_id": "2544",
        "name": "LeBron James",
        "team": "LAL",
        "stat": "pts",
        "side": "over",
        "line": 25.5,
        "book": "fd",
        "odds": -115,
        "model_proj": 28.3,
        "current_stat": 12,
        "sigma": 5.0,
        "raw_ev": 0.06,
        "kelly": 0.04,
        "tier": "A",
        "gate_status": "passed",
        "gate_blocked_by": "",
        "source": "in_play_decision",
    }
    rec.update(overrides)
    return rec


def _read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _find_csv(base_dir: str, game_id: str) -> str:
    """Return the first CSV in base_dir whose name starts with game_id."""
    for fname in os.listdir(base_dir):
        if fname.startswith(game_id):
            return os.path.join(base_dir, fname)
    raise FileNotFoundError(f"No CSV for {game_id} in {base_dir}")


# ── tests ────────────────────────────────────────────────────────────────

class TestLogEvaluation:
    def test_single_row_written_with_all_columns(self, tmp_path):
        """log_evaluation writes exactly one row containing all 21 columns."""
        rec = _base_rec()
        log_evaluation(**rec, base_dir=str(tmp_path))

        path = _find_csv(str(tmp_path), rec["game_id"])
        rows = _read_csv(path)

        assert len(rows) == 1
        row = rows[0]
        # Every column must be present
        for col in _COLUMNS:
            assert col in row, f"Column '{col}' missing from written row"

    def test_header_written_only_on_first_write(self, tmp_path):
        """Header appears once even when log_evaluation is called twice."""
        rec = _base_rec()
        log_evaluation(**rec, base_dir=str(tmp_path))
        log_evaluation(**rec, base_dir=str(tmp_path))

        path = _find_csv(str(tmp_path), rec["game_id"])
        lines = Path(path).read_text(encoding="utf-8").splitlines()

        # First line is header, then one data line per call = 3 lines total
        assert lines[0].startswith("ts,"), "First line should be CSV header"
        assert len(lines) == 3, f"Expected 3 lines (header + 2 rows), got {len(lines)}"

    def test_none_values_become_empty_string(self, tmp_path):
        """None optional fields are serialised as empty string, not 'None'."""
        rec = _base_rec(period=None, clock_remaining=None, gate_blocked_by=None)
        log_evaluation(**rec, base_dir=str(tmp_path))

        path = _find_csv(str(tmp_path), rec["game_id"])
        rows = _read_csv(path)
        row = rows[0]

        assert row["period"] == "", f"Expected '', got {row['period']!r}"
        assert row["clock_remaining"] == ""
        assert row["gate_blocked_by"] == ""

    def test_nested_dir_creation(self, tmp_path):
        """log_evaluation creates data/shadow/ subdirectory if absent."""
        deep = str(tmp_path / "data" / "shadow")
        assert not os.path.exists(deep)

        log_evaluation(**_base_rec(), base_dir=deep)

        assert os.path.isdir(deep)
        assert any(f.endswith(".csv") for f in os.listdir(deep))


class TestLogBatch:
    def test_batch_appends_multiple_rows(self, tmp_path):
        """log_batch writes all records in one call."""
        recs = [_base_rec(name=f"Player {i}", player_id=str(i)) for i in range(5)]
        written = log_batch(recs, base_dir=str(tmp_path))

        assert written == 5
        path = _find_csv(str(tmp_path), recs[0]["game_id"])
        rows = _read_csv(path)
        assert len(rows) == 5

    def test_batch_isolates_separate_games(self, tmp_path):
        """Records from different games land in separate files."""
        recs = [
            _base_rec(game_id="GAME_A"),
            _base_rec(game_id="GAME_A"),
            _base_rec(game_id="GAME_B"),
        ]
        log_batch(recs, base_dir=str(tmp_path))

        files = os.listdir(str(tmp_path))
        game_a_files = [f for f in files if f.startswith("GAME_A")]
        game_b_files = [f for f in files if f.startswith("GAME_B")]
        assert len(game_a_files) == 1
        assert len(game_b_files) == 1

        rows_a = _read_csv(os.path.join(str(tmp_path), game_a_files[0]))
        rows_b = _read_csv(os.path.join(str(tmp_path), game_b_files[0]))
        assert len(rows_a) == 2
        assert len(rows_b) == 1

    def test_blocked_status_preserved(self, tmp_path):
        """gate_status and gate_blocked_by values round-trip correctly."""
        rec = _base_rec(
            gate_status="blocked",
            gate_blocked_by="projection_sane",
            raw_ev=None,
            kelly=None,
            tier="",
        )
        log_batch([rec], base_dir=str(tmp_path))

        path = _find_csv(str(tmp_path), rec["game_id"])
        rows = _read_csv(path)
        assert rows[0]["gate_status"] == "blocked"
        assert rows[0]["gate_blocked_by"] == "projection_sane"
