"""Tests for src/data/injuries.py — shared injury loader (cycle 53)."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.data.injuries import (  # noqa: E402
    UNAVAILABLE_STATUSES, SOFT_WARN_STATUSES,
    _name_key, _strip_accents, default_path,
    load_injuries, load_unavailable_players, load_soft_warn_players,
    lookup_status,
)


def _payload(players):
    return {"date": "2026-05-24", "source_pdf": "x.pdf",
            "fetched_at": "2026-05-24T17:00:00", "players": players}


def _write_tmp(payload):
    fh = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8")
    json.dump(payload, fh); fh.close()
    return fh.name


def test_name_key_strips_diacritics_and_case():
    assert _name_key("Nikola Jokić") == "nikola jokic"
    assert _name_key("Luka Dončić") == "luka doncic"
    assert _name_key("  LEBRON JAMES  ") == "lebron james"
    assert _name_key("") == ""


def test_status_taxonomy_partition():
    # Sanity: the two sets are disjoint and OUT-like are bigger.
    assert UNAVAILABLE_STATUSES & SOFT_WARN_STATUSES == set()
    assert "OUT" in UNAVAILABLE_STATUSES
    assert "DOUBTFUL" in UNAVAILABLE_STATUSES
    assert "NOT WITH TEAM" in UNAVAILABLE_STATUSES
    assert "QUESTIONABLE" in SOFT_WARN_STATUSES
    # AVAILABLE/PROBABLE are neither (no skip, no warn).
    assert "AVAILABLE" not in UNAVAILABLE_STATUSES | SOFT_WARN_STATUSES
    assert "PROBABLE" not in UNAVAILABLE_STATUSES | SOFT_WARN_STATUSES


def test_load_unavailable_partitions_correctly():
    payload = _payload([
        {"team": "LAL", "name": "LeBron James", "status": "OUT", "reason": "x"},
        {"team": "LAL", "name": "Anthony Davis", "status": "DOUBTFUL", "reason": "y"},
        {"team": "DEN", "name": "Nikola Jokić", "status": "QUESTIONABLE", "reason": "z"},
        {"team": "DEN", "name": "Aaron Gordon", "status": "PROBABLE", "reason": ""},
        {"team": "PHI", "name": "Ben Simmons", "status": "NOT WITH TEAM", "reason": ""},
        {"team": "BOS", "name": "Jrue Holiday", "status": "AVAILABLE", "reason": ""},
    ])
    path = _write_tmp(payload)
    try:
        unav = load_unavailable_players(path)
        soft = load_soft_warn_players(path)
    finally:
        os.unlink(path)
    assert set(unav.keys()) == {"lebron james", "anthony davis", "ben simmons"}
    assert unav["ben simmons"] == "NOT WITH TEAM"
    assert set(soft.keys()) == {"nikola jokic"}
    assert soft["nikola jokic"] == "QUESTIONABLE"


def test_load_returns_empty_on_missing_or_malformed():
    assert load_injuries(None) == {}
    assert load_injuries("") == {}
    assert load_injuries("/tmp/never_exists_xyz.json") == {}
    assert load_unavailable_players(None) == {}
    # Malformed JSON
    fh = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8")
    fh.write("{not-json"); fh.close()
    try:
        assert load_injuries(fh.name) == {}
        assert load_unavailable_players(fh.name) == {}
    finally:
        os.unlink(fh.name)


def test_lookup_status_returns_unavailable_first_then_soft():
    unav = {"lebron james": "OUT"}
    soft = {"nikola jokic": "QUESTIONABLE"}
    assert lookup_status("LeBron James", unav, soft) == "OUT"
    # Diacritic stripping flows through
    assert lookup_status("Nikola Jokić", unav, soft) == "QUESTIONABLE"
    assert lookup_status("Stephen Curry", unav, soft) is None
    # soft_warn optional
    assert lookup_status("LeBron James", unav) == "OUT"
    assert lookup_status("Nikola Jokic", unav) is None


def test_default_path_is_under_project_data_dir():
    from datetime import date
    p = default_path(date(2026, 5, 24))
    assert p.endswith(os.path.join("data", "injuries_2026-05-24.json"))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
