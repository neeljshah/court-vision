"""Tests for compare_to_lines.py injury-aware skip path (cycle 51).

The actual EV/Kelly path is exercised by tests/test_compare_to_lines.py
(cycle 42). These tests target only the new helper functions added in
cycle 51 — load_injury_unavailable() and its interaction with the
diacritic-stripped name key.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.compare_to_lines as ctl  # noqa: E402


def _inj_json(players):
    return {"date": "2026-05-24", "source_pdf": "x.pdf",
            "fetched_at": "2026-05-24T17:00:00", "players": players}


def test_unavailable_includes_out_and_doubtful_only():
    payload = _inj_json([
        {"team": "LAL", "name": "LeBron James", "status": "OUT", "reason": "rest"},
        {"team": "LAL", "name": "Anthony Davis", "status": "DOUBTFUL", "reason": "knee"},
        {"team": "DEN", "name": "Nikola Jokic", "status": "QUESTIONABLE", "reason": "ankle"},
        {"team": "DEN", "name": "Aaron Gordon", "status": "PROBABLE", "reason": "back"},
        {"team": "BOS", "name": "Jrue Holiday", "status": "AVAILABLE", "reason": ""},
    ])
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as fh:
        json.dump(payload, fh)
        path = fh.name
    try:
        m = ctl.load_injury_unavailable(path)
    finally:
        os.unlink(path)
    # Only OUT and DOUBTFUL count as unavailable.
    assert set(m.keys()) == {"lebron james", "anthony davis"}
    assert m["lebron james"] == "OUT"
    assert m["anthony davis"] == "DOUBTFUL"


def test_unavailable_normalizes_diacritics_and_case():
    payload = _inj_json([
        {"team": "DEN", "name": "Nikola Jokić", "status": "OUT", "reason": ""},
    ])
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as fh:
        json.dump(payload, fh)
        path = fh.name
    try:
        m = ctl.load_injury_unavailable(path)
    finally:
        os.unlink(path)
    # Key is diacritic-stripped lowercase so 'Jokic' (no accent) lookups match.
    assert "nikola jokic" in m


def test_unavailable_returns_empty_on_missing_file():
    m = ctl.load_injury_unavailable("/tmp/definitely_does_not_exist_xyz.json")
    assert m == {}


def test_unavailable_returns_empty_on_malformed_json():
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as fh:
        fh.write("{not-json")
        path = fh.name
    try:
        m = ctl.load_injury_unavailable(path)
    finally:
        os.unlink(path)
    assert m == {}


def test_unavailable_returns_empty_on_path_none():
    assert ctl.load_injury_unavailable("") == {}
    assert ctl.load_injury_unavailable(None) == {}


def test_not_with_team_status_also_skipped():
    payload = _inj_json([
        {"team": "PHI", "name": "Ben Simmons", "status": "NOT WITH TEAM", "reason": "personal"},
    ])
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as fh:
        json.dump(payload, fh)
        path = fh.name
    try:
        m = ctl.load_injury_unavailable(path)
    finally:
        os.unlink(path)
    assert "ben simmons" in m
    assert m["ben simmons"] == "NOT WITH TEAM"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
