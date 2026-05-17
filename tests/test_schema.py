"""
test_schema.py — Validate database/schema.sql structure (no live DB required).
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "database" / "schema.sql"

EXPECTED_TABLES = {
    "teams", "players", "games", "tracking_frames",
    "possessions", "shots", "lineups", "odds", "predictions",
}
EXPECTED_INDEXES = {
    "idx_players_team", "idx_games_date",
    "idx_frames_game", "idx_possessions_game",
}


def _load_schema() -> str:
    if not SCHEMA_PATH.exists():
        pytest.skip(f"schema.sql not found at {SCHEMA_PATH}")
    return SCHEMA_PATH.read_text(encoding="utf-8")

def _extract_tables(sql: str) -> set:
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql, re.IGNORECASE))

def _extract_indexes(sql: str) -> set:
    return set(re.findall(r"CREATE INDEX IF NOT EXISTS (\w+)", sql, re.IGNORECASE))

def _extract_references(sql: str) -> list:
    return re.findall(r"REFERENCES (\w+)\((\w+)\)", sql)

def _table_block(sql: str, table_name: str) -> str:
    pattern = rf"CREATE TABLE IF NOT EXISTS {table_name}\s*\((.*?)\);"
    m = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
    return m.group(1) if m else ""


def test_all_expected_tables_present() -> None:
    """schema.sql must define all expected core tables."""
    missing = EXPECTED_TABLES - _extract_tables(_load_schema())
    assert not missing, f"Missing tables: {sorted(missing)}"

def test_no_duplicate_table_definitions() -> None:
    sql = _load_schema()
    tables = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql, re.IGNORECASE)
    dupes = {t for t in tables if tables.count(t) > 1}
    assert not dupes, f"Duplicate tables: {sorted(dupes)}"

def test_expected_indexes_present() -> None:
    missing = EXPECTED_INDEXES - _extract_indexes(_load_schema())
    assert not missing, f"Missing indexes: {sorted(missing)}"

def test_foreign_keys_reference_known_tables() -> None:
    sql = _load_schema()
    defined = _extract_tables(sql)
    bad = [(t, c) for t, c in _extract_references(sql) if t not in defined]
    assert not bad, f"FKs referencing undefined tables: {bad}"

def test_players_has_team_fk() -> None:
    assert ("teams", "team_id") in _extract_references(_load_schema())

def test_games_has_two_or_more_team_fks() -> None:
    refs = _extract_references(_load_schema())
    team_refs = [r for r in refs if r == ("teams", "team_id")]
    assert len(team_refs) >= 2

def test_tracking_frames_has_game_fk() -> None:
    assert ("games", "game_id") in _extract_references(_load_schema())

def test_games_table_has_required_columns() -> None:
    block = _table_block(_load_schema(), "games")
    for col in ["game_date", "home_team_id", "away_team_id", "season", "model_home_win_prob"]:
        assert col in block, f"games missing column {col!r}"

def test_players_table_has_required_columns() -> None:
    block = _table_block(_load_schema(), "players")
    for col in ("player_id", "first_name", "last_name", "team_id"):
        assert col in block, f"players missing column {col!r}"

def test_teams_table_has_abbreviation() -> None:
    assert "abbreviation" in _table_block(_load_schema(), "teams")

def test_schema_uses_if_not_exists() -> None:
    """No bare CREATE TABLE/INDEX without IF NOT EXISTS (schema must be idempotent)."""
    sql = _load_schema()
    # Match CREATE TABLE <name> but NOT CREATE TABLE IF NOT EXISTS
    bare = re.findall(r"CREATE TABLE\s+(?!IF\b)(\w+)", sql, re.IGNORECASE)
    assert not bare, f"CREATE TABLE without IF NOT EXISTS: {bare}"

def test_schema_has_no_drop_statements() -> None:
    assert not re.search(r"\bDROP\s+TABLE\b", _load_schema(), re.IGNORECASE)

def test_schema_file_is_valid_utf8() -> None:
    SCHEMA_PATH.read_bytes().decode("utf-8")
