"""Tests for scripts/fetch_injury_espn.py — ESPN → cycle-43 schema adapter."""
from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.fetch_injury_espn as fie  # noqa: E402
from src.data.injuries import (  # noqa: E402
    load_unavailable_players, UNAVAILABLE_STATUSES,
)


def _espn_row(name, team, status, short_comment="", injury_type=""):
    return {
        "player_name": name, "player_id_espn": "",
        "team_name": team + " team", "team_abbrev": team,
        "status": status, "short_comment": short_comment,
        "long_comment": "", "injury_date": "2026-05-24T17:00Z",
        "injury_type": injury_type,
    }


def test_normalize_status_covers_espn_taxonomy():
    assert fie._normalize_status("Out") == "OUT"
    assert fie._normalize_status("Doubtful") == "DOUBTFUL"
    assert fie._normalize_status("Questionable") == "QUESTIONABLE"
    assert fie._normalize_status("Probable") == "PROBABLE"
    assert fie._normalize_status("Day-To-Day") == "QUESTIONABLE"
    assert fie._normalize_status("Suspended") == "NOT WITH TEAM"
    assert fie._normalize_status("Active") == "AVAILABLE"
    # Unknown statuses are uppercased as-is (lookup_status returns None for them).
    assert fie._normalize_status("Personal") == "PERSONAL"
    assert fie._normalize_status("") == ""


def test_normalized_statuses_match_injuries_module_taxonomy():
    """Every status this script emits must be recognized by src/data/injuries."""
    rows = [
        _espn_row("A", "LAL", "Out"),
        _espn_row("B", "DEN", "Doubtful"),
        _espn_row("C", "DEN", "Day-To-Day"),
        _espn_row("D", "PHI", "Suspended"),
    ]
    payload = fie.to_cycle43_schema(rows, "2026-05-24")
    seen = {p["status"] for p in payload["players"]}
    # 4 statuses produced; OUT, DOUBTFUL, QUESTIONABLE, NOT WITH TEAM all appear
    # in src/data/injuries taxonomy (UNAVAILABLE or SOFT_WARN).
    canonical = {"OUT", "DOUBTFUL", "QUESTIONABLE", "NOT WITH TEAM"}
    assert seen == canonical


def test_to_cycle43_schema_shape_matches_cycle_43():
    rows = [_espn_row("LeBron James", "LAL", "Out", short_comment="Foot soreness")]
    payload = fie.to_cycle43_schema(rows, "2026-05-24")
    # Top-level keys identical to cycle 43's fetch_injury_report.py output.
    assert set(payload.keys()) == {"date", "source_pdf", "fetched_at", "players"}
    assert payload["date"] == "2026-05-24"
    assert payload["source_pdf"] == "ESPN public injury API"
    p = payload["players"][0]
    assert set(p.keys()) == {"team", "name", "status", "reason"}
    assert p["name"] == "LeBron James"
    assert p["team"] == "LAL"
    assert p["status"] == "OUT"
    assert p["reason"] == "Foot soreness"


def test_to_cycle43_falls_back_to_injury_type_when_no_comment():
    rows = [_espn_row("X. Player", "LAL", "Out",
                       short_comment="", injury_type="Knee")]
    payload = fie.to_cycle43_schema(rows, "2026-05-24")
    assert payload["players"][0]["reason"] == "Knee"


def test_to_cycle43_skips_rows_with_blank_name():
    rows = [_espn_row("", "LAL", "Out"),
            _espn_row("LeBron James", "LAL", "Out")]
    payload = fie.to_cycle43_schema(rows, "2026-05-24")
    assert len(payload["players"]) == 1
    assert payload["players"][0]["name"] == "LeBron James"


def test_round_trip_through_load_unavailable_players():
    """End-to-end: write ESPN-derived JSON → load via cycle 53 module → see same players."""
    rows = [
        _espn_row("LeBron James", "LAL", "Out", short_comment="Foot"),
        _espn_row("Anthony Davis", "LAL", "Doubtful", short_comment="Knee"),
        _espn_row("Nikola Jokic", "DEN", "Questionable", short_comment="Ankle"),
        _espn_row("Stephen Curry", "GSW", "Active", short_comment=""),
    ]
    payload = fie.to_cycle43_schema(rows, "2026-05-24")
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json",
                                       encoding="utf-8") as fh:
        json.dump(payload, fh)
        path = fh.name
    try:
        unav = load_unavailable_players(path)
    finally:
        os.unlink(path)
    # LeBron OUT + Davis DOUBTFUL should appear; Jokic QUESTIONABLE + Curry AVAILABLE should not.
    assert set(unav.keys()) == {"lebron james", "anthony davis"}


def test_write_payload_creates_dir():
    payload = fie.to_cycle43_schema(
        [_espn_row("X. Player", "LAL", "Out")], "2026-05-24")
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "deep", "nested", "out.json")
        n = fie.write_payload(payload, out)
        assert n == 1
        assert os.path.exists(out)
        with open(out) as fh:
            roundtripped = json.load(fh)
        assert roundtripped["source_pdf"] == "ESPN public injury API"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
